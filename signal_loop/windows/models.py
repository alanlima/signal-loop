"""Identity-side window eligibility; never import these records into feedback/reporting."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import models, transaction

from signal_loop.membership.models import Organisation, ProjectMembership, Role


def weekly_bounds(week_start, timezone_name):
    if week_start.weekday() != 0:
        raise ValidationError("Week identity must be a local Monday date.")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValidationError("Use a valid IANA timezone.") from exc
    boundaries = []
    for day in (week_start, week_start + timedelta(days=7)):
        local = datetime.combine(day, time.min, tzinfo=zone)
        utc = local.astimezone(timezone.utc)
        # Do not silently normalize a nonexistent local midnight.
        if utc.astimezone(zone).replace(tzinfo=None) != local.replace(tzinfo=None):
            raise ValidationError("This timezone has a nonexistent Monday midnight.")
        boundaries.append(utc)
    return tuple(boundaries)


class ImmutableQuerySet(models.QuerySet):
    def delete(self):
        raise TypeError("Use the operations expiry service to remove snapshots.")

    def update(self, **kwargs):
        raise TypeError("Window and snapshot records are immutable.")

    def bulk_create(self, *args, **kwargs):
        raise TypeError("Create windows through validated saves.")

    def bulk_update(self, *args, **kwargs):
        raise TypeError("Window and snapshot records are immutable.")


class WeeklyWindow(models.Model):
    organisation = models.ForeignKey(Organisation, on_delete=models.PROTECT)
    timezone_name = models.CharField(max_length=100)
    week_start = models.DateField()
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    objects = ImmutableQuerySet.as_manager()

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["organisation", "week_start"], name="unique_org_local_week"),
            models.CheckConstraint(condition=models.Q(opens_at__lt=models.F("closes_at")),
                                   name="window_opens_before_close"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Window schedule and snapshots are immutable.")
        self.opens_at, self.closes_at = weekly_bounds(self.week_start, self.timezone_name)
        with transaction.atomic():
            # All supported writers lock the same durable row, even when no window exists.
            Organisation.objects.select_for_update().get(pk=self.organisation_id)
            if type(self).objects.filter(organisation_id=self.organisation_id,
                                         opens_at__lt=self.closes_at, closes_at__gt=self.opens_at).exists():
                raise ValidationError("This organisation already has an overlapping window.")
            self.full_clean()
            super().save(*args, **kwargs)
            assignments = ProjectMembership.objects.filter(
                project__organisation_id=self.organisation_id, project__organisation__is_active=True,
                project__is_active=True, is_active=True, organisation_membership__is_active=True,
                organisation_membership__user__is_active=True,
            ).order_by("pk")
            for assignment in assignments:
                snapshot = EligibilitySnapshot(window=self, membership=assignment, role=assignment.role)
                snapshot.save(_capture=True)

    def delete(self, *args, **kwargs):
        raise TypeError("Window schedules are retained.")


class EligibilitySnapshot(models.Model):
    window = models.ForeignKey(WeeklyWindow, on_delete=models.CASCADE, related_name="eligibility")
    membership = models.ForeignKey(ProjectMembership, on_delete=models.PROTECT, related_name="window_snapshots")
    role = models.CharField(max_length=7, choices=Role.choices)
    objects = ImmutableQuerySet.as_manager()

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["window", "membership"], name="unique_window_membership"),
            models.CheckConstraint(condition=models.Q(role__in=Role.values), name="valid_snapshot_role"),
        ]

    def save(self, *args, **kwargs):
        capture = kwargs.pop("_capture", False)
        if not self._state.adding or not capture:
            raise ValidationError("Eligibility snapshots are immutable.")
        if self.membership.project.organisation_id != self.window.organisation_id:
            raise ValidationError("Snapshot membership must belong to the window organisation.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Use the operations expiry service to remove snapshots.")
