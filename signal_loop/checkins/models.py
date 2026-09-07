"""Private transient reflection; never submitted feedback or admin-visible data."""
from django.db import models


class PersonalDraft(models.Model):
    journey = models.OneToOneField("admission.Journey", on_delete=models.CASCADE)
    answers = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=0)
    stage = models.CharField(max_length=20, default="personal")
    expires_at = models.DateTimeField()
    project_position = models.PositiveSmallIntegerField(default=0)
    omitted_projects = models.JSONField(default=list)
    seen_slots = models.JSONField(default=list)
    adaptive_allocated = models.BooleanField(default=False)
    adaptive_slots = models.JSONField(default=list)
    adaptive_answers = models.JSONField(default=dict)

    class Meta:
        default_permissions = ()


class ProjectDraft(models.Model):
    draft = models.ForeignKey(PersonalDraft, on_delete=models.CASCADE, related_name="project_answers")
    project_id = models.PositiveBigIntegerField()
    answers = models.JSONField(default=dict)

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=["draft", "project_id"], name="one_draft_project_section")]
