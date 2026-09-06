import os

import django
import pytest
from django.test.utils import (
    setup_databases, setup_test_environment, teardown_databases, teardown_test_environment,
)


def pytest_addoption(parser):
    parser.addoption("--postgres", action="store_true", help="Run database tests against disposable PostgreSQL.")


def pytest_configure(config):
    # Service-free mode uses synthetic values; full mode keeps explicit local/CI settings.
    synthetic = {
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "test_signal_loop",
        "POSTGRES_USER": "test_signal_loop",
        "POSTGRES_PASSWORD": "synthetic-test-password",
        "REDIS_HOST": "127.0.0.1",
        "REDIS_PORT": "6379",
        "REDIS_DB": "0",
    }
    if not config.getoption("--postgres"):
        os.environ.update(synthetic)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "signal_loop.settings")
    django.setup()
    setup_test_environment()


def pytest_unconfigure():
    teardown_test_environment()


@pytest.fixture(scope="session")
def postgres_database(request):
    if not request.config.getoption("--postgres"):
        pytest.skip("Use --postgres with the documented disposable PostgreSQL environment.")
    old_config = setup_databases(verbosity=0, interactive=False)
    yield
    teardown_databases(old_config, verbosity=0)
