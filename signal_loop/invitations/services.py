from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.module_loading import import_string

from signal_loop.admission.services import VerifiedPrincipal
from signal_loop.windows.models import EligibilitySnapshot, WeeklyWindow

from .models import InvitationDelivery


@dataclass(frozen=True)
class VerifiedPrimaryContact:
    principal: UUID
    # Zero/multiple designated addresses are withheld, never guessed.
    addresses: tuple[str, ...] = field(repr=False)


class DefiniteDeliveryFailure(Exception):
    """Transport guarantees it did not accept the message; retry is permitted."""
    def __init__(self):
        super().__init__("delivery_failed")


def _configured(name):
    value = getattr(settings, name, None)
    return import_string(value) if isinstance(value, str) else value


def _principals(window, provider):
    rows = EligibilitySnapshot.objects.filter(
        window=window, membership__is_active=True, membership__project__is_active=True,
        membership__project__organisation__is_active=True,
        membership__organisation_membership__is_active=True,
        membership__organisation_membership__user__is_active=True,
    ).select_related("membership__organisation_membership__user")
    users = {row.membership.organisation_membership.user_id: row.membership.organisation_membership.user for row in rows}
    principals = set()
    unresolved = 0
    for user in users.values():
        try:
            value = provider(user, window.organisation) if provider else None
        except Exception:
            value = None
        if type(value) is VerifiedPrincipal and type(value.id) is UUID:
            principals.add(value.id)
        else:
            unresolved += 1
    return principals, unresolved


def _address(principal, organisation, provider):
    try:
        contact = provider(principal, organisation) if provider else None
        if (type(contact) is not VerifiedPrimaryContact or contact.principal != principal
                or type(contact.addresses) is not tuple or len(contact.addresses) != 1):
            return None
        address = contact.addresses[0]
        if type(address) is not str or "\r" in address or "\n" in address:
            return None
        validate_email(address)
        return address
    except Exception:
        return None


def entry_url():
    origin = getattr(settings, "INVITATION_ORIGIN", "http://127.0.0.1:8000")
    parsed = urlsplit(origin)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValidationError("invitation_configuration_invalid")
    return origin.rstrip("/") + reverse("current_check_in")


def deliver(address):
    context = {"entry_url": entry_url()}
    message = EmailMultiAlternatives(
        "Your weekly check-in is open", render_to_string("invitations/open.txt", context),
        settings.DEFAULT_FROM_EMAIL, [address],
    )
    message.attach_alternative(render_to_string("invitations/open.html", context), "text/html")
    if message.send(fail_silently=False) != 1:
        raise DefiniteDeliveryFailure()


def send_window_invitations(*, window_id, principal_provider=None, contact_provider=None,
                            transport=deliver, clock=timezone.now):
    """#24 handoff: retry this window; durable sent/ambiguous rows are skipped.

    Transport occurs after a committed claim, never inside the DB transaction.
    No default identity/contact fallback. Only server configuration supplies providers.
    """
    counts = dict(sent=0, skipped=0, failed=0, ambiguous=0, withheld=0)
    try:
        principal_provider = principal_provider or _configured("CHECKIN_PRINCIPAL_PROVIDER")
        contact_provider = contact_provider or _configured("INVITATION_CONTACT_PROVIDER")
        at = clock()
        if timezone.is_naive(at) or type(window_id) is not int:
            return {**counts, "code": "invalid_window"}
        window = WeeklyWindow.objects.select_related("organisation").get(pk=window_id)
        if not window.opens_at <= at < window.closes_at or not window.organisation.is_active:
            return {**counts, "code": "window_unavailable"}
        entry_url()  # Invalid configuration must not create an ambiguous send.
        principals, unresolved = _principals(window, principal_provider)
        counts["withheld"] += unresolved
    except Exception:
        return {**counts, "code": "configuration_or_window_unavailable"}
    for principal in sorted(principals, key=str):
        try:
            with transaction.atomic():
                locked = WeeklyWindow.objects.select_for_update(of=("self",)).select_related("organisation").get(pk=window_id)
                at = clock()
                if not locked.opens_at <= at < locked.closes_at:
                    counts["withheld"] += 1
                    continue
                row, _ = InvitationDelivery.objects.get_or_create(
                    window=locked, principal=principal,
                    defaults={"retain_until": locked.closes_at + timedelta(days=7)},
                )
                if row.state == row.State.SENDING and row.attempt_started_at <= at - timedelta(minutes=2):
                    row.state = row.State.AMBIGUOUS
                    row.save(update_fields=["state"])
                if row.state in {row.State.SENT, row.State.SENDING, row.State.AMBIGUOUS}:
                    counts["ambiguous" if row.state == row.State.AMBIGUOUS else "skipped"] += 1
                    continue
                current, _ = _principals(locked, principal_provider)
                address = _address(principal, locked.organisation, contact_provider) if principal in current else None
                at = clock()
                if address is None or not locked.opens_at <= at < locked.closes_at:
                    row.state = row.State.WITHHELD
                    row.save(update_fields=["state"])
                    counts["withheld"] += 1
                    continue
                row.state = row.State.SENDING
                row.attempts += 1
                row.attempt_started_at = at
                row.save(update_fields=["state", "attempts", "attempt_started_at"])
            # A crash here leaves SENDING, later quarantined as AMBIGUOUS. A
            # crash after acceptance but before SENT cannot cause automatic resend.
            try:
                transport(address)
                outcome = InvitationDelivery.State.SENT
            except DefiniteDeliveryFailure:
                outcome = InvitationDelivery.State.FAILED
            except Exception:
                outcome = InvitationDelivery.State.AMBIGUOUS
            updated = InvitationDelivery.objects.filter(pk=row.pk, state=InvitationDelivery.State.SENDING).update(state=outcome)
            counts[outcome if updated else "ambiguous"] += 1
        except Exception:
            counts["ambiguous"] += 1
    return {**counts, "code": "complete"}


def expire_deliveries(*, at=None):
    at = timezone.now() if at is None else at
    return InvitationDelivery.objects.filter(retain_until__lte=at).delete()
