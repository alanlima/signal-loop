"""Anonymous project-local sources; no identity or cross-project relationships."""
import uuid

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
    answers = models.JSONField()
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
