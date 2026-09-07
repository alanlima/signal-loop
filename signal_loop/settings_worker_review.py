"""Explicit synthetic-only scheduling review with local console mail."""
from .settings_worker import *  # noqa: F403

INVITATION_REVIEW_MODE = True
CHECKIN_PRINCIPAL_PROVIDER = "signal_loop.invitations.review.principal"
INVITATION_CONTACT_PROVIDER = "signal_loop.invitations.review.contact"
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
CELERY_BEAT_SCHEDULE = {
    "local-weekly-dispatch": {"task": "signal_loop.dispatch_due", "schedule": 2.0,
                              "args": ["40000000-0000-4000-8000-000000000001"]},
}
