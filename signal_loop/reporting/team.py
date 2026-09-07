"""Independent team composition; restricted references never become reader JSON."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from time import monotonic

from django.db import transaction

from signal_loop.analysis.aggregation import RestrictedAnalysisInput
from signal_loop.analysis.evidence import JointContext, RULES
from signal_loop.analysis.recommendations import ACTIONS, RestrictedRecommendations, _joint_safe
from signal_loop.analysis.themes import ConservativeGrounding, RestrictedThemes
from signal_loop.analysis.trends import TOPICS, RestrictedTrends, compare_weeks
from signal_loop.contracts.analysis import Reference, Scope, validate_artifact
from signal_loop.contracts.validation import identifier, monday, require, string, utc_time
from .composition import PublicationContext, prepare_manager
from .models import AudienceRelease, TeamSummary
from .projections import validate_content
from .services import CompositionResult, lock_project_week, publish_locked


TEAM_WORDS = {(rule.theme, rule.category): rule.paraphrase for rule in RULES} | {
    ("The team completed the shared milestone.", "wins"): "Completion of a shared project milestone was reported.",
    ("We need help with the shared backlog.", "support"): "Help is needed with a shared backlog.",
}


@dataclass(frozen=True, repr=False)
class TeamInput:
    eligible: RestrictedAnalysisInput
    themes: RestrictedThemes
    recommendations: RestrictedRecommendations | None = None
    history: object | None = None  # #28 SeverityHistory: previous/current/reviewer


@dataclass(frozen=True, repr=False)
class TeamPublicationContext:
    """Trusted complete inventory, with explicit absent or reviewable manager.

    Absence is supplied by the server inventory, never inferred from missing data.
    A present manager carries its actual #30 lineage and #31 context snapshot.
    """
    joint_context: JointContext
    manager_recommendations: RestrictedRecommendations | None
    manager_context: PublicationContext | None


@dataclass(frozen=True)
class PublishedCommitment:
    """Trusted #36 fixture handoff: already published, not an approval request."""
    project: str
    week: str
    text: str
    published_at: datetime
    expires_at: datetime


@dataclass(frozen=True, repr=False)
class PreparedTeam:
    state: str
    artifact: dict | None = field(default=None, repr=False)
    content: dict | None = field(default=None, repr=False)
    context: TeamPublicationContext | None = field(default=None, repr=False)
    manager_content: dict | None = field(default=None, repr=False)
    expires_at: datetime | None = None
    commitments: tuple = field(default=(), repr=False)


def prepare_team(inputs, *, project, week, version, closes_at, at, context_provider=None,
                 commitment_provider=None):
    if inputs is None or context_provider is None:
        return PreparedTeam("suppressed")
    try:
        require(type(inputs) is TeamInput)
        inputs = deepcopy(inputs)
        eligible, themes = inputs.eligible, inputs.themes
        require(type(eligible) is RestrictedAnalysisInput and type(themes) is RestrictedThemes)
        require((eligible.project, eligible.week) == (project, week))
        require(closes_at <= at < eligible.expires_at <= closes_at + timedelta(days=14))
        sources = eligible.feedback_for_analysis()
        require(type(eligible.distinct_contributors) is int and 5 <= eligible.distinct_contributors == len(sources))
        registry, by_source = {}, {}
        for source in sources:
            validate_artifact(source, Scope(project, week, closes_at, at))
            require(source["schema"] == "feedback/1.0" and source["provenance"]["input_refs"] == [])
            ref = source["data"]["source"]
            require(ref not in registry)
            registry[ref] = Reference("feedback", project, week, utc_time(source["expires_at"]))
            by_source[ref] = source
        require(eligible.expires_at == min(ref.expires_at for ref in registry.values()))
        artifact = themes.artifact_for_analysis()
        validate_artifact(artifact, Scope(project, week, closes_at, at, registry))
        require(artifact["schema"] == "themes/1.0")
        expiry = min(eligible.expires_at, utc_time(artifact["expires_at"]))
        rows, words = {}, []
        grounder = ConservativeGrounding()
        for row in artifact["data"]["items"]:
            ref, support = row["id"], frozenset(row["support"])
            require(ref not in registry and len(support) >= 5 and row["distinct_support"] == len(support))
            word = TEAM_WORDS[(row["statement"], row.get("category"))]
            require(grounder.assess(statement=row["statement"], category=row.get("category"),
                artifacts=tuple(by_source[key] for key in support)).supported_sources == support)
            registry[ref] = Reference("themes", project, week, expiry)
            rows[ref] = row
            words.append(word)
        if not words:
            return PreparedTeam("suppressed", expires_at=expiry)
        trend_refs, trend_words = [], []
        if inputs.history is not None:
            history = inputs.history
            require(history.current.eligible == eligible and history.current.themes == themes)
            trends = compare_weeks(previous=history.previous, current=history.current, at=at, reviewer=history.reviewer)
            require(type(trends) is RestrictedTrends)
            trend_artifact = trends.artifact_for_analysis()
            expiry = min(expiry, utc_time(trend_artifact["expires_at"]))
            for trend in trend_artifact["data"]["items"]:
                require(trend["theme"] in rows and trend["id"] not in registry)
                topic = next(topic for topic in TOPICS if rows[trend["theme"]]["statement"] in topic.statements)
                movement = {"persisting": "persists", "improving": "is improving", "worsening": "is worsening"}[trend["direction"]]
                text = f"{topic.label} {movement} across consecutive weeks."
                if text not in trend_words:
                    trend_words.append(text)
                trend_refs.append(trend["id"])
                registry[trend["id"]] = Reference("trends", project, week, expiry)
        focus = []
        if inputs.recommendations is not None:
            require(type(inputs.recommendations) is RestrictedRecommendations)
            recs = inputs.recommendations.artifact_for_analysis()
            lineage = inputs.recommendations.source_context_for_analysis()
            require(lineage.issues.source_context_for_analysis().eligible == eligible)
            validate_artifact(recs, Scope(project, week, closes_at, at, lineage.references))
            require(recs["schema"] == "recommendations/1.0")
            issues = {row["id"]: row for row in lineage.issues.artifact_for_analysis()["data"]["items"]}
            for rec in recs["data"]["items"]:
                require(type(rec.get("suggest_for_team")) is bool)
                if not rec["suggest_for_team"]:
                    continue
                theme = rows[issues[rec["issue"]]["theme"]]
                require(len(rec["support"]) >= 5 and set(rec["support"]) <= set(theme["support"]))
                require(rec["action"] == ACTIONS[theme["statement"]])
                if rec["action"] not in focus:
                    focus.append(rec["action"])
            if focus:
                expiry = min(expiry, utc_time(recs["expires_at"]))
        published = () if commitment_provider is None else deepcopy(commitment_provider.published_for(project=project, week=week))
        require(type(published) is tuple and len(published) <= 10)
        allowed_actions = {ACTIONS[row["statement"]] for row in rows.values() if row["statement"] in ACTIONS}
        for commitment in published:
            require(type(commitment) is PublishedCommitment and (commitment.project, commitment.week) == (project, week))
            require(commitment.published_at <= at < commitment.expires_at and commitment.text in allowed_actions)
            expiry = min(expiry, commitment.expires_at)
        content = {"title": "Weekly project summary", "overview": words[0], "themes": words,
                   "trends": trend_words, "next_week_focus": focus, "commitments": [item.text for item in published]}
        validate_content(content, "team")
        passages = [text for source in sources for text in (source["data"].get("note", ""),
                    source["data"].get("follow_up", {}).get("answer", "")) if text]
        require(not any(text in passage or passage in text for text in [*words, *trend_words] for passage in passages))
        context = deepcopy(context_provider.load(project=project, week=week))
        require(type(context) is TeamPublicationContext)
        _joint_safe(context.joint_context, project=project, week=week, sources=sources)
        manager_content = None
        if context.manager_recommendations is None:
            require(context.manager_context is None)
        else:
            require(type(context.manager_context) is PublicationContext)
            class ManagerContext:
                def load(self, **kwargs):
                    return deepcopy(context.manager_context)

            manager = prepare_manager(context.manager_recommendations, project=project, week=week, version=version,
                                      closes_at=closes_at, at=at, context_provider=ManagerContext())
            require(manager.state == "ready" and manager.context.joint_context == context.joint_context)
            require(context.manager_recommendations.source_context_for_analysis().issues.source_context_for_analysis().eligible == eligible)
            manager_content = manager.content
            expiry = min(expiry, manager.expires_at)
        canonical = {"schema": "team-summary/1.0", "project": project, "week": week, "privacy_policy": "1.0",
            "expires_at": expiry.isoformat().replace("+00:00", "Z"),
            "provenance": {"producer": "team-composer", "producer_version": version, "input_refs": []},
            "data": {"title": content["title"], "overview": content["overview"], "themes": list(rows),
                     "trends": trend_refs, "next_week_focus": focus,
                     "commitments": [{"text": item.text, "approved": True} for item in published]}}
        validate_artifact(canonical, Scope(project, week, closes_at, at, registry))
        return PreparedTeam("ready", canonical, content, context, manager_content, expiry, published)
    except Exception:
        return PreparedTeam("failed", expires_at=closes_at + timedelta(days=14))


def compose_team(inputs, *, project, week, version, closes_at, at, context_provider=None, commitment_provider=None):
    identifier(project)
    monday(week)
    identifier(version)
    string(version, 32)
    require(at.utcoffset() is not None and closes_at.utcoffset() is not None)
    started = monotonic()
    with transaction.atomic():
        lock_project_week(project, week)
        release = AudienceRelease.objects.filter(project=project, week=week, audience="team").first()
        if release is not None:
            return CompositionResult("ready" if release.state == "ready" and at < release.expires_at else "suppressed")
        key = dict(project=project, week=week, analysis_version=version, schema="team-summary/1.0", privacy_policy="1.0")
        existing = TeamSummary.objects.filter(**key).first()
        if existing is not None:
            return CompositionResult(existing.state if at < existing.expires_at else "suppressed")
        prepared = prepare_team(inputs, project=project, week=week, version=version, closes_at=closes_at, at=at,
                                context_provider=context_provider, commitment_provider=commitment_provider)
        state = prepared.state
        if state == "ready":
            try:
                require(context_provider.load(project=project, week=week) == prepared.context)
                if commitment_provider is not None:
                    require(commitment_provider.published_for(project=project, week=week) == prepared.commitments)
            except Exception:
                state = "suppressed"
        instant = at + timedelta(seconds=max(0, monotonic() - started))
        counterpart = AudienceRelease.objects.filter(project=project, week=week, audience="manager").first()
        if state == "ready" and (instant >= prepared.expires_at or (counterpart is not None and
                (counterpart.state != "ready" or instant >= counterpart.expires_at or counterpart.content != prepared.manager_content))):
            state = "suppressed"
        TeamSummary(**key, state=state, artifact=prepared.artifact if state == "ready" else None,
                    expires_at=prepared.expires_at or closes_at + timedelta(days=14)).save(_validated=True)
        if state == "ready":
            expiry = min(instant + timedelta(days=365), closes_at + timedelta(days=358 if prepared.content["trends"] else 365),
                         *(item.expires_at for item in prepared.commitments))
            if counterpart is not None:
                expiry = min(expiry, counterpart.expires_at)
            publish_locked(project=project, week=week, audience="team", content=prepared.content, at=instant, expires_at=expiry)
        return CompositionResult(state)
