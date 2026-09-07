"""Synthetic opening email review; always local console, even if SMTP env is set."""
from .settings import *  # noqa: F403

INVITATION_REVIEW_MODE = True
CHECKIN_PRINCIPAL_PROVIDER = "signal_loop.invitations.review.principal"
INVITATION_CONTACT_PROVIDER = "signal_loop.invitations.review.contact"
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
