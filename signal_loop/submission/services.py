"""Narrow atomic admission/persistence boundary; no durable identity-feedback join."""
from django.db import transaction
from django.utils import timezone

from signal_loop.admission.services import AdmissionError, own_status, redeem, refresh_credentials
from signal_loop.contracts.feedback import is_substantive, normalize_sections
from signal_loop.feedback.services import persist_sections


def submit_check_in(*, user, organisation, week, scopes, prepare_draft, clear_draft,
                    provider, clock=timezone.now, sink=persist_sections):
    """Callbacks own private draft validation/cleanup on the same DB connection.

    Scope locks precede all draft writes. Errors roll back credential refresh,
    consumption, anonymous rows and cleanup. Status reconciliation reads admission
    only, including when a replay arrives after the credential/window expired.
    """
    try:
        if own_status(user=user, organisation=organisation, week=week, provider=provider, clock=clock) == "complete":
            return "complete"
        with transaction.atomic():
            if not scopes:
                if prepare_draft():
                    raise AdmissionError("invalid_submission")
                return "no_feedback"
            issuance = refresh_credentials(user=user, week=week, scopes=scopes, provider=provider, clock=clock)
            sections = prepare_draft()
            if not sections:
                raise AdmissionError("no_feedback")  # roll back temporary verifier rotations too

            def persist_at_admission(anonymous, admitted_at):
                # This instant was verified under the held window locks. A pre-close
                # admission can commit after closure; #24 waits for these same locks.
                if sink(anonymous, clock=lambda: admitted_at) != "complete":
                    raise AdmissionError("retryable_failure")

            submitted = {section["project"] for section in sections}
            claims = tuple(claim for claim in issuance.credentials if claim.project in submitted)
            return redeem(user=user, week=week, claims=claims, sections=sections,
                          admitted_sink=persist_at_admission, clear_draft=clear_draft,
                          provider=provider, clock=clock)
    except AdmissionError as error:
        code = error.code
    except Exception:
        code = "retryable_failure"
    try:
        if own_status(user=user, organisation=organisation, week=week, provider=provider, clock=clock) == "complete":
            return "complete"
    except Exception:
        pass
    return code if code in {"invalid_submission", "unavailable", "conflict", "retryable_failure", "no_feedback"} else "unavailable"


def preview_submission(sections):
    normalized = normalize_sections(sections)
    if not any(is_substantive(section) for section in normalized):
        return "no_feedback"
    return "preview_complete"
