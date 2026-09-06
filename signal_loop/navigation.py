from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import patch_vary_headers

from signal_loop.authorization.permissions import Permission, has_permission
from signal_loop.membership.models import Project


DESTINATIONS = (
    ("application_entry", "Overview", Permission.READ_TEAM_REPORT),
    ("current_check_in", "Current check-in", Permission.CURRENT_CHECK_IN),
    ("team_reports", "Team reports", Permission.READ_TEAM_REPORT),
    ("manager_reports", "Manager reports", Permission.READ_MANAGER_REPORT),
)


def render_shell(request, destination="application_entry", *, extra_context=None):
    candidates = Project.objects.filter(
        memberships__organisation_membership__user=request.user,
    ).select_related("organisation").distinct().order_by("name", "pk")
    projects = [project for project in candidates if has_permission(
        request.user, Permission.READ_TEAM_REPORT,
        organisation_id=project.organisation_id, project_id=project.pk,
    )]
    selected = projects[0] if projects else None
    if "project" in request.GET:
        values = request.GET.getlist("project")
        value = values[0]
        if len(values) != 1 or not value.isascii() or not value.isdecimal():
            return HttpResponse("Not found.", status=404, content_type="text/plain")
        selected = next((project for project in projects if str(project.pk) == value), None)
        if selected is None:
            return HttpResponse("Not found.", status=404, content_type="text/plain")
    navigation = []
    title = "Overview"
    for name, label, permission in DESTINATIONS:
        permitted = selected is not None and has_permission(
            request.user, permission, organisation_id=selected.organisation_id, project_id=selected.pk,
        )
        if name == destination:
            title = label
            if not permitted and name != "application_entry":
                return HttpResponse("Not found.", status=404, content_type="text/plain")
        if permitted:
            navigation.append({"url": f"{reverse(name)}?project={selected.pk}",
                               "label": label, "current": name == destination})
    is_fragment = (request.headers.get("HX-Request") == "true"
                   and request.headers.get("HX-History-Restore-Request") != "true")
    context = {"projects": projects, "selected_project": selected, "navigation": navigation,
               "page_title": title, "destination": destination, "is_fragment": is_fragment}
    context.update(extra_context or {})
    template = "accounts/shell_panel.html" if is_fragment else "accounts/entry.html"
    response = render(request, template, context)
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    response["Cache-Control"] = "private, no-store"
    return response
