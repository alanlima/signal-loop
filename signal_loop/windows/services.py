"""Trusted admission boundary; callers supply the authenticated user, never a URL user ID."""
from dataclasses import dataclass
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.utils import timezone

from .models import EligibilitySnapshot, WeeklyWindow


@dataclass(frozen=True)
class EligibleProject:
    window_id: int
    project_id: int
    project_name: str
    role_at_open: str


def create_weekly_window(*, organisation, week_start, timezone_name):
    return WeeklyWindow.objects.create(organisation=organisation, week_start=week_start,
                                       timezone_name=timezone_name)


def eligible_projects(*, user, organisation, at=None):
    at = timezone.now() if at is None else at
    if timezone.is_naive(at):
        raise ValidationError("Lookup requires an aware instant.")
    if not user.is_authenticated or not user.is_active:
        return ()
    rows = EligibilitySnapshot.objects.filter(
        window__organisation=organisation, window__opens_at__lte=at, window__closes_at__gt=at,
        membership__organisation_membership__user=user,
        membership__organisation_membership__user__is_active=True,
        membership__organisation_membership__is_active=True,
        membership__organisation_membership__organisation__is_active=True,
        membership__is_active=True, membership__project__is_active=True,
    ).select_related("membership__project")
    results = [EligibleProject(row.window_id, row.membership.project_id,
                               row.membership.project.name, row.role) for row in rows]
    return tuple(sorted(results, key=lambda item: (item.project_name.casefold(), item.project_id)))


def expire_eligibility(*, at=None):
    """Operations-only deletion; schedule wiring belongs to #38."""
    at = timezone.now() if at is None else at
    if timezone.is_naive(at):
        raise ValidationError("Expiry requires an aware instant.")
    expired = EligibilitySnapshot.objects.filter(window__closes_at__lte=at - timedelta(days=7))
    return QuerySet.delete(expired)
