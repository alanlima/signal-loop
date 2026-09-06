import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client, TestCase


pytestmark = pytest.mark.usefixtures("postgres_database")


class SessionAuthenticationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="synthetic_member", password="synthetic-test-password",
        )
        get_user_model().objects.create_user(
            username="inactive_member", password="synthetic-test-password", is_active=False,
        )

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def sign_in(self, **overrides):
        self.client.get("/accounts/login/")
        data = {
            "username": "synthetic_member", "password": "synthetic-test-password",
            "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
        }
        data.update(overrides)
        return self.client.post("/accounts/login/", data)

    def test_protected_entry_redirects_without_content(self):
        response = self.client.get("/app/?tab=weekly")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/login/?next=/app/%3Ftab%3Dweekly")
        self.assertNotContains(response, "You are signed in.", status_code=302)

    def test_success_preserves_safe_local_next_and_cookie_flags(self):
        response = self.sign_in(next="/app/?tab=weekly")
        self.assertEqual(response.url, "/app/?tab=weekly")
        self.assertContains(self.client.get(response.url), "You are signed in.")
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")

    def test_failure_is_generic_for_wrong_unknown_and_inactive_accounts(self):
        errors = []
        for username in ("synthetic_member", "unknown_member", "inactive_member"):
            response = self.sign_in(username=username, password="wrong-password")
            self.assertEqual(response.status_code, 200)
            errors.append(list(response.context["form"].non_field_errors()))
            self.assertNotIn("_auth_user_id", self.client.session)
        response = self.sign_in(username="inactive_member")
        errors.append(list(response.context["form"].non_field_errors()))
        self.assertTrue(errors[0])
        self.assertTrue(all(error == errors[0] for error in errors))

    def test_unsafe_or_malformed_next_falls_back_to_entry(self):
        for target in (
            "https://example.com/", "//example.com/", "///example.com/",
            "javascript:alert(1)", "http://[", "/\\example.com/", "/app/\nLocation:evil",
            "relative/path", "https://testserver/app/",
        ):
            with self.subTest(target=target):
                response = self.sign_in(next=target)
                self.assertEqual(response.url, "/app/")

    def test_login_requires_valid_csrf(self):
        for token in ("", "invalid-token"):
            response = self.client.post("/accounts/login/", {
                "username": "synthetic_member", "password": "synthetic-test-password",
                "csrfmiddlewaretoken": token,
            })
            self.assertEqual(response.status_code, 403)
            self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post_and_csrf_then_invalidates_old_session(self):
        self.sign_in()
        old_key = self.client.session.session_key
        self.assertEqual(self.client.get("/accounts/logout/").status_code, 405)
        self.assertEqual(self.client.post("/accounts/logout/").status_code, 403)
        self.assertContains(self.client.get("/app/"), "You are signed in.")
        response = self.client.post("/accounts/logout/", {
            "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            "next": "/app/",
        })
        self.assertEqual(response.url, "/accounts/login/")
        self.assertFalse(Session.objects.filter(session_key=old_key).exists())
        replay = Client()
        replay.cookies[settings.SESSION_COOKIE_NAME] = old_key
        self.assertEqual(replay.get("/app/").status_code, 302)
        self.assertEqual(self.client.get("/app/").status_code, 302)

    def test_no_public_registration_route(self):
        self.assertEqual(self.client.get("/accounts/register/").status_code, 404)
