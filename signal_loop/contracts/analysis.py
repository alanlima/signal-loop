"""Exact #6 restricted envelopes: structural, local and scoped-reference checks.

Passing is NOT verified grounding, distinct-person support or release approval.
Those require independent analysis/reporting gates, never model booleans.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .feedback import InvalidFeedback, validate_artifact as validate_feedback
from .reports import validate_report_data
from .validation import (
    InvalidContract, boolean, enum, fields, identifier, integer, items, monday,
    references, require, string, utc_time,
)
from .versions import PRIVACY_POLICY, RESTRICTED_SCHEMAS


@dataclass(frozen=True)
class Reference:
    kind: str
    project: str
    week: str
    expires_at: datetime


@dataclass(frozen=True)
class Scope:
    project: str
    week: str
    closes_at: datetime
    now: datetime
    references: dict[str, Reference] = field(default_factory=dict, repr=False)


def validate_data(kind, data):
    if kind in {"manager-report", "team-summary"}:
        validate_report_data(kind, data)
        return
    fields(data, {"items"})
    items(data["items"], 100 if kind == "evidence" else 50)
    for row in data["items"]:
        if kind == "themes":
            fields(row, {"id", "statement", "support", "distinct_support"}, {"category"})
            string(row["statement"], 500)
            references(row["support"], minimum=1)
            integer(row["distinct_support"], 1)
            if "category" in row:
                enum(row["category"], {"delivery", "workload", "collaboration", "wins", "support"})
        elif kind == "trends":
            fields(row, {"id", "theme", "previous_week", "previous_aggregate", "direction", "statement",
                         "current_support", "previous_support", "comparison_safe"})
            identifier(row["theme"])
            identifier(row["previous_aggregate"])
            monday(row["previous_week"])
            enum(row["direction"], {"persisting", "improving", "worsening"})
            string(row["statement"], 500)
            integer(row["current_support"], 5)
            integer(row["previous_support"], 5)
            boolean(row["comparison_safe"])
        elif kind == "issues":
            fields(row, {"id", "theme", "category", "severity", "explanation", "support"}, {"trend"})
            identifier(row["theme"])
            enum(row["category"], {"delivery", "workload", "collaboration", "recurring_concern"})
            enum(row["severity"], {"low", "moderate", "high", "critical"})
            string(row["explanation"], 800)
            references(row["support"], minimum=1)
            if "trend" in row:
                identifier(row["trend"])
        elif kind == "evidence":
            fields(row, {"id", "issue", "form", "text", "support", "grounded"}, {"label"})
            identifier(row["issue"])
            enum(row["form"], {"paraphrase", "synthesis"})
            string(row["text"], 800)
            references(row["support"], minimum=5)
            boolean(row["grounded"])
            require((row["form"] == "synthesis" and row.get("label") == "Synthesized example from shared feedback")
                    or (row["form"] == "paraphrase" and "label" not in row), "invalid_label")
        elif kind == "recommendations":
            fields(row, {"id", "issue", "action", "rationale", "support"}, {"suggest_for_team"})
            identifier(row["issue"])
            string(row["action"], 500)
            string(row["rationale"], 800)
            references(row["support"], minimum=5)
            if "suggest_for_team" in row:
                boolean(row["suggest_for_team"])


def validate_artifact(artifact, scope):
    fields(artifact, {"schema", "project", "week", "privacy_policy", "expires_at", "provenance", "data"})
    enum(artifact["schema"], RESTRICTED_SCHEMAS)
    enum(artifact["privacy_policy"], {PRIVACY_POLICY})
    identifier(artifact["project"])
    week = monday(artifact["week"])
    expiry = utc_time(artifact["expires_at"])
    provenance = artifact["provenance"]
    fields(provenance, {"producer", "producer_version", "input_refs"})
    identifier(provenance["producer"])
    string(provenance["producer_version"], 32)
    references(provenance["input_refs"], 100)
    kind = artifact["schema"].split("/")[0]
    if kind == "feedback":
        try:
            validate_feedback(artifact)
        except InvalidFeedback:
            raise InvalidContract() from None
    else:
        validate_data(kind, artifact["data"])
    # Local invariants precede reference resolution, matching #6 error ordering.
    if kind == "trends":
        for row in artifact["data"]["items"]:
            require(monday(row["previous_week"]) == week - timedelta(days=7), "nonconsecutive_window")
    require(artifact["project"] == scope.project and artifact["week"] == scope.week, "cross_scope_reference")
    require(scope.now < expiry <= scope.closes_at + timedelta(days=14), "expired_source")

    def resolve(ref, expected=None, previous=False):
        record = scope.references.get(ref)
        require(isinstance(record, Reference), "unresolved_reference")
        expected_week = (week - timedelta(days=7)).isoformat() if previous else artifact["week"]
        require(record.project == artifact["project"] and record.week == expected_week, "cross_scope_reference")
        require(expected is None or record.kind == expected, "invalid_reference_kind")
        require(scope.now < record.expires_at and expiry <= record.expires_at, "expired_source")

    for ref in provenance["input_refs"]:
        # Only a trends candidate may carry the expressly scoped preceding aggregate.
        previous = kind == "trends" and any(ref == row["previous_aggregate"] for row in artifact["data"]["items"])
        resolve(ref, "aggregate" if previous else None, previous)
    if kind in {"manager-report", "team-summary"}:
        for key in ("themes", "trends", "issues", "evidence", "recommendations"):
            for ref in artifact["data"].get(key, []):
                resolve(ref, key)
    elif kind != "feedback":
        for row in artifact["data"]["items"]:
            for ref in row.get("support", []):
                resolve(ref, "feedback")
            for key, expected in (("theme", "themes"), ("trend", "trends"), ("issue", "issues")):
                if key in row:
                    resolve(row[key], expected)
            if "previous_aggregate" in row:
                resolve(row["previous_aggregate"], "aggregate", True)
