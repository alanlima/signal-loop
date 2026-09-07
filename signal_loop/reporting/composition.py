"""Pure manager composition: strict source grounding and joint audience review."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from signal_loop.analysis.evidence import JointContext, LABEL, RULES
from signal_loop.analysis.recommendations import (
    ACTIONS, RestrictedRecommendations, _joint_safe,
)
from signal_loop.analysis.severity import IMPACT, URGENCY, factor_points, severity_level
from signal_loop.analysis.themes import ConservativeGrounding
from signal_loop.analysis.trends import TOPICS
from signal_loop.contracts.analysis import Scope, validate_artifact
from signal_loop.contracts.validation import fields, require, utc_time


IMPACT_TEXT = {"none": "No effect on the project is anticipated.",
               "localized": "The effect is limited to a project process.",
               "project_delivery": "The project's delivery is experiencing an effect.",
               "project_objective": "The project's objective could be jeopardized."}
URGENCY_TEXT = {"none": "There is no current need for action.",
                "next_window": "A response is needed in the coming week.",
                "current_window": "A response is needed during this week.",
                "immediate": "A response is needed without delay."}


@dataclass(frozen=True, repr=False)
class PublicationContext:
    """Trusted inventory plus exact independently composed team candidate.

    No approval booleans. #32 supplies its own candidate; unknown means withhold.
    """
    joint_context: JointContext
    team_content: dict = field(repr=False)


@dataclass(frozen=True, repr=False)
class PreparedManager:
    state: str
    artifact: dict | None = field(default=None, repr=False)
    content: dict | None = field(default=None, repr=False)
    context: PublicationContext | None = field(default=None, repr=False)
    expires_at: datetime | None = None


def _team_safe(content, manager, actions):
    fields(content, {"title", "overview", "themes", "trends", "next_week_focus", "commitments"})
    require(content["title"] == "Weekly project summary")
    require(content["overview"] in manager["themes"])
    for key, allowed in (("themes", manager["themes"]), ("trends", manager["trends"]),
                         ("next_week_focus", actions)):
        require(type(content[key]) is list and len(content[key]) <= (10 if key == "next_week_focus" else 50))
        require(all(type(text) is str and text in allowed for text in content[key]))
    require(content["themes"] and content["commitments"] == [])
    # #36 has no approved-commitment handoff yet. An asserted approval flag cannot
    # invent it. #32 can add the independently validated commitment boundary.


def prepare_manager(recommendations, *, project, week, version, closes_at, at, context_provider):
    """Snapshot once; no ORM, provider model call, identity lookup or persistence."""
    if recommendations is None or context_provider is None:
        return PreparedManager("suppressed")
    try:
        require(type(recommendations) is RestrictedRecommendations)
        recommendations = deepcopy(recommendations)
        lineage = recommendations.source_context_for_analysis()
        issues = lineage.issues.artifact_for_analysis()
        evidence = lineage.evidence.artifact_for_analysis()
        require(lineage.evidence.source_context_for_analysis().issues == lineage.issues)
        require(lineage.evidence.source_context_for_analysis().joint_context == lineage.joint_context)
        inputs = lineage.issues.source_context_for_analysis()
        eligible = inputs.eligible
        require((eligible.project, eligible.week) == (project, week))
        require(closes_at <= at < eligible.expires_at)
        sources = eligible.feedback_for_analysis()
        require(type(eligible.distinct_contributors) is int and 5 <= eligible.distinct_contributors == len(sources))
        source_rows = {}
        for source in sources:
            validate_artifact(source, Scope(project, week, closes_at, at))
            require(source["schema"] == "feedback/1.0" and not source["provenance"]["input_refs"])
            ref = source["data"]["source"]
            require(ref not in source_rows)
            source_rows[ref] = source
        require(eligible.expires_at == min(utc_time(row["expires_at"]) for row in sources))
        themes = inputs.themes.artifact_for_analysis()
        trends = inputs.trends.artifact_for_analysis() if inputs.trends is not None else None
        proposed = recommendations.artifact_for_analysis()
        artifacts = [themes, issues, evidence, proposed] + ([trends] if trends is not None else [])
        kinds = ["themes", "issues", "evidence", "recommendations"] + (["trends"] if trends is not None else [])
        registry = lineage.references
        scope = Scope(project, week, closes_at, at, registry)
        seen = set(source_rows)
        for artifact, kind in zip(artifacts, kinds, strict=True):
            validate_artifact(artifact, scope)
            require(artifact["schema"] == f"{kind}/1.0")
            for row in artifact["data"]["items"]:
                ref = row["id"]
                require(ref not in seen and registry[ref].kind == kind)
                require((registry[ref].project, registry[ref].week) == (project, week))
                require(registry[ref].expires_at <= utc_time(artifact["expires_at"]))
                seen.add(ref)
        expiry = min(eligible.expires_at, *(utc_time(row["expires_at"]) for row in artifacts))
        theme_rows = {row["id"]: row for row in themes["data"]["items"]}
        issue_rows = {row["id"]: row for row in issues["data"]["items"]}
        rules = {}
        grounder = ConservativeGrounding()
        for ref, theme in theme_rows.items():
            rule = next((rule for rule in RULES if (rule.theme, rule.category) ==
                         (theme["statement"], theme.get("category"))), None)
            require(rule is not None and len(theme["support"]) >= 5)
            require(theme["distinct_support"] == len(theme["support"]))
            proof = grounder.assess(statement=rule.theme, category=rule.category,
                                    artifacts=tuple(source_rows[ref] for ref in theme["support"]))
            require(proof.supported_sources == frozenset(theme["support"]))
            rules[ref] = rule
        if not theme_rows or not issue_rows or not proposed["data"]["items"] or not evidence["data"]["items"]:
            return PreparedManager("suppressed", expires_at=expiry)
        calculations = {calculation.issue_id: calculation for calculation in lineage.calculations}
        require(set(calculations) == set(issue_rows) and len(calculations) == len(lineage.calculations))
        display_issues = []
        for ref, issue in issue_rows.items():
            support = set(issue["support"])
            require(len(support) >= 5 and support <= set(theme_rows[issue["theme"]]["support"]))
            calculation = calculations[ref]
            require(calculation.severity == issue["severity"] and calculation.explanation == issue["explanation"])
            factors = calculation.factors
            require(type(factors) is tuple and len(factors) == 6)
            require(all(type(f.points) is int and type(f.weight) is int for f in factors))
            require(tuple(f.name for f in factors) == ("frequency", "distinct_support", "trend", "persistence", "impact", "urgency"))
            require(tuple(f.weight for f in factors) == (1, 1, 1, 1, 2, 2))
            require(factors[0].value == (len(support), len(sources)) and factors[1].value == len(support))
            require(type(factors[1].value) is int and type(factors[3].value) is int and factors[3].value == 1)
            require(trends is not None and any(row["id"] == issue.get("trend") and row["direction"] == factors[2].value
                                               for row in trends["data"]["items"]))
            points = factor_points(support=len(support), contributors=len(sources), direction=factors[2].value,
                                   persistence=factors[3].value, impact=factors[4].value, urgency=factors[5].value)
            require(tuple(f.points for f in factors) == points)
            require(calculation.score == sum(p * f.weight for p, f in zip(points, factors, strict=True)))
            require(severity_level(calculation.score) == issue["severity"])
            clauses = [IMPACT[factors[4].value][1], URGENCY[factors[5].value][1]]
            for source_ref in support:
                data = source_rows[source_ref]["data"]
                require(all(clause in (data.get("note"), data.get("follow_up", {}).get("answer")) for clause in clauses))
            # Numeric scoring explanations are restricted. Display uses only
            # independently supported generic clauses, never counts or scores.
            display_issues.append({"severity": issue["severity"],
                                   "explanation": " ".join([rules[issue["theme"]].paraphrase,
                                       IMPACT_TEXT[factors[4].value], URGENCY_TEXT[factors[5].value]])})
        evidence_rows = {}
        for row in evidence["data"]["items"]:
            issue = issue_rows[row["issue"]]
            rule = rules[issue["theme"]]
            require(row["grounded"] is True and row["text"] == getattr(rule, row["form"]))
            support = frozenset(row["support"])
            require(len(support) >= 5 and support <= set(issue["support"]))
            require(grounder.assess(statement=rule.theme, category=rule.category,
                                   artifacts=tuple(source_rows[ref] for ref in support)).supported_sources == support)
            require(not any(row["text"] in text for source in sources for text in (
                source["data"].get("note", ""), source["data"].get("follow_up", {}).get("answer", ""))))
            evidence_rows[row["id"]] = row
        display_recommendations, team_actions = [], []
        for row in proposed["data"]["items"]:
            issue = issue_rows[row["issue"]]
            rule = rules[issue["theme"]]
            require(row["action"] == ACTIONS[rule.theme] and type(row.get("suggest_for_team")) is bool)
            require(any(item["issue"] == row["issue"] and set(row["support"]) <= set(item["support"])
                        and row["rationale"] == (item["text"] if item["form"] == "paraphrase"
                            else f"{LABEL} (hypothetical): {item['text']}") for item in evidence_rows.values()))
            display_recommendations.append({"action": row["action"], "rationale": row["rationale"]})
            if row["suggest_for_team"]:
                team_actions.append(row["action"])
        display_trends = []
        for row in trends["data"]["items"] if trends is not None else ():
            require(row["comparison_safe"] is True and row["theme"] in rules)
            require(row["current_support"] == len(theme_rows[row["theme"]]["support"]))
            topic = next(topic for topic in TOPICS if rules[row["theme"]].theme in topic.statements)
            movement = {"persisting": "has stable prevalence", "improving": "is recovering", "worsening": "is worsening"}[row["direction"]]
            allowed = {f"{topic.label} {movement} across consecutive weeks."}
            if row["direction"] == "persisting":
                allowed.add(f"{topic.label} recurs across consecutive weeks.")
            require(row["statement"] in allowed)
            qualitative = {"persisting": "persists", "improving": "is improving", "worsening": "is worsening"}[row["direction"]]
            text = f"{topic.label} {qualitative} across consecutive weeks."
            if text not in display_trends:
                display_trends.append(text)
        display_themes = [rules[ref].paraphrase for ref in theme_rows]
        content = {"title": "Weekly project report", "overview": display_themes[0], "themes": display_themes,
                   "issues": display_issues, "trends": display_trends, "evidence": lineage.evidence.public_items(),
                   "recommendations": display_recommendations}
        # The no-excerpt rule applies to all displayed clauses, including generated
        # severity explanations and overview, not only evidence rows.
        displayed = [content["overview"], *display_themes, *display_trends,
                     *(row["explanation"] for row in display_issues),
                     *(row["text"] for row in content["evidence"]),
                     *(row["rationale"] for row in display_recommendations)]
        passages = [text for source in sources for text in (source["data"].get("note", ""),
                    source["data"].get("follow_up", {}).get("answer", "")) if text]
        require(not any(text in passage or passage in text for text in displayed for passage in passages))
        context = deepcopy(context_provider.load(project=project, week=week))
        require(type(context) is PublicationContext and context.joint_context == lineage.joint_context)
        _joint_safe(context.joint_context, project=project, week=week, sources=sources)
        _team_safe(context.team_content, content, team_actions)
        require(context_provider.load(project=project, week=week) == context)
        artifact = {"schema": "manager-report/1.0", "project": project, "week": week, "privacy_policy": "1.0",
                    "expires_at": expiry.isoformat().replace("+00:00", "Z"),
                    "provenance": {"producer": "manager-composer", "producer_version": version, "input_refs": []},
                    "data": {"title": content["title"], "overview": content["overview"],
                             **{key: [row["id"] for row in value["data"]["items"]] for key, value in
                                (("themes", themes), ("issues", issues), ("evidence", evidence), ("recommendations", proposed))},
                             "trends": [row["id"] for row in trends["data"]["items"]] if trends is not None else []}}
        validate_artifact(artifact, scope)
        return PreparedManager("ready", artifact, content, context, expiry)
    except Exception:
        return PreparedManager("failed", expires_at=closes_at + timedelta(days=14))
