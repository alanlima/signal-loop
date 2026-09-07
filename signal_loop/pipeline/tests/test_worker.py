import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from celery import Task
from celery.backends.redis import RedisBackend
from celery.exceptions import Retry
import pytest

from signal_loop.celery import app
from signal_loop.pipeline.diagnostics import SafeFormatter
from signal_loop.pipeline.backend import ExpiringRedisBackend, _deadline
from signal_loop.pipeline.tasks import RetryableFailure, smoke, smoke_failure, smoke_retry


def test_reference_only_publication_and_content_free_repr():
    job = str(uuid4())
    with patch.object(Task, "apply_async") as send:
        smoke.apply_async(args=[job], task_id=job)
    assert send.call_args.kwargs["args"] == [job]
    assert send.call_args.kwargs["kwargs"] == {}
    assert send.call_args.kwargs["argsrepr"] == "(<job-reference>)"
    assert send.call_args.kwargs["expires"].utcoffset().total_seconds() == 0
    for args, kwargs in [(["private text"], {}), ([job, "private text"], {}), ([job], {"user": 1})]:
        with patch.object(Task, "apply_async") as send, pytest.raises(ValueError, match="^invalid_job$"):
            smoke.apply_async(args=args, kwargs=kwargs)
        send.assert_not_called()


def test_safe_results_and_bounded_retry_classes():
    job = str(uuid4())
    assert smoke(job) == {"status": "complete", "code": "complete"}
    assert smoke_failure(job) == {"status": "failed", "code": "permanent_failure"}
    assert smoke("private text") == {"status": "failed", "code": "invalid_job"}
    smoke_retry.push_request(retries=0)
    try:
        with patch.object(smoke_retry, "retry", side_effect=Retry()) as retry, pytest.raises(Retry):
            smoke_retry(job)
        assert retry.call_args.kwargs == {"countdown": 1, "max_retries": 2}
    finally:
        smoke_retry.pop_request()
    smoke_retry.push_request(retries=2)
    try:
        with patch.object(smoke_retry, "run", side_effect=RetryableFailure()), patch.object(smoke_retry, "retry") as retry:
            assert smoke_retry(job) == {"status": "failed", "code": "retry_exhausted"}
        retry.assert_not_called()
    finally:
        smoke_retry.pop_request()


def test_unexpected_worker_received_error_and_traceback_messages_are_redacted():
    formatter = SafeFormatter()
    record = logging.LogRecord("celery.worker", logging.ERROR, "", 0,
                               "private text %s", ("credential-sentinel",),
                               (RuntimeError, RuntimeError("private traceback"), None))
    assert json.loads(formatter.format(record)) == {"code": "worker_event"}
    record.name = "signal_loop.pipeline.safe"
    record.safe_code = "permanent_failure"
    record.safe_job = str(uuid4())
    assert json.loads(formatter.format(record)) == {"code": "permanent_failure", "job": record.safe_job}


def test_json_only_bounded_worker_configuration():
    assert app.conf.accept_content == ["json"]
    assert app.conf.task_soft_time_limit == 5
    assert app.conf.task_time_limit == 8
    assert app.conf.result_expires == 86400
    assert not app.conf.result_extended
    assert not app.conf.worker_send_task_events
    assert not app.conf.task_send_sent_event
    assert not app.conf.worker_enable_remote_control
    assert app.conf.worker_prefetch_multiplier == 1
    assert app.conf.broker_transport_options["visibility_timeout"] > app.conf.task_time_limit


def test_result_deadline_is_absolute_and_diagnostics_sanitized():
    backend = ExpiringRedisBackend(app=app, url=app.conf.result_backend)
    expiry = datetime.now(timezone.utc) + timedelta(seconds=20)
    observed = []

    def capture(*args, **kwargs):
        observed.append((_deadline.get(), args, kwargs))

    with patch.object(RedisBackend, "_store_result", side_effect=capture):
        backend._store_result(str(uuid4()), {"private": "sentinel"}, "FAILURE",
                              traceback="private traceback", request=SimpleNamespace(expires=expiry.isoformat()))
    assert observed[0][0] == expiry
    assert observed[0][1][1] == {"exc_type": "RuntimeError", "exc_message": ["worker_failed"], "exc_module": "builtins"}
    assert observed[0][2]["traceback"] is None
    assert _deadline.get() is None
    for deadline in (None, "bad", (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()):
        with patch.object(RedisBackend, "_store_result") as write:
            backend._store_result(str(uuid4()), {}, "SUCCESS", request=SimpleNamespace(expires=deadline))
        write.assert_not_called()


def test_publication_cannot_exceed_task_lifetime():
    with pytest.raises(ValueError, match="^invalid_job$"), patch.object(Task, "apply_async") as send:
        smoke.apply_async(args=[str(uuid4())], expires=datetime.now(timezone.utc) + timedelta(days=2))
    send.assert_not_called()
