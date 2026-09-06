from datetime import datetime, timedelta
from dataclasses import dataclass
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render
from django.utils import timezone
from django.utils.module_loading import import_string
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from signal_loop.admission.models import Journey, Participation, Principal
from signal_loop.admission.services import (
    AdmissionError, VerifiedPrincipal, discard, global_week, issue, own_status, reconcile_expired_journeys,
)
from signal_loop.membership.models import Organisation
from signal_loop.navigation import render_shell
from signal_loop.windows.services import eligible_projects
from signal_loop.windows.models import WeeklyWindow

from .forms import PersonalForm
from .models import PersonalDraft


@dataclass(frozen=True)
class ProjectChoice:
    project_id: int
    window_id: int
    project_name: str
    closes_at: datetime


def _configured(name, default):
    value = getattr(settings, name, default)
    return import_string(value) if isinstance(value, str) else value


def _state(user, at, provider):
    organisations = list(Organisation.objects.filter(memberships__user=user, memberships__is_active=True,
                                                    is_active=True).distinct().order_by("pk"))
    verified = []
    candidates = []
    for organisation in organisations:
        result = provider(user, organisation)
        if not isinstance(result, VerifiedPrincipal):
            continue
        verified.append((organisation, result.id))
        candidates.extend(eligible_projects(user=user, organisation=organisation, at=at))
    if not verified or len({identifier for _, identifier in verified}) != 1:
        return None, None, [], None
    identifier = verified[0][1]
    week, end = global_week(at)
    consumed = set(Participation.objects.filter(principal_id=identifier, consumed=True,
                                                retain_until__gt=at).values_list("project_id", "window_id"))
    closes = dict(WeeklyWindow.objects.filter(pk__in=[row.window_id for row in candidates])
                  .values_list("pk", "closes_at"))
    candidates = sorted((ProjectChoice(row.project_id, row.window_id, row.project_name, closes[row.window_id])
                         for row in candidates if (row.project_id, row.window_id) not in consumed),
                        key=lambda row: (row.project_name.casefold(), row.project_id))
    return identifier, verified[0][0], candidates, (week, end)


@login_required
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters("P1", "P2", "P3", "P4", "P5")
def personal_check_in(request):
    try:
        return _personal_check_in(request)
    except Exception:
        # Keep entered reflection recoverable without logging exception locals/body.
        form = PersonalForm({key: request.POST.get(key, "") for key in PersonalForm.base_fields})
        form.add_error(None, "We could not save or load the draft. Keep this page open and try again.")
        response = render(request, "checkins/retry.html", {"stage": "personal", "form": form,
            "draft": SimpleNamespace(revision=request.POST.get("revision", "0"), expires_at=None)}, status=503)
        response["Cache-Control"] = "private, no-store"
        return response


def _personal_check_in(request):
    # Reject forged shell scope before any draft mutation, using the shared guard.
    guard = render_shell(request, "current_check_in")
    if guard.status_code != 200:
        return guard
    at = timezone.now()
    provider = _configured("CHECKIN_PRINCIPAL_PROVIDER", "signal_loop.admission.services.deny_unverified")
    context = {"checkin_template": "checkins/personal.html", "stage": "unavailable"}
    try:
        identifier, organisation, candidates, cycle = _state(request.user, at, provider)
    except Exception:
        return render_shell(request, "current_check_in", extra_context=context)
    if identifier is None:
        return render_shell(request, "current_check_in", extra_context=context)
    with transaction.atomic():
        reconcile_expired_journeys(user=request.user, organisation=organisation, provider=provider, clock=lambda: at)
        removed, _ = PersonalDraft.objects.filter(journey__principal_id=identifier, expires_at__lte=at).delete()
    if removed:
        context["message"] = "An earlier draft expired and was deleted. Its reflection cannot be recovered."
    week, end = cycle
    context.update(candidates=candidates, week=week, week_end=end,
                   earliest_expiry=min([end, at + timedelta(days=7)] + [row.closes_at for row in candidates])
                   if 0 < len(candidates) <= 3 else None)
    status = own_status(user=request.user, organisation=organisation, week=week, provider=provider, clock=lambda: at)
    journey = Journey.objects.filter(principal_id=identifier, week=week).first()
    if journey and journey.state != Journey.State.OPEN:
        PersonalDraft.objects.filter(journey=journey).delete()
        context["stage"] = "complete" if status == "complete" else "expired"
        return render_shell(request, "current_check_in", extra_context=context)
    action = request.POST.get("action", "") if request.method == "POST" else ""
    if not journey:
        context["stage"] = "select" if candidates else "empty"
        selected = {row.project_id for row in candidates} if len(candidates) <= 3 else set()
        if action == "begin":
            values = request.POST.getlist("projects")
            try:
                selected = {int(value) for value in values}
                if len(values) != len(selected) or not 1 <= len(selected) <= 3:
                    raise ValueError()
                scopes = [(row.project_id, row.window_id) for row in candidates if row.project_id in selected]
                if len(scopes) != len(selected):
                    raise ValueError()
                with transaction.atomic():
                    issuance = issue(user=request.user, scopes=scopes, provider=provider, clock=timezone.now)
                    journey = Journey.objects.get(principal_id=identifier, week=issuance.week)
                    PersonalDraft.objects.get_or_create(journey=journey, defaults={"expires_at": issuance.expires_at})
            except (AdmissionError, ValueError):
                context["message"] = "Choose between one and three available projects. Your selection was not started."
        context["chosen"] = selected
        if not journey:
            # Display each public scope's exact closing instant before Begin; server freezes chosen minimum.
            context["earliest_expiry"] = min([end] + [row.closes_at for row in candidates if row.project_id in selected]) if selected else None
            return render_shell(request, "current_check_in", extra_context=context)
    if action == "discard":
        if request.POST.get("confirm") == "yes":
            with transaction.atomic():
                discard(user=request.user, organisation=organisation, week=week, provider=provider, clock=timezone.now)
                PersonalDraft.objects.filter(journey=journey).delete()
            context["stage"] = "expired"
            return render_shell(request, "current_check_in", extra_context=context)
        context["message"] = "Confirm discard to delete this draft and end this week's journey."
    with transaction.atomic():
        Principal.objects.select_for_update().get(pk=identifier)
        journey.refresh_from_db()
        if journey.state != Journey.State.OPEN or timezone.now() >= journey.expires_at:
            PersonalDraft.objects.filter(journey=journey).delete()
            context["stage"] = "expired"
            return render_shell(request, "current_check_in", extra_context=context)
        draft = PersonalDraft.objects.select_for_update().filter(journey=journey).first()
        if draft is None:
            context["stage"] = "expired"
            return render_shell(request, "current_check_in", extra_context=context)
        form = PersonalForm(initial=draft.answers)
        if action in {"next", "save", "back"}:
            if action == "back":
                draft.stage = "personal"
                draft.save(update_fields=["stage"])
            else:
                raw = {key: request.POST.get(key, "") for key in PersonalForm.base_fields}
                form = PersonalForm(raw)
                if request.POST.get("revision") != str(draft.revision):
                    form.add_error(None, "This draft changed in another tab. Reload before saving; your unsaved text is still shown.")
                else:
                    valid = form.is_valid()
                    draft.answers = form.cleaned_data if valid else raw
                    draft.revision += 1
                    draft.stage = "personal"
                    draft.save()
                    if valid and action == "next":
                        progression = _configured("CHECKIN_PROGRESS_SERVICE", "signal_loop.checkins.services.advance_to_projects")
                        try:
                            if progression() != "projects":
                                raise ValueError()
                            draft.stage = "projects"
                            draft.save(update_fields=["stage"])
                        except Exception:
                            form.add_error(None, "We could not continue. Your answers are saved. Try Next again.")
                    elif valid:
                        context["saved"] = True
        context.update(stage=draft.stage, form=form, draft=draft)
    response = render_shell(request, "current_check_in", extra_context=context)
    response["Cache-Control"] = "private, no-store"
    return response
