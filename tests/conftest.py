import os

import django
from django.test.utils import setup_test_environment, teardown_test_environment


def pytest_configure():
    # Synthetic settings only: unit tests do not need running data services.
    os.environ.update({
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "test_signal_loop",
        "POSTGRES_USER": "test_signal_loop",
        "POSTGRES_PASSWORD": "synthetic-test-password",
        "REDIS_HOST": "127.0.0.1",
        "REDIS_PORT": "6379",
        "REDIS_DB": "0",
    })
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "signal_loop.settings")
    django.setup()
    setup_test_environment()


def pytest_unconfigure():
    teardown_test_environment()
