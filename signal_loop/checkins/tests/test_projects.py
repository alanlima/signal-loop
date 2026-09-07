from datetime import date, datetime, timezone
from unittest.mock import patch
from uuid import UUID

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from signal_loop.admission.models import Journey, Participation
from signal_loop.admission.services import VerifiedPrincipal
from signal_loop.checkins.models import PersonalDraft, ProjectDraft
from signal_loop.feedback.models import FeedbackSection
from signal_loop.membership.models import Organisation, OrganisationMembership, Project, ProjectMembership
from signal_loop.windows.services import create_weekly_window


pytestmark = pytest.mark.usefixtures("postgres_database")


class ProjectFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="synthetic_project_user")
        cls.other = get_user_model().objects.create_user(username="synthetic_project_other")
        cls.projects = []
        for name, zone in (("Birch", "America/New_York"), ("Cedar", "Australia/Brisbane"), ("Maple", "UTC"), ("Pine", "UTC")):
            org = Organisation.objects.create(name=f"Synthetic {name}")
            project = Project.objects.create(organisation=org, name=name)
            member = OrganisationMembership.objects.create(organisation=org, user=cls.user)
            ProjectMembership.objects.create(project=project, organisation_membership=member)
            create_weekly_window(organisation=org, week_start=date(2026, 9, 7), timezone_name=zone)
            cls.projects.append(project)
        foreign_org = Organisation.objects.create(name="Unrelated synthetic organisation")
        cls.foreign = Project.objects.create(organisation=foreign_org, name="Foreign project")
        member = OrganisationMembership.objects.create(organisation=foreign_org, user=cls.other)
        ProjectMembership.objects.create(project=cls.foreign, organisation_membership=member)

    def setUp(self):
        self.client.force_login(self.user)
        self.at = datetime(2026, 9, 8, tzinfo=timezone.utc)
        clock = patch("signal_loop.checkins.views.timezone.now", return_value=self.at)
        clock.start()
        self.addCleanup(clock.stop)
        config = override_settings(CHECKIN_PRINCIPAL_PROVIDER=lambda user, org: VerifiedPrincipal(
            UUID("30000000-0000-4000-8000-000000000001")) if user.pk == self.user.pk else None)
        config.enable()
        self.addCleanup(config.disable)

    def begin(self, count=2):
        self.client.post("/app/check-in/", {"action": "begin", "projects": [p.pk for p in self.projects[:count]]})
        draft = PersonalDraft.objects.get()
        response = self.client.post("/app/check-in/", {"action": "next", "revision": draft.revision,
                                                       "P1": "high", "P2": "manageable", "P3": "private personal"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "How is delivery going in Birch this week?")
        return response

    def post(self, index=0, action="project_next", hx=False, **changes):
        draft = PersonalDraft.objects.get()
        data = {"action": action, "revision": draft.revision, "section": self.projects[index].pk,
                "J1": "on_track", "J2": "manageable", "J3": f"Synthetic section {index}"}
        data.update(changes)
        return self.client.post("/app/check-in/", data, HTTP_HX_REQUEST="true" if hx else "false")

    def test_exact_fields_one_project_and_explicit_review(self):
        response = self.begin(1)
        for label in ("How is delivery going in Birch this week?", "How manageable is the work in Birch this week?",
                      "What should improve or continue in Birch next week?"):
            self.assertContains(response, label)
        self.assertContains(response, 'for="id_J1"')
        self.assertContains(response, 'for="id_J3"')
        self.assertNotContains(response, 'name="F1"')
        self.assertNotContains(response, 'name="F2"')
        self.assertContains(response, "Project 1 of 1")
        response = self.post()
        self.assertContains(response, "Finish and review saved answers")
        self.assertContains(response, "Submit check-in")
        self.assertFalse(FeedbackSection.objects.exists())
        self.assertFalse(Participation.objects.filter(consumed=True).exists())

    def test_full_and_htmx_navigation_preserve_distinct_sections_and_personal_answers(self):
        self.begin(3)
        response = self.post(0, hx=True, J3="Birch saved words")
        self.assertContains(response, "Project 2 of 3")
        self.assertNotContains(response, "<html")
        response = self.post(1, hx=False, J3="Cedar saved words")
        self.assertContains(response, "Project 3 of 3")
        self.assertContains(response, "<html")
        response = self.post(2, action="project_back", hx=True, J3="Maple saved words")
        self.assertContains(response, "Cedar saved words")
        self.assertEqual(ProjectDraft.objects.count(), 3)
        response = self.post(1, action="project_back", hx=False, J3="Cedar saved words")
        self.assertContains(response, "Birch saved words")
        self.assertEqual(PersonalDraft.objects.get().answers["P3"], "private personal")
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_invalid_values_over_limit_and_html_are_preserved_in_relevant_section(self):
        self.begin()
        self.post(0, J3="preserve first")
        response = self.post(1, hx=True, J1="invented", J3="x" * 321)
        self.assertContains(response, "Review the errors for Cedar")
        self.assertContains(response, "Ensure this value has at most 320 characters")
        self.assertEqual(ProjectDraft.objects.get(project_id=self.projects[0].pk).answers["J3"], "preserve first")
        self.assertEqual(ProjectDraft.objects.get(project_id=self.projects[1].pk).answers["J3"], "x" * 321)
        response = self.post(1, action="project_save", J3='<script>alert("synthetic")</script>')
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("synthetic")</script>')
        response = self.post(1, action="project_save", J3="😀" * 320)
        self.assertContains(response, "Project answers saved")
        self.assertEqual(len(ProjectDraft.objects.get(project_id=self.projects[1].pk).answers["J3"]), 320)

    def test_forged_unselected_cross_organisation_and_extra_fields_rejected(self):
        self.begin()
        for foreign in (self.foreign.pk, self.projects[2].pk, 99999):
            self.assertEqual(self.post(section=foreign).status_code, 404)
            self.assertEqual(self.client.get(f"/app/check-in/?section={foreign}").status_code, 404)
        self.assertEqual(self.post(F1="unexpected adaptive answer").status_code, 404)
        self.assertEqual(self.post(sections="extra JSON section").status_code, 404)
        self.assertEqual(self.client.post("/app/check-in/", {"action": "next", "section": self.foreign.pk}).status_code, 404)
        self.assertFalse(ProjectDraft.objects.exists())
        self.assertEqual(len(Journey.objects.get().selected_scopes), 2)

    def test_revocation_requires_acknowledgement_and_preserves_other_sections(self):
        self.begin()
        self.post(0, J3="preserve Birch")
        self.post(1, action="project_save", J3="discard Cedar only when confirmed")
        membership = ProjectMembership.objects.get(project=self.projects[1], organisation_membership__user=self.user)
        membership.is_active = False
        membership.save()
        response = self.client.get("/app/check-in/")
        self.assertContains(response, "This project is no longer available")
        response = self.post(1, action="project_omit")
        self.assertContains(response, "Confirm removal")
        self.assertEqual(ProjectDraft.objects.count(), 2)
        response = self.post(1, action="project_omit", confirm="yes")
        self.assertContains(response, "Finish and review saved answers")
        self.assertEqual(ProjectDraft.objects.count(), 1)
        self.assertEqual(ProjectDraft.objects.get().answers["J3"], "preserve Birch")
        self.assertEqual(len(Journey.objects.get().selected_scopes), 2)  # no replacement or scope rewrite
        self.assertEqual(PersonalDraft.objects.get().omitted_projects, [self.projects[1].pk])

    def test_all_removed_sections_have_no_feedback_empty_finish_path(self):
        self.begin()
        self.post(0, action="project_omit", confirm="yes")
        response = self.post(1, action="project_omit", confirm="yes")
        self.assertContains(response, "No project feedback to submit")
        self.assertContains(response, "All selected sections were removed")
        self.assertFalse(ProjectDraft.objects.exists())

    def test_review_rechecks_previously_saved_project_and_stale_save_keeps_newer_answers(self):
        self.begin()
        self.post(0, J3="newer Birch answer")
        response = self.post(0, action="project_save", revision=0, J3="stale typed answer")
        self.assertContains(response, "This draft changed in another tab")
        self.assertContains(response, "stale typed answer")
        self.assertEqual(ProjectDraft.objects.get(project_id=self.projects[0].pk).answers["J3"], "newer Birch answer")
        membership = ProjectMembership.objects.get(project=self.projects[0], organisation_membership__user=self.user)
        membership.is_active = False
        membership.save()
        response = self.post(1)
        self.assertContains(response, "This project is no longer available")
        self.assertContains(response, "Project 1 of 2")
        self.assertNotContains(response, "Finish and review saved answers")

    def test_empty_window_state_and_maximum_three_offer_no_extra_projects(self):
        response = self.client.get("/app/check-in/")
        self.assertNotContains(response, " checked")
        response = self.client.post("/app/check-in/", {"action": "begin", "projects": [p.pk for p in self.projects]})
        self.assertContains(response, "Choose between one and three")
        self.assertFalse(PersonalDraft.objects.exists())
        with patch("signal_loop.checkins.views.timezone.now", return_value=datetime(2026, 9, 15, tzinfo=timezone.utc)):
            response = self.client.get("/app/check-in/")
        self.assertContains(response, "No projects are available for this week's check-in")

    def test_expiry_cascades_private_project_answers_and_seals_journey(self):
        self.begin()
        self.post(action="project_save", J3="expiring project text")
        expiry = PersonalDraft.objects.get().expires_at
        with patch("signal_loop.checkins.views.timezone.now", return_value=expiry):
            response = self.client.get("/app/check-in/", HTTP_HX_REQUEST="true")
        self.assertContains(response, "This draft is no longer available")
        self.assertNotContains(response, "expiring project text")
        self.assertFalse(ProjectDraft.objects.exists())
        self.assertFalse(PersonalDraft.objects.exists())
        self.assertEqual(Journey.objects.get().selected_scopes, [])

    def test_final_section_cannot_skip_missing_prior_required_answers(self):
        self.begin()
        self.client.get(f"/app/check-in/?section={self.projects[1].pk}")
        response = self.post(1)
        self.assertContains(response, "Complete or explicitly remove this section")
        self.assertContains(response, "Project 1 of 2")
        self.assertNotContains(response, "Finish and review saved answers")

    def test_project_storage_failure_preserves_typed_project_answer(self):
        self.begin()
        with patch.object(ProjectDraft, "save", side_effect=RuntimeError("Synthetic private database detail")):
            response = self.post(J3="keep this typed project answer")
        self.assertContains(response, "keep this typed project answer", status_code=503)
        self.assertContains(response, "Keep this page open and try again", status_code=503)
        self.assertNotContains(response, "Synthetic private database detail", status_code=503)

