"""Restricted, fail-closed project-week aggregation. No identity imports or writes."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import re
from typing import Protocol

from signal_loop.contracts.analysis import Scope, validate_artifact


@dataclass(frozen=True)
class Suppressed:
    # All failure causes have the same safe representation, including repr().
    status: str = field(default="unavailable", init=False)


@dataclass(frozen=True)
class Assessment:
    """Trusted verifier result, never a request payload or AI assertion.

    Each source must be an independently admitted eligible natural person for
    this scope. A verifier cannot infer this from UUID uniqueness or roster size.
    """
    project: str
    week: str
    sources: frozenset[str]
    distinct_contributors: int
    admission_verified: bool
    content_safe: bool
    inference_safe: bool


class EvidenceVerifier(Protocol):
    def assess(self, *, project: str, week: str, artifacts: tuple[dict, ...]) -> Assessment: ...


@dataclass(frozen=True, repr=False)
class RestrictedAnalysisInput:
    """In-process container of exact #6 feedback/1.0 envelopes, not a new schema.

    Do not serialize to views. Counts and source references remain restricted.
    There is deliberately no publication-ready flag or audience projection.
    """
    project: str
    week: str
    expires_at: datetime
    distinct_contributors: int
    _artifacts: tuple[dict, ...] = field(repr=False)

    def __repr__(self):
        return "RestrictedAnalysisInput(<restricted>)"

    def feedback_for_analysis(self):
        return deepcopy(self._artifacts)


def aggregate(*, project, week, artifacts, closes_at, at, verifier=None, threshold=5):
    """Accept only closed, unexpired, validated input with trusted scoped proof.

    The verifier is server-injected infrastructure, not caller-provided JSON.
    No production verifier exists yet: absence always suppresses. No exception
    diagnostics, source text, counts or identities escape a failure response.
    """
    try:
        if (not isinstance(project, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", project)
                or not isinstance(week, str) or date.fromisoformat(week).isoformat() != week
                or date.fromisoformat(week).weekday() != 0
                or type(threshold) is not int or not 5 <= threshold <= 10000
                or not isinstance(at, datetime) or at.utcoffset() is None
                or not isinstance(closes_at, datetime) or closes_at.utcoffset() is None
                or at < closes_at or at >= closes_at + timedelta(days=14)
                or not isinstance(artifacts, (tuple, list)) or not 1 <= len(artifacts) <= 10000
                or verifier is None):
            return Suppressed()
        inputs = deepcopy(tuple(artifacts))
        sources = set()
        expiries = []
        scope = Scope(project, week, closes_at, at)
        for artifact in inputs:
            validate_artifact(artifact, scope)
            if artifact["schema"] != "feedback/1.0":
                return Suppressed()
            source = artifact["data"]["source"]
            if source in sources:
                return Suppressed()
            sources.add(source)
            expiry = datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
            if not at < expiry <= closes_at + timedelta(days=14):
                return Suppressed()
            # Persistence sources have no upstream references. Accepting arbitrary
            # refs here would permit an unresolved or cross-project correlation.
            if artifact["provenance"]["input_refs"]:
                return Suppressed()
            expiries.append(expiry)
        proof = verifier.assess(project=project, week=week, artifacts=deepcopy(inputs))
        if (type(proof) is not Assessment or proof.project != project or proof.week != week
                or type(proof.sources) is not frozenset or proof.sources != frozenset(sources)
                or type(proof.distinct_contributors) is not int
                or proof.distinct_contributors != len(sources)
                or proof.distinct_contributors < threshold
                or proof.admission_verified is not True
                or proof.content_safe is not True or proof.inference_safe is not True):
            return Suppressed()
        return RestrictedAnalysisInput(project, week, min(expiries), proof.distinct_contributors, inputs)
    except Exception:
        return Suppressed()


def aggregate_stored(*, project_id, week, at, verifier=None, threshold=5):
    """Persistence handoff: public schedule facts plus same-scope anonymous rows.

    #24/#33 must freeze the input set at closure using the shared window lock;
    this read-only service neither publishes nor revises a frozen aggregate.
    """
    from signal_loop.feedback.models import FeedbackSection
    from signal_loop.windows.services import project_week_scope

    try:
        if type(project_id) is not int or project_id <= 0 or type(week) is not date:
            return Suppressed()
        scope = project_week_scope(project_id=project_id, week=week)
        if scope is None:
            return Suppressed()
        rows = FeedbackSection.objects.filter(project_id=project_id, week=week).order_by("id")[:10001]
        return aggregate(project=str(project_id), week=week.isoformat(),
                         artifacts=[row.as_artifact() for row in rows], closes_at=scope.closes_at,
                         at=at, verifier=verifier, threshold=threshold)
    except Exception:
        return Suppressed()
