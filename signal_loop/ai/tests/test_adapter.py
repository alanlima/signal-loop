from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import multiprocessing
from pathlib import Path
import re
import time

import pytest

from signal_loop.ai.adapter import Adapter, Configuration, Failure, Limits
from signal_loop.ai.fake import FakeProvider
from signal_loop.contracts.analysis import Reference, Scope, validate_artifact
from signal_loop.contracts.validation import InvalidContract


DOCUMENT = Path(__file__).resolve().parents[3] / "_docs" / "analysis-contracts.md"
BLOCKS = [json.loads(block) for block in re.findall(r"```json\s*(.*?)\s*```", DOCUMENT.read_text(encoding="utf-8"), re.S)]
KINDS = ("feedback", "themes", "trends", "issues", "evidence", "recommendations", "manager-report", "team-summary")
EXPIRY = datetime(2026, 9, 21, tzinfo=timezone.utc)


def artifact(kind="themes", invalid=False):
    value = deepcopy(BLOCKS[0])
    value["schema"] = f"{kind}/1.0"
    value["data"] = deepcopy(BLOCKS[1 + 2 * KINDS.index(kind) + int(invalid)])
    return value


def scope():
    refs = {f"s{i}": Reference("feedback", "cedar", "2026-09-07", EXPIRY) for i in range(1, 6)}
    refs.update({ref: Reference(kind, "cedar", "2026-09-07", EXPIRY) for ref, kind in (
        ("t1", "themes"), ("tr1", "trends"), ("i1", "issues"), ("e1", "evidence"),
        ("r1", "recommendations"), ("a1", "aggregate"))})
    refs["a0"] = Reference("aggregate", "cedar", "2026-08-31", EXPIRY)
    refs["birch_s5"] = Reference("feedback", "birch", "2026-09-07", EXPIRY)
    return Scope("cedar", "2026-09-07", datetime(2026, 9, 14, tzinfo=timezone.utc),
                 datetime(2026, 9, 14, tzinfo=timezone.utc), refs)


def request(kind="themes"):
    inputs = []
    for number in range(1, 6):
        value = artifact("feedback")
        value["data"]["source"] = f"s{number}"
        inputs.append(value)
    return {"schema": "analysis-request/1.0", "output_schema": f"{kind}/1.0", "inputs": inputs}


def followup():
    return {"schema": "followup-request/1.0", "project": "cedar", "week": "2026-09-07",
            "privacy_policy": "1.0", "question": "F1",
            "data": {"delivery": "blocked", "workload": "manageable", "note": "Synthetic ordinary delay."}}


@pytest.mark.parametrize("kind", KINDS)
def test_exact_document_valid_and_invalid_fixtures(kind):
    validate_artifact(artifact(kind), scope())
    with pytest.raises(InvalidContract):
        validate_artifact(artifact(kind, invalid=True), scope())


@pytest.mark.parametrize("kind", KINDS[1:])
def test_adapter_returns_repeatable_exact_restricted_candidate(kind):
    adapter = Adapter(FakeProvider(response=artifact(kind)))
    first = adapter.structured_analysis(request(kind), scope=scope())
    second = adapter.structured_analysis(request(kind), scope=scope())
    assert first.failure is None and first.candidate == second.candidate == artifact(kind)
    assert first.attempts == second.attempts == 1
    assert "Review turnaround" not in repr(first)


def test_followup_fixed_catalog_no_prompt_no_personal_or_wrong_scope():
    assert Adapter(FakeProvider()).follow_up(followup()).candidate["question"] == "F1"
    assert Adapter(FakeProvider(script=("suppress",))).follow_up(followup()).candidate["decision"] == "suppress"
    for key, value in (("P1", "high"), ("identity", "synthetic-person"), ("prompt", "Invented question")):
        invalid = followup()
        invalid["data"][key] = value
        result = Adapter(FakeProvider()).follow_up(invalid)
        assert result.failure == Failure.INVALID_REQUEST and result.attempts == 0
    invalid = followup()
    invalid["data"]["delivery"] = "on_track"
    assert Adapter(FakeProvider()).follow_up(invalid).failure == Failure.INVALID_REQUEST
    response = Adapter(FakeProvider()).follow_up(followup()).candidate
    for key, value in (("project", "birch"), ("question", "F2"), ("prompt", "Invented question")):
        wrong = {**response, key: value}
        assert Adapter(FakeProvider(response=wrong)).follow_up(followup()).failure == Failure.INVALID_OUTPUT


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(identity="synthetic-person"),
    lambda value: value.update(schema="themes/2.0"),
    lambda value: value.update(privacy_policy="2.0"),
    lambda value: value.update(week="2026-09-08"),
    lambda value: value.update(expires_at="2026-09-21T00:00:00+10:00"),
    lambda value: value["provenance"].update(input_refs=["s1", "s1"]),
    lambda value: value["data"]["items"][0].update(distinct_support=True),
    lambda value: value["data"]["items"][0].update(statement=None),
    lambda value: value["data"]["items"][0].update(statement="x" * 501),
    lambda value: value["data"]["items"][0].pop("statement"),
    lambda value: value["data"].update(extra="unknown"),
])
def test_strict_nested_schema_types_and_limits(mutation):
    value = artifact()
    mutation(value)
    with pytest.raises(InvalidContract):
        validate_artifact(value, scope())


def test_resolution_order_expiry_scope_and_untrusted_safety_claims():
    invalid = artifact("trends", invalid=True)
    with pytest.raises(InvalidContract, match="nonconsecutive_window"):
        validate_artifact(invalid, scope())
    invalid = artifact()
    invalid["data"]["items"][0]["support"] = ["unknown"]
    with pytest.raises(InvalidContract, match="unresolved_reference"):
        validate_artifact(invalid, scope())
    invalid["data"]["items"][0]["support"] = ["birch_s5"]
    with pytest.raises(InvalidContract, match="cross_scope_reference"):
        validate_artifact(invalid, scope())
    expired = replace(scope(), now=EXPIRY)
    with pytest.raises(InvalidContract, match="expired_source"):
        validate_artifact(artifact(), expired)
    refs = dict(scope().references)
    refs["s1"] = replace(refs["s1"], expires_at=EXPIRY - timedelta(days=1))
    with pytest.raises(InvalidContract, match="expired_source"):
        validate_artifact(artifact(), replace(scope(), references=refs))
    # False model safety remains a restricted candidate, never a ready release.
    value = artifact("evidence")
    value["data"]["items"][0]["grounded"] = False
    result = Adapter(FakeProvider(response=value)).structured_analysis(request("evidence"), scope=scope())
    assert result.candidate == value and not hasattr(result, "ready")
    for kind in ("release-control/1.0", "audience-release/1.0"):
        invalid_request = request()
        invalid_request["output_schema"] = kind
        assert Adapter(FakeProvider()).structured_analysis(invalid_request, scope=scope()).failure == Failure.INVALID_REQUEST


def test_retries_are_explicit_bounded_and_nonretryable_output_stops():
    config = Configuration(analysis=Limits(timeout=2, total_timeout=8, max_attempts=3))
    for script, expected, attempts in (
        (("unavailable", "valid"), None, 2),
        (("timeout", "valid"), None, 2),
        (("unavailable",), Failure.RETRIES_EXHAUSTED, 3),
        (("timeout",), Failure.RETRIES_EXHAUSTED, 3),
        (("malformed", "valid"), Failure.INVALID_OUTPUT, 1),
        (("rejected", "valid"), Failure.REJECTED, 1),
    ):
        result = Adapter(FakeProvider(response=artifact(), script=script), config).structured_analysis(request(), scope=scope())
        assert result.failure == expected and result.attempts == attempts


def test_real_blocking_provider_is_terminated_total_deadline_cannot_multiply():
    baseline = {child.pid for child in multiprocessing.active_children()}
    config = Configuration(analysis=Limits(timeout=0.35, total_timeout=0.55, max_attempts=5))
    started = time.monotonic()
    result = Adapter(FakeProvider(response=artifact(), delay=10), config).structured_analysis(request(), scope=scope())
    elapsed = time.monotonic() - started
    assert result.failure == Failure.TIMEOUT
    assert 0.3 <= elapsed < 1.1 and result.attempts <= 2
    assert {child.pid for child in multiprocessing.active_children()} == baseline
    started = time.monotonic()
    result = Adapter(FakeProvider(delay=10)).follow_up(followup())
    assert result.failure == Failure.TIMEOUT and result.attempts == 1
    assert time.monotonic() - started < 2.6
    assert {child.pid for child in multiprocessing.active_children()} == baseline


def test_failures_never_include_request_response_credential_or_exception_text(capfd, caplog):
    value = followup()
    value["data"]["note"] = "synthetic-secret-input"
    result = Adapter(FakeProvider(script=("error",))).follow_up(value)
    assert result.failure == Failure.INTERNAL
    captured = capfd.readouterr()
    combined = repr(result) + captured.out + captured.err + caplog.text
    for secret in ("synthetic-secret-input", "synthetic-private-provider-detail"):
        assert secret not in combined


def test_duplicate_json_keys_nonfinite_values_and_input_extra_fields_fail_closed():
    for raw in ('{"schema":"themes/1.0","schema":"themes/1.0"}', '{"data":NaN}', 'null', '[]'):
        result = Adapter(FakeProvider(raw_response=raw)).structured_analysis(request(), scope=scope())
        assert result.failure == Failure.INVALID_OUTPUT and result.attempts == 1
    invalid = request()
    invalid["credential"] = "synthetic-secret-credential"
    result = Adapter(FakeProvider()).structured_analysis(invalid, scope=scope())
    assert result.failure == Failure.INVALID_REQUEST and result.attempts == 0
    assert "synthetic-secret-credential" not in repr(result)


def test_output_cannot_extend_input_lifetime_or_change_requested_kind():
    short = request()
    for value in short["inputs"]:
        value["expires_at"] = "2026-09-20T00:00:00Z"
    result = Adapter(FakeProvider(response=artifact())).structured_analysis(short, scope=scope())
    assert result.failure == Failure.INVALID_OUTPUT
    result = Adapter(FakeProvider(response=artifact("issues"))).structured_analysis(request(), scope=scope())
    assert result.failure == Failure.INVALID_OUTPUT


def test_duplicate_request_sources_do_not_represent_multiple_contributions():
    invalid = request()
    invalid["inputs"][1] = deepcopy(invalid["inputs"][0])
    result = Adapter(FakeProvider(response=artifact())).structured_analysis(invalid, scope=scope())
    assert result.failure == Failure.INVALID_REQUEST and result.attempts == 0


@pytest.mark.parametrize("kwargs", [{"max_attempts": True}, {"max_attempts": 6}, {"timeout": float("nan")},
                                    {"total_timeout": 0}, {"timeout": True}])
def test_invalid_limits_have_fixed_safe_error(kwargs):
    with pytest.raises(ValueError, match="^invalid_configuration$"):
        Limits(**kwargs)


def test_followup_configuration_cannot_retry_or_exceed_two_seconds():
    for limits in (Limits(2, 2, 2), Limits(3, 3, 1)):
        with pytest.raises(ValueError, match="^invalid_configuration$"):
            Configuration(followup=limits)
