"""Identity-side invitation delivery only; never join to response content."""
from django.db import models

from signal_loop.windows.models import WeeklyWindow


class InvitationDelivery(models.Model):
    class State(models.TextChoices):
        PENDING = "pending"
        SENDING = "sending"
        SENT = "sent"
        FAILED = "failed"
        AMBIGUOUS = "ambiguous"
        WITHHELD = "withheld"

    window = models.ForeignKey(WeeklyWindow, on_delete=models.CASCADE)
    principal = models.UUIDField()
    state = models.CharField(max_length=10, choices=State.choices, default=State.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    attempt_started_at = models.DateTimeField(null=True)
    retain_until = models.DateTimeField()

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["window", "principal"], name="one_invitation_principal_window"),
            models.CheckConstraint(condition=models.Q(state__in=["pending", "sending", "sent", "failed", "ambiguous", "withheld"]),
                                   name="valid_invitation_state"),
        ]
