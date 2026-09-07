"""Authenticated final HTTP adapter; private draft callbacks stay in checkins."""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from signal_loop.admission.models import Journey
from signal_loop.admission.services import AdmissionError, own_status, reconcile_expired_journeys
from signal_loop.navigation import render_shell
from signal_loop.submission.services import submit_check_in as finalize

from .journey import _submission_sections
from .models import PersonalDraft
from .views import _configured, _state


def _result(request, code, *, week="", revision=""):
    messages = {
        "complete": "Your check-in is complete.",
        "no_feedback": "No project feedback to submit. Return to review or discard your draft.",
        "conflict": "Your draft changed in another tab. Return to review your saved answers before submitting.",
        "invalid_submission": "Review incomplete or invalid saved sections before submitting. Your answers are preserved.",
        "unavailable": "This check-in is unavailable. Return to check its current status.",
        "retryable_failure": "We could not submit your check-in. Your saved answers are preserved; try again.",
    }
    code = code if code in messages else "unavailable"
    response = render(request, "checkins/submission_result.html", {"completed": code == "complete",
        "page_title": "Check-in complete" if code == "complete" else "Check-in status",
        "result_message": messages[code], "retryable": code == "retryable_failure", "week": week, "revision": revision},
        status={"complete": 200, "no_feedback": 200, "conflict": 409,
                "invalid_submission": 400, "unavailable": 403, "retryable_failure": 503}[code])
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_POST
@sensitive_post_parameters()
def submit_check_in(request):
    guard = render_shell(request, "current_check_in")
    if guard.status_code != 200:
        return guard
    try:
        if (set(request.POST) - {"csrfmiddlewaretoken", "week", "revision"}
                or any(len(request.POST.getlist(key)) != 1 for key in request.POST)):
            raise ValueError()
        week_text = request.POST["week"]
        week = date.fromisoformat(week_text)
        revision = int(request.POST["revision"])
        if week.weekday() != 0 or week.isoformat() != week_text or str(revision) != request.POST["revision"] or revision < 0:
            raise ValueError()
    except (ValueError, KeyError):
        return _result(request, "invalid_submission")
    provider = _configured("CHECKIN_PRINCIPAL_PROVIDER", "signal_loop.admission.services.deny_unverified")
    try:
        identifier, organisation, _, _ = _state(request.user, timezone.now(), provider)
        if identifier is None:
            return _result(request, "unavailable")
        with transaction.atomic():
            reconcile_expired_journeys(user=request.user, organisation=organisation, provider=provider, clock=timezone.now)
            PersonalDraft.objects.filter(journey__principal_id=identifier, expires_at__lte=timezone.now()).delete()
        if own_status(user=request.user, organisation=organisation, week=week, provider=provider, clock=timezone.now) == "complete":
            return _result(request, "complete")
        journey = Journey.objects.filter(principal_id=identifier, week=week).first()
        draft = PersonalDraft.objects.filter(journey=journey).first() if journey else None
        if not draft:
            return _result(request, "unavailable")
        scopes = [pair for pair in journey.selected_scopes if pair[0] not in draft.omitted_projects]

        def prepare():
            current = PersonalDraft.objects.select_for_update().filter(pk=draft.pk, journey=journey).first()
            journey.refresh_from_db()
            if not current or journey.state != "open" or timezone.now() >= current.expires_at:
                raise AdmissionError("unavailable")
            if current.revision != revision:
                raise AdmissionError("conflict")
            if current.stage != "finish" or not current.adaptive_allocated:
                raise AdmissionError("invalid_submission")
            if scopes != [pair for pair in journey.selected_scopes if pair[0] not in current.omitted_projects]:
                raise AdmissionError("conflict")
            try:
                return _submission_sections(current, journey, request.user)
            except Exception:
                raise AdmissionError("invalid_submission") from None

        def clear():
            deleted, _ = PersonalDraft.objects.filter(pk=draft.pk, journey=journey).delete()
            if not deleted:
                raise AdmissionError("retryable_failure")

        code = finalize(user=request.user, organisation=organisation, week=week, scopes=scopes,
                        prepare_draft=prepare, clear_draft=clear, provider=provider, clock=timezone.now)
    except Exception:
        code = "retryable_failure"
    return _result(request, code, week=week_text, revision=revision)
