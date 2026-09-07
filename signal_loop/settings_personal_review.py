"""Explicit local synthetic review only; never a production identity provider."""
import os

from .settings import *  # noqa: F403

CHECKIN_REVIEW_MODE = True
CHECKIN_REVIEW_FAIL = os.environ.get("CHECKIN_REVIEW_FAIL") == "1"
CHECKIN_PRINCIPAL_PROVIDER = "signal_loop.checkins.services.review_provider"
CHECKIN_PROGRESS_SERVICE = "signal_loop.checkins.services.review_progression"
CHECKIN_REVIEW_AI_FAULT = os.environ.get("CHECKIN_REVIEW_AI_FAULT", "valid")
CHECKIN_AI_FACTORY = "signal_loop.checkins.services.review_ai"
