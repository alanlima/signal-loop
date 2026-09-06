import os

import django
from django.test.utils import setup_test_environment, teardown_test_environment


def pytest_configure():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "signal_loop.settings")
    django.setup()
    setup_test_environment()


def pytest_unconfigure():
    teardown_test_environment()
