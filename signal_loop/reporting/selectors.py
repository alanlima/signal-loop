"""Views receive an authorized safe projection, never candidate/provenance data."""
from copy import deepcopy

from signal_loop.authorization.permissions import Permission, has_permission
from .models import AudienceRelease
from .projections import unavailable, validate_content


def manager_report_for(user, *, project, week, at, closes_at):
    scope = str(project.pk)
    result = unavailable(scope, week)
    if not has_permission(user, Permission.READ_MANAGER_REPORT,
                          organisation_id=project.organisation_id, project_id=project.pk):
        return result
    if at < closes_at:
        return unavailable(scope, week, before_close=True)
    release = AudienceRelease.objects.filter(project=scope, week=week, audience="manager", state="ready",
                                              expires_at__gt=at).first()
    if release is None:
        return result
    try:
        content = deepcopy(release.content)
        validate_content(content, "manager")
    except Exception:
        return result
    return {**result, "status": "available", "content": content}


def team_summary_for(user, *, project, week, at, closes_at):
    scope = str(project.pk)
    result = unavailable(scope, week, "team")
    if not has_permission(user, Permission.READ_TEAM_REPORT,
                          organisation_id=project.organisation_id, project_id=project.pk):
        return result
    if at < closes_at:
        return unavailable(scope, week, "team", before_close=True)
    release = AudienceRelease.objects.filter(project=scope, week=week, audience="team", state="ready",
                                              expires_at__gt=at).first()
    if release is None:
        return result
    try:
        content = deepcopy(release.content)
        validate_content(content, "team")
    except Exception:
        return result
    return {**result, "status": "available", "content": content}
