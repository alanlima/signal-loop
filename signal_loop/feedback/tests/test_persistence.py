import ast
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest
from django.contrib import admin
from django.db import connection, transaction
from django.test import TestCase

from signal_loop.contracts.feedback import InvalidFeedback, SCHEMA, PRIVACY_POLICY, normalize_sections
from signal_loop.feedback.models import FeedbackSection
from signal_loop.feedback.services import PersistenceError, persist_sections
from signal_loop.membership.models import Organisation, Project
from signal_loop.windows.services import create_weekly_window, project_week_scope


pytestmark = pytest.mark.usefixtures("postgres_database")


class PersistenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.at = datetime(2026, 9, 8, tzinfo=timezone.utc)
        cls.projects = []
        cls.windows = []
        for name, zone in (("Cedar", "Australia/Brisbane"), ("Birch", "America/New_York")):
            org = Organisation.objects.create(name=f"Synthetic {name}")
            cls.projects.append(Project.objects.create(organisation=org, name=name))
            cls.windows.append(create_weekly_window(organisation=org, week_start=date(2026, 9, 7),
                                                    timezone_name=zone))

    def payload(self):
        return [{"project": p.pk, "week": "2026-09-07", "schema": SCHEMA, "privacy_policy": PRIVACY_POLICY,
                 "answers": {"J1": "on_track", "J2": "manageable", "J3": "Synthetic shared win"}}
                for p in self.projects]

    def persist(self, payload=None, **kwargs):
        return persist_sections(self.payload() if payload is None else payload,
                                clock=kwargs.get("clock", lambda: self.at))

    def test_independent_rows_coarse_expiry_and_no_identity_schema(self):
        self.assertEqual(self.persist(), "complete")
        rows = list(FeedbackSection.objects.order_by("project_id"))
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0].pk, rows[1].pk)
        for row, window in zip(rows, self.windows):
            self.assertIsInstance(row.pk, UUID)
            self.assertEqual(row.pk.version, 4)
            self.assertEqual(row.expires_at, window.closes_at + timedelta(days=14))
            self.assertEqual(row.week, date(2026, 9, 7))
        fields = {field.name for field in FeedbackSection._meta.fields}
        self.assertEqual(fields, {"id", "project_id", "week", "schema", "privacy_policy", "answers", "expires_at"})
        self.assertFalse(any(field.is_relation for field in FeedbackSection._meta.fields))
        self.assertEqual(FeedbackSection._meta.default_permissions, ())
        self.assertFalse(admin.site.is_registered(FeedbackSection))
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, FeedbackSection._meta.db_table)
        self.assertFalse(any(item["foreign_key"] for item in constraints.values()))

    def test_unknown_personal_identity_and_nested_metadata_rejected_before_writes(self):
        for key in ("user", "account_id", "credential", "participation_id", "batch_id", "created_at", "P1"):
            payload = self.payload()
            payload[1][key] = "synthetic forbidden value"
            with self.assertRaises(PersistenceError):
                self.persist(payload)
            self.assertFalse(FeedbackSection.objects.exists())
        for value in ({"P1": "high"}, {"J1": "on_track", "J2": "manageable", "user": "synthetic"},
                      {"J1": "on_track", "J2": "manageable", "J3": {"user": "synthetic"}}):
            payload = self.payload()
            payload[1]["answers"] = value
            with self.assertRaises(PersistenceError):
                self.persist(payload)
        self.assertFalse(FeedbackSection.objects.exists())

    def test_invalid_enums_lengths_types_versions_and_context_rejected(self):
        changes = [
            ("answers", {"J1": "invented", "J2": "manageable"}),
            ("answers", {"J1": "on_track"}),
            ("answers", {"J1": "on_track", "J2": "manageable", "J3": "x" * 321}),
            ("answers", {"J1": "blocked", "J2": "manageable", "F1": "x" * 241}),
            ("answers", {"J1": "on_track", "J2": "manageable", "F1": "not eligible"}),
            ("answers", {"J1": "blocked", "J2": "overloaded", "F1": "one", "F2": "two"}),
            ("answers", {"J1": True, "J2": "manageable"}),
            ("schema", "project-feedback/99"), ("privacy_policy", "99"),
            ("week", "2026-09-08"), ("week", "2026-08-31"), ("week", "20260907"),
            ("week", "invalid"), ("week", None), ("project", 999999), ("project", True),
        ]
        for key, value in changes:
            payload = self.payload()
            payload[1][key] = value
            with self.assertRaises(PersistenceError) as error:
                self.persist(payload)
            self.assertEqual(str(error.exception), "invalid_submission")
            self.assertFalse(FeedbackSection.objects.exists())
        for payload in ([], self.payload() * 2, [self.payload()[0]] * 2):
            with self.assertRaises(PersistenceError):
                self.persist(payload)

    def test_exact_unicode_limits_newline_normalization_and_blanks(self):
        payload = self.payload()
        payload[0]["answers"] = {"J1": "blocked", "J2": "manageable", "J3": "😀" * 320, "F1": "é" * 240}
        payload[1]["answers"]["J3"] = " \r\n\t\r "
        self.persist(payload)
        self.assertEqual(FeedbackSection.objects.get(project_id=self.projects[0].pk).answers["J3"], "😀" * 320)
        self.assertEqual(FeedbackSection.objects.get(project_id=self.projects[1].pk).answers["J3"], " \n\t\n ")
        self.assertEqual(payload[1]["answers"]["J3"], " \r\n\t\r ")  # no caller mutation

    def test_declined_and_blank_sections_omitted_without_neutral_defaults(self):
        payload = self.payload()
        for section in payload:
            section["answers"] = {"J1": "prefer_not_to_say", "J2": "not_enough_context", "J3": " \n"}
        self.assertEqual(self.persist(payload), "no_feedback")
        self.assertFalse(FeedbackSection.objects.exists())
        payload[0]["answers"]["J3"] = "A synthetic shared concern"
        self.assertEqual(self.persist(payload), "complete")
        self.assertEqual(FeedbackSection.objects.count(), 1)
        self.assertEqual(FeedbackSection.objects.get().answers["J1"], "prefer_not_to_say")

    def test_partial_database_failure_rolls_back_first_section(self):
        original_save = FeedbackSection.save
        saved = 0

        def fail_second(row, *args, **kwargs):
            nonlocal saved
            saved += 1
            if saved == 2:
                raise RuntimeError("Synthetic database detail that must stay private")
            return original_save(row, *args, **kwargs)

        with patch.object(FeedbackSection, "save", fail_second):
            with self.assertRaises(PersistenceError) as error:
                self.persist()
        self.assertEqual(str(error.exception), "persistence_failed")
        self.assertEqual(FeedbackSection.objects.count(), 0)
        self.assertEqual(self.persist(), "complete")

    def test_outer_transaction_rollback_removes_all_sink_rows(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.persist()
                raise RuntimeError("Synthetic admission failure after sink")
        self.assertFalse(FeedbackSection.objects.exists())

    def test_closed_scope_and_validation_boundary_rejected(self):
        with self.assertRaises(PersistenceError):
            self.persist(clock=lambda: self.windows[0].closes_at)
        ticks = iter([self.at, self.windows[0].closes_at])
        with self.assertRaises(PersistenceError):
            self.persist(clock=lambda: next(ticks))
        self.assertFalse(FeedbackSection.objects.exists())
        with patch("signal_loop.feedback.services.project_week_scope", side_effect=RuntimeError("Synthetic private detail")):
            with self.assertRaises(PersistenceError) as error:
                self.persist()
        self.assertEqual(str(error.exception), "persistence_failed")

    def test_direct_supported_mutations_cannot_insert_or_rewrite_raw_json(self):
        with self.assertRaises(TypeError):
            FeedbackSection.objects.create(project_id=1, week=date(2026, 9, 7), schema=SCHEMA,
                                           privacy_policy=PRIVACY_POLICY, answers={"user": "synthetic"},
                                           expires_at=self.at)
        self.persist()
        row = FeedbackSection.objects.first()
        with self.assertRaises(TypeError):
            row.save()
        with self.assertRaises(TypeError):
            FeedbackSection.objects.update(answers={"user": "synthetic"})
        with self.assertRaises(TypeError):
            FeedbackSection.objects.bulk_create([])

    def test_contract_matches_admission_transport_and_scope_selector_is_non_identity(self):
        versioned = self.payload()
        admission = [{key: value for key, value in section.items() if key not in {"schema", "privacy_policy"}}
                     for section in deepcopy(versioned)]
        self.assertEqual(normalize_sections(admission), versioned)
        self.assertEqual(normalize_sections(versioned, versioned=True), versioned)
        excessive = [deepcopy(admission[0]) for _ in range(3)]
        for index, section in enumerate(excessive):
            section["project"] = index + 1
            section["answers"] = {"J1": "blocked", "J2": "manageable", "F1": "Synthetic improvement"}
        with self.assertRaises(InvalidFeedback):
            normalize_sections(excessive)
        scope = project_week_scope(project_id=self.projects[0].pk, week=date(2026, 9, 7))
        self.assertEqual(set(scope.__dataclass_fields__), {"project_id", "week", "opens_at", "closes_at"})
        for path in Path("signal_loop/feedback").glob("*.py"):
            tree = ast.parse(path.read_text())
            imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            self.assertFalse(any(module.startswith(("signal_loop.admission", "signal_loop.membership", "django.contrib.auth"))
                                 for module in imports))
