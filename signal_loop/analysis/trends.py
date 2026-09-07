"""Pure two-week project trend candidates; no identities, provider or publication."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from signal_loop.contracts.analysis import Reference, Scope, validate_artifact
from signal_loop.contracts.validation import identifier, require, utc_time

from .aggregation import RestrictedAnalysisInput
from .themes import ConservativeGrounding, RestrictedThemes


RULE_VERSION = "project-trends/1.0"
MINIMUM_SUPPORT = 5
CHANGE_PERCENTAGE_POINTS = 10


@dataclass(frozen=True)
class Topic:
    key: str
    dimension: str
    category: str
    label: str
    statements: tuple[str, ...]
    positive: bool = False


TOPICS = (
    Topic("shared-milestone", "sentiment", "wins", "Positive project feedback about the shared milestone",
          ("The team completed the shared milestone.", "The shared milestone was completed by the team."), True),
    Topic("workload-overload", "workload", "workload", "Reported workload overload",
          ("Workload is overloaded.",)),
    Topic("delivery-blocked", "blocker", "delivery", "Reported delivery blockers",
          ("Delivery is blocked.",)),
    Topic("review-delay", "blocker", "delivery", "Reported review delays",
          ("Review turnaround delays shared work.", "Shared work is delayed by review turnaround.")),
    Topic("handoff-coordination", "collaboration", "collaboration", "Reported handoff coordination concerns",
          ("Teams have trouble coordinating handoffs.", "Handoffs are difficult to coordinate between teams.")),
)


@dataclass(frozen=True, repr=False)
class WeeklyHistory:
    """Trusted, ephemeral #33 handoff; never deserialize client history into it."""
    aggregate_ref: str
    closes_at: datetime
    eligible: RestrictedAnalysisInput
    themes: RestrictedThemes


@dataclass(frozen=True, repr=False)
class HistoryReview:
    """Independent decision tied to exact immutable snapshot content, not IDs."""
    previous: WeeklyHistory
    current: WeeklyHistory
    original_releases_verified: bool
    membership_unchanged: bool
    participation_safe: bool
    joint_inference_safe: bool


class HistoryReviewer(Protocol):
    def assess(self, *, previous: WeeklyHistory, current: WeeklyHistory) -> HistoryReview:
        """Review exact original releases and joint context without identity joins."""


@dataclass(frozen=True)
class TrendUnavailable:
    reason: str = field(repr=False)
    status: str = field(default="unavailable", init=False)

    def public_status(self):
        return {"status": "unavailable"}


@dataclass(frozen=True, repr=False)
class RestrictedTrends:
    _artifact: dict = field(repr=False)

    def __repr__(self):
        return "RestrictedTrends(<restricted>)"

    def artifact_for_analysis(self):
        return deepcopy(self._artifact)

    def public_status(self):
        # Even successful analysis has no authority to publish a trend.
        return {"status": "unavailable"}


def _snapshot(history, at):
    require(type(history) is WeeklyHistory)
    identifier(history.aggregate_ref)
    eligible = history.eligible
    require(type(eligible) is RestrictedAnalysisInput and type(history.themes) is RestrictedThemes)
    require(history.closes_at <= at < eligible.expires_at <= history.closes_at + timedelta(days=14))
    sources = eligible.feedback_for_analysis()
    require(type(eligible.distinct_contributors) is int
            and MINIMUM_SUPPORT <= eligible.distinct_contributors == len(sources) <= 10000)
    scope = Scope(eligible.project, eligible.week, history.closes_at, at)
    registry, feedback = {}, {}
    for source in sources:
        validate_artifact(source, scope)
        require(source["schema"] == "feedback/1.0" and not source["provenance"]["input_refs"])
        key = source["data"]["source"]
        require(key not in registry)
        registry[key] = Reference("feedback", eligible.project, eligible.week, utc_time(source["expires_at"]))
        feedback[key] = source
    require(eligible.expires_at == min(row.expires_at for row in registry.values()))
    themes = history.themes.artifact_for_analysis()
    validate_artifact(themes, Scope(eligible.project, eligible.week, history.closes_at, at, registry))
    require(themes["schema"] == "themes/1.0" and utc_time(themes["expires_at"]) <= eligible.expires_at)
    matched = {}
    grounder = ConservativeGrounding()
    for theme in themes["data"]["items"]:
        require(theme["id"] not in registry)
        for topic in TOPICS:
            if theme.get("category") != topic.category or theme["statement"] not in topic.statements:
                continue
            require(topic.key not in matched)
            cited = tuple(feedback[key] for key in theme["support"])
            # Catalog aliases are explicit equivalent labels, but even a known
            # label must be grounded in THIS week's actual sources. Whole-field
            # matching preserves all context; structured facts use exact enums.
            structured = grounder.assess(statement=theme["statement"], category=topic.category, artifacts=cited)
            extracted = grounder.assess(statement=theme["statement"], category=None, artifacts=cited)
            supported = structured.supported_sources | extracted.supported_sources
            require(supported == frozenset(theme["support"]))
            require(theme["distinct_support"] == len(supported))
            matched[topic.key] = theme
    return matched, utc_time(themes["expires_at"])


def compare_weeks(*, previous, current, at, reviewer=None, version=RULE_VERSION):
    """Deterministic restricted comparison; every missing gate fails closed."""
    if previous is None or current is None:
        return TrendUnavailable("insufficient_history")
    try:
        require(version == RULE_VERSION)
        require(isinstance(at, datetime) and at.utcoffset() is not None)
        require(type(previous) is WeeklyHistory and type(current) is WeeklyHistory)
        # Work on copies so review and result cannot mutate caller history.
        previous, current = deepcopy(previous), deepcopy(current)
        require(previous.eligible.project == current.eligible.project)
        if date.fromisoformat(previous.eligible.week) + timedelta(days=7) != date.fromisoformat(current.eligible.week):
            return TrendUnavailable("gap")
        require(previous.closes_at < current.closes_at)
        require(previous.aggregate_ref != current.aggregate_ref)
        before, before_expiry = _snapshot(previous, at)
        after, after_expiry = _snapshot(current, at)
    except Exception:
        return TrendUnavailable("invalid_history")
    try:
        require(reviewer is not None)
        review = reviewer.assess(previous=deepcopy(previous), current=deepcopy(current))
        require(type(review) is HistoryReview and review.previous == previous and review.current == current)
        require(all(value is True for value in (review.original_releases_verified, review.membership_unchanged,
                                               review.participation_safe, review.joint_inference_safe)))
    except Exception:
        return TrendUnavailable("unsafe_comparison")

    expiry = min(previous.eligible.expires_at, current.eligible.expires_at, before_expiry, after_expiry)
    rows = []
    references = {previous.aggregate_ref: Reference("aggregate", previous.eligible.project,
                                                   previous.eligible.week, previous.eligible.expires_at)}
    for topic in TOPICS:
        old, new = before.get(topic.key), after.get(topic.key)
        if old is None or new is None or min(old["distinct_support"], new["distinct_support"]) < MINIMUM_SUPPORT:
            continue
        if new["id"] in references:
            return TrendUnavailable("invalid_history")
        references[new["id"]] = Reference("themes", current.eligible.project, current.eligible.week, after_expiry)
        old_total, new_total = previous.eligible.distinct_contributors, current.eligible.distinct_contributors
        # Percentage-point comparison without floats or rounding at the boundary.
        delta = 100 * (new["distinct_support"] * old_total - old["distinct_support"] * new_total)
        boundary = CHANGE_PERCENTAGE_POINTS * old_total * new_total
        direction = "persisting"
        if abs(delta) >= boundary:
            improves = (delta > 0) if topic.positive else (delta < 0)
            direction = "improving" if improves else "worsening"
        movement = {"persisting": "has stable prevalence", "improving": "is recovering",
                    "worsening": "is worsening"}[direction]
        if topic.positive and direction == "improving":
            movement = "is improving"
        row = {"id": f"trend_{len(rows) + 1}", "theme": new["id"], "previous_week": previous.eligible.week,
               "previous_aggregate": previous.aggregate_ref, "direction": direction,
               "statement": f"{topic.label} {movement} across consecutive weeks.",
               "current_support": new["distinct_support"], "previous_support": old["distinct_support"],
               "comparison_safe": True}
        rows.append(row)
        if not topic.positive:
            rows.append({**row, "id": f"trend_{len(rows) + 1}", "direction": "persisting",
                         "statement": f"{topic.label} recurs across consecutive weeks."})
    if not rows:
        return TrendUnavailable("insufficient_supported_history")
    artifact = {"schema": "trends/1.0", "project": current.eligible.project, "week": current.eligible.week,
                "privacy_policy": "1.0", "expires_at": expiry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "provenance": {"producer": "project-trends", "producer_version": "1.0", "input_refs": list(references)},
                "data": {"items": rows}}
    try:
        validate_artifact(artifact, Scope(current.eligible.project, current.eligible.week,
                                          current.closes_at, at, references))
    except Exception:
        return TrendUnavailable("invalid_history")
    return RestrictedTrends(artifact)
