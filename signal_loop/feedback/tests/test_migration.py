from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from signal_loop.contracts.feedback import validate_artifact
from signal_loop.feedback.models import FeedbackSection


pytestmark = pytest.mark.usefixtures("postgres_database")


class CanonicalMigrationTests(TransactionTestCase):
    def test_existing_intake_row_preserves_source_and_answers(self):
        before = [("feedback", "0001_initial")]
        after = [("feedback", "0002_canonical_feedback_artifact")]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            old_model = executor.loader.project_state(before).apps.get_model("feedback", "FeedbackSection")
            source = uuid4()
            expiry = datetime(2026, 9, 28, tzinfo=timezone.utc)
            old_model.objects.create(id=source, project_id=42, week=date(2026, 9, 7),
                schema="project-feedback/1.0", privacy_policy="1.0", expires_at=expiry,
                answers={"J1": "at_risk", "J2": "manageable", "J3": "Synthetic shared concern",
                         "F1": "Synthetic suggestion"})
            MigrationExecutor(connection).migrate(after)
            row = FeedbackSection.objects.get(pk=source)
            self.assertEqual(row.expires_at, expiry)
            self.assertEqual(row.data, {"source": str(source), "delivery": "at_risk", "workload": "manageable",
                                       "note": "Synthetic shared concern",
                                       "follow_up": {"question": "F1", "answer": "Synthetic suggestion"}})
            validate_artifact(row.as_artifact())
        finally:
            MigrationExecutor(connection).migrate(after)
