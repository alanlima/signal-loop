from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock, patch
from uuid import UUID

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from signal_loop.admission.models import Credential, Journey, Participation
from signal_loop.admission.services import VerifiedPrincipal
from signal_loop.checkins.forms import PersonalForm
from signal_loop.checkins.models import PersonalDraft
from signal_loop.feedback.models import FeedbackSection
from signal_loop.membership.models import Organisation, OrganisationMembership, Project, ProjectMembership
from signal_loop.windows.services import create_weekly_window


pytestmark = pytest.mark.usefixtures("postgres_database")


class PersonalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="synthetic_personal")
        cls.other = get_user_model().objects.create_user(username="synthetic_other")
        cls.projects = []
        for name, zone in (("Cedar", "Australia/Brisbane"), ("Birch", "America/New_York")):
            org = Organisation.objects.create(name=f"Synthetic {name}")
            project = Project.objects.create(organisation=org, name=name)
            member = OrganisationMembership.objects.create(organisation=org, user=cls.user)
            ProjectMembership.objects.create(project=project, organisation_membership=member)
            create_weekly_window(organisation=org, week_start=date(2026, 9, 7), timezone_name=zone)
            cls.projects.append(project)

    def setUp(self):
        self.client.force_login(self.user)
        self.at = datetime(2026, 9, 8, tzinfo=timezone.utc)
        self.clock = patch("signal_loop.checkins.views.timezone.now", return_value=self.at)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.provider = lambda user, org: VerifiedPrincipal(UUID("20000000-0000-4000-8000-000000000001")) if user.pk == self.user.pk else None
        self.config = override_settings(CHECKIN_PRINCIPAL_PROVIDER=self.provider)
        self.config.enable()
        self.addCleanup(self.config.disable)

    def begin(self):
        response = self.client.post("/app/check-in/", {"action": "begin", "projects": [p.pk for p in self.projects]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "How is your energy this week?")
        return response

    def answers(self, **changes):
        draft = PersonalDraft.objects.get()
        payload = {"action": "next", "revision": draft.revision, "P1": "high", "P2": "manageable",
                   "P3": "", "P4": "", "P5": ""}
        payload.update(changes)
        return payload

    def test_default_denial_and_forged_selection_create_no_draft(self):
        with override_settings(CHECKIN_PRINCIPAL_PROVIDER="signal_loop.admission.services.deny_unverified"):
            response = self.client.get("/app/check-in/")
        self.assertContains(response, "Check-in unavailable")
        response = self.client.post("/app/check-in/", {"action": "begin", "projects": [99999]})
        self.assertContains(response, "Choose between one and three")
        self.assertEqual(self.client.post("/app/check-in/?project=99999", {"action": "begin"}).status_code, 404)
        self.assertFalse(PersonalDraft.objects.exists())

    def test_combined_begin_exact_questions_labels_expiry_and_private_boundary(self):
        response = self.client.get("/app/check-in/")
        self.assertContains(response, "2026-09-13 14:00:00 UTC")
        response = self.begin()
        for field in PersonalForm():
            self.assertContains(response, field.label)
            self.assertContains(response, f'for="{field.id_for_label}"')
        self.assertContains(response, "(Required)", count=2)
        self.assertContains(response, "(Optional)", count=3)
        self.assertContains(response, "Your personal reflection stays in this draft and is discarded when you submit.")
        self.assertNotContains(response, 'maxlength="240"')
        self.assertEqual(len(Journey.objects.get().selected_scopes), 2)
        self.assertEqual(PersonalDraft.objects.get().expires_at, datetime(2026, 9, 13, 14, tzinfo=timezone.utc))
        self.assertFalse(FeedbackSection.objects.exists())

    def test_empty_optionals_advance_fake_service_and_back_retains_answers(self):
        self.begin()
        fake = Mock(return_value="projects")
        with override_settings(CHECKIN_PROGRESS_SERVICE=fake):
            response = self.client.post("/app/check-in/", self.answers())
        fake.assert_called_once_with()  # no personal text sent to progression/sink
        self.assertContains(response, "Personal reflection saved")
        self.assertContains(response, "No feedback has been submitted")
        response = self.client.post("/app/check-in/", {"action": "back"})
        self.assertContains(response, 'value="high" selected')
        self.assertEqual(PersonalDraft.objects.get().answers["P3"], "")
        self.assertFalse(Participation.objects.filter(consumed=True).exists())
        self.assertFalse(FeedbackSection.objects.exists())

    def test_limits_unicode_normalization_invalid_fields_and_no_progression(self):
        self.begin()
        valid = self.client.post("/app/check-in/", self.answers(action="save", P3="😀" * 240, P4=" \r\n\t"))
        self.assertContains(valid, "Your answers are saved")
        draft = PersonalDraft.objects.get()
        self.assertEqual(draft.answers["P3"], "😀" * 240)
        self.assertEqual(draft.answers["P4"], " \n\t")
        fake = Mock(return_value="projects")
        with override_settings(CHECKIN_PROGRESS_SERVICE=fake):
            response = self.client.post("/app/check-in/", self.answers(P1="invented", P3="x" * 241, P5="keep support"))
        fake.assert_not_called()
        self.assertContains(response, "Ensure this value has at most 240 characters")
        self.assertContains(response, "Select a valid choice")
        self.assertContains(response, "keep support")
        self.assertEqual(PersonalDraft.objects.get().answers["P3"], "x" * 241)

    def test_html_like_text_escaped_and_absent_from_urls(self):
        self.begin()
        text = '<script>alert("synthetic")</script>'
        response = self.client.post("/app/check-in/", self.answers(action="save", P3=text))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, text)
        self.assertNotIn("Location", response.headers)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(PersonalDraft.objects.get().answers["P3"], text)
        response = self.client.get("/app/check-in/", HTTP_HX_REQUEST="true")
        self.assertNotContains(response, "<html")
        self.assertContains(response, "&lt;script&gt;")

    def test_fake_service_failure_retries_without_losing_answers(self):
        self.begin()
        fail = Mock(side_effect=RuntimeError("Synthetic sensitive service detail"))
        with override_settings(CHECKIN_PROGRESS_SERVICE=fail):
            response = self.client.post("/app/check-in/", self.answers(P3="recoverable reflection"))
        self.assertContains(response, "Your answers are saved. Try Next again")
        self.assertContains(response, "recoverable reflection")
        self.assertNotContains(response, "Synthetic sensitive service detail")
        self.assertEqual(PersonalDraft.objects.get().stage, "personal")
        response = self.client.post("/app/check-in/", self.answers(P3="recoverable reflection"))
        self.assertContains(response, "Personal reflection saved")

    def test_expired_draft_deleted_and_week_sealed_without_reconstruction(self):
        self.begin()
        self.client.post("/app/check-in/", self.answers(action="save", P3="expired secret reflection"))
        expiry = PersonalDraft.objects.get().expires_at
        with patch("signal_loop.checkins.views.timezone.now", return_value=expiry):
            response = self.client.get("/app/check-in/")
        self.assertContains(response, "This draft is no longer available")
        self.assertContains(response, "next Monday at 00:00 UTC")
        self.assertNotContains(response, "expired secret reflection")
        self.assertFalse(PersonalDraft.objects.exists())
        self.assertEqual(Journey.objects.get().state, Journey.State.EXPIRED)

    def test_discard_confirmation_and_stale_revision_do_not_overwrite(self):
        self.begin()
        stale = self.answers(P3="stale browser content")
        self.client.post("/app/check-in/", self.answers(action="save", P3="newer server content"))
        response = self.client.post("/app/check-in/", stale)
        self.assertContains(response, "changed in another tab")
        self.assertContains(response, "stale browser content")
        self.assertEqual(PersonalDraft.objects.get().answers["P3"], "newer server content")
        self.client.post("/app/check-in/", {"action": "discard"})
        self.assertTrue(PersonalDraft.objects.exists())
        self.client.post("/app/check-in/", {"action": "discard", "confirm": "yes"})
        self.assertFalse(PersonalDraft.objects.exists())
        self.assertEqual(Journey.objects.get().state, Journey.State.DISCARDED)

    def test_new_browser_session_resumes_only_owner_and_get_does_not_start_clock(self):
        self.client.get("/app/check-in/")
        self.assertFalse(Journey.objects.exists())
        self.begin()
        self.client.post("/app/check-in/", self.answers(action="save", P5="private support reflection"))
        start = Journey.objects.get().started_at
        self.client.logout()
        self.client.force_login(self.other)
        response = self.client.get("/app/check-in/")
        self.assertNotContains(response, "private support reflection", status_code=404)
        self.client.force_login(self.user)
        with patch("signal_loop.checkins.views.timezone.now", return_value=self.at + timedelta(minutes=5)):
            response = self.client.get("/app/check-in/")
        self.assertContains(response, "private support reflection")
        self.assertEqual(Journey.objects.get().started_at, start)

    def test_storage_failure_preserves_posted_text_without_sensitive_error(self):
        self.begin()
        with patch.object(PersonalDraft, "save", side_effect=RuntimeError("Synthetic storage detail")):
            response = self.client.post("/app/check-in/", self.answers(P3="keep typed answer"))
        self.assertContains(response, "Keep this page open and try again", status_code=503)
        self.assertContains(response, "keep typed answer", status_code=503)
        self.assertNotContains(response, "Synthetic storage detail", status_code=503)

    def test_more_than_three_projects_require_explicit_selection(self):
        for name in ("Maple", "Pine"):
            org = Organisation.objects.create(name=f"Synthetic {name}")
            project = Project.objects.create(organisation=org, name=name)
            membership = OrganisationMembership.objects.create(organisation=org, user=self.user)
            ProjectMembership.objects.create(project=project, organisation_membership=membership)
            create_weekly_window(organisation=org, week_start=date(2026, 9, 7), timezone_name="UTC")
        response = self.client.get("/app/check-in/")
        self.assertNotContains(response, " checked")
        projects = list(Project.objects.values_list("pk", flat=True))
        response = self.client.post("/app/check-in/", {"action": "begin", "projects": projects})
        self.assertContains(response, "Choose between one and three")
        self.assertFalse(PersonalDraft.objects.exists())
        response = self.client.post("/app/check-in/", {"action": "begin", "projects": projects[:3]})
        self.assertContains(response, "How is your energy this week?")
        self.assertEqual(len(Journey.objects.get().selected_scopes), 3)

    def test_new_global_week_does_not_recover_expired_old_reflection(self):
        self.begin()
        self.client.post("/app/check-in/", self.answers(action="save", P3="old private reflection"))
        with patch("signal_loop.checkins.views.timezone.now", return_value=datetime(2026, 9, 14, 1, tzinfo=timezone.utc)):
            response = self.client.get("/app/check-in/")
        self.assertNotContains(response, "old private reflection")
        self.assertFalse(PersonalDraft.objects.exists())
        old = Journey.objects.get()
        self.assertEqual(old.state, Journey.State.EXPIRED)
        self.assertEqual((old.selected_scopes, old.started_at, old.expires_at), ([], None, None))
        self.assertFalse(Credential.objects.filter(active=True).exists())
