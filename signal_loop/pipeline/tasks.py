"""Harmless reference-only tasks. No feedback, identity, mail or business writes."""
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded
from celery import Task, shared_task

from .diagnostics import event


def valid_job(value):
    try:
        return type(value) is str and str(UUID(value)) == value and UUID(value).version == 4
    except (ValueError, AttributeError):
        return False


class RetryableFailure(Exception):
    def __init__(self):
        super().__init__("retryable_failure")


class SafeTask(Task):
    abstract = True
    max_retries = 2
    soft_time_limit = 5
    time_limit = 8

    def apply_async(self, args=None, kwargs=None, **options):
        if not isinstance(args, (list, tuple)) or len(args) != 1 or kwargs or not valid_job(args[0]):
            raise ValueError("invalid_job")
        if "task_id" in options and not valid_job(options["task_id"]):
            raise ValueError("invalid_job")
        options["argsrepr"] = "(<job-reference>)"
        options["kwargsrepr"] = "{}"
        maximum = datetime.now(timezone.utc) + timedelta(hours=24)
        expiry = options.get("expires", maximum)
        if isinstance(expiry, str):
            try:
                expiry = datetime.fromisoformat(expiry)
            except ValueError:
                raise ValueError("invalid_job") from None
        if not isinstance(expiry, datetime) or expiry.utcoffset() is None or expiry > maximum:
            raise ValueError("invalid_job")
        options["expires"] = expiry
        return super().apply_async(args=args, kwargs={}, **options)

    def __call__(self, *args, **kwargs):
        job = args[0] if len(args) == 1 and not kwargs else None
        if not valid_job(job):
            event("invalid_job", None)
            return {"status": "failed", "code": "invalid_job"}
        try:
            self.run(job)
        except RetryableFailure:
            if self.request.retries >= self.max_retries:
                event("retry_exhausted", job)
                return {"status": "failed", "code": "retry_exhausted"}
            event("retrying", job)
            # Explicit 1s, 2s backoff, at most two retries; no exception payload.
            raise self.retry(countdown=2 ** self.request.retries, max_retries=self.max_retries) from None
        except SoftTimeLimitExceeded:
            event("timeout", job)
            return {"status": "failed", "code": "timeout"}
        except Exception:
            event("permanent_failure", job)
            return {"status": "failed", "code": "permanent_failure"}
        event("complete", job)
        return {"status": "complete", "code": "complete"}


@shared_task(base=SafeTask, name="signal_loop.smoke")
def smoke(job):
    return None


@shared_task(base=SafeTask, bind=True, name="signal_loop.smoke_retry")
def smoke_retry(self, job):
    if self.request.retries == 0:
        raise RetryableFailure()


@shared_task(base=SafeTask, name="signal_loop.smoke_failure")
def smoke_failure(job):
    raise RuntimeError("synthetic-private-sentinel must never appear in diagnostics")


@shared_task(base=SafeTask, name="signal_loop.smoke_timeout")
def smoke_timeout(job):
    time.sleep(30)


TASKS = {"complete": smoke, "retry": smoke_retry, "failure": smoke_failure, "timeout": smoke_timeout}
