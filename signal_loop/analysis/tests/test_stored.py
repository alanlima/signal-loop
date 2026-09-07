from datetime import date, datetime, timezone

import pytest
from django.test import TestCase

from signal_loop.analysis.aggregation import Assessment, RestrictedAnalysisInput, Suppressed, aggregate_stored
from signal_loop.analysis.tests.test_aggregation import FixtureVerifier
from signal_loop.feedback.models import FeedbackSection
from signal_loop.feedback.services import persist_sections
from signal_loop.membership.models import Organisation, Project
from signal_loop.windows.services import create_weekly_window


pytestmark = pytest.mark.usefixtures("postgres_database")


class StoredAggregationTests(TestCase):
    def test_canonical_database_input_scoped_no_identity_or_writes(self):
        week = date(2026, 9, 7)
        projects = []
        windows = []
        for name in ("Cedar", "Birch"):
            org = Organisation.objects.create(name=f"Synthetic {name}")
            project = Project.objects.create(organisation=org, name=name)
            projects.append(project)
            windows.append(create_weekly_window(organisation=org, week_start=week, timezone_name="UTC"))
            for _ in range(5):
                persist_sections([{"project": project.pk, "week": week.isoformat(),
                                   "schema": "project-feedback/1.0", "privacy_policy": "1.0",
                                   "answers": {"J1": "at_risk", "J2": "manageable"}}],
                                 clock=lambda: datetime(2026, 9, 8, tzinfo=timezone.utc))
        project = projects[0]
        sources = frozenset(str(row.pk) for row in FeedbackSection.objects.filter(project_id=project.pk))
        # Independent synthetic fixture attestation; production cannot manufacture
        # this assertion by counting the rows above. Missing provider fails closed.
        verifier = FixtureVerifier(Assessment(str(project.pk), week.isoformat(), sources, 5, True, True, True))
        args = {"project_id": project.pk, "week": week, "at": windows[0].closes_at}
        self.assertEqual(aggregate_stored(**args), Suppressed())
        result = aggregate_stored(**args, verifier=verifier)
        self.assertIsInstance(result, RestrictedAnalysisInput)
        self.assertEqual(len(result.feedback_for_analysis()), 5)
        self.assertTrue(all(row["project"] == str(project.pk) for row in result.feedback_for_analysis()))
        self.assertEqual(FeedbackSection.objects.count(), 10)
        self.assertEqual(aggregate_stored(**{**args, "project_id": projects[1].pk}, verifier=verifier), Suppressed())
        self.assertEqual(aggregate_stored(**{**args, "project_id": 999999}, verifier=verifier), Suppressed())
