from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import date, datetime, timedelta, timezone
from functools import partial
from threading import Event
from unittest.mock import patch

import pytest
from django.db import close_old_connections, transaction
from django.test import TestCase, TransactionTestCase

from signal_loop.feedback.services import persist_sections
from signal_loop.feedback.models import FeedbackSection
from signal_loop.invitations.services import DefiniteDeliveryFailure, send_window_invitations
from signal_loop.invitations.tests.test_invitations import contact, principal, setup_fixture
from signal_loop.membership.models import Organisation, Project
from signal_loop.pipeline.models import DispatchJob, WindowDispatch
from signal_loop.pipeline.scheduling import configure_schedule, dispatch_due, enqueue_due, plan_due, run_job, expire_source_references
from signal_loop.windows.models import WeeklyWindow
from signal_loop.windows.services import create_weekly_window


pytestmark = pytest.mark.usefixtures("postgres_database")
START = datetime(2026, 9, 7, tzinfo=timezone.utc)


def configure(zone="UTC"):
    org = Organisation.objects.create(name="Synthetic schedule")
    projects = [Project.objects.create(organisation=org, name=name) for name in ("Cedar", "Empty")]
    configure_schedule(organisation_id=org.pk, timezone_name=zone)
    return org, projects


class SchedulingTests(TestCase):
    def test_open_close_exact_bounds_empty_projects_unique_versioned_jobs(self):
        org, projects = configure()
        sent = []
        result = dispatch_due(clock=lambda: START, publisher=lambda *args: sent.append(args))
        self.assertEqual(result["planning"]["opened"], 1)
        first = WeeklyWindow.objects.get(organisation=org)
        self.assertFalse(WindowDispatch.objects.get(window=first).captured_late)
        self.assertEqual(DispatchJob.objects.filter(kind="analysis").count(), 0)
        plan_due(clock=lambda: first.closes_at - timedelta(microseconds=1))
        self.assertEqual(DispatchJob.objects.filter(kind="analysis").count(), 0)
        plan_due(clock=lambda: first.closes_at)
        jobs = list(DispatchJob.objects.filter(kind="analysis"))
        self.assertEqual({job.project_id for job in jobs}, {p.pk for p in projects})
        self.assertTrue(all(job.frozen_sources == [] for job in jobs))
        for job in jobs:
            self.assertEqual(run_job(str(job.pk), clock=lambda: first.closes_at), "unavailable")
        plan_due(clock=lambda: first.closes_at)
        self.assertEqual(DispatchJob.objects.filter(kind="analysis").count(), 2)

    def test_dst_and_local_monday_boundaries(self):
        org, _ = configure("America/New_York")
        spring = datetime(2026, 3, 2, 5, tzinfo=timezone.utc)
        fall = datetime(2026, 10, 26, 4, tzinfo=timezone.utc)
        for instant, hours in ((spring, 167), (fall, 169)):
            plan_due(clock=lambda: instant)
            window = WeeklyWindow.objects.get(organisation=org, opens_at=instant)
            self.assertEqual((window.closes_at - window.opens_at).total_seconds(), hours * 3600)
            self.assertFalse(DispatchJob.objects.filter(kind="analysis", window=window).exists())
            plan_due(clock=lambda: window.closes_at)
            self.assertEqual(DispatchJob.objects.filter(kind="analysis", window=window).count(), 2)

    def test_legacy_materialized_window_queues_empty_project_without_inventing_roster(self):
        org, _ = configure()
        window = create_weekly_window(organisation=org, week_start=date(2026, 9, 7), timezone_name="UTC")
        self.assertEqual(window.eligibility.count(), 0)
        plan_due(clock=lambda: window.closes_at)
        self.assertEqual(DispatchJob.objects.filter(window=window, kind="analysis").count(), 2)
        self.assertEqual(window.eligibility.count(), 0)

    def test_downtime_only_current_late_capture_no_closed_historical_fabrication(self):
        org, projects = configure()
        plan_due(clock=lambda: START)
        # New project is captured for the current late window, never copied into old scope.
        late = Project.objects.create(organisation=org, name="Late")
        at = START + timedelta(days=15)
        plan_due(clock=lambda: at)
        self.assertEqual(set(WeeklyWindow.objects.filter(organisation=org).values_list("week_start", flat=True)),
                         {date(2026, 9, 7), date(2026, 9, 21)})
        current = WeeklyWindow.objects.get(organisation=org, week_start=date(2026, 9, 21))
        self.assertTrue(WindowDispatch.objects.get(window=current).captured_late)
        self.assertIn(late.pk, WindowDispatch.objects.get(window=current).projects)
        old_jobs = DispatchJob.objects.filter(kind="analysis", week=date(2026, 9, 7))
        self.assertEqual(set(old_jobs.values_list("project_id", flat=True)), {p.pk for p in projects})
        self.assertTrue(all(job.expires_at == START + timedelta(days=21) for job in old_jobs))

    def test_outbox_crash_recovery_duplicate_enqueue_and_fake_idempotency(self):
        configure()
        plan_due(clock=lambda: START)
        seen = []
        def crash(kind, reference, expiry):
            seen.append(reference)  # Simulates broker acceptance followed by lost acknowledgment.
            raise RuntimeError("synthetic private transport diagnostic")
        self.assertEqual(enqueue_due(clock=lambda: START, publisher=crash)["failed"], 1)
        job = DispatchJob.objects.get()
        self.assertEqual(job.state, "pending")
        enqueue_due(clock=lambda: START + timedelta(seconds=31), publisher=lambda kind, ref, expiry: seen.append(ref))
        self.assertEqual(seen, [str(job.pk), str(job.pk)])
        called = []
        def service(**kwargs):
            called.append(kwargs["window_id"])
            return {"code": "complete", "failed": 0, "withheld": 0}
        self.assertEqual(run_job(str(job.pk), clock=lambda: START + timedelta(seconds=32), invitation_service=service), "complete")
        self.assertEqual(run_job(str(job.pk), clock=lambda: START + timedelta(seconds=33), invitation_service=service), "complete")
        self.assertEqual(len(called), 1)

    def test_actual_invitation_service_partial_retry_uses_delivery_state(self):
        org, _, window = setup_fixture()
        configure_schedule(organisation_id=org.pk, timezone_name="UTC")
        plan_due(clock=lambda: START + timedelta(days=1))
        job = DispatchJob.objects.get(kind="invitation")
        delivered = []
        def first(address):
            if address.startswith("avery"):
                raise DefiniteDeliveryFailure()
            delivered.append(address)
        service = partial(send_window_invitations, principal_provider=principal, contact_provider=contact, transport=first)
        self.assertEqual(run_job(str(job.pk), clock=lambda: START + timedelta(days=1), invitation_service=service), "pending")
        service = partial(send_window_invitations, principal_provider=principal, contact_provider=contact, transport=delivered.append)
        run_job(str(job.pk), clock=lambda: START + timedelta(days=1, minutes=1), invitation_service=service)
        self.assertEqual(sorted(delivered), ["avery.primary@example.com", "rowan.primary@example.com"])
        self.assertEqual(job.window_id, window.pk)

    def test_expired_manifests_are_erased_even_terminal_and_rollback_counts_truthful(self):
        configure()
        with patch("signal_loop.pipeline.scheduling._create_job", side_effect=RuntimeError()):
            result = plan_due(clock=lambda: START)
        self.assertEqual(result, {"opened": 0, "closed": 0, "jobs": 0, "failed": 1})
        self.assertFalse(WeeklyWindow.objects.exists())
        plan_due(clock=lambda: START)
        job = DispatchJob.objects.get()
        job.state = "complete"
        job.frozen_sources = ["synthetic-local-ref"]
        job.save()
        expire_source_references(at=job.expires_at)
        job.refresh_from_db()
        self.assertEqual(job.frozen_sources, [])

    def test_stale_worker_lease_recovers_but_active_claim_and_deadline_block_execution(self):
        configure()
        plan_due(clock=lambda: START)
        job = DispatchJob.objects.get()
        job.state = "running"
        job.run_lease_until = START + timedelta(seconds=120)
        job.save()
        service = partial(send_window_invitations, principal_provider=principal, contact_provider=contact)
        self.assertEqual(run_job(str(job.pk), clock=lambda: START, invitation_service=service), "running")
        with patch("signal_loop.pipeline.scheduling.publish_job") as publish:
            enqueue_due(clock=lambda: START, publisher=publish)
        publish.assert_not_called()
        self.assertEqual(run_job(str(job.pk), clock=lambda: START + timedelta(seconds=121), invitation_service=service), "complete")
        job.state = "queued"
        job.save(update_fields=["state"])
        self.assertEqual(run_job(str(job.pk), clock=lambda: job.expires_at, invitation_service=service), "expired")

    def test_earlier_source_expiry_and_withdrawal_cannot_be_extended_by_job(self):
        _, projects = configure()
        plan_due(clock=lambda: START)
        window = WeeklyWindow.objects.get()
        # Explicit anonymous fixture with a stricter source deadline than P10's max.
        source = FeedbackSection(project_id=projects[0].pk, week=window.week_start,
                                 schema="feedback/1.0", privacy_policy="1.0",
                                 provenance={"producer": "fixture", "producer_version": "1.0", "input_refs": []},
                                 expires_at=window.closes_at + timedelta(hours=2))
        source.data = {"source": str(source.pk), "delivery": "on_track", "workload": "manageable"}
        source.save(_validated=True)
        plan_due(clock=lambda: window.closes_at)
        job = DispatchJob.objects.get(kind="analysis", project_id=projects[0].pk)
        self.assertEqual(job.expires_at, source.expires_at)
        self.assertEqual(run_job(str(job.pk), clock=lambda: source.expires_at), "expired")
        job.state = "pending"
        job.save(update_fields=["state"])
        # Operations-only withdrawal escape hatch, deliberately scoped to this fixture.
        from django.db.models import QuerySet
        QuerySet.delete(FeedbackSection.objects.filter(pk=source.pk))
        job.frozen_sources = [str(source.pk)]
        job.save(update_fields=["frozen_sources"])
        with patch("signal_loop.pipeline.scheduling.fake_analysis") as handler:
            self.assertEqual(run_job(str(job.pk), clock=lambda: window.closes_at, analysis_handler=handler), "unavailable")
        handler.assert_not_called()


class SchedulingConcurrencyTests(TransactionTestCase):
    def test_duplicate_concurrent_dispatchers_one_job_per_scope(self):
        configure()
        def plan():
            close_old_connections()
            try:
                return plan_due(clock=lambda: START)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result(timeout=10) for future in [pool.submit(plan), pool.submit(plan)]]
        self.assertEqual(sum(item["opened"] for item in results), 1)
        self.assertEqual(DispatchJob.objects.count(), 1)
        self.assertEqual(WeeklyWindow.objects.count(), 1)

    def test_closure_waits_for_preclose_transaction_before_freezing_sources(self):
        _, projects = configure()
        plan_due(clock=lambda: START)
        window = WeeklyWindow.objects.get()
        locked, release = Event(), Event()
        def admission():
            close_old_connections()
            try:
                with transaction.atomic():
                    WeeklyWindow.objects.select_for_update().get(pk=window.pk)
                    persist_sections([{"project": projects[0].pk, "week": "2026-09-07", "schema": "project-feedback/1.0",
                                       "privacy_policy": "1.0", "answers": {"J1": "on_track", "J2": "manageable"}}],
                                     clock=lambda: window.closes_at - timedelta(microseconds=1))
                    locked.set()
                    assert release.wait(10)
            finally:
                close_old_connections()
        def close():
            close_old_connections()
            try:
                return plan_due(clock=lambda: window.closes_at)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            submitting = pool.submit(admission)
            self.assertTrue(locked.wait(10))
            closing = pool.submit(close)
            with self.assertRaises(TimeoutError):
                closing.result(timeout=0.2)
            release.set()
            submitting.result(timeout=10)
            closing.result(timeout=10)
        job = DispatchJob.objects.get(kind="analysis", window=window, project_id=projects[0].pk)
        self.assertEqual(len(job.frozen_sources), 1)
        self.assertEqual(run_job(str(job.pk), clock=lambda: window.closes_at), "unavailable")
