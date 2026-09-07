"""Explicit synthetic directory, never account-email fallback."""
from uuid import UUID

from django.conf import settings

from signal_loop.admission.services import VerifiedPrincipal

from .services import VerifiedPrimaryContact


def principal(user, organisation):
    values = {"synthetic_invitation_rowan": 1, "synthetic_invitation_alias": 1, "synthetic_invitation_avery": 2}
    if getattr(settings, "INVITATION_REVIEW_MODE", False) and user.username in values:
        return VerifiedPrincipal(UUID(f"30000000-0000-4000-8000-{values[user.username]:012d}"))
    return None


def contact(identifier, organisation):
    if not getattr(settings, "INVITATION_REVIEW_MODE", False):
        return None
    values = {UUID("30000000-0000-4000-8000-000000000001"): "rowan.primary@example.com",
              UUID("30000000-0000-4000-8000-000000000002"): "avery.primary@example.com"}
    return VerifiedPrimaryContact(identifier, (values[identifier],)) if identifier in values else None
