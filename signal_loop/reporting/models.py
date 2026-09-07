"""Separate expiring restricted candidates and immutable safe audience releases."""
import uuid

from django.db import models


class OwnedQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise TypeError("Use the reporting service.")

    def delete(self):
        raise TypeError("Use reporting withdrawal or expiry.")

    def bulk_create(self, *args, **kwargs):
        raise TypeError("Use the reporting service.")

    def bulk_update(self, *args, **kwargs):
        raise TypeError("Use the reporting service.")


class OwnedModel(models.Model):
    objects = OwnedQuerySet.as_manager()

    class Meta:
        abstract = True
        default_permissions = ()

    def save(self, *args, **kwargs):
        if not self._state.adding or not kwargs.pop("_validated", False):
            raise TypeError("Use the reporting service.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Use reporting withdrawal or expiry.")


class ManagerReport(OwnedModel):
    project = models.CharField(max_length=64)
    week = models.DateField()
    analysis_version = models.CharField(max_length=64)
    schema = models.CharField(max_length=40, default="manager-report/1.0")
    privacy_policy = models.CharField(max_length=20, default="1.0")
    state = models.CharField(max_length=16)
    artifact = models.JSONField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta(OwnedModel.Meta):
        constraints = [models.UniqueConstraint(
            fields=["project", "week", "analysis_version", "schema", "privacy_policy"], name="manager_candidate_key")]


class AudienceRelease(OwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.CharField(max_length=64)
    week = models.DateField()
    audience = models.CharField(max_length=10, choices=[("manager", "Manager"), ("team", "Team")])
    privacy_policy = models.CharField(max_length=20, default="1.0")
    state = models.CharField(max_length=16, default="ready")
    content = models.JSONField(null=True, blank=True)
    released_at = models.DateTimeField()
    expires_at = models.DateTimeField()

    class Meta(OwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["project", "week", "audience"], name="one_audience_release")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("A published release cannot be replaced.")
        return super().save(*args, **kwargs)
