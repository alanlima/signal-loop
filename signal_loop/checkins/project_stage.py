"""Private project-stage handling inside the caller's principal/draft transaction."""
from django.http import HttpResponse
from django.utils import timezone

from signal_loop.membership.models import Organisation, Project
from signal_loop.windows.services import eligible_projects

from .forms import ProjectForm
from .models import ProjectDraft


def project_stage(request, *, journey, draft, candidates):
    scopes = journey.selected_scopes
    if not scopes or len(scopes) > 3:
        return HttpResponse("Not found.", status=404, content_type="text/plain")
    ids = [scope[0] for scope in scopes]
    projects = {project.pk: project for project in Project.objects.filter(pk__in=ids)}
    if len(projects) != len(ids):
        return HttpResponse("Not found.", status=404, content_type="text/plain")
    action = request.POST.get("action", "") if request.method == "POST" else ""
    position = min(draft.project_position, len(scopes) - 1)
    claimed = request.POST.getlist("section") if action.startswith("project_") else request.GET.getlist("section")
    if claimed:
        if len(claimed) != 1 or claimed[0] not in {str(value) for value in ids}:
            return HttpResponse("Not found.", status=404, content_type="text/plain")
        position = ids.index(int(claimed[0]))
    elif action.startswith("project_") and action != "project_return":
        return HttpResponse("Not found.", status=404, content_type="text/plain")
    if request.method == "POST" and action.startswith("project_"):
        allowed = {"csrfmiddlewaretoken", "action", "revision", "section", "J1", "J2", "J3", "confirm"}
        if set(request.POST) - allowed or any(len(request.POST.getlist(key)) != 1 for key in request.POST):
            return HttpResponse("Not found.", status=404, content_type="text/plain")
    project_id, window_id = scopes[position]
    project = projects[project_id]
    # Recheck snapshot/current activity after acquiring the outer principal lock.
    eligible = {(row.project_id, row.window_id) for org in Organisation.objects.filter(
        pk__in={p.organisation_id for p in projects.values()})
        for row in eligible_projects(user=request.user, organisation=org, at=timezone.now())}
    eligible &= {(row.project_id, row.window_id) for row in candidates}
    available = (project_id, window_id) in eligible and project_id not in draft.omitted_projects
    row = ProjectDraft.objects.filter(draft=draft, project_id=project_id).first()
    form = ProjectForm(initial=row.answers if row else {}, project_name=project.name)
    message = None
    if action == "project_return":
        draft.stage = "projects"
        retained = [i for i, item in enumerate(ids) if item not in draft.omitted_projects]
        if retained:
            position = retained[-1]
        action = ""
    elif action.startswith("project_"):
        if request.POST.get("revision") != str(draft.revision):
            form = ProjectForm({key: request.POST.get(key, "") for key in ProjectForm.base_fields}, project_name=project.name)
            form.add_error(None, "This draft changed in another tab. Reload before saving; your unsaved text is still shown.")
        elif action == "project_omit":
            if request.POST.get("confirm") == "yes":
                if project_id not in draft.omitted_projects:
                    draft.omitted_projects.append(project_id)
                    ProjectDraft.objects.filter(draft=draft, project_id=project_id).delete()
                draft.revision += 1
                next_positions = [i for i in range(position + 1, len(ids)) if ids[i] not in draft.omitted_projects]
                if next_positions:
                    position = next_positions[0]
                else:
                    draft.stage = "project_review"
            else:
                message = "Confirm removal before discarding this project's answers. No replacement project will be added."
        elif action in {"project_next", "project_back", "project_save"} and available:
            form = ProjectForm({key: request.POST.get(key, "") for key in ProjectForm.base_fields}, project_name=project.name)
            valid = form.is_valid()
            saved_answers = form.cleaned_data if valid else {key: request.POST.get(key, "") for key in ProjectForm.base_fields}
            if action == "project_back" and not saved_answers.get("J3") and (row is None or "J3" not in row.answers):
                saved_answers.pop("J3", None)  # Back alone does not complete an unanswered optional slot.
            ProjectDraft.objects.update_or_create(draft=draft, project_id=project_id, defaults={"answers": saved_answers})
            draft.revision += 1
            if valid and action == "project_next":
                next_positions = [i for i in range(position + 1, len(ids)) if ids[i] not in draft.omitted_projects]
                if next_positions:
                    position = next_positions[0]
                else:
                    draft.stage = "project_review"
            elif action == "project_back":
                previous = [i for i in range(position) if ids[i] not in draft.omitted_projects]
                if previous:
                    position = previous[-1]
                else:
                    draft.stage = "personal"
            elif valid:
                message = "Project answers saved. No feedback has been submitted."
    elif claimed:
        draft.stage = "projects"
    incomplete = False
    if draft.stage == "project_review":
        saved_answers = {row.project_id: row.answers for row in ProjectDraft.objects.filter(draft=draft)}
        for index, pid in enumerate(ids):
            if pid not in draft.omitted_projects and (
                (pid, scopes[index][1]) not in eligible or not ProjectForm(
                    saved_answers.get(pid, {}), project_name=projects[pid].name
                ).is_valid()
            ):
                position = index
                draft.stage = "projects"
                incomplete = True
                message = "Complete or explicitly remove this section before continuing. Your other answers are preserved."
                break
    moved = position != ids.index(project_id)
    draft.project_position = position
    draft.save(update_fields=["project_position", "omitted_projects", "revision", "stage"])
    if moved or incomplete:
        project_id, window_id = scopes[position]
        project = projects[project_id]
        row = ProjectDraft.objects.filter(draft=draft, project_id=project_id).first()
        form = ProjectForm(row.answers if row else {}, project_name=project.name) if incomplete else ProjectForm(
            initial=row.answers if row else {}, project_name=project.name)
        available = (project_id, window_id) in eligible and project_id not in draft.omitted_projects
    stored = {row.project_id: row.answers for row in ProjectDraft.objects.filter(draft=draft)}
    resolved = len(draft.omitted_projects) + sum(
        ProjectForm(values, project_name=projects[pid].name).is_valid()
        for pid, values in stored.items() if pid not in draft.omitted_projects)
    return {"project_form": form, "current_project": project, "project_number": position + 1,
            "project_total": len(ids), "project_resolved": resolved, "project_available": available,
            "project_message": message, "project_sections": [projects[pid] for pid in ids if pid not in draft.omitted_projects],
            "no_projects_left": len(draft.omitted_projects) == len(ids)}
