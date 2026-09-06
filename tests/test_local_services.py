import io
from unittest.mock import MagicMock

import psycopg
import pytest
from django.core.exceptions import ImproperlyConfigured

from signal_loop import settings


@pytest.mark.parametrize("name", [
    "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER",
    "POSTGRES_PASSWORD", "REDIS_HOST", "REDIS_PORT", "REDIS_DB",
])
@pytest.mark.parametrize("value", [None, "", "  "])
def test_missing_settings_explain_how_to_load_environment(monkeypatch, name, value):
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)
    factory = settings._database_settings if name.startswith("POSTGRES") else settings._redis_settings
    with pytest.raises(ImproperlyConfigured, match=name) as error:
        factory()
    assert "--env-file .env" in str(error.value)


@pytest.mark.parametrize("name,value", [
    ("POSTGRES_PORT", "0"), ("POSTGRES_PORT", "65536"),
    ("REDIS_PORT", "-1"), ("REDIS_PORT", "abc"), ("REDIS_PORT", "²"),
    ("REDIS_PORT", "9" * 5000),
    ("REDIS_DB", "-1"), ("REDIS_DB", "16"),
    ("POSTGRES_DB", "bad database"), ("POSTGRES_USER", "x" * 64),
    ("POSTGRES_HOST", "postgresql://user:secret@example.com/db"),
    ("REDIS_HOST", "redis://:secret@example.com/0"),
])
def test_invalid_settings_do_not_echo_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    factory = settings._database_settings if name.startswith("POSTGRES") else settings._redis_settings
    with pytest.raises(ImproperlyConfigured, match=name) as error:
        factory()
    assert "secret" not in str(error.value)
    assert "://" not in str(error.value)


def test_connection_settings_come_from_environment(monkeypatch):
    monkeypatch.setenv("POSTGRES_PORT", "55432")
    monkeypatch.setenv("POSTGRES_DB", "another_db")
    monkeypatch.setenv("POSTGRES_PASSWORD", "synthetic:$@password")
    monkeypatch.setenv("REDIS_PORT", "56379")
    monkeypatch.setenv("REDIS_DB", "15")
    database = settings._database_settings()
    assert database["ENGINE"] == "django.db.backends.postgresql"
    assert database["PORT"] == 55432
    assert database["NAME"] == "another_db"
    assert database["PASSWORD"] == "synthetic:$@password"
    assert settings._redis_settings() == {"HOST": "127.0.0.1", "PORT": 56379, "DB": 15}


def test_postgres_probe_queries_database(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(settings.psycopg, "connect", connect)
    assert settings.check_local_postgres(None) == []
    connect.return_value.__enter__.return_value.execute.assert_called_once_with("SELECT 1")
    assert connect.call_args.kwargs["connect_timeout"] == 3


def test_postgres_failure_is_actionable_and_redacted(monkeypatch):
    monkeypatch.setattr(settings.psycopg, "connect", MagicMock(
        side_effect=psycopg.OperationalError("postgresql://user:secret@localhost/db"),
    ))
    errors = settings.check_local_postgres(None)
    assert [error.id for error in errors] == ["signal_loop.E001"]
    assert "docker compose up" in str(errors[0])
    assert "secret" not in str(errors[0])
    assert "://" not in str(errors[0])


@pytest.mark.parametrize("response,successful", [
    (b"+OK\r\n+PONG\r\n", True),
    (b"-ERR invalid DB secret\r\n", False),
    (b"+OK\r\n-WRONGPASS secret\r\n", False),
    (b"", False),
])
def test_redis_probe_requires_select_and_pong(monkeypatch, response, successful):
    connect = MagicMock()
    connection = connect.return_value.__enter__.return_value
    connection.makefile.return_value = io.BytesIO(response)
    monkeypatch.setattr(settings.socket, "create_connection", connect)
    errors = settings.check_local_redis(None)
    if successful:
        assert errors == []
    else:
        assert errors[0].id == "signal_loop.E002"
    assert "secret" not in str(errors)
    connect.assert_called_once_with(("127.0.0.1", 6379), timeout=3)


@pytest.mark.parametrize("failure", [ConnectionRefusedError, TimeoutError])
def test_redis_connection_failure_is_actionable_and_redacted(monkeypatch, failure):
    monkeypatch.setattr(settings.socket, "create_connection", MagicMock(
        side_effect=failure("redis://:secret@localhost/0"),
    ))
    errors = settings.check_local_redis(None)
    assert [error.id for error in errors] == ["signal_loop.E002"]
    assert "docker compose up" in str(errors[0])
    assert "secret" not in str(errors[0])
    assert "://" not in str(errors[0])
