import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from signal_loop.membership.admin import site
from signal_loop.membership.models import Organisation, OrganisationMembership, Project, ProjectMembership, Role


pytestmark = pytest.mark.usefixtures("postgres_database")


class OrganisationAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(name="Synthetic Studio")
        cls.other = Organisation.objects.create(name="Other Studio")
        cls.project = Project.objects.create(name="Cedar", organisation=cls.org)
        cls.foreign_project = Project.objects.create(name="Foreign confidential project", organisation=cls.other)
        cls.admin = get_user_model().objects.create_user(username="organisation_admin")
        cls.member = get_user_model().objects.create_user(username="member")
        cls.project_manager = get_user_model().objects.create_user(username="project_manager")
        cls.foreign_user = get_user_model().objects.create_user(username="foreign_confidential_user")
        cls.superuser = get_user_model().objects.create_user(username="unscoped_superuser", is_staff=True, is_superuser=True)
        cls.admin_membership = OrganisationMembership.objects.create(organisation=cls.org, user=cls.admin, role=Role.MANAGER)
        cls.member_membership = OrganisationMembership.objects.create(organisation=cls.org, user=cls.member)
        cls.foreign_membership = OrganisationMembership.objects.create(organisation=cls.other, user=cls.foreign_user)
        manager_membership = OrganisationMembership.objects.create(organisation=cls.org, user=cls.project_manager)
        ProjectMembership.objects.create(project=cls.project, organisation_membership=manager_membership, role=Role.MANAGER)

    def setUp(self):
        self.client.force_login(self.admin)

    def url(self, model, action, pk=None):
        app = "auth" if model == "user" else "membership"
        return reverse(f"organisation_admin:{app}_{model}_{action}", args=[pk] if pk else [])

    def test_org_admin_without_staff_can_create_project(self):
        self.assertFalse(self.admin.is_staff)
        response = self.client.post(self.url("project", "add"), {
            "organisation": self.org.pk, "name": "Birch", "is_active": "on", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Project.objects.filter(organisation=self.org, name="Birch").exists())

    def test_admin_login_accepts_org_role_without_staff(self):
        self.admin.set_password("synthetic-admin-password")
        self.admin.save()
        self.client.logout()
        response = self.client.post("/admin/login/", {
            "username": self.admin.username, "password": "synthetic-admin-password", "next": "/admin/",
        })
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get("/admin/"), "SignalLoop organisation administration")

    def test_provision_user_atomically_without_global_privileges(self):
        response = self.client.post(self.url("user", "add"), {
            "username": "new_synthetic_user", "organisation": self.org.pk,
            "password1": "synthetic-strong-password", "password2": "synthetic-strong-password",
            "is_superuser": "on", "is_staff": "on", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username="new_synthetic_user")
        self.assertTrue(user.check_password("synthetic-strong-password"))
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        self.assertEqual(user.organisation_memberships.get().organisation_id, self.org.pk)
        self.assertEqual(user.organisation_memberships.get().role, Role.MEMBER)

    def test_role_assignment_and_change_in_scope(self):
        response = self.client.post(self.url("projectmembership", "add"), {
            "project": self.project.pk, "organisation_membership": self.member_membership.pk,
            "role": Role.MEMBER, "is_active": "on", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        membership = ProjectMembership.objects.get(organisation_membership=self.member_membership)
        response = self.client.post(self.url("projectmembership", "change", membership.pk), {
            "project": self.project.pk, "organisation_membership": self.member_membership.pk,
            "role": Role.MANAGER, "is_active": "on", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.role, Role.MANAGER)

    def test_lists_details_and_choices_hide_other_organisation(self):
        for model, forbidden in (("project", self.foreign_project.name), ("user", self.foreign_user.username)):
            response = self.client.get(self.url(model, "changelist"))
            self.assertNotContains(response, forbidden)
        response = self.client.get(self.url("project", "change", self.foreign_project.pk))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(self.foreign_project.name.encode(), response.content)
        form = self.client.get(self.url("projectmembership", "add")).context["adminform"].form
        self.assertNotIn(self.foreign_project, form.fields["project"].queryset)
        self.assertNotIn(self.foreign_membership, form.fields["organisation_membership"].queryset)
        form = self.client.get(self.url("organisationmembership", "add")).context["adminform"].form
        self.assertNotIn(self.foreign_user, form.fields["user"].queryset)

    def test_submitted_foreign_ids_and_invalid_role_cannot_write(self):
        response = self.client.post(self.url("project", "change", self.foreign_project.pk), {
            "organisation": self.org.pk, "name": "Attempted takeover", "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.foreign_project.refresh_from_db()
        self.assertEqual(self.foreign_project.name, "Foreign confidential project")
        for project_id, member_id, role in (
            (self.foreign_project.pk, self.member_membership.pk, Role.MEMBER),
            (self.project.pk, self.foreign_membership.pk, Role.MEMBER),
            (self.project.pk, self.member_membership.pk, "owner"),
        ):
            response = self.client.post(self.url("projectmembership", "add"), {
                "project": project_id, "organisation_membership": member_id, "role": role, "is_active": "on",
            })
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["adminform"].form.errors)
        self.assertFalse(ProjectMembership.objects.filter(organisation_membership=self.member_membership).exists())
        response = self.client.post(self.url("user", "add"), {
            "username": "forbidden_new_user", "organisation": self.other.pk,
            "password1": "synthetic-password", "password2": "synthetic-password",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["adminform"].form.errors)
        self.assertFalse(get_user_model().objects.filter(username="forbidden_new_user").exists())

    def test_organisation_role_change_and_duplicate_validation(self):
        data = {"organisation": self.org.pk, "user": self.member.pk,
                "role": Role.MANAGER, "is_active": "on", "_save": "Save"}
        response = self.client.post(self.url("organisationmembership", "add"), data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["adminform"].form.non_field_errors())
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.role, Role.MEMBER)
        response = self.client.post(self.url("organisationmembership", "change", self.member_membership.pk), data)
        self.assertEqual(response.status_code, 302)
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.role, Role.MANAGER)

    def test_duplicate_and_cross_org_form_errors_leave_assignment_unchanged(self):
        assignment = ProjectMembership.objects.create(project=self.project, organisation_membership=self.member_membership)
        response = self.client.post(self.url("projectmembership", "add"), {
            "project": self.project.pk, "organisation_membership": self.member_membership.pk, "role": Role.MANAGER,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["adminform"].form.non_field_errors())
        # With authority in both organisations, both choices are valid individually,
        # but their cross-organisation combination must still fail model validation.
        OrganisationMembership.objects.create(organisation=self.other, user=self.admin, role=Role.MANAGER)
        response = self.client.post(self.url("projectmembership", "change", assignment.pk), {
            "project": self.project.pk, "organisation_membership": self.foreign_membership.pk,
            "role": Role.MANAGER, "is_active": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["adminform"].form.errors)
        assignment.refresh_from_db()
        self.assertEqual((assignment.role, assignment.organisation_membership_id), (Role.MEMBER, self.member_membership.pk))

    def test_regular_project_manager_and_unscoped_superuser_denied(self):
        for user in (self.member, self.project_manager, self.superuser):
            self.client.force_login(user)
            for method in (self.client.get, self.client.post):
                response = method(self.url("project", "add"))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login/", response.url)

    def test_existing_shared_user_cannot_be_modified_or_escalated(self):
        response = self.client.post(self.url("user", "change", self.member.pk), {
            "username": "taken_over", "is_staff": "on", "is_superuser": "on",
        })
        self.assertEqual(response.status_code, 403)
        self.member.refresh_from_db()
        self.assertEqual(self.member.username, "member")
        self.assertFalse(self.member.is_superuser)

    def test_bulk_delete_and_restricted_models_not_exposed(self):
        response = self.client.post(self.url("project", "changelist"), {
            "action": "delete_selected", "_selected_action": [self.project.pk, self.foreign_project.pk], "post": "yes",
        })
        self.assertIn(response.status_code, (200, 302))
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.assertTrue(Project.objects.filter(pk=self.foreign_project.pk).exists())
        self.assertEqual(set(site._registry), {get_user_model(), Project, OrganisationMembership, ProjectMembership})
        for registered in site._registry.values():
            self.assertFalse(registered.actions)
            self.assertFalse(registered.search_fields)
