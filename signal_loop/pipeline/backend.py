"""Result keys expire at the original task deadline, never completion + 24h."""
from contextvars import ContextVar
from datetime import datetime, timezone

from celery.backends.redis import RedisBackend


_deadline = ContextVar("result_deadline", default=None)


class ExpiringRedisBackend(RedisBackend):
    def _store_result(self, task_id, result, state, traceback=None, request=None, **kwargs):
        expiry = getattr(request, "expires", None)
        try:
            if isinstance(expiry, str):
                expiry = datetime.fromisoformat(expiry)
            if not isinstance(expiry, datetime) or expiry.utcoffset() is None:
                return result
            if expiry <= datetime.now(timezone.utc):
                return result
            token = _deadline.set(expiry)
            try:
                if state in {"FAILURE", "REVOKED"}:
                    result = {"exc_type": "RuntimeError", "exc_message": ["worker_failed"], "exc_module": "builtins"}
                return super()._store_result(task_id, result, state, traceback=None, request=request, **kwargs)
            finally:
                _deadline.reset(token)
        except (ValueError, TypeError):
            return result

    def _set(self, key, value):
        expiry = _deadline.get()
        if expiry is None or expiry <= datetime.now(timezone.utc):
            return
        with self.client.pipeline() as pipe:
            pipe.set(key, value, pxat=int(expiry.timestamp() * 1000))
            pipe.publish(key, value)
            pipe.execute()
