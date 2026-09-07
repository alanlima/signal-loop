from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from functools import lru_cache
import json

import pytest

from signal_loop.analysis.tests.test_recommendations import bundle, run
from signal_loop.analysis.tests.test_aggregation import CLOSE
from signal_loop.reporting.composition import PublicationContext, prepare_manager
from signal_loop.reporting.projections import validate_content
from signal_loop.contracts.analysis import Scope, validate_artifact


class FixturePublicationContext:
    def __init__(self, joint):
        self.context = PublicationContext(joint, {
            "title": "Weekly project summary", "overview": "The volume of work exceeds available capacity.",
            "themes": ["The volume of work exceeds available capacity."],
            "trends": ["Reported workload overload persists across consecutive weeks."],
            "next_week_focus": ["Review team capacity and reduce concurrent work."], "commitments": [],
        })

    def load(self, **kwargs):
        return deepcopy(self.context)


@lru_cache(maxsize=1)
def _fixture():
    assessment, evidence, context, output = bundle()
    recommendations = run(assessment, evidence, context, output).recommendations
    assert recommendations is not None
    return recommendations, FixturePublicationContext(context.context)


def fixture():
    return deepcopy(_fixture())


def prepare(recommendations, context, **kwargs):
    return prepare_manager(recommendations, project="cedar", week="2026-09-07", version="analysis-v1",
                           closes_at=CLOSE, at=kwargs.pop("at", CLOSE), context_provider=context, **kwargs)


def test_complete_actual_stage_fixture_exact_restricted_and_public_shapes():
    recommendations, context = fixture()
    result = prepare(recommendations, context)
    assert result.state == "ready"
    validate_artifact(result.artifact, Scope("cedar", "2026-09-07", CLOSE, CLOSE,
                                           recommendations.source_context_for_analysis().references))
    assert result.artifact["schema"] == "manager-report/1.0"
    assert result.artifact["data"]["issues"] == ["issue_1"]
    validate_content(result.content, "manager")
    assert result.content["issues"] == [{"severity": "moderate", "explanation":
        "The volume of work exceeds available capacity. The effect is limited to a project process. There is no current need for action."}]
    assert result.content["evidence"] == [{"form": "paraphrase", "text": "The volume of work exceeds available capacity."}]
    assert result.content["trends"] == ["Reported workload overload persists across consecutive weeks."]
    encoded = json.dumps(result.content)
    for forbidden in ("new_s0", "issue_1", "recommendation_1", "provenance", "support", "score", "20", "5/", "suggest_for_team"):
        assert forbidden not in encoded
    assert "new_s0" not in repr(result)


@pytest.mark.parametrize("mutation", ["source", "count", "four", "schema", "issue", "rationale", "evidence", "trend", "numeric_bool"])
def test_changed_lineage_or_unsafe_fields_never_produce_partial_content(mutation):
    recommendations, context = fixture()
    lineage = recommendations._source_context
    issue_context = lineage.issues._source_context
    if mutation == "source":
        issue_context.eligible._artifacts[0]["data"]["workload"] = "manageable"
    elif mutation == "count":
        object.__setattr__(issue_context.eligible, "distinct_contributors", 4)
    elif mutation == "four":
        lineage.evidence._artifact["data"]["items"][0]["support"].pop()
    elif mutation == "schema":
        recommendations._artifact["schema"] = "recommendations/2.0"
    elif mutation == "issue":
        lineage.issues._artifact["data"]["items"][0]["explanation"] = "Alex caused the incident."
    elif mutation == "rationale":
        recommendations._artifact["data"]["items"][0]["rationale"] = "The only night operator caused the private launch failure."
    elif mutation == "evidence":
        lineage.evidence._artifact["data"]["items"][0]["text"] = "Alex is overloaded."
    elif mutation == "trend":
        issue_context.trends._artifact["data"]["items"][0]["statement"] = "Five people submitted and one did not."
    else:
        factor = lineage.calculations[0].factors[0]
        object.__setattr__(factor, "weight", True)
    result = prepare(recommendations, context)
    assert result.state != "ready" and result.content is None and result.artifact is None


@pytest.mark.parametrize("mutation", ["missing", "unknown_team", "manager_field", "unapproved_commitment", "joint", "changed"])
def test_joint_team_and_manager_review_is_required(mutation):
    recommendations, context = fixture()
    if mutation == "missing":
        context = None
    elif mutation == "unknown_team":
        context.context.team_content["overview"] = "The lone new hire complained."
    elif mutation == "manager_field":
        context.context.team_content["issues"] = []
    elif mutation == "unapproved_commitment":
        context.context.team_content["commitments"] = ["Target the only reviewer."]
    elif mutation == "joint":
        context.context.joint_context.intersections[frozenset()] = 1
    else:
        original = context.load
        calls = 0

        def changed(**kwargs):
            nonlocal calls
            calls += 1
            value = original(**kwargs)
            if calls > 1:
                value.team_content["next_week_focus"] = []
            return value

        context.load = changed
    result = prepare(recommendations, context)
    assert result.state != "ready" and result.content is None


def test_empty_supported_and_missing_input_are_uniform_non_ready():
    recommendations, context = fixture()
    recommendations._artifact["data"]["items"] = []
    assert prepare(recommendations, context).state == "suppressed"
    assert prepare(None, context).state == "suppressed"
    result = prepare(*fixture(), at=CLOSE + timedelta(days=14))
    assert result.state != "ready" and result.content is None


def test_snapshot_does_not_rebind_when_caller_changes_during_review():
    recommendations, context = fixture()
    original = context.load

    def mutate(**kwargs):
        recommendations._artifact["data"]["items"][0]["rationale"] = "Alex"
        return original(**kwargs)

    context.load = mutate
    result = prepare(recommendations, context)
    assert result.state == "ready"
    assert "Alex" not in json.dumps(result.content)


def test_other_scope_source_or_qualified_private_context_is_rejected():
    recommendations, context = fixture()
    source = recommendations._source_context.issues._source_context.eligible._artifacts[0]
    source["project"] = "birch"
    assert prepare(recommendations, context).content is None
    recommendations, context = fixture()
    context.context = replace(context.context, joint_context=replace(context.context.joint_context, scopes=()))
    assert prepare(recommendations, context).content is None
