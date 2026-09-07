"""Journey timing, seen questions, adaptive flow and answer-preserving review."""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.module_loading import import_string

from signal_loop.ai.adapter import Adapter
from signal_loop.ai.fake import FakeProvider
from signal_loop.contracts.feedback import is_substantive, normalize_sections
from signal_loop.membership.models import Organisation, Project
from signal_loop.windows.services import eligible_projects
from signal_loop.windows.models import WeeklyWindow

from .allocation import DraftAllocationStore
from .followups import CATALOG, Decision, Outcome, reserve_followups, select_followup
from .forms import PersonalForm, ProjectForm, ReflectionText
from .models import PersonalDraft, ProjectDraft
from django import forms


class AdaptiveForm(forms.Form):
    answer = ReflectionText(required=False, max_length=240, strip=False,
        widget=forms.Textarea(attrs={"rows": 3, "data-codepoint-limit": 240}),
        help_text="Up to 240 characters. Avoid names, exact dates and details that could identify someone.")

    def __init__(self, *args, label, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["answer"].label = label


def deadline(journey):
    return min(journey.started_at + timedelta(seconds=600), journey.expires_at)


def expired_clock(journey):
    return timezone.now() >= deadline(journey)


def project_keys(project_id):
    return [f"{project_id}:{key}" for key in ProjectForm.base_fields]


def adaptive_key(row):
    return f'{row["slot"]["project"]}:{row["slot"]["question"]}'


def _label(row):
    return CATALOG[row["slot"]["question"]].format(project_name=row["slot"]["project_name"])


def _valid_field(form_class, answers, key, **kwargs):
    form = form_class(answers, **kwargs)
    form.is_valid()
    return key in answers and key not in form.errors


def _allowed(journey, user):
    projects = {p.pk: p for p in Project.objects.filter(pk__in=[s[0] for s in journey.selected_scopes])}
    allowed = {(row.project_id, row.window_id) for org in Organisation.objects.filter(
        pk__in={project.organisation_id for project in projects.values()})
        for row in eligible_projects(user=user, organisation=org, at=timezone.now())}
    return projects, allowed


def progress(draft, journey):
    stopped = expired_clock(journey)
    resolved = 0
    for key in PersonalForm.base_fields:
        if (stopped and key not in draft.seen_slots) or (key in draft.seen_slots and _valid_field(PersonalForm, draft.answers, key)):
            resolved += 1
    answers = {row.project_id: row.answers for row in ProjectDraft.objects.filter(draft=draft)}
    for pid, _ in journey.selected_scopes:
        for key in ProjectForm.base_fields:
            if pid in draft.omitted_projects or (f"{pid}:{key}" in draft.seen_slots and _valid_field(ProjectForm, answers.get(pid, {}), key, project_name="project")):
                resolved += 1
    if draft.adaptive_allocated:
        resolved += 2 - len(draft.adaptive_slots)
        for row in draft.adaptive_slots:
            key = adaptive_key(row)
            if row["state"] in {"no_question", "unavailable"} or int(row["slot"]["project"]) in draft.omitted_projects or (row["state"] == "shown" and key in draft.seen_slots and key in draft.adaptive_answers and draft.adaptive_answers[key].get("resolved", False) and AdaptiveForm(
                    {"answer": draft.adaptive_answers[key]["answer"]}, label=_label(row)).is_valid()):
                resolved += 1
    return resolved, 5 + 3 * len(journey.selected_scopes) + 2


def _configured(name, default):
    value = getattr(settings, name, default)
    return import_string(value) if isinstance(value, str) else value


def _close_unseen(draft):
    draft.adaptive_allocated = True
    for row in draft.adaptive_slots:
        if row["state"] in {"reserved", "claimed"} or adaptive_key(row) not in draft.seen_slots:
            row["state"] = "no_question"


def _seen_form(form, keys):
    for key in list(form.fields):
        if key not in keys:
            del form.fields[key]
    return form


def handle_journey(request, *, journey, draft, context):
    """Called only after the personal/project transaction commits; AI claims commit first."""
    action = request.POST.get("action", "") if request.method == "POST" else ""
    own_actions = {"adaptive_next", "adaptive_skip", "adaptive_back", "review", "finish_personal",
                   "finish_project", "finish_adaptive", "finish_skip", "finish_omit", "preview_submit", "resume_questions"}
    if action in own_actions:
        response = _save_journey_action(request, journey, draft.pk, action, context)
        if response is not None:
            return response
        draft.refresh_from_db()
    if draft.stage == "projects" and "current_project" not in context and not expired_clock(journey):
        from .project_stage import project_stage
        with transaction.atomic():
            draft = PersonalDraft.objects.select_for_update().get(pk=draft.pk)
            rendered = project_stage(request, journey=journey, draft=draft, candidates=context["candidates"])
            if isinstance(rendered, HttpResponse):
                return rendered
            context.update(rendered)
    if draft.stage == "project_review" and not expired_clock(journey):
        projects, allowed = _allowed(journey, request.user)
        answers = {row.project_id: row.answers for row in ProjectDraft.objects.filter(draft=draft)}
        inputs = [{"project": str(pid), "week": WeeklyWindow.objects.get(pk=wid).week_start.isoformat(),
                   "project_name": projects[pid].name, "answers": answers[pid]}
                  for pid, wid in journey.selected_scopes if pid not in draft.omitted_projects and (pid, wid) in allowed]
        store = DraftAllocationStore(draft.pk)
        slots = reserve_followups(inputs, remaining_budget=2, deadline=deadline(journey), store=store, clock=timezone.now)
        factory = _configured("CHECKIN_AI_FACTORY", lambda: Adapter(FakeProvider()))
        for slot in slots:
            latest = PersonalDraft.objects.get(pk=draft.pk)
            if not any(row["slot"]["project"] == slot.project and row["state"] == "reserved" for row in latest.adaptive_slots):
                continue
            try:
                adapter = factory()
            except Exception:
                if store.claim(slot):
                    store.record(slot, Decision(Outcome.UNAVAILABLE))
                continue
            select_followup(slot, store=store, adapter=adapter, deadline=deadline(journey), clock=timezone.now)
        draft.refresh_from_db()
        draft.stage = "adaptive"
        if any(row["state"] == "unavailable" for row in draft.adaptive_slots):
            context["journey_message"] = "An optional follow-up is unavailable. You can continue reviewing your answers."
    with transaction.atomic():
        current = PersonalDraft.objects.select_for_update().get(pk=draft.pk)
        # Preserve a new stage selected above while retaining concurrently saved answers.
        if draft.stage == "adaptive" and current.stage == "project_review":
            current.stage = "adaptive"
        if expired_clock(journey):
            _close_unseen(current)
            current.stage = "finish"
            context["timed_out"] = True
        if current.stage == "personal":
            current.seen_slots = list(dict.fromkeys(current.seen_slots + list(PersonalForm.base_fields)))
        elif current.stage == "projects" and context.get("project_available"):
            current.seen_slots = list(dict.fromkeys(current.seen_slots + project_keys(context["current_project"].pk)))
        if current.stage == "adaptive":
            _, allowed_now = _allowed(journey, request.user)
            if any(pid not in current.omitted_projects and (pid, wid) not in allowed_now for pid, wid in journey.selected_scopes):
                for row in current.adaptive_slots:
                    if (int(row["slot"]["project"]), dict(journey.selected_scopes)[int(row["slot"]["project"])]) not in allowed_now:
                        row["state"] = "no_question"
                current.stage = "finish"
            for row in current.adaptive_slots:
                if row["state"] == "claimed":
                    row["state"] = "no_question"
            shown = [row for row in current.adaptive_slots if row["state"] == "shown" and (
                adaptive_key(row) not in current.adaptive_answers or not current.adaptive_answers[adaptive_key(row)].get("resolved", False) or not AdaptiveForm(
                    {"answer": current.adaptive_answers[adaptive_key(row)]["answer"]}, label=_label(row)).is_valid())]
            if shown and current.stage == "adaptive":
                row = shown[0]
                current.seen_slots = list(dict.fromkeys(current.seen_slots + [adaptive_key(row)]))
                context.update(adaptive_row=row, adaptive_key=adaptive_key(row),
                               adaptive_form=context.get("adaptive_form") or AdaptiveForm(
                                   initial={"answer": current.adaptive_answers.get(adaptive_key(row), {}).get("answer", "")}, label=_label(row)))
            else:
                current.stage = "finish"
        if current.stage == "finish":
            context.update(_finish_context(current, journey, request.user, context))
        current.save(update_fields=["stage", "seen_slots", "adaptive_allocated", "adaptive_slots"])
        draft = current
    done, total = progress(draft, journey)
    context.update(stage=draft.stage, draft=draft, question_done=done, question_total=total,
                   journey_deadline=deadline(journey), elapsed_seconds=max(0, int((timezone.now() - journey.started_at).total_seconds())))
    return None


def _save_journey_action(request, journey, draft_id, action, context):
    if action == "preview_submit" and not getattr(settings, "CHECKIN_FINAL_SUBMISSION", None):
        return HttpResponse("Not found.", status=404)
    allowed = {"csrfmiddlewaretoken", "action", "revision"}
    if action == "finish_personal":
        allowed |= set(PersonalForm.base_fields)
    elif action in {"finish_project", "finish_omit"}:
        allowed |= {"section", "confirm"} | (set(ProjectForm.base_fields) if action == "finish_project" else set())
    elif action in {"adaptive_next", "adaptive_skip", "adaptive_back", "finish_adaptive", "finish_skip"}:
        allowed |= {"question", "answer", "acknowledge"}
    if set(request.POST) - allowed or any(len(request.POST.getlist(key)) != 1 for key in request.POST):
        return HttpResponse("Not found.", status=404)
    with transaction.atomic():
        draft = PersonalDraft.objects.select_for_update().get(pk=draft_id)
        if request.POST.get("revision") != str(draft.revision):
            context["journey_message"] = "This draft changed in another tab. Reload before saving; your unsaved answers are shown."
            if action == "finish_personal":
                context["finish_personal_form"] = _seen_form(PersonalForm(request.POST), draft.seen_slots)
            elif action == "finish_project":
                pid = request.POST.get("section")
                if pid in {str(pair[0]) for pair in journey.selected_scopes}:
                    form = ProjectForm(request.POST, project_name=Project.objects.get(pk=pid).name, auto_id=f"id_{pid}_%s")
                    context["finish_project_form"] = (int(pid), form)
            elif action in {"adaptive_next", "finish_adaptive"}:
                row = next((row for row in draft.adaptive_slots if adaptive_key(row) == request.POST.get("question")), None)
                if row:
                    form = AdaptiveForm(request.POST, label=_label(row))
                    context.update(adaptive_form=form, finish_adaptive_form=(adaptive_key(row), form))
            return None
        if action == "resume_questions" and not expired_clock(journey):
            if not PersonalForm(draft.answers).is_valid():
                draft.stage = "personal"
            else:
                saved = {row.project_id: row.answers for row in ProjectDraft.objects.filter(draft=draft)}
                unfinished = [i for i, (pid, _) in enumerate(journey.selected_scopes) if pid not in draft.omitted_projects
                              and not ProjectForm(saved.get(pid, {}), project_name="project").is_valid()]
                draft.stage = "projects" if unfinished else "project_review"
                if unfinished:
                    draft.project_position = unfinished[0]
        elif action == "review":
            draft.stage = "finish"
        elif action == "adaptive_back":
            key = request.POST.get("question", "")
            row = next((row for row in draft.adaptive_slots if adaptive_key(row) == key
                        and row["state"] == "shown" and key in draft.seen_slots), None)
            if row is None:
                return HttpResponse("Not found.", status=404)
            form = AdaptiveForm(request.POST, label=_label(row))
            valid = form.is_valid()
            draft.adaptive_answers[key] = {"answer": form.cleaned_data["answer"] if valid else request.POST.get("answer", ""),
                "skipped": False, "acknowledged": False, "resolved": draft.adaptive_answers.get(key, {}).get("resolved", False)}
            context["finish_adaptive_form"] = (key, form)
            draft.stage = "finish"
        elif action == "finish_personal":
            if any(key in request.POST and key not in draft.seen_slots for key in PersonalForm.base_fields):
                return HttpResponse("Not found.", status=404)
            raw = {key: request.POST.get(key, "") for key in PersonalForm.base_fields if key in draft.seen_slots}
            form = _seen_form(PersonalForm(raw), raw)
            valid = form.is_valid()
            draft.answers.update(form.cleaned_data if valid else raw)
            context["finish_personal_form"] = form
        elif action in {"finish_project", "finish_omit"}:
            claimed = request.POST.get("section", "")
            ids = [pid for pid, _ in journey.selected_scopes]
            if claimed not in {str(pid) for pid in ids}:
                return HttpResponse("Not found.", status=404)
            pid = int(claimed)
            if action == "finish_omit":
                if request.POST.get("confirm") != "yes":
                    context["journey_message"] = "Confirm removal; other answers will be preserved."
                elif pid not in draft.omitted_projects:
                    draft.omitted_projects.append(pid)
                    ProjectDraft.objects.filter(draft=draft, project_id=pid).delete()
            elif pid not in draft.omitted_projects:
                projects, allowed = _allowed(journey, request.user)
                if (pid, dict(journey.selected_scopes)[pid]) not in allowed:
                    context["journey_message"] = "This project is no longer available. Confirm removal to continue."
                else:
                    keys = [key for key in ProjectForm.base_fields if f"{pid}:{key}" in draft.seen_slots]
                    if not keys or any(key in request.POST and key not in keys for key in ProjectForm.base_fields):
                        return HttpResponse("Not found.", status=404)
                    raw = {key: request.POST.get(key, "") for key in keys}
                    form = _seen_form(ProjectForm(raw, project_name=projects[pid].name, auto_id=f"id_{pid}_%s"), keys)
                    valid = form.is_valid()
                    ProjectDraft.objects.update_or_create(draft=draft, project_id=pid,
                        defaults={"answers": form.cleaned_data if valid else raw})
                    context["finish_project_form"] = (pid, form)
        elif action in {"adaptive_next", "adaptive_skip", "finish_adaptive", "finish_skip"}:
            key = request.POST.get("question", "")
            row = next((row for row in draft.adaptive_slots if adaptive_key(row) == key
                        and row["state"] == "shown" and key in draft.seen_slots), None)
            if row is None:
                return HttpResponse("Not found.", status=404)
            if action in {"adaptive_skip", "finish_skip"}:
                draft.adaptive_answers[key] = {"answer": "", "skipped": True, "acknowledged": True, "resolved": True}
            else:
                form = AdaptiveForm({"answer": request.POST.get("answer", "")}, label=_label(row))
                valid = form.is_valid()
                draft.adaptive_answers[key] = {"answer": form.cleaned_data["answer"] if valid else request.POST.get("answer", ""),
                                               "skipped": False, "acknowledged": request.POST.get("acknowledge") == "yes", "resolved": valid}
                if not valid:
                    context["adaptive_form"] = form
                    context["finish_adaptive_form"] = (key, form)
        elif action == "preview_submit":
            draft.stage = "finish"
            try:
                sections = _submission_sections(draft, journey, request.user)
                if not sections:
                    context["journey_message"] = "No project feedback to submit. You can discard or return to saved answers."
                else:
                    result = _configured("CHECKIN_FINAL_SUBMISSION", "signal_loop.submission.services.preview_submission")(sections)
                    context["journey_message"] = ("Practice finish complete. No feedback was submitted. Your draft remains until discard or expiry."
                        if result == "preview_complete" else "Could not finish. Your answers are preserved; try again.")
            except Exception:
                context["journey_message"] = "Review incomplete, invalid or unavailable sections below. Your answers are preserved."
        draft.revision += 1
        draft.save()
    return None


def _eligible_followup(row, answers):
    return (row["slot"]["question"] == "F1" and answers.get("J1") in {"blocked", "at_risk"}) or (
        row["slot"]["question"] == "F2" and answers.get("J2") in {"overloaded", "stretched"})


def _finish_context(draft, journey, user, existing):
    projects, allowed = _allowed(journey, user)
    saved = {row.project_id: row.answers for row in ProjectDraft.objects.filter(draft=draft)}
    personal = existing.get("finish_personal_form") or (
        existing["form"] if existing.get("form") is not None and existing["form"].is_bound
        else _seen_form(PersonalForm(initial=draft.answers), draft.seen_slots))
    sections = []
    for pid, wid in journey.selected_scopes:
        if pid in draft.omitted_projects:
            continue
        keys = [key for key in ProjectForm.base_fields if f"{pid}:{key}" in draft.seen_slots]
        form = _seen_form(ProjectForm(initial=saved.get(pid, {}), project_name=projects[pid].name, auto_id=f"id_{pid}_%s"), keys)
        if existing.get("finish_project_form", (None,))[0] == pid:
            form = existing["finish_project_form"][1]
        elif existing.get("current_project") and existing["current_project"].pk == pid and existing.get("project_form") and existing["project_form"].is_bound:
            form = existing["project_form"]
            form.auto_id = f"id_{pid}_%s"
        sections.append({"project": projects[pid], "form": form, "available": (pid, wid) in allowed,
                         "unseen": not keys})
    followups = []
    for row in draft.adaptive_slots:
        key = adaptive_key(row)
        if row["state"] != "shown" or key not in draft.seen_slots:
            continue
        pid = int(row["slot"]["project"])
        if pid in draft.omitted_projects:
            continue
        answer = draft.adaptive_answers.get(key, {})
        form = AdaptiveForm(initial={"answer": answer.get("answer", "")}, label=_label(row), auto_id=f"id_{key}_%s")
        if existing.get("finish_adaptive_form", (None,))[0] == key:
            form = existing["finish_adaptive_form"][1]
        followups.append({"key": key, "form": form, "excluded": not _eligible_followup(row, saved.get(pid, {})),
                          "acknowledged": answer.get("acknowledged", False)})
    return {"finish_personal": personal, "finish_sections": sections, "finish_followups": followups,
            "no_retained_projects": not sections}


def _submission_sections(draft, journey, user):
    projects, allowed = _allowed(journey, user)
    personal = _seen_form(PersonalForm(draft.answers), draft.seen_slots)
    if not personal.is_valid():
        raise ValueError()
    saved = {row.project_id: row.answers for row in ProjectDraft.objects.filter(draft=draft)}
    sections = []
    for pid, wid in journey.selected_scopes:
        if pid in draft.omitted_projects:
            continue
        if (pid, wid) not in allowed:
            raise ValueError()
        answers = dict(saved.get(pid, {}))
        # Revalidate the authoritative offer record independently of save handlers.
        # This also denies stale/forged rows written before the seen-field guard.
        if (not set(answers) <= set(ProjectForm.base_fields)
                or any(f"{pid}:{key}" not in draft.seen_slots for key in {"J1", "J2"} | set(answers))):
            raise ValueError()
        if not ProjectForm(answers, project_name=projects[pid].name).is_valid():
            raise ValueError()
        for row in draft.adaptive_slots:
            key = adaptive_key(row)
            if row["slot"]["project"] != str(pid) or row["state"] != "shown":
                continue
            value = draft.adaptive_answers.get(key)
            if key not in draft.seen_slots:
                if value is not None:
                    raise ValueError()
                continue
            if value is None or not value.get("resolved", False) or not AdaptiveForm({"answer": value["answer"]}, label=_label(row)).is_valid():
                raise ValueError()
            if not _eligible_followup(row, answers):
                if not value["acknowledged"]:
                    raise ValueError()
            elif not value["skipped"]:
                answers[row["slot"]["question"]] = value["answer"]
        normalized = normalize_sections([{"project": pid, "week": WeeklyWindow.objects.get(pk=wid).week_start.isoformat(), "answers": answers}])[0]
        if is_substantive(normalized):
            sections.append({key: normalized[key] for key in ("project", "week", "answers")})
    return sections
