"""Application-role permissions; raw analysis data has no human-role grant."""

from enum import StrEnum

from signal_loop.membership.models import OrganisationMembership, ProjectMembership, Role


class Permission(StrEnum):
    ADMINISTER_ORGANISATION = "administer_organisation"
    CURRENT_CHECK_IN = "current_check_in"
    READ_TEAM_REPORT = "read_team_report"
    READ_MANAGER_REPORT = "read_manager_report"
    PUBLISH_COMMITMENT = "publish_commitment"
    READ_RAW_FEEDBACK = "read_raw_feedback"


def _valid_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def has_permission(user, permission, *, organisation_id=None, project_id=None):
    if not isinstance(permission, str):
        return False
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    if not _valid_id(organisation_id):
        return False
    if permission == Permission.ADMINISTER_ORGANISATION:
        return project_id is None and OrganisationMembership.objects.filter(
            user_id=user.pk, user__is_active=True, organisation_id=organisation_id,
            organisation__is_active=True, is_active=True, role=Role.MANAGER,
        ).exists()
    allowed_project_permissions = {
        Permission.CURRENT_CHECK_IN, Permission.READ_TEAM_REPORT,
        Permission.READ_MANAGER_REPORT, Permission.PUBLISH_COMMITMENT,
    }
    if permission not in allowed_project_permissions or not _valid_id(project_id):
        return False
    memberships = ProjectMembership.objects.filter(
        project_id=project_id, project__organisation_id=organisation_id,
        project__organisation__is_active=True, project__is_active=True, is_active=True,
        organisation_membership__organisation_id=organisation_id,
        organisation_membership__is_active=True,
        organisation_membership__user_id=user.pk,
        organisation_membership__user__is_active=True,
        role__in=Role.values,
        organisation_membership__role__in=Role.values,
    )
    if permission in {Permission.READ_MANAGER_REPORT, Permission.PUBLISH_COMMITMENT}:
        memberships = memberships.filter(role=Role.MANAGER)
    return memberships.exists()
