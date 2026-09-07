from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json

import pytest

from signal_loop.analysis.aggregation import Assessment, Suppressed, aggregate
from signal_loop.analysis.themes import RestrictedThemes
from signal_loop.analysis.trends import (
    HistoryReview, RestrictedTrends, TOPICS, TrendUnavailable, WeeklyHistory, compare_weeks,
)
from .test_aggregation import CLOSE, FixtureVerifier, artifacts


def snapshot(*, prior=False, total=10, support=5, topic_index=1, alias=0):
    week = "2026-08-31" if prior else "2026-09-07"
    close = CLOSE - timedelta(days=7) if prior else CLOSE
    expiry = close + timedelta(days=14)
    topic = TOPICS[topic_index]
    text = topic.statements[alias]
    rows = artifacts(total)
    for i, row in enumerate(rows):
        row.update(week=week, expires_at=expiry.isoformat().replace("+00:00", "Z"))
        row["data"] = {"source": f"{'old' if prior else 'new'}_s{i}", "delivery": "on_track",
                       "workload": "manageable", "note": text if i < support else "No additional concern."}
        if i < support and topic.key == "workload-overload":
            row["data"]["workload"] = "overloaded"
        if i < support and topic.key == "delivery-blocked":
            row["data"]["delivery"] = "blocked"
    proof = Assessment("cedar", week, frozenset(row["data"]["source"] for row in rows), total, True, True, True)
    eligible = aggregate(project="cedar", week=week, artifacts=rows, closes_at=close, at=CLOSE,
                         verifier=FixtureVerifier(proof))
    envelope = deepcopy(rows[0])
    envelope["schema"] = "themes/1.0"
    envelope["data"] = {"items": [{"id": "old_theme" if prior else "new_theme", "category": topic.category,
                                   "statement": text, "support": [row["data"]["source"] for row in rows[:support]],
                                   "distinct_support": support}]}
    # Explicit #26 interface fixture; runtime trend validation independently
    # checks complete source grounding, so the fixture cannot assume it true.
    return WeeklyHistory("old_aggregate" if prior else "new_aggregate", close, eligible, RestrictedThemes(envelope))


class SyntheticHistoryReviewer:
    def __init__(self, previous, current, **changes):
        self.proof = replace(HistoryReview(deepcopy(previous), deepcopy(current), True, True, True, True), **changes)

    def assess(self, **kwargs):
        return self.proof


def compare(previous=None, current=None, **kwargs):
    previous = snapshot(prior=True) if previous is None else previous
    current = snapshot() if current is None else current
    reviewer = kwargs.pop("reviewer", SyntheticHistoryReviewer(previous, current))
    return compare_weeks(previous=previous, current=current, at=kwargs.pop("at", CLOSE), reviewer=reviewer, **kwargs)


@pytest.mark.parametrize("topic,old_support,old_total,new_support,new_total,direction,recurrence", [
    (1, 5, 10, 6, 10, "worsening", True),
    (2, 6, 10, 5, 10, "improving", True),
    (4, 5, 10, 5, 10, "persisting", True),
    (1, 5, 20, 6, 20, "persisting", True),
    (1, 5, 10, 9, 15, "worsening", True),
    (0, 5, 10, 6, 10, "improving", False),
    (0, 6, 10, 5, 10, "worsening", False),
    (1, 6, 10, 6, 10, "persisting", True),
])
def test_documented_numeric_boundaries_all_dimensions(topic, old_support, old_total, new_support, new_total, direction, recurrence):
    previous = snapshot(prior=True, total=old_total, support=old_support, topic_index=topic)
    current = snapshot(total=new_total, support=new_support, topic_index=topic)
    result = compare(previous, current)
    assert isinstance(result, RestrictedTrends)
    rows = result.artifact_for_analysis()["data"]["items"]
    assert rows[0]["direction"] == direction
    assert rows[0]["current_support"] == new_support and rows[0]["previous_support"] == old_support
    assert rows[0]["theme"] == "new_theme" and rows[0]["previous_aggregate"] == "old_aggregate"
    assert len(rows) == (2 if recurrence else 1)
    if recurrence:
        assert rows[1]["direction"] == "persisting" and "recurs across consecutive weeks" in rows[1]["statement"]
    assert compare(previous, current).artifact_for_analysis() == result.artifact_for_analysis()


@pytest.mark.parametrize("topic", [0, 3, 4])
def test_explicit_rename_preserves_matching_and_current_theme_reference(topic):
    result = compare(snapshot(prior=True, topic_index=topic), snapshot(topic_index=topic, alias=1))
    assert isinstance(result, RestrictedTrends)
    row = result.artifact_for_analysis()["data"]["items"][0]
    assert row["theme"] == "new_theme" and row["direction"] == "persisting"
    assert set(row) == {"id", "theme", "previous_week", "previous_aggregate", "direction", "statement",
                        "current_support", "previous_support", "comparison_safe"}


@pytest.mark.parametrize("old_support,new_support", [(4, 5), (5, 4)])
def test_five_supporters_required_in_both_weeks(old_support, new_support):
    result = compare(snapshot(prior=True, support=old_support), snapshot(support=new_support))
    assert result == TrendUnavailable("insufficient_supported_history")


def test_isolated_and_unknown_or_reclassified_themes_do_not_mean_recovery():
    previous = snapshot(prior=True)
    envelope = previous.themes.artifact_for_analysis()
    for mutation in ("empty", "unknown", "category"):
        changed = deepcopy(envelope)
        if mutation == "empty":
            changed["data"]["items"] = []
        elif mutation == "unknown":
            changed["data"]["items"][0]["statement"] = "An unreviewed rename."
        else:
            changed["data"]["items"][0]["category"] = "support"
        result = compare(replace(previous, themes=RestrictedThemes(changed)))
        assert result == TrendUnavailable("insufficient_supported_history")


def test_missing_suppressed_gap_and_insufficient_history_never_zero_fill():
    assert compare_weeks(previous=None, current=snapshot(), at=CLOSE) == TrendUnavailable("insufficient_history")
    assert compare_weeks(previous=snapshot(prior=True), current=None, at=CLOSE) == TrendUnavailable("insufficient_history")
    assert compare_weeks(previous=Suppressed(), current=snapshot(), at=CLOSE) == TrendUnavailable("invalid_history")
    previous = snapshot(prior=True)
    previous = replace(previous, eligible=replace(previous.eligible, week="2026-08-24"))
    assert compare(previous) == TrendUnavailable("gap")


@pytest.mark.parametrize("field,value", [
    ("original_releases_verified", False), ("membership_unchanged", False),
    ("participation_safe", False), ("joint_inference_safe", False),
    ("membership_unchanged", None), ("participation_safe", 1),
])
def test_eligible_weeks_still_withheld_for_release_membership_participation_or_joint_risk(field, value):
    previous, current = snapshot(prior=True), snapshot(support=6, total=11)
    reviewer = SyntheticHistoryReviewer(previous, current, **{field: value})
    assert compare(previous, current, reviewer=reviewer) == TrendUnavailable("unsafe_comparison")


def test_review_bound_to_exact_content_not_only_same_ids_counts_or_scope():
    previous, current = snapshot(prior=True), snapshot()
    reviewer = SyntheticHistoryReviewer(previous, current)
    rows = current.eligible.feedback_for_analysis()
    rows[-1]["data"]["note"] = "Changed after review."
    current = replace(current, eligible=replace(current.eligible, _artifacts=rows))
    assert compare(previous, current, reviewer=reviewer) == TrendUnavailable("unsafe_comparison")
    assert compare(previous, current, reviewer=None) == TrendUnavailable("unsafe_comparison")


@pytest.mark.parametrize("mutation", ["count", "ref", "unsupported", "duplicate_topic", "expiry", "crossproject", "version"])
def test_invalid_or_ungrounded_history_fails_closed(mutation):
    current = snapshot()
    envelope = current.themes.artifact_for_analysis()
    if mutation == "count":
        envelope["data"]["items"][0]["distinct_support"] = 6
    elif mutation == "ref":
        envelope["data"]["items"][0]["support"][0] = "foreign"
    elif mutation == "unsupported":
        rows = current.eligible.feedback_for_analysis()
        rows[0]["data"].update(workload="manageable", note="Workload is not overloaded.")
        current = replace(current, eligible=replace(current.eligible, _artifacts=rows))
    elif mutation == "duplicate_topic":
        envelope["data"]["items"].append({**deepcopy(envelope["data"]["items"][0]), "id": "duplicate"})
    elif mutation == "expiry":
        envelope["expires_at"] = "2026-09-14T00:00:00Z"
    elif mutation == "crossproject":
        envelope["project"] = "birch"
    else:
        envelope["schema"] = "themes/2.0"
    current = replace(current, themes=RestrictedThemes(envelope))
    assert compare(current=current) == TrendUnavailable("invalid_history")


def test_unknown_rule_expired_raw_support_and_preclosure_history_reject():
    assert compare(version="project-trends/2.0") == TrendUnavailable("invalid_history")
    assert compare(at=CLOSE + timedelta(days=7)) == TrendUnavailable("invalid_history")
    assert compare(at=CLOSE - timedelta(seconds=1)) == TrendUnavailable("invalid_history")


def test_reviewer_exception_is_content_free_and_public_status_uniform(capsys, caplog):
    class Broken:
        def assess(self, **kwargs):
            raise ValueError("synthetic-private-history")
    result = compare(reviewer=Broken())
    assert result == TrendUnavailable("unsafe_comparison")
    assert repr(result) == "TrendUnavailable(status='unavailable')"
    assert capsys.readouterr().out == "" and caplog.text == ""
    assert result.public_status() == compare().public_status() == {"status": "unavailable"}


def test_permitted_provenance_only_no_old_source_keys_public_counts_or_mutable_result():
    result = compare()
    assert repr(result) == "RestrictedTrends(<restricted>)"
    with pytest.raises(TypeError):
        json.dumps(result)
    envelope = result.artifact_for_analysis()
    assert envelope["schema"] == "trends/1.0" and envelope["expires_at"] == "2026-09-21T00:00:00Z"
    assert set(envelope["provenance"]["input_refs"]) == {"old_aggregate", "new_theme"}
    assert "old_s" not in json.dumps(envelope) and "new_s" not in json.dumps(envelope)
    assert json.dumps(result.public_status()) == '{"status": "unavailable"}'
    envelope["data"]["items"].clear()
    assert result.artifact_for_analysis()["data"]["items"]


def test_multiple_topics_order_and_independent_below_threshold_withholding():
    def with_win(history):
        sources = history.eligible.feedback_for_analysis()
        for source in sources[:5]:
            source["data"]["note"] = TOPICS[0].statements[0]
        eligible = replace(history.eligible, _artifacts=sources)
        envelope = history.themes.artifact_for_analysis()
        envelope["data"]["items"].append({"id": "win_theme", "statement": TOPICS[0].statements[0],
                                           "category": "wins", "support": [row["data"]["source"] for row in sources[:5]],
                                           "distinct_support": 5})
        return replace(history, eligible=eligible, themes=RestrictedThemes(envelope))
    previous, current = with_win(snapshot(prior=True)), with_win(snapshot())
    original = compare(previous, current).artifact_for_analysis()
    assert [row["theme"] for row in original["data"]["items"]] == ["win_theme", "new_theme", "new_theme"]
    reordered = current.themes.artifact_for_analysis()
    reordered["data"]["items"].reverse()
    current = replace(current, themes=RestrictedThemes(reordered))
    assert compare(previous, current).artifact_for_analysis() == original
    below = with_win(snapshot(prior=True, support=4))
    result = compare(below, current).artifact_for_analysis()
    assert len(result["data"]["items"]) == 1
    assert result["data"]["items"][0]["theme"] == "win_theme"
    assert "new_theme" not in result["provenance"]["input_refs"]
