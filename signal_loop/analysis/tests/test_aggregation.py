from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from signal_loop.analysis.aggregation import Assessment, RestrictedAnalysisInput, Suppressed, aggregate
from signal_loop.contracts.analysis import Scope, validate_artifact


CLOSE = datetime(2026, 9, 14, tzinfo=timezone.utc)


def artifacts(count=5, project="cedar"):
    return [{"schema": "feedback/1.0", "project": project, "week": "2026-09-07",
             "privacy_policy": "1.0", "expires_at": "2026-09-28T00:00:00Z",
             "provenance": {"producer": "fixture", "producer_version": "1.0", "input_refs": []},
             "data": {"source": f"{project}_s{i}", "delivery": "at_risk", "workload": "manageable",
                      "note": "Shared review delays.",
                      "follow_up": {"question": "F1", "answer": "Shared queue."}}}
            for i in range(count)]


class FixtureVerifier:
    """Explicit independently prepared fixture evidence, never guessed from input."""
    def __init__(self, proof):
        self.proof = proof

    def assess(self, **kwargs):
        return self.proof


def proof(count=5, project="cedar", **changes):
    return replace(Assessment(project, "2026-09-07", frozenset(f"{project}_s{i}" for i in range(count)),
                              count, True, True, True), **changes)


def run(rows=None, evidence=None, **kwargs):
    return aggregate(project="cedar", week="2026-09-07", artifacts=artifacts() if rows is None else rows,
                     closes_at=CLOSE, at=kwargs.pop("at", CLOSE),
                     verifier=FixtureVerifier(proof() if evidence is None else evidence), **kwargs)


@pytest.mark.parametrize("roster,count,eligible", [(0, 0, False), (4, 4, False), (40, 4, False),
                                                   (5, 5, True), (40, 6, True)])
def test_threshold_actual_people_not_roster_answers_or_followups(roster, count, eligible):
    # Roster is deliberately not an API input; two enums + note + follow-up are one contribution.
    result = run(artifacts(count), proof(count))
    assert isinstance(result, RestrictedAnalysisInput) is eligible
    if eligible:
        assert result.distinct_contributors == count
        assert len(result.feedback_for_analysis()) == count
    else:
        assert asdict(result) == {"status": "unavailable"}


def test_exact_canonical_envelopes_restricted_and_defensive_copies():
    rows = artifacts()
    result = run(rows)
    assert isinstance(result, RestrictedAnalysisInput)
    assert result.expires_at == CLOSE + timedelta(days=14)
    assert result.feedback_for_analysis() == tuple(rows)
    for artifact in result.feedback_for_analysis():
        validate_artifact(artifact, Scope("cedar", "2026-09-07", CLOSE, CLOSE))
    rows[0]["data"]["note"] = "changed caller"
    copy = result.feedback_for_analysis()
    copy[0]["data"]["note"] = "changed consumer"
    assert result.feedback_for_analysis()[0]["data"]["note"] == "Shared review delays."
    assert repr(result) == "RestrictedAnalysisInput(<restricted>)"
    with pytest.raises(TypeError):
        json.dumps(result)
    assert not hasattr(result, "publish") and not hasattr(result, "ready")


@pytest.mark.parametrize("changes", [
    {"distinct_contributors": 4}, {"distinct_contributors": True}, {"distinct_contributors": 6},
    {"admission_verified": False}, {"admission_verified": 1}, {"content_safe": False},
    {"inference_safe": False}, {"inference_safe": None}, {"project": "birch"},
    {"week": "2026-09-14"}, {"sources": frozenset({"wrong"})},
])
def test_incomplete_forged_or_unsafe_evidence_uniformly_suppresses(changes):
    assert run(evidence=proof(**changes)) == Suppressed()


def test_untrusted_counts_and_missing_proof_never_suffice():
    assert run(evidence=asdict(proof())) == Suppressed()
    assert aggregate(project="cedar", week="2026-09-07", artifacts=artifacts(),
                     closes_at=CLOSE, at=CLOSE) == Suppressed()
    # Two different source UUIDs for one alias person cannot inflate the proof count.
    assert run(artifacts(6), proof(6, distinct_contributors=5)) == Suppressed()
    repeated = artifacts(4)
    repeated.append(deepcopy(repeated[0]))
    assert run(repeated) == Suppressed()


@pytest.mark.parametrize("mutation", ["missing_seconds", "unnormalized_producer"])
def test_strict_downstream_envelope_rejects_qa_mutations(mutation):
    rows = artifacts()
    if mutation == "missing_seconds":
        rows[0]["expires_at"] = "2026-09-28T00:00Z"
    else:
        rows[0]["provenance"]["producer_version"] = "v1\rv2"
    assert run(rows) == Suppressed()


@pytest.mark.parametrize("change", ["personal", "crossproject", "crossweek", "unknown", "version", "refs", "declined"])
def test_invalid_input_has_no_feedback_in_suppression(change):
    rows = artifacts()
    if change == "personal":
        rows[0]["data"]["P4"] = "Only overnight specialist"
    elif change == "crossproject":
        rows[0]["project"] = "birch"
    elif change == "crossweek":
        rows[0]["week"] = "2026-09-14"
    elif change == "unknown":
        rows[0]["person"] = "Rowan"
    elif change == "version":
        rows[0]["privacy_policy"] = "2.0"
    elif change == "refs":
        rows[0]["provenance"]["input_refs"] = ["birch_s0"]
    else:
        rows[0]["data"] = {"source": "cedar_s0", "delivery": "prefer_not_to_say",
                           "workload": "not_enough_context", "note": ""}
    result = run(rows)
    assert asdict(result) == {"status": "unavailable"}
    assert repr(result) == "Suppressed(status='unavailable')"


def test_overlap_review_withholds_identifying_narrative_without_identity_map():
    cedar, birch = artifacts(), artifacts(project="birch")
    for group in (cedar, birch):
        group[0]["data"]["note"] = "As the only overnight specialist, I handled the rare outage."
    assert run(cedar, proof(inference_safe=False)) == Suppressed()
    assert aggregate(project="birch", week="2026-09-07", artifacts=birch, closes_at=CLOSE, at=CLOSE,
                     verifier=FixtureVerifier(proof(project="birch", inference_safe=False))) == Suppressed()
    assert not ({row["data"]["source"] for row in cedar} & {row["data"]["source"] for row in birch})


def test_expiry_schedule_bounds_and_stricter_configuration():
    assert run(at=CLOSE - timedelta(microseconds=1)) == Suppressed()
    assert run(at=CLOSE + timedelta(days=14)) == Suppressed()
    assert run(threshold=4) == Suppressed()
    assert run(threshold=True) == Suppressed()
    assert run(threshold=6) == Suppressed()
    rows = artifacts()
    rows[0]["expires_at"] = "2026-09-15T00:00:00Z"
    assert run(rows).expires_at == CLOSE + timedelta(days=1)
    assert run(rows, at=CLOSE + timedelta(days=1)) == Suppressed()
    rows[0]["expires_at"] = "2026-09-29T00:00:00Z"
    assert run(rows) == Suppressed()


def test_verifier_errors_do_not_log_content_or_leak_exception(capsys, caplog):
    class Broken:
        def assess(self, **kwargs):
            raise RuntimeError("Rowan secret feedback")
    result = aggregate(project="cedar", week="2026-09-07", artifacts=artifacts(), closes_at=CLOSE,
                       at=CLOSE, verifier=Broken())
    assert result == Suppressed()
    assert capsys.readouterr().out == ""
    assert caplog.text == ""
