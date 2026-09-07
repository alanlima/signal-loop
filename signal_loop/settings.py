"""Minimal local-development settings; not a production configuration."""

import os
import re
import socket

import psycopg
from django.core.checks import Error, register
from django.core.exceptions import ImproperlyConfigured


def _required(name):
    value = os.environ.get(name, "")
    if not value or not value.strip():
        raise ImproperlyConfigured(
            f"Set {name} in the environment. Copy .env.example to .env, fill it in, "
            "and run uv with --env-file .env."
        )
    return value


def _integer(name, minimum, maximum):
    value = _required(name)
    if (
        len(value) > len(str(maximum))
        or not value.isascii()
        or not value.isdecimal()
        or not minimum <= int(value) <= maximum
    ):
        raise ImproperlyConfigured(f"Set {name} to an integer from {minimum} to {maximum}.")
    return int(value)


def _local_host(name):
    value = _required(name)
    if value not in {"localhost", "127.0.0.1"}:
        raise ImproperlyConfigured(f"Set {name} to localhost or 127.0.0.1 for local services.")
    return value


def _identifier(name):
    value = _required(name)
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value):
        raise ImproperlyConfigured(
            f"Set {name} to a lowercase PostgreSQL identifier (letters, digits, underscores; "
            "start with a letter or underscore; maximum 63 characters)."
        )
    return value


def _database_settings():
    return {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": _local_host("POSTGRES_HOST"),
        "PORT": _integer("POSTGRES_PORT", 1, 65535),
        "NAME": _identifier("POSTGRES_DB"),
        "USER": _identifier("POSTGRES_USER"),
        "PASSWORD": _required("POSTGRES_PASSWORD"),
        "OPTIONS": {"connect_timeout": 3},
    }


def _redis_settings():
    return {
        "HOST": _local_host("REDIS_HOST"),
        "PORT": _integer("REDIS_PORT", 1, 65535),
        "DB": _integer("REDIS_DB", 0, 15),
    }


DATABASES = {"default": _database_settings()}
REDIS = _redis_settings()


@register()
def check_local_postgres(app_configs, **kwargs):
    """Fail management-command preflight without exposing driver diagnostics."""
    database = DATABASES["default"]
    try:
        with psycopg.connect(
            host=database["HOST"], port=database["PORT"], dbname=database["NAME"],
            user=database["USER"], password=database["PASSWORD"], connect_timeout=3,
        ) as connection:
            connection.execute("SELECT 1")
    except psycopg.Error:
        return [Error(
            "Cannot connect to local PostgreSQL.",
            hint="Run docker compose up -d --wait; verify POSTGRES_* in .env. "
                 "Existing volumes retain their original database, user and password.",
            id="signal_loop.E001",
        )]
    return []


@register()
def check_local_redis(app_configs, **kwargs):
    """Use Redis' documented RESP interface; no worker/client dependency yet."""
    try:
        with socket.create_connection((REDIS["HOST"], REDIS["PORT"]), timeout=3) as connection:
            with connection.makefile("rb") as response:
                # SELECT validates the configured logical database as well as connectivity.
                index = str(REDIS["DB"])
                connection.sendall(
                    f"*2\r\n$6\r\nSELECT\r\n${len(index)}\r\n{index}\r\n"
                    "*1\r\n$4\r\nPING\r\n".encode("ascii")
                )
                if response.readline(128) != b"+OK\r\n" or response.readline(128) != b"+PONG\r\n":
                    raise OSError("Unexpected Redis response")
    except OSError:
        return [Error(
            "Cannot connect to local Redis.",
            hint="Run docker compose up -d --wait; verify REDIS_HOST, REDIS_PORT and REDIS_DB "
                 "in .env. The local Redis service does not use authentication.",
            id="signal_loop.E002",
        )]
    return []


SECRET_KEY = "development-only-not-for-production"
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    "signal_loop.accounts",
    "signal_loop.membership",
    "signal_loop.windows",
    "signal_loop.admission",
    "signal_loop.feedback",
    "signal_loop.checkins",
    "signal_loop.invitations",
    "signal_loop.pipeline",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "signal_loop.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
LOGIN_URL = "login"
STATIC_URL = "/static/"
LOGIN_REDIRECT_URL = "application_entry"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# Local HTTP only; the production settings handoff must enable both for HTTPS.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
WSGI_APPLICATION = "signal_loop.wsgi.application"
ASGI_APPLICATION = "signal_loop.asgi.application"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Local reference-only worker; production service isolation belongs to #42.
CELERY_BROKER_URL = f"redis://{REDIS['HOST']}:{REDIS['PORT']}/{REDIS['DB']}"
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_DEFAULT_QUEUE = "signal-loop-local"
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SOFT_TIME_LIMIT = 5
CELERY_TASK_TIME_LIMIT = 8
CELERY_RESULT_EXPIRES = 86400
CELERY_RESULT_EXTENDED = False
CELERY_TASK_REMOTE_TRACEBACKS = False
CELERY_TASK_SEND_SENT_EVENT = False
CELERY_WORKER_SEND_TASK_EVENTS = False
CELERY_WORKER_ENABLE_REMOTE_CONTROL = False
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_REDIRECT_STDOUTS = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = False
CELERY_BROKER_CONNECTION_TIMEOUT = 3
CELERY_BROKER_CONNECTION_MAX_RETRIES = 2
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 120, "socket_connect_timeout": 3, "socket_timeout": 3}
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {"global_keyprefix": "signal-loop-local-", "retry_policy": {"timeout": 3}}
CELERY_REDIS_SOCKET_CONNECT_TIMEOUT = 3
CELERY_REDIS_SOCKET_TIMEOUT = 3
CELERY_TASK_PUBLISH_RETRY = False

# Default local-only delivery; selecting SMTP requires explicit deployment setup.
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "false").lower() == "true"
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "false").lower() == "true"
EMAIL_TIMEOUT = 10
EMAIL_FILE_PATH = os.environ.get("EMAIL_FILE_PATH", ".local-email")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "SignalLoop <noreply@example.com>")
INVITATION_ORIGIN = os.environ.get("INVITATION_ORIGIN", "http://127.0.0.1:8000")
INVITATION_CONTACT_PROVIDER = None  # Mandatory trusted server injection; no email/account fallback.

CELERY_BEAT_SCHEDULE = {
    "local-weekly-dispatch": {"task": "signal_loop.dispatch_due", "schedule": 60.0,
                              "args": ["40000000-0000-4000-8000-000000000001"]},
}
