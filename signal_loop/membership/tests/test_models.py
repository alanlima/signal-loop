import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.test import TestCase

from signal_loop.membership.models import (
    Organisation, OrganisationMembership, Project, ProjectMembership, Role,
)
from signal_loop.membership.services import assign_project_member, change_membership


pytestmark = pytest.mark.usefixtures("postgres_database")


class MembershipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="synthetic_member")
        cls.organisation = Organisation.objects.create(name="Synthetic Studio")
        cls.other = Organisation.objects.create(name="Other Studio")
        cls.member = OrganisationMembership.objects.create(organisation=cls.organisation, user=cls.user)
        cls.foreign_member = OrganisationMembership.objects.create(organisation=cls.other, user=cls.user)
        cls.cedar = Project.objects.create(name="Cedar", organisation=cls.organisation)
        cls.birch = Project.objects.create(name="Birch", organisation=cls.organisation)

    def test_multiple_projects_do_not_share_roles_or_create_membership(self):
        assign_project_member(project=self.cedar, organisation_membership=self.member, role=Role.MANAGER)
        self.assertFalse(self.birch.memberships.exists())
        second = assign_project_member(project=self.birch, organisation_membership=self.member, role=Role.MEMBER)
        self.assertEqual(second.role, Role.MEMBER)
        self.assertEqual(self.member.project_memberships.count(), 2)

    def test_duplicate_organisation_membership_database_constraint(self):
        duplicate = OrganisationMembership(organisation=self.organisation, user=self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.Model.save(duplicate, force_insert=True)

    def test_duplicate_project_membership_database_constraint(self):
        assign_project_member(project=self.cedar, organisation_membership=self.member, role=Role.MEMBER)
        duplicate = ProjectMembership(project=self.cedar, organisation_membership=self.member)
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.Model.save(duplicate, force_insert=True)

    def test_direct_validation_and_save_reject_cross_organisation(self):
        invalid = ProjectMembership(project=self.cedar, organisation_membership=self.foreign_member)
        for operation in (invalid.full_clean, invalid.save):
            with self.assertRaises(ValidationError):
                operation()
        self.assertFalse(self.cedar.memberships.exists())

    def test_service_rejects_cross_organisation(self):
        with self.assertRaises(ValidationError):
            assign_project_member(project=self.cedar, organisation_membership=self.foreign_member, role=Role.MEMBER)

    def test_update_cannot_reassign_membership_or_project_organisation(self):
        membership = assign_project_member(project=self.cedar, organisation_membership=self.member, role=Role.MEMBER)
        membership.organisation_membership = self.foreign_member
        with self.assertRaises(ValidationError):
            membership.save(update_fields=["organisation_membership"])
        self.cedar.organisation = self.other
        with self.assertRaises(ValidationError):
            self.cedar.save()
        self.member.organisation = self.other
        with self.assertRaises(ValidationError):
            self.member.save()

    def test_invalid_roles_rejected_on_create_and_update(self):
        with self.assertRaises(ValidationError):
            assign_project_member(project=self.cedar, organisation_membership=self.member, role="owner")
        with self.assertRaises(ValidationError):
            change_membership(membership=self.member, role="owner")
        invalid = ProjectMembership(project=self.cedar, organisation_membership=self.member, role="owner")
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.Model.save(invalid, force_insert=True)

    def test_role_change_and_removal_retain_records(self):
        membership = assign_project_member(project=self.cedar, organisation_membership=self.member, role=Role.MEMBER)
        change_membership(membership=membership, role=Role.MANAGER)
        change_membership(membership=membership, is_active=False)
        membership.refresh_from_db()
        self.assertFalse(membership.is_active)
        self.assertEqual(membership.role, Role.MANAGER)
        self.assertEqual(self.member.project_memberships.count(), 1)
        with self.assertRaises(TypeError):
            membership.delete()

    def test_bulk_bypasses_are_rejected(self):
        with self.assertRaises(TypeError):
            OrganisationMembership.objects.filter(pk=self.member.pk).update(role="owner")
        with self.assertRaises(TypeError):
            ProjectMembership.objects.bulk_create([
                ProjectMembership(project=self.cedar, organisation_membership=self.foreign_member),
            ])
        with self.assertRaises(TypeError):
            OrganisationMembership.objects.bulk_update([self.member], ["role"])
        with self.assertRaises(TypeError):
            self.member.project_memberships.all().delete()
