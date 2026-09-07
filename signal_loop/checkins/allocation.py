"""Durable private-draft implementation of #19's allocation/claim contract."""
from dataclasses import asdict

from django.db import transaction
from django.utils import timezone

from .followups import Slot
from .models import PersonalDraft


class DraftAllocationStore:
    def __init__(self, draft_id):
        self.draft_id = draft_id

    def _draft(self):
        draft = PersonalDraft.objects.select_for_update().select_related("journey").get(pk=self.draft_id)
        if draft.journey.state != "open" or timezone.now() >= draft.expires_at:
            raise ValueError("unavailable")
        return draft

    def reserve_once(self, slots):
        with transaction.atomic():
            draft = self._draft()
            if not draft.adaptive_allocated:
                draft.adaptive_slots = [{"slot": asdict(slot), "state": "reserved"} for slot in slots]
                draft.adaptive_allocated = True
                draft.save(update_fields=["adaptive_slots", "adaptive_allocated"])
            return tuple(Slot(**row["slot"]) for row in draft.adaptive_slots)

    def claim(self, slot):
        with transaction.atomic():
            draft = self._draft()
            for row in draft.adaptive_slots:
                if row["slot"] == asdict(slot) and row["state"] == "reserved":
                    row["state"] = "claimed"
                    draft.save(update_fields=["adaptive_slots"])
                    return True
            return False

    def record(self, slot, decision):
        with transaction.atomic():
            draft = self._draft()
            for row in draft.adaptive_slots:
                if row["slot"] == asdict(slot) and row["state"] == "claimed":
                    row["state"] = decision.outcome.value
                    draft.save(update_fields=["adaptive_slots"])
                    return
            raise ValueError("unavailable")
