"""Docker Compose Linux worker: only service hosts differ from local settings."""
from signal_loop.settings import *  # noqa: F403

DATABASES["default"]["HOST"] = "postgres"  # noqa: F405
DATABASES["default"]["PORT"] = 5432  # noqa: F405
REDIS.update(HOST="redis", PORT=6379)  # noqa: F405
CELERY_BROKER_URL = f"redis://redis:6379/{REDIS['DB']}"  # noqa: F405
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
