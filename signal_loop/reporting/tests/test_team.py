from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.db import connections, models
import pytest

from signal_loop.analysis.evidence import ContextScope, JointContext
from signal_loop.analysis.themes import RestrictedThemes
from signal_loop.analysis.tests.test_aggregation import CLOSE, artifacts, run as aggregate
from signal_loop.reporting.models import AudienceRelease, ManagerReport, TeamSummary
from signal_loop.reporting.selectors import team_summary_for
from signal_loop.reporting.services import compose_manager, withdraw_release
from signal_loop.reporting.team import (
    PublishedCommitment, TEAM_WORDS, TeamInput, TeamPublicationContext, compose_team, prepare_team,
)
from .test_composition import fixture as manager_fixture
from signal_loop.analysis.severity import SeverityHistory
from signal_loop.analysis.tests.test_trends import snapshot, SyntheticHistoryReviewer


class Context:
    def __init__(self, value):
        self.value = value

    def load(self, **kwargs):
        return deepcopy(self.value)


def fixture():
    rows = artifacts()
    for row in rows:
        row["data"].update(delivery="blocked", workload="overloaded", note="The team completed the shared milestone.",
                           follow_up={"question": "F1", "answer": "We need help with the shared backlog."})
    eligible = aggregate(rows)
    themes = deepcopy(rows[0])
    themes["schema"] = "themes/1.0"
    keys = [("Workload is overloaded.", "workload"), ("Delivery is blocked.", "delivery"),
            ("The team completed the shared milestone.", "wins"), ("We need help with the shared backlog.", "support")]
    themes["data"] = {"items": [{"id": f"theme_{i}", "statement": statement, "category": category,
        "support": [row["data"]["source"] for row in rows], "distinct_support": 5} for i, (statement, category) in enumerate(keys)]}
    scope = ContextScope("cedar", "2026-09-07", tuple(text for row in rows for text in
                         (row["data"]["note"], row["data"]["follow_up"]["answer"])), 5)
    context = Context(TeamPublicationContext(JointContext("cedar", "2026-09-07",
                      frozenset({("cedar", "2026-09-07")}), (scope,), {}), None, None))
    return TeamInput(eligible, RestrictedThemes(themes)), context


def prepare(values=None, **kwargs):
    inputs, context = values or fixture()
    return prepare_team(inputs, project="cedar", week="2026-09-07", version="analysis-v1", closes_at=CLOSE,
                        at=kwargs.pop("at", CLOSE), context_provider=context, **kwargs)


def test_complete_independent_team_without_manager_or_scored_issues():
    result = prepare()
    assert result.state == "ready"
    assert result.artifact["schema"] == "team-summary/1.0"
    assert len(result.artifact["data"]["themes"]) == 4
    assert set(result.content["themes"]) == {TEAM_WORDS[key] for key in [
        ("Workload is overloaded.", "workload"), ("Delivery is blocked.", "delivery"),
        ("The team completed the shared milestone.", "wins"), ("We need help with the shared backlog.", "support")]}
    assert result.content["trends"] == result.content["next_week_focus"] == result.content["commitments"] == []
    assert result.manager_content is None


@pytest.mark.parametrize("case", ["four", "scope", "schema", "grounding", "empty", "missing_context", "unknown", "expired", "source"])
def test_unsafe_or_unavailable_has_no_partial_candidate(case):
    inputs, context = fixture()
    if case == "four":
        inputs.themes._artifact["data"]["items"][0]["support"].pop()
    elif case == "scope":
        inputs.themes._artifact["project"] = "birch"
    elif case == "schema":
        inputs.themes._artifact["schema"] = "themes/2.0"
    elif case == "grounding":
        inputs.eligible._artifacts[0]["data"]["workload"] = "manageable"
    elif case == "empty":
        inputs.themes._artifact["data"]["items"] = []
    elif case == "missing_context":
        context = None
    elif case == "unknown":
        context.value = replace(context.value, joint_context=replace(context.value.joint_context, scopes=()))
    elif case == "source":
        inputs.eligible._artifacts[0]["data"]["note"] = "PRIVATE_EMPLOYEE_SENTINEL"
    result = prepare((inputs, context), at=CLOSE + timedelta(days=14) if case == "expired" else CLOSE)
    assert result.state != "ready" and result.artifact is None and result.content is None


def recommendation_fixture():
    recs, manager_context = manager_fixture()
    source = recs.source_context_for_analysis().issues.source_context_for_analysis()
    context = Context(TeamPublicationContext(manager_context.context.joint_context, None, None))
    return TeamInput(source.eligible, source.themes, recs), context


def test_normative_focus_and_private_manager_sentinels_never_copied():
    inputs, context = recommendation_fixture()
    recs = inputs.recommendations
    private = deepcopy(recs._artifact["data"]["items"][0])
    private.update(id="private_rec", suggest_for_team=False, action="PRIVATE_ACTION_SENTINEL", rationale="PRIVATE_RISK_SENTINEL")
    recs._artifact["data"]["items"].append(private)
    recs._source_context.issues._artifact["data"]["items"][0]["explanation"] = "MANAGER_SCORE_SENTINEL"
    result = prepare((inputs, context))
    assert result.state == "ready"
    assert result.content["next_week_focus"] == ["Review team capacity and reduce concurrent work."]
    serialized = json.dumps([result.artifact, result.content])
    for text in ("SENTINEL", "new_s0", "issue_1", "suggest_for_team", "severity", "rationale"):
        assert text not in serialized


def rich_focus_fixture():
    inputs, context = fixture()
    recs = recommendation_fixture()[0].recommendations
    source = recs._source_context.issues._source_context
    object.__setattr__(source, "eligible", deepcopy(inputs.eligible))
    recs._source_context.issues._artifact["data"]["items"][0]["theme"] = "theme_0"
    recs._artifact["data"]["items"][0]["support"] = [row["data"]["source"] for row in inputs.eligible.feedback_for_analysis()]
    # Synthetic #30 handoff, actual team validator proves every selected action
    # from the actual #25/#26 sources; no expected-result grounding assertion.
    registry = recs._source_context.references
    from signal_loop.contracts.analysis import Reference
    for source_ref in recs._artifact["data"]["items"][0]["support"]:
        registry[source_ref] = Reference("feedback", "cedar", "2026-09-07", inputs.eligible.expires_at)
    recs._source_context.issues._artifact["data"]["items"][0]["explanation"] = "MANAGER_ONLY_RISK_SENTINEL"
    return replace(inputs, recommendations=recs), context


def test_complete_fixture_has_wins_blockers_concerns_and_focus_together():
    result = prepare(rich_focus_fixture())
    assert result.state == "ready" and len(result.content["themes"]) == 4
    assert result.content["next_week_focus"] == ["Review team capacity and reduce concurrent work."]


@pytest.mark.parametrize("mutation", ["private", "unsupported_action", "unsupported_source"])
def test_selected_focus_is_independently_checked(mutation):
    inputs, context = recommendation_fixture()
    row = inputs.recommendations._artifact["data"]["items"][0]
    if mutation == "private":
        row["suggest_for_team"] = False
    elif mutation == "unsupported_action":
        row["action"] = "Investigate the only engineer."
    else:
        row["support"] = row["support"][:4]
    result = prepare((inputs, context))
    if mutation == "private":
        assert result.state == "ready" and result.content["next_week_focus"] == []
    else:
        assert result.state != "ready" and result.content is None


def test_trends_recomputed_from_actual_two_week_sources_and_review():
    previous, current = snapshot(prior=True), snapshot()
    sources = current.eligible.feedback_for_analysis()
    passages = tuple(row["data"]["note"] for row in sources)
    context = Context(TeamPublicationContext(JointContext("cedar", "2026-09-07",
        frozenset({("cedar", "2026-09-07")}), (ContextScope("cedar", "2026-09-07", passages, 10),), {}), None, None))
    history = SeverityHistory(previous, current, SyntheticHistoryReviewer(previous, current))
    inputs = TeamInput(current.eligible, current.themes, history=history)
    result = prepare((inputs, context))
    assert result.state == "ready"
    assert result.content["trends"] == ["Reported workload overload persists across consecutive weeks."]
    assert result.expires_at == CLOSE + timedelta(days=7)
    bad = replace(history, reviewer=SyntheticHistoryReviewer(previous, current, membership_unchanged=False))
    assert prepare((replace(inputs, history=bad), context)).content is None


def test_snapshot_preserves_input_when_context_callback_mutates_caller():
    inputs, context = fixture()
    original = context.load
    def mutate(**kwargs):
        inputs.eligible._artifacts[0]["data"]["workload"] = "manageable"
        return original(**kwargs)
    context.load = mutate
    assert prepare((inputs, context)).state == "ready"


class Commitments:
    def __init__(self, values):
        self.values = values

    def published_for(self, **kwargs):
        return deepcopy(self.values)


@pytest.mark.parametrize("case", ["published", "unpublished", "scope", "unsafe", "expired", "boolean"])
def test_commitment_requires_scoped_already_published_handoff_and_safe_process_action(case):
    item = PublishedCommitment("cedar", "2026-09-07", "Review team capacity and reduce concurrent work.", CLOSE,
                               CLOSE + timedelta(days=3))
    if case == "unpublished":
        item = replace(item, published_at=CLOSE + timedelta(seconds=1))
    elif case == "scope":
        item = replace(item, project="birch")
    elif case == "unsafe":
        item = replace(item, text="UNPUBLISHED_PRIVATE_SENTINEL")
    elif case == "expired":
        item = replace(item, expires_at=CLOSE)
    elif case == "boolean":
        item = {"text": item.text, "approved": True}
    result = prepare(commitment_provider=Commitments((item,)))
    assert (result.state == "ready") == (case == "published")
    if case == "published":
        assert result.artifact["data"]["commitments"] == [{"text": item.text, "approved": True}]
        assert result.content["commitments"] == [item.text]


@pytest.fixture
def clear_team(postgres_database):
    yield
    models.QuerySet(model=TeamSummary).delete()
    models.QuerySet(model=ManagerReport).delete()
    models.QuerySet(model=AudienceRelease).delete()


def compose(values=None, **kwargs):
    inputs, context = values or fixture()
    return compose_team(inputs, project="cedar", week="2026-09-07", version=kwargs.pop("version", "analysis-v1"),
                        closes_at=CLOSE, at=kwargs.pop("at", CLOSE), context_provider=context, **kwargs)


def display(at=CLOSE + timedelta(minutes=1), allowed=True):
    with patch("signal_loop.reporting.selectors.has_permission", return_value=allowed):
        return team_summary_for(AnonymousUser(), project=SimpleNamespace(pk="cedar", organisation_id=1),
                                week="2026-09-07", at=at, closes_at=CLOSE)


@pytest.mark.usefixtures("clear_team")
def test_atomic_canonical_storage_separate_projection_and_immutable_retry():
    assert compose().state == "ready"
    candidate, release = TeamSummary.objects.get(), AudienceRelease.objects.get()
    assert candidate.artifact["schema"] == "team-summary/1.0"
    assert candidate.artifact["data"]["themes"] == [f"theme_{i}" for i in range(4)]
    assert candidate.expires_at == CLOSE + timedelta(days=14)
    assert display()["content"] == release.content
    assert "theme_0" not in json.dumps(display())
    before = AudienceRelease.objects.values().get()
    assert compose(version="analysis-v2", at=CLOSE + timedelta(days=1)).state == "ready"
    assert TeamSummary.objects.count() == 1 and AudienceRelease.objects.values().get() == before
    assert display(at=release.expires_at)["status"] == "unavailable"
    assert display(at=CLOSE - timedelta(seconds=1))["status"] == "not_yet_available"
    assert display(allowed=False)["status"] == "unavailable"
    withdraw_release(project="cedar", week="2026-09-07", audience="team")
    assert display()["status"] == "unavailable" and compose().state == "suppressed"


@pytest.mark.usefixtures("clear_team")
def test_nonready_persists_no_partial_summary_and_rollback():
    inputs, context = fixture()
    assert compose((None, context)).state == "suppressed"
    assert TeamSummary.objects.get().artifact is None and not AudienceRelease.objects.exists()
    assert compose().state == "suppressed"
    with patch("signal_loop.reporting.team.publish_locked", side_effect=RuntimeError("synthetic")):
        with pytest.raises(RuntimeError):
            compose(version="analysis-v2")
    assert TeamSummary.objects.count() == 1 and not AudienceRelease.objects.exists()


@pytest.mark.usefixtures("clear_team")
def test_concurrent_versions_have_one_original_release():
    values = fixture()
    barrier = Barrier(2)
    def work(index):
        try:
            barrier.wait(timeout=10)
            return compose(values, version=f"analysis-v{index}").state
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(work, (1, 2))) == ["ready", "ready"]
    assert TeamSummary.objects.count() == AudienceRelease.objects.count() == 1


@pytest.mark.usefixtures("clear_team")
def test_final_context_change_withholds_and_consumes_original_deadline():
    inputs, context = fixture()
    original = context.load
    count = 0
    def changed(**kwargs):
        nonlocal count
        count += 1
        value = original(**kwargs)
        return replace(value, joint_context=replace(value.joint_context, scopes=())) if count > 1 else value
    context.load = changed
    assert compose((inputs, context)).state == "suppressed"
    assert not AudienceRelease.objects.exists()
    with patch("signal_loop.reporting.team.monotonic", side_effect=[0, 15 * 86400]):
        assert compose(version="analysis-v2").state == "suppressed"


@pytest.mark.usefixtures("clear_team")
@pytest.mark.parametrize("case", ["matching", "absent_inventory", "different", "withdrawn", "expired", "team_four"])
def test_actual_manager_release_does_not_grant_team_eligibility_and_must_match(case):
    recs, manager_context = manager_fixture()
    assert compose_manager(recs, project="cedar", week="2026-09-07", version="analysis-v1",
        closes_at=CLOSE, at=CLOSE, context_provider=manager_context).state == "ready"
    inputs, context = recommendation_fixture()
    context.value = TeamPublicationContext(context.value.joint_context, recs, manager_context.context)
    if case == "absent_inventory":
        context.value = replace(context.value, manager_recommendations=None, manager_context=None)
    elif case == "different":
        value = deepcopy(AudienceRelease.objects.get().content)
        value["recommendations"] = []
        models.QuerySet(model=AudienceRelease).update(content=value)  # Out-of-band corruption probe.
    elif case == "withdrawn":
        withdraw_release(project="cedar", week="2026-09-07", audience="manager")
    elif case == "expired":
        models.QuerySet(model=AudienceRelease).update(expires_at=CLOSE)
    elif case == "team_four":
        inputs.themes._artifact["data"]["items"][0]["support"].pop()
    result = compose((inputs, context))
    assert (result.state == "ready") == (case == "matching")
    assert AudienceRelease.objects.filter(audience="team").exists() == (case == "matching")
    if case == "matching":
        team, manager = AudienceRelease.objects.get(audience="team"), AudienceRelease.objects.get(audience="manager")
        assert team.expires_at <= manager.expires_at


@pytest.mark.usefixtures("clear_team")
def test_rich_stored_fixture_excludes_manager_only_fields_and_raw_provenance():
    assert compose(rich_focus_fixture()).state == "ready"
    encoded = json.dumps([TeamSummary.objects.get().artifact, AudienceRelease.objects.get().content, display()])
    for forbidden in ("SENTINEL", "new_s0", "cedar_s0", "severity", "rationale", "suggest_for_team"):
        assert forbidden not in encoded
    safe = json.dumps(AudienceRelease.objects.get().content)
    assert "provenance" not in safe and "theme_0" not in safe


@pytest.mark.usefixtures("clear_team")
def test_untrusted_reader_never_queries_reports_and_owned_candidate_is_immutable():
    with patch.object(AudienceRelease.objects, "filter") as query:
        assert display(allowed=False)["status"] == "unavailable"
    query.assert_not_called()
    compose()
    row = TeamSummary.objects.get()
    with pytest.raises(TypeError):
        row.save(_validated=True)
    with pytest.raises(TypeError):
        TeamSummary.objects.update(artifact={})


@pytest.mark.usefixtures("clear_team")
def test_published_commitments_reloaded_before_write_and_bound_retention():
    item = PublishedCommitment("cedar", "2026-09-07", "Review team capacity and reduce concurrent work.",
                               CLOSE, CLOSE + timedelta(days=3))
    provider = Commitments((item,))
    assert compose(commitment_provider=provider).state == "ready"
    assert AudienceRelease.objects.get().expires_at == item.expires_at
