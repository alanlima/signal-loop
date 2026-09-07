import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "signal_loop.settings")

app = Celery("signal_loop")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.loader.override_backends = {"redis": "signal_loop.pipeline.backend.ExpiringRedisBackend"}
app.autodiscover_tasks(["signal_loop.pipeline"])

# Install content-free logging before the worker configures its handlers.
from signal_loop.pipeline import diagnostics  # noqa: E402,F401
