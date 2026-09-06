import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from signal_loop.membership.models import Organisation, OrganisationMembership, Project, ProjectMembership, Role


pytestmark = pytest.mark.usefixtures("postgres_database")


class ShellTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="shell_member")
        cls.empty_user = get_user_model().objects.create_user(username="no_projects")
        org = Organisation.objects.create(name="Synthetic Studio")
        membership = OrganisationMembership.objects.create(organisation=org, user=cls.user)
        cls.cedar = Project.objects.create(organisation=org, name="Cedar")
        cls.birch = Project.objects.create(organisation=org, name="Birch")
        cls.hidden = Project.objects.create(organisation=org, name="Hidden project")
        cls.assignment = ProjectMembership.objects.create(project=cls.cedar, organisation_membership=membership)
        ProjectMembership.objects.create(project=cls.birch, organisation_membership=membership, role=Role.MANAGER)

    def setUp(self):
        self.client.force_login(self.user)

    def test_scoped_selector_and_role_navigation_preserve_selection(self):
        for project, manager_visible in ((self.cedar, False), (self.birch, True)):
            response = self.client.get(f"/app/?project={project.pk}")
            self.assertContains(response, f'value="{project.pk}" selected')
            self.assertNotContains(response, "Hidden project")
            self.assertContains(response, f'/app/check-in/?project={project.pk}')
            self.assertContains(response, f'/app/team-reports/?project={project.pk}')
            if manager_visible:
                self.assertContains(response, f'/app/manager-reports/?project={project.pk}')
            else:
                self.assertNotContains(response, "Manager reports")

    def test_placeholders_resolve_and_preserve_navigation(self):
        for route, text in (("check-in", "Check-in coming soon"), ("team-reports", "No team reports yet"),
                            ("manager-reports", "No manager reports yet")):
            response = self.client.get(f"/app/{route}/?project={self.birch.pk}")
            self.assertContains(response, text)
            self.assertContains(response, f'/app/?project={self.birch.pk}')
            self.assertContains(response, 'aria-current="page"')

    def test_no_project_state_has_no_selector_or_report_links(self):
        self.client.force_login(self.empty_user)
        response = self.client.get("/app/")
        self.assertContains(response, "No projects yet")
        self.assertNotContains(response, '<select')
        self.assertNotContains(response, '/app/team-reports/')
        self.assertNotContains(response, '/app/manager-reports/')

    def test_forged_or_revoked_selection_rejected_for_full_and_fragments(self):
        for value in (str(self.hidden.pk), "999999", "bad", "", "-1", "1&project=2"):
            for htmx in (False, True):
                response = self.client.get(f"/app/?project={value}", HTTP_HX_REQUEST="true" if htmx else "false")
                self.assertEqual((response.status_code, response.content), (404, b"Not found."))
        self.assignment.is_active = False
        self.assignment.save()
        self.assertEqual(self.client.get(f"/app/?project={self.cedar.pk}").status_code, 404)

    def test_manager_destination_checks_role_server_side(self):
        for htmx in (False, True):
            response = self.client.get(f"/app/manager-reports/?project={self.cedar.pk}",
                                       HTTP_HX_REQUEST="true" if htmx else "false")
            self.assertEqual((response.status_code, response.content), (404, b"Not found."))

    def test_htmx_fragment_has_same_content_and_vary_header(self):
        response = self.client.get(f"/app/team-reports/?project={self.cedar.pk}", HTTP_HX_REQUEST="true")
        self.assertContains(response, "No team reports yet")
        self.assertContains(response, 'id="application-shell"')
        self.assertNotContains(response, '<html')
        self.assertIn("HX-Request", response.headers["Vary"])
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertContains(response, '<title>Team reports | SignalLoop</title>')
        self.assertContains(response, 'hx-history="false"')

    def test_htmx_history_restoration_returns_complete_document(self):
        response = self.client.get(f"/app/team-reports/?project={self.cedar.pk}",
                                   HTTP_HX_REQUEST="true", HTTP_HX_HISTORY_RESTORE_REQUEST="true")
        self.assertContains(response, '<html lang="en">')
        self.assertContains(response, 'No team reports yet')
        self.assertContains(response, 'django_htmx/htmx-2.min.js')
        self.assertIn("HX-History-Restore-Request", response.headers["Vary"])

    def test_shared_accessible_regions_and_login_required(self):
        response = self.client.get("/app/")
        for snippet in ('Skip to content', 'aria-label="Project navigation"', 'label for="project"',
                        'role="status"', 'role="alert"', 'accounts/shell.css',
                        'django_htmx/htmx-2.min.js', 'accounts/shell.js'):
            self.assertContains(response, snippet)
        self.client.logout()
        self.assertEqual(self.client.get("/app/team-reports/").status_code, 302)
