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
