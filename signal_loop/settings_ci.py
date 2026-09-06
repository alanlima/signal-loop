"""Disposable CI configuration with in-memory email delivery."""

from signal_loop.settings import *  # noqa: F403

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
