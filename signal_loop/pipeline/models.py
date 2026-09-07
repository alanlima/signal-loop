"""Durable scheduler/outbox state; no identities or response bodies."""
import uuid

from django.core.exceptions import ValidationError
from django.db import models

from signal_loop.membership.models import Organisation
from signal_loop.windows.models import WeeklyWindow, weekly_bounds


class OrganisationSchedule(models.Model):
    organisation = models.OneToOneField(Organisation, on_delete=models.PROTECT)
    timezone_name = models.CharField(max_length=100)
    enabled = models.BooleanField(default=True)

    class Meta:
        default_permissions = ()

    def save(self, *args, **kwargs):
        from datetime import date
        weekly_bounds(date(2026, 9, 7), self.timezone_name)
        self.full_clean()
        return super().save(*args, **kwargs)


class WindowDispatch(models.Model):
    window = models.OneToOneField(WeeklyWindow, on_delete=models.PROTECT)
    captured_late = models.BooleanField(default=False)
    projects = models.JSONField(default=list)
    frozen = models.BooleanField(default=False)

    class Meta:
        default_permissions = ()


class DispatchJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=10, choices=[("invitation", "Invitation"), ("analysis", "Analysis")])
    window = models.ForeignKey(WeeklyWindow, on_delete=models.PROTECT)
    project_id = models.PositiveBigIntegerField(null=True)
    week = models.DateField()
    version = models.CharField(max_length=64, default="analysis1-privacy1-fake1")
    # Restricted scope-local references only; no shared person/submission identifier.
    frozen_sources = models.JSONField(default=list)
    state = models.CharField(max_length=12, default="pending")
    enqueue_after = models.DateTimeField()
    enqueue_lease_until = models.DateTimeField(null=True)
    run_lease_until = models.DateTimeField(null=True)
    run_token = models.UUIDField(null=True)
    expires_at = models.DateTimeField()

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["window", "version"], condition=models.Q(kind="invitation"), name="unique_invitation_dispatch"),
            models.UniqueConstraint(fields=["project_id", "week", "version"], condition=models.Q(kind="analysis"), name="unique_versioned_analysis_job"),
            models.CheckConstraint(condition=models.Q(kind="invitation", project_id__isnull=True) | models.Q(kind="analysis", project_id__isnull=False), name="valid_dispatch_kind_scope"),
            models.CheckConstraint(condition=models.Q(state__in=["pending", "queued", "running", "complete", "unavailable", "expired"]), name="valid_dispatch_job_state"),
        ]

    def clean(self):
        if self.week != self.window.week_start:
            raise ValidationError("invalid_job_scope")
