"""Private draft helpers and explicit local fake progression, no feedback sink."""
from uuid import UUID

from django.conf import settings

from signal_loop.admission.services import VerifiedPrincipal


def advance_to_projects():
    """Placeholder progression seam until #17/#20; receives no reflection content."""
    return "projects"


def review_provider(user, organisation):
    if not getattr(settings, "CHECKIN_REVIEW_MODE", False):
        return None
    if user.username == "synthetic_personal_review":
        return VerifiedPrincipal(UUID("10000000-0000-4000-8000-000000000001"))
    return None


def review_progression():
    if getattr(settings, "CHECKIN_REVIEW_FAIL", False):
        raise RuntimeError("Synthetic progression failure")
    return advance_to_projects()
