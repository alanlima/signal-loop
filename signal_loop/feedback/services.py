"""Trusted anonymous sink, not a public submission or raw-feedback read API."""
from datetime import date, datetime, timedelta

from django.db import transaction
from django.utils import timezone

from signal_loop.contracts.feedback import InvalidFeedback, is_substantive, normalize_sections
from signal_loop.windows.services import project_week_scope

from .models import FeedbackSection


class PersistenceError(Exception):
    def __init__(self, code="invalid_submission"):
        self.code = code
        super().__init__(code)


def persist_sections(sections, *, clock=timezone.now):
    """Return generic completion; failure raises a content-free error and rolls back.

    #21 must call inside admission's transaction, never expose this as an endpoint.
    No source IDs, body fingerprints, identity context or batch records are returned.
    """
    try:
        return _persist_sections(sections, clock=clock)
    except PersistenceError:
        raise
    except Exception:
        raise PersistenceError("persistence_failed") from None


def _persist_sections(sections, *, clock):
    try:
        normalized = normalize_sections(sections, versioned=True)
    except InvalidFeedback:
        raise PersistenceError() from None
    at = clock()
    if not isinstance(at, datetime) or timezone.is_naive(at):
        raise PersistenceError()
    prepared = []
    valid_scopes = []
    # Validate every scope and complete section before the first insertion.
    for section in normalized:
        week = date.fromisoformat(section["week"])
        scope = project_week_scope(project_id=section["project"], week=week)
        if scope is None or not scope.opens_at <= at < scope.closes_at:
            raise PersistenceError()
        valid_scopes.append(scope)
        if is_substantive(section):
            prepared.append(FeedbackSection(project_id=section["project"], week=week,
                schema=section["schema"], privacy_policy=section["privacy_policy"],
                answers=section["answers"], expires_at=scope.closes_at + timedelta(days=14)))
    if not prepared:
        return "no_feedback"
    admitted_at = clock()
    if (not isinstance(admitted_at, datetime) or timezone.is_naive(admitted_at)
            or any(not scope.opens_at <= admitted_at < scope.closes_at for scope in valid_scopes)):
        raise PersistenceError()
    try:
        with transaction.atomic():
            for row in prepared:
                row.save(_validated=True, force_insert=True)
    except Exception:
        raise PersistenceError("persistence_failed") from None
    return "complete"
