"""Atomic candidate composition and first immutable audience release."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
import hashlib
from time import monotonic

from django.db import connection, models, transaction

from signal_loop.contracts.validation import identifier, monday, require, string
from .composition import prepare_manager
from .models import AudienceRelease, ManagerReport
from .projections import validate_content


@dataclass(frozen=True)
class CompositionResult:
    state: str


def lock_project_week(project, week):
    """Internal shared #31/#32 lock: caller must own an atomic transaction."""
    require(connection.in_atomic_block and connection.vendor == "postgresql")
    key = int.from_bytes(hashlib.blake2b(f"report:{project}:{week}".encode(), digest_size=8).digest(), "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def publish_locked(*, project, week, audience, content, at, expires_at):
    """Internal persistence only, after owning audience gate and shared lock.

    #32 uses this helper after independently composing its team candidate. This
    helper and a correctly shaped JSON object are not privacy approval.
    """
    require(connection.in_atomic_block)
    validate_content(content, audience)
    existing = AudienceRelease.objects.filter(project=project, week=week, audience=audience).first()
    if existing is not None:
        return existing
    require(at < expires_at <= at + timedelta(days=365))
    release = AudienceRelease(project=project, week=week, audience=audience, content=deepcopy(content),
                              released_at=at, expires_at=expires_at)
    release.save(_validated=True)
    return release


def compose_manager(recommendations, *, project, week, version, closes_at, at, context_provider=None):
    identifier(project)
    monday(week)
    identifier(version)
    string(version, 32)
    require(at.utcoffset() is not None and closes_at.utcoffset() is not None)
    started = monotonic()
    # Candidate and every nested source/context value are snapshotted by the pure
    # gate. No mutable caller data is reread when the record is persisted.
    with transaction.atomic():
        lock_project_week(project, week)
        release = AudienceRelease.objects.filter(project=project, week=week, audience="manager").first()
        if release is not None:
            return CompositionResult("ready" if release.state == "ready" and at < release.expires_at else "suppressed")
        key = dict(project=project, week=week, analysis_version=version, schema="manager-report/1.0", privacy_policy="1.0")
        existing = ManagerReport.objects.filter(**key).first()
        if existing is not None:
            # Explicit workflow retry belongs to #33. Ordinary duplicate delivery
            # reuses the same decision, including failed/suppressed candidates.
            return CompositionResult(existing.state if at < existing.expires_at else "suppressed")
        prepared = prepare_manager(recommendations, project=project, week=week, version=version,
                                   closes_at=closes_at, at=at, context_provider=context_provider)
        state = prepared.state
        if state == "ready":
            try:
                if context_provider.load(project=project, week=week) != prepared.context:
                    state = "suppressed"
            except Exception:
                state = "suppressed"
        # The last context reload itself consumes the original source lifetime.
        instant = at + timedelta(seconds=max(0, monotonic() - started))
        if state == "ready" and instant >= prepared.expires_at:
            state = "suppressed"
        counterpart = AudienceRelease.objects.filter(project=project, week=week, audience="team").first()
        if state == "ready" and counterpart is not None and (counterpart.state != "ready" or
                instant >= counterpart.expires_at or counterpart.content != prepared.context.team_content):
            state = "suppressed"
        candidate = ManagerReport(**key, state=state, artifact=prepared.artifact if state == "ready" else None,
                                  expires_at=prepared.expires_at or closes_at + timedelta(days=14))
        candidate.save(_validated=True)
        if state == "ready":
            # Qualitative historical derivatives cannot outlive the older release
            # they describe. Closed historical weeks are already at least a week
            # old; this conservative bound never starts their retention anew.
            has_trends = bool(prepared.content["trends"])
            expires = min(instant + timedelta(days=365), closes_at + timedelta(days=365 - (7 if has_trends else 0)))
            if counterpart is not None:
                expires = min(expires, counterpart.expires_at)
            publish_locked(project=project, week=week, audience="manager", content=prepared.content,
                           at=instant, expires_at=expires)
        return CompositionResult(state)


def withdraw_release(*, project, week, audience):
    """Withdraw the entire original release; never replace it with new text."""
    with transaction.atomic():
        lock_project_week(project, week)
        return models.QuerySet(model=AudienceRelease).filter(project=project, week=week, audience=audience,
                                                             state="ready").update(state="withdrawn", content=None)
