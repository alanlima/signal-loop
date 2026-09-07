from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.db import connections, models, transaction
import pytest

from signal_loop.reporting.models import AudienceRelease, ManagerReport
from signal_loop.reporting.selectors import manager_report_for
from signal_loop.reporting.services import compose_manager, lock_project_week, publish_locked, withdraw_release
from .test_composition import CLOSE, fixture


@pytest.fixture
def clear_reports(postgres_database):
    yield
    models.QuerySet(model=ManagerReport).delete()
    models.QuerySet(model=AudienceRelease).delete()


pytestmark = pytest.mark.usefixtures("clear_reports")


def compose(values=None, **kwargs):
    recommendations, context = values or fixture()
    return compose_manager(recommendations, project="cedar", week="2026-09-07", version=kwargs.pop("version", "analysis-v1"),
                           closes_at=CLOSE, at=kwargs.pop("at", CLOSE), context_provider=context, **kwargs)


def display(*, at=CLOSE + timedelta(minutes=1), allowed=True):
    with patch("signal_loop.reporting.selectors.has_permission", return_value=allowed):
        return manager_report_for(AnonymousUser(), project=SimpleNamespace(pk="cedar", organisation_id=1),
                                  week="2026-09-07", at=at, closes_at=CLOSE)


def test_exact_candidate_and_separate_safe_storage_serialization():
    assert compose().state == "ready"
    candidate = ManagerReport.objects.get()
    release = AudienceRelease.objects.get()
    assert candidate.artifact["schema"] == "manager-report/1.0"
    assert candidate.artifact["data"]["issues"] == ["issue_1"]
    assert candidate.artifact["provenance"]["producer_version"] == "analysis-v1"
    assert candidate.expires_at == CLOSE + timedelta(days=7)  # Earliest previous-week source.
    assert release.expires_at == CLOSE + timedelta(days=358)
    assert set(display()) == {"schema", "project", "week", "audience", "status", "content"}
    assert display()["content"] == release.content
    serialized = json.dumps(display())
    stored_safe = json.dumps(release.content)
    for forbidden in ("new_s0", "issue_1", "input_refs", "provenance", "distinct", "support", "score", "credential", "analysis-v1"):
        assert forbidden not in serialized + stored_safe
    assert not any(field.name in {"user", "contributor", "credential", "source", "analysis_version"}
                   for field in AudienceRelease._meta.fields)


@pytest.mark.parametrize("case", ["missing", "empty", "unsafe", "invalid"])
def test_non_ready_storage_has_no_partial_artifact_or_public_content(case):
    recommendations, context = fixture()
    if case == "missing":
        recommendations = None
    elif case == "empty":
        recommendations._artifact["data"]["items"] = []
    elif case == "unsafe":
        recommendations._artifact["data"]["items"][0]["rationale"] = "Alex is the only operator."
    else:
        recommendations._artifact["schema"] = "invalid/9"
    assert compose((recommendations, context)).state in {"suppressed", "failed"}
    assert ManagerReport.objects.get().artifact is None
    assert not AudienceRelease.objects.exists()
    assert display() == {"schema": "audience-release/1.0", "project": "cedar", "week": "2026-09-07",
                         "audience": "manager", "status": "unavailable"}


def test_duplicate_and_new_version_never_refresh_original_release_or_expiry():
    compose()
    before = AudienceRelease.objects.values().get()
    assert compose(at=CLOSE + timedelta(days=1)).state == "ready"
    assert compose(version="analysis-v2", at=CLOSE + timedelta(days=2)).state == "ready"
    assert AudienceRelease.objects.values().get() == before
    assert ManagerReport.objects.count() == 1


def test_failed_same_key_reuses_result_and_new_candidate_cannot_change_a_release():
    assert compose((None, fixture()[1])).state == "suppressed"
    assert compose().state == "suppressed"
    assert ManagerReport.objects.count() == 1
    assert compose(version="analysis-v2").state == "ready"
    assert ManagerReport.objects.count() == 2 and AudienceRelease.objects.count() == 1


def test_withdrawal_is_content_removal_without_replacement():
    compose()
    release = AudienceRelease.objects.get()
    assert withdraw_release(project="cedar", week="2026-09-07", audience="manager") == 1
    assert withdraw_release(project="cedar", week="2026-09-07", audience="manager") == 0
    assert compose(version="replacement").state == "suppressed"
    after = AudienceRelease.objects.get()
    assert after.pk == release.pk and after.expires_at == release.expires_at and after.content is None
    assert display()["status"] == "unavailable"


def test_expiry_and_public_schedule_do_not_reveal_participation_or_failure():
    compose()
    release = AudienceRelease.objects.get()
    assert display(at=release.expires_at)["status"] == "unavailable"
    assert display(at=CLOSE - timedelta(seconds=1))["status"] == "not_yet_available"
    assert display(allowed=False)["status"] == "unavailable"
    assert display(at=CLOSE + timedelta(days=15))["status"] == "available"  # Approved safe output survives raw expiry.
    assert compose(version="late", at=release.expires_at).state == "suppressed"


def test_unauthorized_reader_does_not_query_safe_or_restricted_report_storage():
    with patch.object(AudienceRelease.objects, "filter") as query:
        result = manager_report_for(AnonymousUser(), project=SimpleNamespace(pk=1, organisation_id=1),
                                    week="2026-09-07", at=CLOSE, closes_at=CLOSE)
    query.assert_not_called()
    assert result["status"] == "unavailable"


def test_supported_orm_paths_cannot_modify_immutable_release_or_candidate():
    compose()
    for obj in (AudienceRelease.objects.get(), ManagerReport.objects.get()):
        with pytest.raises(TypeError):
            obj.save()
        with pytest.raises(TypeError):
            obj.save(_validated=True)
        with pytest.raises(TypeError):
            obj.delete()
        with pytest.raises(TypeError):
            type(obj).objects.filter(pk=obj.pk).update(state="failed")
        with pytest.raises(TypeError):
            type(obj).objects.bulk_update([obj], ["state"])


@pytest.mark.parametrize("different_version", [False, True])
def test_real_postgres_concurrent_composition_linearizes_first_release(different_version):
    values = fixture()
    barrier = Barrier(2)

    def work(index):
        try:
            barrier.wait(timeout=10)
            return compose(values, version=f"analysis-v{index if different_version else 1}").state
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(work, index) for index in range(2)]
        assert [future.result(timeout=20) for future in futures] == ["ready", "ready"]
    assert AudienceRelease.objects.count() == 1 and ManagerReport.objects.count() == 1


def test_persistence_failure_rolls_back_candidate_and_release_together():
    with patch("signal_loop.reporting.services.publish_locked", side_effect=RuntimeError("synthetic persistence failure")):
        with pytest.raises(RuntimeError):
            compose()
    assert not ManagerReport.objects.exists() and not AudienceRelease.objects.exists()
    assert display()["status"] == "unavailable"
    assert compose().state == "ready"


def test_elapsed_source_expiry_or_final_context_change_withholds_before_storage():
    with patch("signal_loop.reporting.services.monotonic", side_effect=[0, 8 * 86400]):
        assert compose().state == "suppressed"
    assert ManagerReport.objects.get().artifact is None and not AudienceRelease.objects.exists()


def test_latest_context_failure_is_safe_and_does_not_store_partial_candidate():
    recommendations, context = fixture()
    original = context.load
    calls = 0

    def fail(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("secret context diagnostic")
        return original(**kwargs)

    context.load = fail
    assert compose((recommendations, context)).state == "suppressed"
    assert ManagerReport.objects.get().artifact is None
    assert not AudienceRelease.objects.exists()


def test_final_context_reload_time_cannot_extend_original_source_deadline():
    values = fixture()
    context = values[1]
    original = context.load
    elapsed = 0
    calls = 0

    def delayed(**kwargs):
        nonlocal elapsed, calls
        calls += 1
        if calls == 3:
            elapsed = 8 * 86400
        return original(**kwargs)

    context.load = delayed
    with patch("signal_loop.reporting.services.monotonic", side_effect=lambda: elapsed):
        assert compose(values).state == "suppressed"
    assert calls == 3 and not AudienceRelease.objects.exists()


@pytest.mark.parametrize("case", ["same", "different", "withdrawn", "expired"])
def test_existing_team_release_must_match_exact_reviewed_joint_candidate(case):
    values = fixture()
    content = values[1].context.team_content.copy()
    if case == "different":
        content["next_week_focus"] = []
    with transaction.atomic():
        lock_project_week("cedar", "2026-09-07")
        publish_locked(project="cedar", week="2026-09-07", audience="team", content=content,
                       at=CLOSE - timedelta(days=1) if case == "expired" else CLOSE,
                       expires_at=CLOSE if case == "expired" else CLOSE + timedelta(days=30))
    if case == "withdrawn":
        withdraw_release(project="cedar", week="2026-09-07", audience="team")
    result = compose(values)
    assert result.state == ("ready" if case == "same" else "suppressed")
    assert AudienceRelease.objects.filter(audience="manager").exists() == (case == "same")
    if case == "same":
        assert AudienceRelease.objects.get(audience="manager").expires_at == CLOSE + timedelta(days=30)
