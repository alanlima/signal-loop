from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from functools import partial
import json
from threading import Event
from uuid import UUID
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings

from signal_loop.admission.services import VerifiedPrincipal
from signal_loop.invitations.models import InvitationDelivery
from signal_loop.invitations.services import DefiniteDeliveryFailure, VerifiedPrimaryContact, deliver, send_window_invitations
from signal_loop.membership.models import Organisation, OrganisationMembership, Project, ProjectMembership
from signal_loop.windows.services import create_weekly_window


pytestmark = pytest.mark.usefixtures("postgres_database")
AT = datetime(2026, 9, 8, tzinfo=timezone.utc)
P1 = UUID("20000000-0000-4000-8000-000000000001")
P2 = UUID("20000000-0000-4000-8000-000000000002")


def principal(user, organisation):
    values = {"rowan": P1, "rowan_alias": P1, "avery": P2}
    return VerifiedPrincipal(values[user.username]) if user.username in values else None


def contact(identifier, organisation):
    return VerifiedPrimaryContact(identifier, ("rowan.primary@example.com" if identifier == P1 else "avery.primary@example.com",))


def setup_fixture():
    org = Organisation.objects.create(name="Synthetic invitations")
    projects = [Project.objects.create(organisation=org, name=name) for name in ("Cedar", "Birch")]
    for name in ("rowan", "rowan_alias", "avery", "unverified"):
        user = get_user_model().objects.create_user(username=name, email="do-not-use-alias@example.com")
        membership = OrganisationMembership.objects.create(organisation=org, user=user)
        for project in projects:
            ProjectMembership.objects.create(project=project, organisation_membership=membership)
    window = create_weekly_window(organisation=org, week_start=date(2026, 9, 7), timezone_name="UTC")
    return org, projects, window


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class InvitationTests(TestCase):
    def setUp(self):
        self.org, self.projects, self.window = setup_fixture()

    def send(self, **kwargs):
        return send_window_invitations(window_id=self.window.pk, principal_provider=principal,
                                       contact_provider=kwargs.pop("contact_provider", contact),
                                       clock=kwargs.pop("clock", lambda: AT), **kwargs)

    def test_alias_projects_primary_contact_templates_neutral_url_and_rerun(self):
        result = self.send()
        self.assertEqual(result["sent"], 2)
        self.assertEqual(result["withheld"], 1)
        self.assertEqual({message.to[0] for message in mail.outbox}, {"rowan.primary@example.com", "avery.primary@example.com"})
        for message in mail.outbox:
            self.assertIn("http://127.0.0.1:8000/app/check-in/", message.body)
            self.assertIn("http://127.0.0.1:8000/app/check-in/", message.alternatives[0].content)
            self.assertNotIn("?", message.body)
            self.assertNotIn(str(P1), message.body)
            self.assertNotIn("Cedar", message.body)
        self.assertEqual(self.send()["skipped"], 2)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(InvitationDelivery.objects.count(), 2)
        fields = {field.name for field in InvitationDelivery._meta.fields}
        self.assertFalse(fields & {"email", "user", "feedback", "response", "content", "credential"})

    def test_missing_ambiguous_wrong_principal_contact_withheld(self):
        for addresses in ((), ("one@example.com", "two@example.com"), ("invalid",)):
            result = self.send(contact_provider=lambda identifier, org: VerifiedPrimaryContact(identifier, addresses))
            self.assertEqual(result["sent"], 0)
        self.assertEqual(self.send(contact_provider=lambda identifier, org: VerifiedPrimaryContact(UUID(int=0), ("one@example.com",)))["sent"], 0)
        self.assertEqual(InvitationDelivery.objects.filter(state="withheld").count(), 2)
        self.assertEqual(self.send()["sent"], 2)

    def test_snapshot_live_revocation_late_join_and_cross_organisation(self):
        foreign = Organisation.objects.create(name="Foreign")
        foreign_project = Project.objects.create(organisation=foreign, name="Foreign")
        outsider = get_user_model().objects.create_user(username="outside")
        outside_membership = OrganisationMembership.objects.create(organisation=foreign, user=outsider)
        ProjectMembership.objects.create(project=foreign_project, organisation_membership=outside_membership)
        late = get_user_model().objects.create_user(username="late")
        late_membership = OrganisationMembership.objects.create(organisation=self.org, user=late)
        ProjectMembership.objects.create(project=self.projects[0], organisation_membership=late_membership)
        avery = get_user_model().objects.get(username="avery")
        avery.is_active = False
        avery.save()
        result = self.send()
        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["withheld"], 1)
        self.assertEqual(mail.outbox[0].to, ["rowan.primary@example.com"])
        self.assertEqual(InvitationDelivery.objects.count(), 1)

    def test_partial_definite_failure_retries_only_failed(self):
        def partial(address):
            if address.startswith("avery"):
                raise DefiniteDeliveryFailure()
            deliver(address)
        self.assertEqual(self.send(transport=partial)["failed"], 1)
        self.assertEqual(len(mail.outbox), 1)
        result = self.send()
        self.assertEqual((result["sent"], result["skipped"]), (1, 1))
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(InvitationDelivery.objects.get(principal=P2).attempts, 2)

    def test_unknown_result_or_crash_quarantines_without_resend(self):
        def ambiguous(address):
            raise RuntimeError("synthetic private address diagnostic")
        self.assertEqual(self.send(transport=ambiguous)["ambiguous"], 2)
        self.assertEqual(self.send()["ambiguous"], 2)
        self.assertFalse(mail.outbox)
        row = InvitationDelivery.objects.get(principal=P1)
        row.state = "sending"
        row.attempt_started_at = AT - timedelta(minutes=3)
        row.save()
        self.assertEqual(self.send()["ambiguous"], 2)
        row.refresh_from_db()
        self.assertEqual(row.state, "ambiguous")

    def test_exact_window_bounds_and_command_safe_counts(self):
        self.assertEqual(self.send(clock=lambda: self.window.opens_at - timedelta(microseconds=1))["code"], "window_unavailable")
        self.assertEqual(self.send(clock=lambda: self.window.closes_at)["code"], "window_unavailable")
        self.assertEqual(self.send(clock=lambda: self.window.opens_at)["sent"], 2)
        output = StringIO()
        with override_settings(CHECKIN_PRINCIPAL_PROVIDER=principal, INVITATION_CONTACT_PROVIDER=contact):
            # Date in the past is fine: command safely reports window unavailable.
            call_command("send_invitations", str(self.window.pk), stdout=output)
        result = json.loads(output.getvalue())
        self.assertIn("code", result)
        self.assertNotIn("@", output.getvalue())

    def test_duplicate_command_invocation_uses_durable_delivery_state(self):
        outputs = [StringIO(), StringIO()]
        with override_settings(CHECKIN_PRINCIPAL_PROVIDER=principal, INVITATION_CONTACT_PROVIDER=contact), patch(
            "signal_loop.invitations.management.commands.send_invitations.send_window_invitations",
            partial(send_window_invitations, clock=lambda: AT),
        ):
            for output in outputs:
                call_command("send_invitations", str(self.window.pk), stdout=output)
        self.assertEqual(json.loads(outputs[0].getvalue())["sent"], 2)
        self.assertEqual(json.loads(outputs[1].getvalue())["skipped"], 2)
        self.assertEqual(len(mail.outbox), 2)


class ConcurrentInvitationTests(TransactionTestCase):
    def test_concurrent_dispatch_cannot_send_twice_while_first_transport_inflight(self):
        _, _, window = setup_fixture()
        entered, release = Event(), Event()
        calls = []
        def transport(address):
            calls.append(address)
            entered.set()
            assert release.wait(10)
        def send(transport):
            close_old_connections()
            try:
                return send_window_invitations(window_id=window.pk, principal_provider=principal,
                                               contact_provider=contact, transport=transport, clock=lambda: AT)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(send, transport)
            self.assertTrue(entered.wait(10))
            # The concurrent caller may claim the other person, but never P1 twice.
            second = pool.submit(send, lambda address: calls.append(address))
            second.result(timeout=10)
            release.set()
            first.result(timeout=10)
        self.assertEqual(sorted(calls), ["avery.primary@example.com", "rowan.primary@example.com"])
        self.assertEqual(InvitationDelivery.objects.filter(state="sent").count(), 2)
