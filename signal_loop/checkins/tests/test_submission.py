from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
from unittest.mock import patch

import pytest
from django.db import close_old_connections, transaction
from django.db.models.query import QuerySet
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from signal_loop.admission.models import Credential, Journey, Participation
from signal_loop.checkins.journey import _submission_sections
from signal_loop.checkins.models import PersonalDraft, ProjectDraft
from signal_loop.checkins.tests import test_projects
from signal_loop.feedback.models import FeedbackSection
from signal_loop.feedback.services import persist_sections
from signal_loop.membership.models import ProjectMembership
from signal_loop.submission.services import submit_check_in
from signal_loop.windows.models import WeeklyWindow


pytestmark = pytest.mark.usefixtures("postgres_database")


class SubmissionTests(TestCase):
    setUpTestData = classmethod(test_projects.ProjectFormTests.setUpTestData.__func__)
    setUp = test_projects.ProjectFormTests.setUp
    begin = test_projects.ProjectFormTests.begin
    post = test_projects.ProjectFormTests.post

    def ready(self, count=2, **answers):
        self.begin(count)
        for index in range(count):
            self.post(index, **answers)
        draft = PersonalDraft.objects.get()
        return {"week": draft.journey.week.isoformat(), "revision": draft.revision}

    def submit(self, data):
        return self.client.post("/app/check-in/submit/", data)

    def test_success_canonical_storage_consumption_cleanup_and_generic_replay(self):
        data = self.ready()
        expiry = PersonalDraft.objects.get().expires_at
        response = self.submit(data)
        self.assertContains(response, "Your check-in is complete.")
        self.assertEqual(FeedbackSection.objects.count(), 2)
        self.assertEqual(Participation.objects.filter(consumed=True).count(), 2)
        self.assertFalse(Credential.objects.filter(active=True).exists())
        self.assertFalse(PersonalDraft.objects.exists())
        self.assertFalse(ProjectDraft.objects.exists())
        journey = Journey.objects.get()
        self.assertEqual(journey.state, "completed")
        self.assertEqual(journey.selected_scopes, [])
        self.assertIsNone(journey.started_at)
        self.assertIsNone(journey.expires_at)
        for row in FeedbackSection.objects.all():
            self.assertEqual(row.schema, "feedback/1.0")
            self.assertNotContains(response, str(row.pk))
            self.assertNotIn("private personal", str(row.data))
            self.assertEqual(set(row.provenance), {"producer", "producer_version", "input_refs"})
        replay = self.submit(data)
        self.assertContains(replay, "Your check-in is complete.")
        self.assertEqual(response.content, replay.content)
        # Simulate losing the response, then retrying after window/credential expiry.
        with patch("signal_loop.checkins.views.timezone.now", return_value=expiry + timedelta(hours=6)):
            self.assertContains(self.submit(data), "Your check-in is complete.")
        self.assertEqual(FeedbackSection.objects.count(), 2)

    def test_partial_second_insert_failure_rolls_back_refresh_consumption_and_all_rows(self):
        data = self.ready()
        before = dict(Credential.objects.values_list("pk", "verifier"))
        real_save = FeedbackSection.save
        writes = []

        def fail_second(instance, *args, **kwargs):
            writes.append(instance.pk)
            if len(writes) == 2:
                raise RuntimeError("synthetic-private-sink-detail")
            return real_save(instance, *args, **kwargs)

        with patch.object(FeedbackSection, "save", fail_second):
            response = self.submit(data)
        self.assertContains(response, "saved answers are preserved", status_code=503)
        self.assertNotContains(response, "synthetic-private-sink-detail", status_code=503)
        self.assertFalse(FeedbackSection.objects.exists())
        self.assertFalse(Participation.objects.filter(consumed=True).exists())
        self.assertEqual(dict(Credential.objects.values_list("pk", "verifier")), before)
        self.assertEqual(PersonalDraft.objects.get().answers["P3"], "private personal")
        self.assertEqual(Journey.objects.get().state, "open")
        self.assertContains(self.submit(data), "Your check-in is complete.")

    def test_cleanup_failure_rolls_back_sink_and_preserves_adaptive_private_draft(self):
        data = self.ready()
        original_delete = QuerySet.delete
        cleanup_counts = []

        def fail_draft(queryset):
            if queryset.model is PersonalDraft and queryset.exists():
                cleanup_counts.append(FeedbackSection.objects.count())
                raise RuntimeError("synthetic-private-cleanup-detail")
            return original_delete(queryset)

        with patch.object(QuerySet, "delete", fail_draft):
            response = self.submit(data)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(cleanup_counts, [2])
        self.assertFalse(FeedbackSection.objects.exists())
        self.assertFalse(Participation.objects.filter(consumed=True).exists())
        self.assertEqual(ProjectDraft.objects.count(), 2)
        self.assertTrue(PersonalDraft.objects.exists())

    def test_acknowledged_revoked_scope_is_omitted_and_remaining_scope_refreshes(self):
        self.ready()
        removed = self.projects[1]
        membership = ProjectMembership.objects.get(project=removed, organisation_membership__user=self.user)
        membership.is_active = False
        membership.save()
        draft = PersonalDraft.objects.get()
        response = self.client.post("/app/check-in/", {"action": "finish_omit", "revision": draft.revision,
                                                       "section": removed.pk, "confirm": "yes"})
        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        response = self.submit({"week": draft.journey.week.isoformat(), "revision": draft.revision})
        self.assertContains(response, "Your check-in is complete.")
        self.assertEqual(list(FeedbackSection.objects.values_list("project_id", flat=True)), [self.projects[0].pk])
        self.assertFalse(Participation.objects.get(project=removed).consumed)
        self.assertFalse(Credential.objects.filter(active=True).exists())

    def test_stale_tampered_expired_and_non_substantive_submissions_never_partially_write(self):
        data = self.ready()
        self.assertEqual(self.submit({**data, "revision": -1}).status_code, 400)
        self.assertEqual(self.submit({**data, "revision": data["revision"] - 1}).status_code, 409)
        self.assertEqual(self.submit({**data, "project": self.foreign.pk}).status_code, 400)
        self.assertEqual(self.submit({**data, "sections": "invented payload"}).status_code, 400)
        self.assertEqual(self.submit({**data, "week": "2026-09-08"}).status_code, 400)
        credential = Credential.objects.first()
        credential.expires_at = self.at - timedelta(seconds=1)
        credential.save(update_fields=["expires_at"])
        self.assertEqual(self.submit(data).status_code, 403)
        self.assertFalse(FeedbackSection.objects.exists())
        self.assertFalse(Participation.objects.filter(consumed=True).exists())

    def test_all_non_substantive_keeps_draft_and_credentials_unconsumed(self):
        data = self.ready(J1="prefer_not_to_say", J2="not_enough_context", J3="")
        before = dict(Credential.objects.values_list("pk", "verifier"))
        self.assertContains(self.submit(data), "No project feedback to submit")
        self.assertFalse(FeedbackSection.objects.exists())
        self.assertFalse(Participation.objects.filter(consumed=True).exists())
        self.assertTrue(PersonalDraft.objects.exists())
        self.assertEqual(dict(Credential.objects.values_list("pk", "verifier")), before)

    def test_mixed_substantive_and_declined_sections_only_consume_the_submitted_scope(self):
        self.begin()
        self.post(0)
        self.post(1, J1="prefer_not_to_say", J2="not_enough_context", J3="")
        draft = PersonalDraft.objects.get()
        response = self.submit({"week": draft.journey.week.isoformat(), "revision": draft.revision})
        self.assertContains(response, "Your check-in is complete.")
        self.assertEqual(list(FeedbackSection.objects.values_list("project_id", flat=True)), [self.projects[0].pk])
        self.assertFalse(Participation.objects.get(project=self.projects[1]).consumed)
        self.assertFalse(Credential.objects.filter(active=True).exists())

    def test_final_post_cannot_skip_unallocated_adaptive_stage(self):
        self.begin(1)
        self.post(0, action="project_save", J1="blocked")
        draft = PersonalDraft.objects.get()
        self.assertFalse(draft.adaptive_allocated)
        response = self.submit({"week": draft.journey.week.isoformat(), "revision": draft.revision})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FeedbackSection.objects.exists())
        self.assertFalse(Participation.objects.filter(consumed=True).exists())

    def test_real_endpoint_rejects_stale_unseen_answers_at_601_seconds(self):
        self.begin()
        draft = PersonalDraft.objects.get()
        ProjectDraft.objects.create(draft=draft, project_id=self.projects[1].pk,
                                    answers={"J1": "on_track", "J2": "manageable", "J3": "hidden unseen text"})
        start = draft.journey.started_at
        with patch("signal_loop.checkins.views.timezone.now", return_value=start + timedelta(seconds=601)):
            self.post(0)
            draft.refresh_from_db()
            response = self.submit({"week": draft.journey.week.isoformat(), "revision": draft.revision})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FeedbackSection.objects.exists())
        self.assertFalse(Participation.objects.filter(consumed=True).exists())

    def test_post_only_csrf_and_foreign_account_have_no_submission_access(self):
        data = self.ready()
        self.assertEqual(self.client.get("/app/check-in/submit/").status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post("/app/check-in/submit/", data).status_code, 403)
        self.client.force_login(self.other)
        self.assertNotEqual(self.submit(data).status_code, 200)
        self.assertFalse(FeedbackSection.objects.exists())

    def test_fresh_submission_at_closing_is_refused_and_expired_private_state_is_erased(self):
        data = self.ready()
        closing = PersonalDraft.objects.get().expires_at
        with patch("signal_loop.checkins.views.timezone.now", return_value=closing):
            response = self.submit(data)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(FeedbackSection.objects.exists())
        self.assertFalse(Participation.objects.filter(consumed=True).exists())
        self.assertFalse(PersonalDraft.objects.exists())
        self.assertFalse(ProjectDraft.objects.exists())
        self.assertEqual(Journey.objects.get().state, "expired")


class SubmissionConcurrencyTests(TransactionTestCase):
    begin = test_projects.ProjectFormTests.begin
    post = test_projects.ProjectFormTests.post
    ready = SubmissionTests.ready

    def setUp(self):
        test_projects.ProjectFormTests.setUpTestData.__func__(type(self))
        test_projects.ProjectFormTests.setUp(self)

    def test_simultaneous_http_submissions_store_once_and_both_return_complete(self):
        data = self.ready()
        barrier = threading.Barrier(2)

        def submit(_):
            close_old_connections()
            try:
                client = Client()
                client.force_login(self.user)
                barrier.wait(timeout=5)
                response = client.post("/app/check-in/submit/", data)
                return response.status_code, "Your check-in is complete." in response.content.decode()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        self.assertEqual(results, [(200, True), (200, True)])
        self.assertEqual(FeedbackSection.objects.count(), 2)
        self.assertEqual(Participation.objects.filter(consumed=True).count(), 2)
        self.assertFalse(PersonalDraft.objects.exists())

    def test_preclose_admission_commits_after_close_and_window_freezer_waits(self):
        data = self.ready()
        draft = PersonalDraft.objects.get()
        journey = draft.journey
        window = WeeklyWindow.objects.get(pk=journey.selected_scopes[1][1])
        entered, release, freezer_started, frozen = (threading.Event() for _ in range(4))
        observed = []

        def delayed_sink(sections, *, clock):
            observed.append(clock())
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test synchronization timeout")
            return persist_sections(sections, clock=clock)

        def submit():
            close_old_connections()
            try:
                def prepare():
                    locked = PersonalDraft.objects.select_for_update().get(pk=draft.pk)
                    return _submission_sections(locked, journey, self.user)

                return submit_check_in(user=self.user, organisation=window.organisation, week=journey.week,
                    scopes=journey.selected_scopes, prepare_draft=prepare,
                    clear_draft=lambda: PersonalDraft.objects.filter(pk=draft.pk).delete(),
                    provider=lambda user, org: self._provider(user), sink=delayed_sink, clock=timezone.now)
            finally:
                close_old_connections()

        def freeze():
            close_old_connections()
            try:
                freezer_started.set()
                with transaction.atomic():
                    WeeklyWindow.objects.select_for_update().get(pk=window.pk)
                    count = FeedbackSection.objects.filter(project_id=self.projects[1].pk).count()
                frozen.set()
                return count
            finally:
                close_old_connections()

        with patch("signal_loop.checkins.views.timezone.now", return_value=window.closes_at - timedelta(seconds=1)) as clock:
            with ThreadPoolExecutor(max_workers=2) as pool:
                sending = pool.submit(submit)
                self.assertTrue(entered.wait(timeout=5))
                clock.return_value = window.closes_at + timedelta(seconds=1)
                freezing = pool.submit(freeze)
                self.assertTrue(freezer_started.wait(timeout=5))
                self.assertFalse(frozen.wait(timeout=0.1))
                release.set()
                self.assertEqual(sending.result(timeout=5), "complete")
                self.assertEqual(freezing.result(timeout=5), 1)
        self.assertEqual(observed, [window.closes_at - timedelta(seconds=1)])
        self.assertFalse(PersonalDraft.objects.exists())
        self.assertEqual(data["week"], journey.week.isoformat())

    def _provider(self, user):
        from uuid import UUID
        from signal_loop.admission.services import VerifiedPrincipal
        return VerifiedPrincipal(UUID("30000000-0000-4000-8000-000000000001")) if user.pk == self.user.pk else None
