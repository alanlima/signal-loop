"""Validated mutations; callers must separately enforce request authorization."""

from .models import ProjectMembership


def assign_project_member(*, project, organisation_membership, role):
    return ProjectMembership.objects.create(
        project=project, organisation_membership=organisation_membership, role=role,
    )


def change_membership(*, membership, role=None, is_active=None):
    if role is not None:
        membership.role = role
    if is_active is not None:
        membership.is_active = is_active
    membership.save()
    return membership
