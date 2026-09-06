"""Anonymous project-local sources; no identity or cross-project relationships."""
import uuid
from copy import deepcopy
from datetime import timezone

from django.db import models


class RestrictedQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise TypeError("Submitted feedback is immutable.")

    def bulk_create(self, *args, **kwargs):
        raise TypeError("Use the validated persistence service.")

    def bulk_update(self, *args, **kwargs):
        raise TypeError("Submitted feedback is immutable.")

    def delete(self):
        raise TypeError("Use the operations expiry/withdrawal boundary.")


class FeedbackSection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_id = models.PositiveBigIntegerField()
    week = models.DateField()
    schema = models.CharField(max_length=40)
    privacy_policy = models.CharField(max_length=20)
    data = models.JSONField()
    provenance = models.JSONField(default=dict)
    expires_at = models.DateTimeField()
    objects = RestrictedQuerySet.as_manager()

    class Meta:
        default_permissions = ()
        indexes = [models.Index(fields=["project_id", "week"], name="feedback_project_week")]

    def save(self, *args, **kwargs):
        validated = kwargs.pop("_validated", False)
        if not self._state.adding or not validated:
            raise TypeError("Use the validated persistence service; submitted feedback is immutable.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Use the operations expiry/withdrawal boundary.")

    def as_artifact(self):
        """Restricted in-process artifact for workers/tests; never an admission result."""
        return {"schema": self.schema, "project": str(self.project_id), "week": self.week.isoformat(),
                "privacy_policy": self.privacy_policy,
                "expires_at": self.expires_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "provenance": deepcopy(self.provenance), "data": deepcopy(self.data)}
