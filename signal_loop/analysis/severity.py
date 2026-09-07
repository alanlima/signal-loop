"""Pure, restricted project-issue severity; no employee scoring or release."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from signal_loop.contracts.analysis import Reference, Scope, validate_artifact
from signal_loop.contracts.validation import enum, identifier, require, utc_time

from .aggregation import RestrictedAnalysisInput
from .themes import ConservativeGrounding, RestrictedThemes
from .trends import RestrictedTrends, WeeklyHistory, compare_weeks


RULE_VERSION = "severity/1.0"
IMPACT = {
    "none": (0, "No project impact is expected."),
    "localized": (1, "A localized project process is affected."),
    "project_delivery": (2, "Project delivery is affected."),
    "project_objective": (3, "The project objective is at risk."),
}
URGENCY = {
    "none": (0, "No action is currently needed."),
    "next_window": (1, "Action is needed next week."),
    "current_window": (2, "Action is needed this week."),
    "immediate": (3, "Action is needed immediately."),
}


@dataclass(frozen=True, repr=False)
class Estimate:
    value: str | None
    origin: str = "model_estimated"


@dataclass(frozen=True, repr=False)
class IssueCandidate:
    id: str
    theme: str
    category: str
    impact: Estimate | None
    urgency: Estimate | None


@dataclass(frozen=True, repr=False)
class SeverityHistory:
    previous: WeeklyHistory
    current: WeeklyHistory
    reviewer: object = field(repr=False)


@dataclass(frozen=True, repr=False)
class Factor:
    name: str
    value: object
    points: int
    weight: int
    origin: str


@dataclass(frozen=True, repr=False)
class Calculation:
    issue_id: str
    severity: str
    score: int
    factors: tuple[Factor, ...]
    explanation: str


@dataclass(frozen=True, repr=False)
class Unscored:
    issue_id: str | None
    reason: str


@dataclass(frozen=True, repr=False)
class IssuesSourceContext:
    eligible: RestrictedAnalysisInput
    themes: RestrictedThemes
    trends: RestrictedTrends | None
    references: dict[str, Reference] = field(repr=False)


@dataclass(frozen=True, repr=False)
class RestrictedIssues:
    _artifact: dict = field(repr=False)
    _source_context: IssuesSourceContext = field(repr=False)

    def __repr__(self):
        return "RestrictedIssues(<restricted>)"

    def artifact_for_analysis(self):
        return deepcopy(self._artifact)

    def source_context_for_analysis(self):
        return deepcopy(self._source_context)


@dataclass(frozen=True, repr=False)
class SeverityAssessment:
    issues: RestrictedIssues | None = None
    calculations: tuple[Calculation, ...] = field(default=(), repr=False)
    unscored: tuple[Unscored, ...] = field(default=(), repr=False)
    failure: str | None = None
    rule_version: str = field(default=RULE_VERSION, init=False)

    def __repr__(self):
        return "SeverityAssessment(<restricted>)"

    def public_status(self):
        return {"status": "unavailable"}


def factor_points(*, support, contributors, direction, persistence, impact, urgency):
    """The documented pure arithmetic rule, not an eligibility/scoring grant.

    Supports table-driven rule-boundary fixtures independently of history gates.
    Production callers use score_issues, which derives and proves these inputs.
    """
    require(type(support) is int and type(contributors) is int and 1 <= support <= contributors <= 10000)
    enum(direction, {"improving", "persisting", "worsening"})
    require(type(persistence) is int and persistence in {0, 1})
    enum(impact, set(IMPACT))
    enum(urgency, set(URGENCY))
    frequency = 0 if 100 * support < 25 * contributors else 1 if 100 * support < 50 * contributors else 2
    distinct = 0 if support < 5 else 1 if support < 10 else 2
    return (frequency, distinct, {"improving": 0, "persisting": 1, "worsening": 2}[direction],
            persistence, IMPACT[impact][0], URGENCY[urgency][0])


def severity_level(score):
    require(type(score) is int and 0 <= score <= 19)
    return "low" if score <= 4 else "moderate" if score <= 9 else "high" if score <= 14 else "critical"


def _inputs(eligible, themes, at, closes_at):
    require(type(eligible) is RestrictedAnalysisInput and type(themes) is RestrictedThemes)
    require(isinstance(at, datetime) and at.utcoffset() is not None)
    require(isinstance(closes_at, datetime) and closes_at.utcoffset() is not None)
    require(closes_at <= at < eligible.expires_at <= closes_at + timedelta(days=14))
    feedback = eligible.feedback_for_analysis()
    require(type(eligible.distinct_contributors) is int and 5 <= eligible.distinct_contributors == len(feedback) <= 10000)
    scope = Scope(eligible.project, eligible.week, closes_at, at)
    sources, registry = {}, {}
    for artifact in feedback:
        validate_artifact(artifact, scope)
        require(artifact["schema"] == "feedback/1.0" and not artifact["provenance"]["input_refs"])
        key = artifact["data"]["source"]
        require(key not in registry)
        sources[key] = artifact
        registry[key] = Reference("feedback", eligible.project, eligible.week, utc_time(artifact["expires_at"]))
    require(eligible.expires_at == min(ref.expires_at for ref in registry.values()))
    envelope = themes.artifact_for_analysis()
    validate_artifact(envelope, Scope(eligible.project, eligible.week, closes_at, at, registry))
    require(envelope["schema"] == "themes/1.0" and utc_time(envelope["expires_at"]) <= eligible.expires_at)
    by_id = {}
    for theme in envelope["data"]["items"]:
        require(theme["id"] not in registry)
        by_id[theme["id"]] = theme
        registry[theme["id"]] = Reference("themes", eligible.project, eligible.week, utc_time(envelope["expires_at"]))
    return sources, by_id, registry, utc_time(envelope["expires_at"])


def _estimate(candidate, catalog, sources):
    if candidate is None:
        return False
    require(type(candidate) is Estimate)
    enum(candidate.origin, {"model_estimated", "synthetic_estimate"})
    if candidate.value is None:
        return False
    enum(candidate.value, set(catalog))
    statement = catalog[candidate.value][1]
    # Every supporter of this issue must support each estimated factual clause.
    # Exact WHOLE field comparison never drops qualifiers, negation or context.
    return all(statement in (source["data"].get("note"), source["data"].get("follow_up", {}).get("answer"))
               for source in sources)


def score_issues(*, eligible, themes, candidates, at, closes_at, history=None, version=RULE_VERSION):
    """Score proven factors only; uncertainties never become a severity default.

    All inputs are trusted in-process handoffs; this is not a client JSON API.
    No provider calls are made. Estimates are claims, grounded locally before
    calculation. Unscored candidates have no canonical issue or resolvable ID.
    """
    try:
        require(version == RULE_VERSION)
        eligible, themes = deepcopy(eligible), deepcopy(themes)
        sources, theme_rows, registry, expiry = _inputs(eligible, themes, at, closes_at)
        require(type(candidates) in {tuple, list} and len(candidates) <= 50)
        candidates = deepcopy(candidates)
        ids = set()
        for candidate in candidates:
            require(type(candidate) is IssueCandidate)
            identifier(candidate.id)
            identifier(candidate.theme)
            enum(candidate.category, {"delivery", "workload", "collaboration", "recurring_concern"})
            require(candidate.id not in ids and candidate.id not in registry)
            ids.add(candidate.id)
    except Exception:
        return SeverityAssessment(failure="invalid_input")

    trend_result, trend_rows = None, []
    if history is not None:
        try:
            require(type(history) is SeverityHistory)
            require(history.current.eligible == eligible and history.current.themes == themes
                    and history.current.closes_at == closes_at)
            trend_result = compare_weeks(previous=history.previous, current=history.current, at=at, reviewer=history.reviewer)
            if isinstance(trend_result, RestrictedTrends):
                trend_artifact = trend_result.artifact_for_analysis()
                expiry = min(expiry, utc_time(trend_artifact["expires_at"]))
                trend_rows = trend_artifact["data"]["items"]
                previous = history.previous
                require(previous.aggregate_ref not in registry and previous.aggregate_ref not in ids)
                registry[previous.aggregate_ref] = Reference("aggregate", eligible.project, previous.eligible.week,
                                                              previous.eligible.expires_at)
                for trend in trend_rows:
                    require(trend["id"] not in registry and trend["id"] not in ids)
                    registry[trend["id"]] = Reference("trends", eligible.project, eligible.week,
                                                       utc_time(trend_artifact["expires_at"]))
        except Exception:
            return SeverityAssessment(failure="invalid_history")

    calculations, unscored, rows = [], [], []
    grounder = ConservativeGrounding()
    for candidate in candidates:
        try:
            require(candidate.theme in theme_rows)
            theme = theme_rows[candidate.theme]
            require(theme.get("category") in {"delivery", "workload", "collaboration"})
            require(candidate.category in {theme["category"], "recurring_concern"})
            cited = tuple(sources[ref] for ref in theme["support"])
            evidence = grounder.assess(statement=theme["statement"], category=theme.get("category"), artifacts=cited)
            require(evidence.supported_sources == frozenset(theme["support"]))
            require(theme["distinct_support"] == len(evidence.supported_sources))
            impact_known = _estimate(candidate.impact, IMPACT, cited)
            urgency_known = _estimate(candidate.urgency, URGENCY, cited)
            if not impact_known or not urgency_known:
                unscored.append(Unscored(candidate.id, "insufficient_estimate_evidence"))
                continue
            temporal = [row for row in trend_rows if row["theme"] == candidate.theme]
            recurring = [row for row in temporal if row["statement"].endswith(" recurs across consecutive weeks.")]
            movement = [row for row in temporal if row not in recurring]
            if len(recurring) != 1 or len(movement) != 1:
                # #27 currently proves two-week recurrence, not isolated absence.
                # Missing/suppressed history cannot be treated as zero persistence.
                unscored.append(Unscored(candidate.id, "insufficient_history"))
                continue
            trend = movement[0]
            require(all(row["comparison_safe"] is True and row["current_support"] == theme["distinct_support"]
                        for row in temporal))
            values = (len(cited), eligible.distinct_contributors, trend["direction"], 1,
                      candidate.impact.value, candidate.urgency.value)
            points = factor_points(support=values[0], contributors=values[1], direction=values[2],
                                   persistence=values[3], impact=values[4], urgency=values[5])
            factors = tuple(Factor(name, value, point, weight, origin) for name, value, point, weight, origin in zip(
                ("frequency", "distinct_support", "trend", "persistence", "impact", "urgency"),
                ((values[0], values[1]), values[0], values[2], values[3], values[4], values[5]), points,
                (1, 1, 1, 1, 2, 2), ("calculated", "calculated", "calculated", "calculated",
                                      candidate.impact.origin, candidate.urgency.origin), strict=True))
            score = sum(factor.points * factor.weight for factor in factors)
            level = severity_level(score)
            explanation = (f"Project issue severity is {level} under {RULE_VERSION}. "
                           f"Calculated frequency is {values[0]}/{values[1]}, verified support is {values[0]}, "
                           f"trend is {values[2]}, and the concern recurs across two consecutive weeks. "
                           f"Grounded estimated impact: {IMPACT[values[4]][1]} "
                           f"Grounded estimated urgency: {URGENCY[values[5]][1]} "
                           f"Weighted score: {score}/19. This restricted calculation is not publication approval.")
            rows.append({"id": candidate.id, "theme": candidate.theme, "category": candidate.category,
                         "severity": level, "explanation": explanation, "support": list(theme["support"]),
                         "trend": trend["id"]})
            calculations.append(Calculation(candidate.id, level, score, factors, explanation))
        except Exception:
            unscored.append(Unscored(candidate.id, "invalid_input"))
    if not rows:
        return SeverityAssessment(unscored=tuple(unscored))
    artifact = {"schema": "issues/1.0", "project": eligible.project, "week": eligible.week, "privacy_policy": "1.0",
                "expires_at": expiry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "provenance": {"producer": "severity", "producer_version": "1.0",
                               "input_refs": list(dict.fromkeys(ref for row in rows for ref in (row["theme"], row["trend"])))},
                "data": {"items": rows}}
    try:
        validate_artifact(artifact, Scope(eligible.project, eligible.week, closes_at, at, registry))
        for row in rows:
            registry[row["id"]] = Reference("issues", eligible.project, eligible.week, expiry)
        context = IssuesSourceContext(eligible, themes,
                                      trend_result if isinstance(trend_result, RestrictedTrends) else None, registry)
        return SeverityAssessment(RestrictedIssues(artifact, context), tuple(calculations), tuple(unscored))
    except Exception:
        return SeverityAssessment(failure="invalid_output")
