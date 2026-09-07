from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import re
from unittest.mock import Mock, patch

import pytest
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings

from signal_loop.admission.models import Journey, Participation
from signal_loop.ai.adapter import Adapter
from signal_loop.ai.fake import FakeProvider
from signal_loop.checkins.allocation import DraftAllocationStore
from signal_loop.checkins.followups import Slot
from signal_loop.checkins.models import PersonalDraft, ProjectDraft
from signal_loop.checkins.tests import test_projects
from signal_loop.feedback.models import FeedbackSection


pytestmark = pytest.mark.usefixtures("postgres_database")


class JourneyTests(TestCase):
    setUpTestData = classmethod(test_projects.ProjectFormTests.setUpTestData.__func__)
    setUp = test_projects.ProjectFormTests.setUp
    begin = test_projects.ProjectFormTests.begin
    post = test_projects.ProjectFormTests.post

    def action(self, action, **values):
        return self.client.post("/app/check-in/", {"action": action,
            "revision": PersonalDraft.objects.get().revision, **values})

    def test_ordinary_journey_fixed_progress_and_preview_excludes_personal(self):
        self.begin()
        self.post(0)
        response = self.post(1)
        self.assertContains(response, "13 of 13 question slots complete")
        self.assertContains(response, "Finish and review saved answers")
        fake = Mock(return_value="preview_complete")
        with override_settings(CHECKIN_FINAL_SUBMISSION=fake):
            response = self.action("preview_submit")
        self.assertContains(response, "Practice finish complete. No feedback was submitted")
        payload = fake.call_args.args[0]
        self.assertEqual(len(payload), 2)
        self.assertNotIn("private personal", str(payload))
        self.assertFalse(FeedbackSection.objects.exists())
        self.assertFalse(Participation.objects.filter(consumed=True).exists())
        self.assertEqual(Journey.objects.get().state, "open")
        self.assertTrue(PersonalDraft.objects.exists())

    def test_many_projects_two_adaptive_slots_skip_resume_and_no_refill(self):
        self.begin(3)
        self.post(0, J1="blocked")
        self.post(1, J2="overloaded")
        response = self.post(2, J1="at_risk")
        self.assertContains(response, "14 of 16 question slots complete")
        draft = PersonalDraft.objects.get()
        self.assertEqual(len(draft.adaptive_slots), 2)
        first = f"{self.projects[0].pk}:F1"
        response = self.action("adaptive_skip", question=first)
        self.assertContains(response, "15 of 16 question slots complete")
        self.assertContains(response, "workload in Cedar more manageable")
        second = f"{self.projects[1].pk}:F2"
        response = self.action("adaptive_next", question=second, answer="Synthetic shared rota")
        self.assertContains(response, "16 of 16 question slots complete")
        factory = Mock(side_effect=AssertionError("must not replenish"))
        with override_settings(CHECKIN_AI_FACTORY=factory):
            response = self.client.get("/app/check-in/")
            self.action("resume_questions")
        factory.assert_not_called()
        self.assertContains(response, "Synthetic shared rota")
        self.assertEqual(len(PersonalDraft.objects.get().adaptive_slots), 2)

    def test_boundary_post_preserves_current_text_and_never_introduces_unseen_project(self):
        self.begin()
        journey = Journey.objects.get()
        started = journey.started_at
        with patch("signal_loop.checkins.views.timezone.now", return_value=started + timedelta(seconds=600)):
            response = self.post(0, J3="Typed at the boundary")
            self.assertContains(response, "ten-minute question time has ended")
            self.assertContains(response, "Typed at the boundary")
            self.assertNotContains(response, "How is delivery going in Cedar")
            self.assertContains(response, "This section was not seen")
            response = self.action("finish_omit", section=self.projects[1].pk, confirm="yes")
            self.assertContains(response, "13 of 13 question slots complete")
            response = self.action("preview_submit")
            self.assertContains(response, "Practice finish complete")
        journey.refresh_from_db()
        self.assertEqual(journey.started_at, started)
        self.assertNotIn(f"{self.projects[1].pk}:J1", PersonalDraft.objects.get().seen_slots)

    def test_599_seconds_can_offer_next_section_but_600_cannot(self):
        self.begin()
        start = Journey.objects.get().started_at
        with patch("signal_loop.checkins.views.timezone.now", return_value=start + timedelta(seconds=599)):
            response = self.post(0)
        self.assertContains(response, "How is delivery going in Cedar")
        seen = PersonalDraft.objects.get().seen_slots
        with patch("signal_loop.checkins.views.timezone.now", return_value=start + timedelta(seconds=600)):
            response = self.client.get("/app/check-in/")
        self.assertContains(response, "ten-minute question time has ended")
        self.assertEqual(PersonalDraft.objects.get().seen_slots, seen)

    def test_failure_closes_slot_and_finish_errors_retain_values_with_unique_labels(self):
        self.begin()
        self.post(0, J1="blocked")
        def factory():
            return Adapter(FakeProvider(script=("timeout",)))
        with override_settings(CHECKIN_AI_FACTORY=factory):
            response = self.post(1)
        self.assertContains(response, "Finish and review saved answers")
        self.assertEqual(PersonalDraft.objects.get().adaptive_slots[0]["state"], "unavailable")
        response = self.action("finish_project", section=self.projects[0].pk, J1="blocked", J2="manageable", J3="x" * 321)
        self.assertContains(response, "at most 320 characters")
        self.assertContains(response, "x" * 321)
        self.assertEqual(ProjectDraft.objects.get(project_id=self.projects[0].pk).answers["J3"], "x" * 321)
        ids = re.findall(r'\bid="([^"]+)"', response.content.decode())
        self.assertEqual(len(ids), len(set(ids)))

    def test_invalid_adaptive_answer_stays_on_question_and_is_recoverable(self):
        self.begin(1)
        self.post(0, J1="blocked")
        key = f"{self.projects[0].pk}:F1"
        response = self.action("adaptive_next", question=key, answer="z" * 241)
        self.assertContains(response, "at most 240 characters")
        self.assertContains(response, "Optional project follow-up")
        response = self.client.get("/app/check-in/")
        self.assertContains(response, "z" * 241)
        self.assertNotContains(response, "10 of 10 question slots complete")
        response = self.action("adaptive_back", question=key, answer="Typed before Back")
        self.assertContains(response, "Typed before Back")
        self.assertNotContains(response, "10 of 10 question slots complete")

    def test_answer_edit_excludes_ineligible_followup_until_acknowledged(self):
        self.begin(1)
        self.post(0, J1="blocked")
        key = f"{self.projects[0].pk}:F1"
        self.action("adaptive_next", question=key, answer="Synthetic help")
        response = self.action("finish_project", section=self.projects[0].pk, J1="on_track", J2="manageable", J3="")
        self.assertContains(response, "follow-up is excluded")
        fake = Mock(return_value="preview_complete")
        with override_settings(CHECKIN_FINAL_SUBMISSION=fake):
            self.action("preview_submit")
            fake.assert_not_called()
            self.action("finish_adaptive", question=key, answer="Synthetic help", acknowledge="yes")
            self.action("preview_submit")
        self.assertNotIn("F1", fake.call_args.args[0][0]["answers"])
        self.assertEqual(len(PersonalDraft.objects.get().adaptive_slots), 1)

    def test_expiry_removes_all_adaptive_state_and_closed_window_has_no_preview(self):
        self.begin(1)
        self.post(0, J1="blocked")
        expiry = PersonalDraft.objects.get().expires_at
        with patch("signal_loop.checkins.views.timezone.now", return_value=expiry):
            response = self.client.get("/app/check-in/")
        self.assertContains(response, "expired")
        self.assertEqual(Journey.objects.get().state, "expired")
        self.assertFalse(PersonalDraft.objects.exists())
        self.assertFalse(ProjectDraft.objects.exists())

    def test_finish_storage_failure_and_stale_tab_keep_typed_answers(self):
        self.begin(1)
        self.post(0)
        response = self.client.post("/app/check-in/", {"action": "finish_project", "revision": -1,
            "section": self.projects[0].pk, "J1": "on_track", "J2": "manageable", "J3": "stale typed text"})
        self.assertContains(response, "stale typed text")
        self.assertContains(response, "changed in another tab")
        self.assertNotEqual(ProjectDraft.objects.get().answers["J3"], "stale typed text")
        with patch.object(ProjectDraft, "save", side_effect=RuntimeError("synthetic-private-db-detail")):
            response = self.action("finish_project", section=self.projects[0].pk, J1="on_track", J2="manageable", J3="retry typed text")
        self.assertContains(response, "retry typed text", status_code=503)
        self.assertNotContains(response, "synthetic-private-db-detail", status_code=503)

    def test_migration_preserves_saved_seen_questions_without_resetting_start(self):
        from django.apps import apps
        from importlib import import_module
        self.begin(1)
        self.post(0)
        started = Journey.objects.get().started_at
        draft = PersonalDraft.objects.get()
        draft.seen_slots = []
        draft.save(update_fields=["seen_slots"])
        migration = import_module("signal_loop.checkins.migrations.0003_personaldraft_adaptive_allocated_and_more")
        migration.preserve_seen_saved_questions(apps, None)
        draft.refresh_from_db()
        self.assertIn("P3", draft.seen_slots)
        self.assertIn(f"{self.projects[0].pk}:J3", draft.seen_slots)
        self.assertEqual(Journey.objects.get().started_at, started)


class DurableAllocationTests(TransactionTestCase):
    def test_atomic_reservation_and_permanent_claim_survive_store_reconstruction(self):
        from datetime import date
        from uuid import uuid4
        from django.utils import timezone
        from signal_loop.admission.models import Principal
        principal = Principal.objects.create(id=uuid4())
        journey = Journey.objects.create(principal=principal, week=date(2026, 9, 7), state="open",
            started_at=timezone.now(), expires_at=timezone.now() + timedelta(hours=1),
            retain_until=timezone.now() + timedelta(days=1), selected_scopes=[[1, 1]])
        draft = PersonalDraft.objects.create(journey=journey, expires_at=journey.expires_at)
        slot = Slot("1", "2026-09-07", "F1", "Synthetic", "blocked", "manageable")
        DraftAllocationStore(draft.pk).reserve_once((slot,))
        self.assertEqual(DraftAllocationStore(draft.pk).reserve_once(()), (slot,))

        def claim(_):
            close_old_connections()
            try:
                return DraftAllocationStore(draft.pk).claim(slot)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, range(2)))
        self.assertEqual(sum(results), 1)
        self.assertFalse(DraftAllocationStore(draft.pk).claim(slot))
