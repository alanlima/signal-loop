from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import Barrier
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase

from signal_loop.membership.models import Organisation, OrganisationMembership, Project, ProjectMembership, Role
from signal_loop.windows.models import EligibilitySnapshot, WeeklyWindow, weekly_bounds
from signal_loop.windows.services import create_weekly_window, eligible_projects, expire_eligibility


pytestmark = pytest.mark.usefixtures("postgres_database")


class WindowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(name="Synthetic Studio")
        cls.user = get_user_model().objects.create_user(username="window_member")
        member = OrganisationMembership.objects.create(organisation=cls.org, user=cls.user)
        cls.cedar = Project.objects.create(organisation=cls.org, name="Cedar")
        cls.birch = Project.objects.create(organisation=cls.org, name="birch")
        cls.assignment = ProjectMembership.objects.create(project=cls.cedar, organisation_membership=member)
        cls.other_assignment = ProjectMembership.objects.create(project=cls.birch, organisation_membership=member,
                                                                 role=Role.MANAGER)

    def create(self, week=date(2026, 9, 7), zone="Australia/Brisbane", org=None):
        return create_weekly_window(organisation=org or self.org, week_start=week, timezone_name=zone)

    def test_local_open_inclusive_close_exclusive_and_request_after_close(self):
        window = self.create()
        self.assertEqual(window.opens_at, datetime(2026, 9, 6, 14, tzinfo=timezone.utc))
        self.assertEqual(window.closes_at, datetime(2026, 9, 13, 14, tzinfo=timezone.utc))
        for at, count in ((window.opens_at - timedelta(microseconds=1), 0), (window.opens_at, 2),
                          (window.closes_at - timedelta(microseconds=1), 2), (window.closes_at, 0),
                          (window.closes_at + timedelta(days=1), 0)):
            self.assertEqual(len(eligible_projects(user=self.user, organisation=self.org, at=at)), count)
        local = window.opens_at.astimezone(ZoneInfo(window.timezone_name))
        self.assertEqual(len(eligible_projects(user=self.user, organisation=self.org, at=local)), 2)

    def test_dst_weeks_preserve_both_local_midnights(self):
        for week, hours in ((date(2026, 3, 2), 167), (date(2026, 10, 26), 169)):
            window = self.create(week, "America/New_York")
            self.assertEqual((window.closes_at - window.opens_at).total_seconds(), hours * 3600)
            for bound in (window.opens_at, window.closes_at):
                local = bound.astimezone(ZoneInfo(window.timezone_name))
                self.assertEqual((local.weekday(), local.hour, local.minute), (0, 0, 0))

    def test_year_rollover_adjacent_windows_and_invalid_schedule(self):
        first = self.create(date(2025, 12, 29))
        second = self.create(date(2026, 1, 5))
        self.assertEqual(first.closes_at, second.opens_at)
        self.assertEqual(first.week_start.isocalendar()[:2], (2026, 1))
        self.assertEqual(eligible_projects(user=self.user, organisation=self.org,
                                           at=second.opens_at)[0].window_id, second.pk)
        for week, zone in ((date(2026, 9, 8), "UTC"), (date(2026, 9, 7), "Invalid/Zone")):
            with self.assertRaises(ValidationError):
                weekly_bounds(week, zone)
        with self.assertRaises(ValidationError):
            eligible_projects(user=self.user, organisation=self.org, at=datetime(2026, 9, 7))

    def test_snapshot_zero_one_multiple_and_tenant_isolation(self):
        window = self.create()
        empty = get_user_model().objects.create_user(username="window_empty")
        self.assertEqual(eligible_projects(user=empty, organisation=self.org, at=window.opens_at), ())
        rows = eligible_projects(user=self.user, organisation=self.org, at=window.opens_at)
        self.assertEqual([row.project_id for row in rows], [self.birch.pk, self.cedar.pk])
        other_org = Organisation.objects.create(name="Other synthetic studio")
        other_member = OrganisationMembership.objects.create(organisation=other_org, user=self.user)
        other_project = Project.objects.create(organisation=other_org, name="Unrelated")
        ProjectMembership.objects.create(project=other_project, organisation_membership=other_member)
        other_window = self.create(org=other_org)
        own = eligible_projects(user=self.user, organisation=other_org, at=other_window.opens_at)
        self.assertEqual([row.project_id for row in own], [other_project.pk])
        self.assertEqual(window.eligibility.count(), 2)

    def test_membership_changes_do_not_rewrite_snapshot(self):
        window = self.create()
        self.assignment.role = Role.MANAGER
        self.assignment.save()
        self.other_assignment.is_active = False
        self.other_assignment.save()
        added = Project.objects.create(organisation=self.org, name="Newly joined")
        ProjectMembership.objects.create(project=added, organisation_membership=self.assignment.organisation_membership)
        rows = eligible_projects(user=self.user, organisation=self.org, at=window.opens_at)
        self.assertEqual([(row.project_id, row.role_at_open) for row in rows], [(self.cedar.pk, Role.MEMBER)])
        self.assertEqual(list(window.eligibility.order_by("membership_id").values_list("role", flat=True)),
                         [Role.MEMBER, Role.MANAGER])
        self.assertEqual(window.eligibility.count(), 2)

    def test_overlap_rejected_even_with_changed_timezone(self):
        self.create()
        with self.assertRaises(ValidationError):
            self.create()
        # Previous week's New York close overlaps the Brisbane opening by 14 hours.
        with self.assertRaises(ValidationError):
            self.create(date(2026, 8, 31), "America/New_York")
        self.assertEqual(WeeklyWindow.objects.count(), 1)
        self.assertEqual(EligibilitySnapshot.objects.count(), 2)

    def test_snapshot_capture_failure_rolls_back_window_and_all_rows(self):
        original_save = EligibilitySnapshot.save
        captured = 0

        def fail_second(snapshot, *args, **kwargs):
            nonlocal captured
            captured += 1
            if captured == 2:
                raise RuntimeError("Synthetic capture failure")
            return original_save(snapshot, *args, **kwargs)

        with patch.object(EligibilitySnapshot, "save", fail_second):
            with self.assertRaises(RuntimeError):
                self.create()
        self.assertEqual(WeeklyWindow.objects.count(), 0)
        self.assertEqual(EligibilitySnapshot.objects.count(), 0)

    def test_deactivated_account_is_rechecked_from_database(self):
        window = self.create()
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertTrue(self.user.is_active)  # caller retains an old object
        self.assertEqual(eligible_projects(user=self.user, organisation=self.org, at=window.opens_at), ())
        self.assertEqual(window.eligibility.count(), 2)

    def test_no_snapshot_mutation_or_default_admin_permissions_and_expiry(self):
        window = self.create()
        snapshot = window.eligibility.first()
        with self.assertRaises(ValidationError):
            snapshot.save()
        with self.assertRaises(ValidationError):
            EligibilitySnapshot.objects.create(window=window, membership=self.assignment, role=Role.MEMBER)
        with self.assertRaises(ValidationError):
            window.save()
        for model in (WeeklyWindow, EligibilitySnapshot):
            self.assertEqual(model._meta.default_permissions, ())
            with self.assertRaises(TypeError):
                model.objects.all().update()
            with self.assertRaises(TypeError):
                model.objects.all().delete()
            with self.assertRaises(TypeError):
                model.objects.bulk_create([])
        expire_eligibility(at=window.closes_at + timedelta(days=7) - timedelta(microseconds=1))
        self.assertEqual(window.eligibility.count(), 2)
        expire_eligibility(at=window.closes_at + timedelta(days=7))
        self.assertEqual(window.eligibility.count(), 0)
        self.assertTrue(WeeklyWindow.objects.filter(pk=window.pk).exists())


class ConcurrentWindowTests(TransactionTestCase):
    def test_concurrent_overlapping_creates_leave_one_complete_snapshot(self):
        org = Organisation.objects.create(name="Concurrent synthetic studio")
        user = get_user_model().objects.create_user(username="concurrent_member")
        member = OrganisationMembership.objects.create(organisation=org, user=user)
        project = Project.objects.create(organisation=org, name="Cedar")
        ProjectMembership.objects.create(project=project, organisation_membership=member)
        start = Barrier(2)

        def create(schedule):
            close_old_connections()
            try:
                start.wait(timeout=10)
                week, zone = schedule
                create_weekly_window(organisation=org, week_start=week, timezone_name=zone)
                return "created"
            except ValidationError:
                return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(create, ((date(2026, 9, 7), "Australia/Brisbane"),
                                                (date(2026, 8, 31), "America/New_York"))))
        self.assertCountEqual(results, ["created", "rejected"])
        self.assertEqual(WeeklyWindow.objects.count(), 1)
        self.assertEqual(EligibilitySnapshot.objects.count(), 1)
