"""Trusted Python admission boundary. No endpoints or production identity provider.

Callers own authentication transport/CSRF. Sink and draft cleanup must use this
transaction's Django connection and must not perform external side effects.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone as utc_timezone
import hashlib
import hmac
import secrets
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from signal_loop.contracts.feedback import InvalidFeedback, is_substantive, normalize_sections
from signal_loop.membership.models import Organisation, OrganisationMembership, Project, ProjectMembership
from signal_loop.windows.models import WeeklyWindow
from signal_loop.windows.services import eligible_projects

from .models import Credential, Journey, Participation, Principal


class AdmissionError(Exception):
    """Content-free public error; never include tokens, identities or payloads."""
    def __init__(self, code="unavailable"):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class VerifiedPrincipal:
    id: UUID


@dataclass(frozen=True)
class IssuedCredential:
    project: int
    window: int
    secret: str = field(repr=False)


@dataclass(frozen=True)
class Issuance:
    week: date
    expires_at: datetime
    credentials: tuple[IssuedCredential, ...]


def deny_unverified(user, organisation):
    return None


def _now(clock):
    value = clock()
    if not isinstance(value, datetime) or timezone.is_naive(value):
        raise AdmissionError()
    return value.astimezone(utc_timezone.utc)


def global_week(at):
    day = at.astimezone(utc_timezone.utc).date()
    monday = day - timedelta(days=day.weekday())
    end = datetime.combine(monday + timedelta(days=7), time.min, tzinfo=utc_timezone.utc)
    return monday, end


def _resolve(user, organisations, provider):
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        raise AdmissionError()
    identifiers = []
    for organisation in organisations:
        try:
            result = provider(user, organisation)
        except Exception:
            raise AdmissionError() from None
        if not isinstance(result, VerifiedPrincipal) or not isinstance(result.id, UUID):
            raise AdmissionError()
        identifiers.append(result.id)
    if not identifiers or len(set(identifiers)) != 1:
        raise AdmissionError()
    return identifiers[0]


def _scope_rows(scopes):
    if not isinstance(scopes, (tuple, list)) or not 1 <= len(scopes) <= 3:
        raise AdmissionError("invalid_submission")
    if any(not isinstance(scope, (tuple, list)) or len(scope) != 2 or
           any(type(value) is not int or value <= 0 for value in scope) for scope in scopes):
        raise AdmissionError("invalid_submission")
    if len({scope[0] for scope in scopes}) != len(scopes):
        raise AdmissionError("invalid_submission")
    windows = list(WeeklyWindow.objects.filter(pk__in=[s[1] for s in scopes]).order_by("organisation_id", "pk"))
    if len(windows) != len({s[1] for s in scopes}):
        raise AdmissionError()
    projects = list(Project.objects.filter(pk__in=[s[0] for s in scopes]).order_by("pk"))
    window_map = {window.pk: window for window in windows}
    project_map = {project.pk: project for project in projects}
    if len(projects) != len(scopes) or any(project_map[p].organisation_id != window_map[w].organisation_id
                                           for p, w in scopes):
        raise AdmissionError()
    return windows, projects


def _lock_context(user, windows, projects, provider):
    org_ids = sorted({w.organisation_id for w in windows})
    organisations = list(Organisation.objects.select_for_update().filter(pk__in=org_ids).order_by("pk"))
    list(WeeklyWindow.objects.select_for_update().filter(pk__in=[w.pk for w in windows]).order_by("pk"))
    identifier = _resolve(user, organisations, provider)
    Principal.objects.get_or_create(pk=identifier)
    principal = Principal.objects.select_for_update().get(pk=identifier)
    fresh_user = get_user_model().objects.select_for_update().get(pk=user.pk)
    list(OrganisationMembership.objects.select_for_update().filter(user=user,
        organisation_id__in=org_ids).order_by("pk"))
    list(Project.objects.select_for_update().filter(pk__in=[p.pk for p in projects]).order_by("pk"))
    list(ProjectMembership.objects.select_for_update().filter(organisation_membership__user=user,
        project_id__in=[p.pk for p in projects]).order_by("pk"))
    if not fresh_user.is_active or any(not organisation.is_active for organisation in organisations):
        raise AdmissionError()
    return principal, organisations


def _check_eligibility(user, organisations, scopes, at):
    eligible = {(row.project_id, row.window_id) for org in organisations
                for row in eligible_projects(user=user, organisation=org, at=at)}
    if any(tuple(scope) not in eligible for scope in scopes):
        raise AdmissionError()


def _seal(journey, state):
    # The scope list is transient; never retain a multi-project group after sealing.
    for project, window in journey.selected_scopes:
        Credential.objects.filter(participation__principal=journey.principal,
                                  participation__project_id=project,
                                  participation__window_id=window,
                                  expires_at__lte=journey.expires_at).update(active=False)
    journey.state = state
    journey.selected_scopes = []
    journey.started_at = None
    journey.expires_at = None
    journey.save()


def issue(*, user, scopes, provider=deny_unverified, clock=timezone.now):
    """Begin/resume the combined journey. Resume rotates secrets, never time/selection."""
    windows, projects = _scope_rows(scopes)
    with transaction.atomic():
        principal, organisations = _lock_context(user, windows, projects, provider)
        at = _now(clock)
        week, end = global_week(at)
        journey = Journey.objects.filter(principal=principal, week=week).first()
        if journey and journey.state != Journey.State.OPEN:
            raise AdmissionError()
        if journey and at >= journey.expires_at:
            _seal(journey, Journey.State.EXPIRED)
            # Commit sealing; signal refusal after leaving the transaction.
            result = None
        else:
            _check_eligibility(user, organisations, scopes, at)
            frozen = [[p, w] for p, w in scopes]
            if journey and journey.selected_scopes != frozen:
                raise AdmissionError("conflict")
            if not journey:
                journey = Journey.objects.create(principal=principal, week=week, started_at=at,
                    expires_at=min(end, at + timedelta(days=7), *(w.closes_at for w in windows)),
                    selected_scopes=frozen, retain_until=end + timedelta(days=7))
            issued = []
            for project, window_id in scopes:
                window = next(w for w in windows if w.pk == window_id)
                participation, _ = Participation.objects.get_or_create(principal=principal,
                    project_id=project, window=window,
                    defaults={"retain_until": window.closes_at + timedelta(days=7)})
                if participation.consumed:
                    raise AdmissionError()
                secret = secrets.token_urlsafe(32)
                Credential.objects.update_or_create(participation=participation, defaults={
                    "verifier": hashlib.sha256(secret.encode()).hexdigest(), "active": True,
                    "expires_at": journey.expires_at, "purpose": "project-feedback-v1"})
                issued.append(IssuedCredential(project, window_id, secret))
            result = Issuance(week, journey.expires_at, tuple(issued))
    if result is None:
        raise AdmissionError()
    return result


def _anonymous_sections(sections):
    try:
        return normalize_sections(sections)
    except InvalidFeedback:
        raise AdmissionError("invalid_submission") from None


def redeem(*, user, week, claims, sections, sink, provider=deny_unverified,
           clear_draft=None, clock=timezone.now):
    """Reject repeated redemption; own_status separately reconciles a lost response.

    `sink(sections)` and optional `clear_draft()` are trusted transaction participants.
    They must use the current connection, raise on failure, return no source IDs,
    and perform no external effects. #21 wires the real draft/persistence adapters.
    """
    if not isinstance(claims, (list, tuple)) or any(not isinstance(c, IssuedCredential) for c in claims):
        raise AdmissionError("invalid_submission")
    scopes = [(c.project, c.window) for c in claims]
    windows, projects = _scope_rows(scopes)
    anonymous = _anonymous_sections(sections)
    if {s["project"] for s in anonymous} != {c.project for c in claims}:
        raise AdmissionError("invalid_submission")
    project_weeks = {p: next(w.week_start.isoformat() for w in windows if w.pk == wid) for p, wid in scopes}
    if any(s["week"] != project_weeks[s["project"]] for s in anonymous):
        raise AdmissionError("invalid_submission")
    try:
        with transaction.atomic():
            principal, organisations = _lock_context(user, windows, projects, provider)
            at = _now(clock)
            if global_week(at)[0] != week:
                raise AdmissionError()
            journey = Journey.objects.filter(principal=principal, week=week).first()
            if not journey or journey.state != Journey.State.OPEN or at >= journey.expires_at:
                raise AdmissionError()
            if any([p, w] not in journey.selected_scopes for p, w in scopes):
                raise AdmissionError()
            _check_eligibility(user, organisations, scopes, at)
            participants = []
            for claim in sorted(claims, key=lambda c: c.project):
                participation = Participation.objects.select_for_update().filter(principal=principal,
                    project_id=claim.project, window_id=claim.window).first()
                credential = Credential.objects.select_for_update().filter(participation=participation).first()
                if (not participation or participation.consumed or not credential or not credential.active
                        or credential.purpose != "project-feedback-v1" or at >= credential.expires_at
                        or not isinstance(claim.secret, str) or len(claim.secret) > 128
                        or not hmac.compare_digest(credential.verifier,
                                                   hashlib.sha256(claim.secret.encode()).hexdigest())):
                    raise AdmissionError()
                participants.append(participation)
            # Recheck the admission instant after credential validation, before any write.
            admitted_at = _now(clock)
            if admitted_at >= journey.expires_at or any(admitted_at >= w.closes_at for w in windows):
                raise AdmissionError()
            anonymous = [section for section in anonymous if is_substantive(section)]
            if not anonymous:
                return "no_feedback"
            submitted_projects = {section["project"] for section in anonymous}
            for participation in participants:
                if participation.project_id not in submitted_projects:
                    continue
                participation.consumed = True
                participation.save(update_fields=["consumed"])
            sink(anonymous)
            if clear_draft is not None:
                clear_draft()
            _seal(journey, Journey.State.COMPLETED)
    except AdmissionError:
        raise
    except Exception:
        raise AdmissionError("retryable_failure") from None
    return "complete"


def own_status(*, user, organisation, week, provider=deny_unverified, clock=timezone.now):
    identifier = _resolve(user, [organisation], provider)
    with transaction.atomic():
        principal = Principal.objects.select_for_update().filter(pk=identifier).first()
        if not principal or not get_user_model().objects.filter(pk=user.pk, is_active=True).exists():
            return "unavailable"
        journey = Journey.objects.filter(principal=principal, week=week).first()
        at = _now(clock)
        if not journey or at >= journey.retain_until:
            return "unavailable"
        if journey.state == Journey.State.OPEN and at >= journey.expires_at:
            _seal(journey, Journey.State.EXPIRED)
        return "complete" if journey.state == Journey.State.COMPLETED else (
            "open" if journey.state == Journey.State.OPEN else "unavailable")


def discard(*, user, organisation, week, provider=deny_unverified, clock=timezone.now):
    identifier = _resolve(user, [organisation], provider)
    with transaction.atomic():
        principal = Principal.objects.select_for_update().filter(pk=identifier).first()
        if not principal or not get_user_model().objects.filter(pk=user.pk, is_active=True).exists():
            raise AdmissionError()
        journey = Journey.objects.filter(principal=principal, week=week).first()
        at = _now(clock)
        if not journey or at >= journey.retain_until or journey.state != Journey.State.OPEN:
            raise AdmissionError()
        _seal(journey, Journey.State.EXPIRED if at >= journey.expires_at else Journey.State.DISCARDED)
    return "unavailable"
