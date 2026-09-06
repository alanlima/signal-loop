"""Private transient reflection; never submitted feedback or admin-visible data."""
from django.db import models


class PersonalDraft(models.Model):
    journey = models.OneToOneField("admission.Journey", on_delete=models.CASCADE)
    answers = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=0)
    stage = models.CharField(max_length=12, default="personal")
    expires_at = models.DateTimeField()

    class Meta:
        default_permissions = ()
