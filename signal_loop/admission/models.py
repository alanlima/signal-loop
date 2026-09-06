"""Restricted identity-side state: no response content or feedback identifiers."""
from django.db import models


class Principal(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)

    class Meta:
        default_permissions = ()


class Journey(models.Model):
    class State(models.TextChoices):
        OPEN = "open"
        COMPLETED = "completed"
        DISCARDED = "discarded"
        EXPIRED = "expired"

    principal = models.ForeignKey(Principal, on_delete=models.CASCADE)
    week = models.DateField()
    state = models.CharField(max_length=10, choices=State.choices, default=State.OPEN)
    # Transient fields are cleared when sealed. No actual draft answers live here.
    started_at = models.DateTimeField(null=True)
    expires_at = models.DateTimeField(null=True)
    selected_scopes = models.JSONField(default=list)
    retain_until = models.DateTimeField()

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["principal", "week"], name="one_principal_global_journey"),
            models.CheckConstraint(condition=models.Q(state__in=["open", "completed", "discarded", "expired"]),
                                   name="valid_journey_state"),
        ]


class Participation(models.Model):
    principal = models.ForeignKey(Principal, on_delete=models.CASCADE)
    project = models.ForeignKey("membership.Project", on_delete=models.PROTECT)
    window = models.ForeignKey("windows.WeeklyWindow", on_delete=models.PROTECT)
    consumed = models.BooleanField(default=False)
    retain_until = models.DateTimeField()

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=["principal", "project", "window"],
                                                name="one_principal_project_window")]


class Credential(models.Model):
    participation = models.OneToOneField(Participation, on_delete=models.CASCADE)
    verifier = models.CharField(max_length=64, unique=True)
    purpose = models.CharField(max_length=20, default="project-feedback-v1")
    expires_at = models.DateTimeField()
    active = models.BooleanField(default=True)

    class Meta:
        default_permissions = ()
