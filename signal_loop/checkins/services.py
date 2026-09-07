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
    names = {"synthetic_personal_review": 1, "synthetic_journey_ordinary": 2,
             "synthetic_journey_many": 3, "synthetic_journey_zero": 4}
    if user.username in names:
        return VerifiedPrincipal(UUID(f"10000000-0000-4000-8000-{names[user.username]:012d}"))
    return None


def review_progression():
    if getattr(settings, "CHECKIN_REVIEW_FAIL", False):
        raise RuntimeError("Synthetic progression failure")
    return advance_to_projects()


def review_ai():
    from signal_loop.ai.adapter import Adapter
    from signal_loop.ai.fake import FakeProvider
    return Adapter(FakeProvider(script=(getattr(settings, "CHECKIN_REVIEW_AI_FAULT", "valid"),)))
