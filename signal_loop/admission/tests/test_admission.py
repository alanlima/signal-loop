from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import json
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase

from signal_loop.admission.models import Credential, Journey, Participation, Principal
from signal_loop.admission.services import (
    AdmissionError, IssuedCredential, VerifiedPrincipal, discard, issue, own_status, redeem, reconcile_expired_journeys,
)
from signal_loop.membership.models import Organisation, OrganisationMembership, Project, ProjectMembership
from signal_loop.windows.services import create_weekly_window


pytestmark = pytest.mark.usefixtures("postgres_database")
P1 = UUID("00000000-0000-4000-8000-000000000001")
P2 = UUID("00000000-0000-4000-8000-000000000002")


class AdmissionTests(TransactionTestCase):
    def setUp(self):
        self.at = datetime(2026, 9, 8, tzinfo=timezone.utc)
        self.rowan = get_user_model().objects.create_user(username="synthetic_rowan")
        self.alias = get_user_model().objects.create_user(username="synthetic_rowan_alias")
        self.avery = get_user_model().objects.create_user(username="synthetic_avery")
        self.unverified = get_user_model().objects.create_user(username="synthetic_unverified")
        self.directory = {self.rowan.pk: P1, self.alias.pk: P1, self.avery.pk: P2}
        self.orgs, self.projects, self.windows = [], [], []
        for name, zone in (("Cedar", "Australia/Brisbane"), ("Birch", "America/New_York")):
            org = Organisation.objects.create(name=f"Synthetic {name} studio")
            project = Project.objects.create(organisation=org, name=name)
            for user in (self.rowan, self.alias, self.avery, self.unverified):
                membership = OrganisationMembership.objects.create(organisation=org, user=user)
                ProjectMembership.objects.create(project=project, organisation_membership=membership)
            self.orgs.append(org)
            self.projects.append(project)
            self.windows.append(create_weekly_window(organisation=org, week_start=date(2026, 9, 7),
                                                      timezone_name=zone))
        self.scopes = [(p.pk, w.pk) for p, w in zip(self.projects, self.windows)]
        # Actual transaction participants, exclusively inside the disposable test DB.
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE admission_test_sink (id uuid PRIMARY KEY, payload jsonb NOT NULL)")
            cursor.execute("CREATE TABLE admission_test_draft (content text NOT NULL)")
            cursor.execute("INSERT INTO admission_test_draft VALUES ('Synthetic private reflection')")

    def tearDown(self):
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE admission_test_sink")
            cursor.execute("DROP TABLE admission_test_draft")

    def provider(self, user, organisation):
        identifier = self.directory.get(user.pk)
        return VerifiedPrincipal(identifier) if identifier else None

    def begin(self, user=None, scopes=None, at=None):
        return issue(user=user or self.rowan, scopes=self.scopes if scopes is None else scopes,
                     provider=self.provider, clock=lambda: at or self.at)

    def sections(self, issued):
        return [{"project": credential.project, "week": "2026-09-07",
                 "answers": {"J1": "on_track", "J2": "manageable", "J3": "Shared synthetic feedback"}}
                for credential in issued.credentials]

    @staticmethod
    def sink(sections):
        with connection.cursor() as cursor:
            for section in sections:
                cursor.execute("INSERT INTO admission_test_sink VALUES (%s, %s::jsonb)",
                               [uuid4(), json.dumps(section)])

    @staticmethod
    def clear_draft():
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM admission_test_draft")

    def submit(self, issued, **overrides):
        args = dict(user=self.rowan, week=issued.week, claims=issued.credentials,
                    sections=self.sections(issued), sink=self.sink, provider=self.provider,
                    clear_draft=self.clear_draft, clock=lambda: self.at)
        args.update(overrides)
        return redeem(**args)

    def count_sink(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM admission_test_sink")
            return cursor.fetchone()[0]

    def test_verified_provider_mandatory_aliases_share_one_journey(self):
        with self.assertRaises(AdmissionError):
            issue(user=self.rowan, scopes=self.scopes, clock=lambda: self.at)
        with self.assertRaises(AdmissionError):
            self.begin(self.unverified)
        self.assertEqual(Principal.objects.count(), 0)
        first = self.begin()
        rotated = self.begin(self.alias)
        self.assertEqual(Journey.objects.count(), 1)
        self.assertEqual(Participation.objects.count(), 2)
        self.assertEqual(first.expires_at, rotated.expires_at)
        self.assertNotEqual(first.credentials[0].secret, rotated.credentials[0].secret)
        with self.assertRaises(AdmissionError):
            self.submit(first)
        self.assertEqual(self.submit(rotated, user=self.alias), "complete")
        self.assertEqual(own_status(user=self.rowan, organisation=self.orgs[0], week=first.week,
                                   provider=self.provider, clock=lambda: self.at), "complete")

    def test_success_sink_contains_only_anonymous_fields_and_clears_transient_state(self):
        issued = self.begin()
        self.assertEqual(issued.expires_at, self.windows[0].closes_at)
        self.submit(issued)
        with connection.cursor() as cursor:
            cursor.execute("SELECT payload FROM admission_test_sink")
            payloads = [row[0] if isinstance(row[0], dict) else json.loads(row[0]) for row in cursor.fetchall()]
            cursor.execute("SELECT COUNT(*) FROM admission_test_draft")
            self.assertEqual(cursor.fetchone()[0], 0)
        for payload in payloads:
            self.assertEqual(set(payload), {"project", "week", "schema", "privacy_policy", "answers"})
            self.assertEqual(set(payload["answers"]), {"J1", "J2", "J3"})
            self.assertNotIn(issued.credentials[0].secret, json.dumps(payload))
        journey = Journey.objects.get()
        self.assertEqual((journey.state, journey.selected_scopes, journey.started_at, journey.expires_at),
                         (Journey.State.COMPLETED, [], None, None))
        self.assertEqual(Participation.objects.filter(consumed=True).count(), 2)
        self.assertFalse(Credential.objects.filter(active=True).exists())
        self.assertEqual(len(Credential.objects.first().verifier), 64)

    def test_unknown_tampered_wrong_owner_project_week_and_payload_rejected(self):
        issued = self.begin()
        original = issued.credentials[0]
        bad_secret = IssuedCredential(original.project, original.window, "synthetic-unknown-secret")
        cases = [
            {"claims": (bad_secret, issued.credentials[1])},
            {"claims": (IssuedCredential(original.project, original.window, issued.credentials[1].secret),
                        issued.credentials[1])},
            {"user": self.avery},
            {"week": date(2026, 8, 31)},
            {"claims": (IssuedCredential(original.project, 999999, original.secret),)},
            {"sections": [{**self.sections(issued)[0], "week": "2026-08-31"}, self.sections(issued)[1]]},
            {"sections": [{**self.sections(issued)[0], "user": "synthetic"}, self.sections(issued)[1]]},
            {"sections": [{**self.sections(issued)[0], "answers": {"P1": "high"}}, self.sections(issued)[1]]},
            {"sections": [{**self.sections(issued)[0], "answers": {"J1": "invented", "J2": "manageable"}}, self.sections(issued)[1]]},
        ]
        for args in cases:
            with self.assertRaises(AdmissionError) as error:
                self.submit(issued, **args)
            self.assertNotIn(original.secret, str(error.exception))
            self.assertFalse(Participation.objects.filter(consumed=True).exists())
            self.assertEqual(self.count_sink(), 0)

    def test_sink_failure_rolls_back_every_write_and_preserves_safe_retry(self):
        issued = self.begin()

        def fail_after_first(sections):
            self.sink(sections[:1])
            raise RuntimeError("Synthetic internal failure; must not reach client")

        with self.assertRaises(AdmissionError) as error:
            self.submit(issued, sink=fail_after_first)
        self.assertEqual(str(error.exception), "retryable_failure")
        self.assertEqual(self.count_sink(), 0)
        self.assertFalse(Participation.objects.filter(consumed=True).exists())
        self.assertEqual(Journey.objects.get().state, Journey.State.OPEN)
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM admission_test_draft")
            self.assertEqual(cursor.fetchone()[0], 1)
        self.assertEqual(self.submit(issued), "complete")
        self.assertEqual(self.count_sink(), 2)

    def test_draft_cleanup_failure_rolls_back_sink_and_consumption(self):
        issued = self.begin()

        def fail_cleanup():
            self.clear_draft()
            raise RuntimeError("Synthetic cleanup failure")

        with self.assertRaises(AdmissionError):
            self.submit(issued, clear_draft=fail_cleanup)
        self.assertEqual(self.count_sink(), 0)
        self.assertFalse(Participation.objects.filter(consumed=True).exists())
        self.assertEqual(self.submit(issued), "complete")

    def test_replay_and_lost_response_status_never_call_sink_again(self):
        issued = self.begin()
        self.submit(issued)  # simulate response discarded by caller
        with self.assertRaises(AdmissionError):
            self.submit(issued)
        self.assertEqual(self.count_sink(), 2)
        late = self.windows[0].closes_at + timedelta(hours=1)
        self.assertEqual(own_status(user=self.alias, organisation=self.orgs[1], week=issued.week,
                                   provider=self.provider, clock=lambda: late), "complete")
        deadline = Journey.objects.get().retain_until
        self.assertEqual(own_status(user=self.rowan, organisation=self.orgs[0], week=issued.week,
                                   provider=self.provider, clock=lambda: deadline), "unavailable")

    def test_expiry_exact_boundary_and_late_validation_seal_no_second_journey(self):
        issued = self.begin()
        with self.assertRaises(AdmissionError):
            self.submit(issued, clock=lambda: issued.expires_at)
        clock_values = iter([issued.expires_at - timedelta(microseconds=1), issued.expires_at])
        with self.assertRaises(AdmissionError):
            self.submit(issued, clock=lambda: next(clock_values))
        self.assertEqual(self.count_sink(), 0)
        with self.assertRaises(AdmissionError):
            self.begin(at=issued.expires_at)
        self.assertEqual(Journey.objects.get().state, Journey.State.EXPIRED)
        self.assertEqual(Journey.objects.get().selected_scopes, [])
        with self.assertRaises(AdmissionError):
            self.begin(scopes=[self.scopes[1]], at=issued.expires_at + timedelta(minutes=1))

    def test_discard_and_selection_resume_cannot_reset_week_or_expiry(self):
        issued = self.begin()
        with self.assertRaises(AdmissionError):
            self.begin(scopes=[self.scopes[1]])
        self.assertEqual(discard(user=self.rowan, organisation=self.orgs[0], week=issued.week,
                                 provider=self.provider, clock=lambda: self.at), "unavailable")
        self.assertEqual(Journey.objects.get().state, Journey.State.DISCARDED)
        self.assertFalse(Credential.objects.filter(active=True).exists())
        with self.assertRaises(AdmissionError):
            self.begin(self.alias)

    def test_revoked_membership_rejects_all_without_consumption(self):
        issued = self.begin()
        membership = ProjectMembership.objects.get(project=self.projects[0], organisation_membership__user=self.rowan)
        membership.is_active = False
        membership.save()
        with self.assertRaises(AdmissionError):
            self.submit(issued)
        self.assertEqual(self.count_sink(), 0)
        self.assertFalse(Participation.objects.filter(consumed=True).exists())

    def test_non_substantive_projects_do_not_consume_slots(self):
        issued = self.begin()
        sections = self.sections(issued)
        for section in sections:
            section["answers"] = {"J1": "prefer_not_to_say", "J2": "not_enough_context", "J3": " \n"}
        self.assertEqual(self.submit(issued, sections=sections), "no_feedback")
        self.assertEqual(self.count_sink(), 0)
        self.assertFalse(Participation.objects.filter(consumed=True).exists())
        sections[0]["answers"]["J1"] = "on_track"
        self.assertEqual(self.submit(issued, sections=sections), "complete")
        self.assertEqual(self.count_sink(), 1)
        self.assertEqual(Participation.objects.filter(consumed=True).count(), 1)

    def test_global_week_rollover_does_not_repeat_unclosed_local_window(self):
        issued = self.begin(scopes=[self.scopes[1]])
        self.assertEqual(issued.expires_at, datetime(2026, 9, 14, tzinfo=timezone.utc))
        self.submit(issued)
        with self.assertRaises(AdmissionError):
            self.begin(scopes=[self.scopes[1]], at=datetime(2026, 9, 14, 1, tzinfo=timezone.utc))
        self.assertEqual(Journey.objects.count(), 1)  # failed Begin rolled back
        self.assertEqual(self.count_sink(), 1)

    def test_concurrent_alias_redemptions_commit_one_anonymous_set(self):
        issued = self.begin()
        barrier = Barrier(2)

        def submit(user):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return self.submit(issued, user=user)
            except AdmissionError as error:
                return error.code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, [self.rowan, self.alias]))
        self.assertCountEqual(results, ["complete", "unavailable"])
        self.assertEqual(self.count_sink(), 2)
        self.assertEqual(Participation.objects.filter(consumed=True).count(), 2)

    def test_late_old_journey_expiry_does_not_cancel_new_week_credential(self):
        old = self.begin(scopes=[self.scopes[1]])
        new_time = datetime(2026, 9, 14, 1, tzinfo=timezone.utc)
        new = self.begin(scopes=[self.scopes[1]], at=new_time)
        reconcile_expired_journeys(user=self.rowan, organisation=self.orgs[1], provider=self.provider,
                                   clock=lambda: new_time)
        self.assertEqual(Journey.objects.get(week=old.week).state, Journey.State.EXPIRED)
        self.assertEqual(own_status(user=self.rowan, organisation=self.orgs[1], week=old.week,
                                   provider=self.provider, clock=lambda: new_time), "unavailable")
        self.assertEqual(self.submit(new, clock=lambda: new_time), "complete")

    def test_open_inclusive_and_invalid_selection_do_not_issue_early(self):
        opening = self.windows[0].opens_at
        with self.assertRaises(AdmissionError):
            self.begin(scopes=[self.scopes[0]], at=opening - timedelta(microseconds=1))
        for scopes in ([], [self.scopes[0]] * 2, [self.scopes[0]] * 4):
            with self.assertRaises(AdmissionError):
                self.begin(scopes=scopes)
        self.assertEqual(Journey.objects.count(), 0)
        issued = self.begin(scopes=[self.scopes[0]], at=opening)
        self.assertEqual(issued.week, date(2026, 8, 31))
        self.assertEqual(issued.expires_at, datetime(2026, 9, 7, tzinfo=timezone.utc))
        self.assertNotIn(issued.credentials[0].secret, repr(issued))

    def test_provider_cannot_assign_different_people_for_one_combined_journey(self):
        def inconsistent(user, organisation):
            return VerifiedPrincipal(P1 if organisation.pk == self.orgs[0].pk else P2)

        with self.assertRaises(AdmissionError):
            issue(user=self.rowan, scopes=self.scopes, provider=inconsistent, clock=lambda: self.at)
        self.assertEqual(Journey.objects.count(), 0)
