import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, override_settings

from signal_loop.authorization.permissions import Permission, has_permission
from signal_loop.membership.models import Organisation, OrganisationMembership, Project, ProjectMembership, Role


pytestmark = pytest.mark.usefixtures("postgres_database")


@override_settings(ROOT_URLCONF="signal_loop.authorization.tests.urls")
class AuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(name="Synthetic Studio")
        cls.other = Organisation.objects.create(name="Other Studio")
        cls.cedar = Project.objects.create(name="Cedar", organisation=cls.org)
        cls.birch = Project.objects.create(name="Birch", organisation=cls.org)
        cls.foreign = Project.objects.create(name="Foreign", organisation=cls.other)
        cls.member = get_user_model().objects.create_user(username="member")
        cls.manager = get_user_model().objects.create_user(username="manager")
        cls.admin = get_user_model().objects.create_user(username="admin", is_staff=True, is_superuser=True)
        cls.memberships = {}
        for user in (cls.member, cls.manager, cls.admin):
            org_member = OrganisationMembership.objects.create(
                organisation=cls.org, user=user,
                role=Role.MANAGER if user == cls.admin else Role.MEMBER,
            )
            if user != cls.admin:
                cls.memberships[user.username] = ProjectMembership.objects.create(
                    project=cls.cedar, organisation_membership=org_member,
                    role=Role.MANAGER if user == cls.manager else Role.MEMBER,
                )
        ProjectMembership.objects.create(
            project=cls.birch, organisation_membership=cls.memberships["manager"].organisation_membership,
            role=Role.MEMBER,
        )

    def allowed(self, user, permission, project=None, organisation=None):
        return has_permission(user, permission, organisation_id=(organisation or self.org).pk,
                              project_id=(project or self.cedar).pk)

    def url(self, permission, project=None, organisation=None):
        prefix = f"/probe/{(organisation or self.org).pk}/"
        if permission != Permission.ADMINISTER_ORGANISATION:
            prefix += f"{(project or self.cedar).pk}/"
        return prefix + permission.value + "/"

    def test_role_matrix(self):
        for permission in (Permission.CURRENT_CHECK_IN, Permission.READ_TEAM_REPORT):
            self.assertTrue(self.allowed(self.member, permission))
            self.assertTrue(self.allowed(self.manager, permission))
            self.assertFalse(self.allowed(self.admin, permission))
        for permission in (Permission.READ_MANAGER_REPORT, Permission.PUBLISH_COMMITMENT):
            self.assertFalse(self.allowed(self.member, permission))
            self.assertTrue(self.allowed(self.manager, permission))
            self.assertFalse(self.allowed(self.admin, permission))
            self.assertFalse(self.allowed(self.manager, permission, self.birch))
        self.assertTrue(has_permission(self.admin, Permission.ADMINISTER_ORGANISATION, organisation_id=self.org.pk))
        self.assertFalse(has_permission(self.manager, Permission.ADMINISTER_ORGANISATION, organisation_id=self.org.pk))
        self.assertFalse(has_permission(self.admin, Permission.ADMINISTER_ORGANISATION, organisation_id=self.other.pk))

    def test_raw_data_and_unknown_permissions_always_denied(self):
        for user in (self.member, self.manager, self.admin, AnonymousUser()):
            self.assertFalse(self.allowed(user, Permission.READ_RAW_FEEDBACK))
            self.assertFalse(self.allowed(user, "unknown"))

    def test_combined_admin_manager_has_only_explicit_project_grants(self):
        ProjectMembership.objects.create(
            project=self.cedar,
            organisation_membership=OrganisationMembership.objects.get(user=self.admin),
            role=Role.MANAGER,
        )
        self.assertTrue(self.allowed(self.admin, Permission.READ_MANAGER_REPORT))
        self.assertFalse(self.allowed(self.admin, Permission.READ_MANAGER_REPORT, self.birch))
        self.assertFalse(self.allowed(self.admin, Permission.READ_RAW_FEEDBACK))

    def test_missing_and_tampered_context_denies(self):
        for context in ({}, {"organisation_id": self.org.pk}, {"organisation_id": self.org.pk, "project_id": "1"},
                        {"organisation_id": self.org.pk, "project_id": True}):
            self.assertFalse(has_permission(self.manager, Permission.READ_MANAGER_REPORT, **context))
        self.assertFalse(self.allowed(self.manager, Permission.READ_TEAM_REPORT, self.foreign))
        self.assertFalse(self.allowed(self.manager, Permission.READ_TEAM_REPORT, self.foreign, self.other))

    def test_each_inactive_ancestor_revokes_access(self):
        membership = self.memberships["manager"]
        for record in (membership, membership.organisation_membership, self.cedar, self.org, self.manager):
            record.is_active = False
            record.save()
            self.assertFalse(self.allowed(self.manager, Permission.READ_MANAGER_REPORT))
            record.is_active = True
            record.save()

    def test_http_and_htmx_methods_enforce_same_permissions(self):
        for user, expected in ((self.member, 404), (self.manager, 200), (self.admin, 404)):
            self.client.force_login(user)
            for method in (self.client.get, self.client.post):
                for htmx in (False, True):
                    for permission in (Permission.READ_MANAGER_REPORT, Permission.PUBLISH_COMMITMENT):
                        response = method(self.url(permission), HTTP_HX_REQUEST="true" if htmx else "false")
                        self.assertEqual(response.status_code, expected)
                        self.assertEqual(response.content, b"Authorized synthetic payload" if expected == 200 else b"Not found.")

    def test_denied_and_nonexistent_ids_have_same_response(self):
        self.client.force_login(self.manager)
        for url in (self.url(Permission.READ_MANAGER_REPORT, self.birch),
                    self.url(Permission.READ_MANAGER_REPORT, self.foreign),
                    f"/probe/{self.org.pk}/999999/read_manager_report/"):
            for method in (self.client.get, self.client.post):
                response = method(url, {"project_id": self.cedar.pk}, HTTP_HX_REQUEST="true")
                self.assertEqual((response.status_code, response.content), (404, b"Not found."))

    def test_anonymous_all_methods_follow_login_behavior(self):
        for method in (self.client.get, self.client.post):
            response = method(self.url(Permission.READ_TEAM_REPORT), HTTP_HX_REQUEST="true")
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith("/accounts/login/?next=/probe/"))
            self.assertNotIn(b"Authorized synthetic payload", response.content)

    def test_removed_membership_and_raw_routes_deny_requests(self):
        self.client.force_login(self.manager)
        membership = self.memberships["manager"]
        membership.is_active = False
        membership.save()
        self.assertEqual(self.client.get(self.url(Permission.READ_TEAM_REPORT)).status_code, 404)
        for user in (self.member, self.manager, self.admin):
            self.client.force_login(user)
            response = self.client.get(self.url(Permission.READ_RAW_FEEDBACK))
            self.assertEqual((response.status_code, response.content), (404, b"Not found."))
