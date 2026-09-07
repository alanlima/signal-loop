"""Bounded live local smoke; requires the documented Linux worker and Redis."""
import json
import time
from uuid import uuid4

import django

from signal_loop.celery import app


def main():
    django.setup()
    from .tasks import TASKS
    expected = {"complete": "complete", "retry": "complete", "failure": "permanent_failure", "timeout": "timeout"}
    jobs = {}
    started = time.monotonic()
    try:
        for kind in expected:
            job = str(uuid4())
            TASKS[kind].apply_async(args=[job], task_id=job, retry=False)
            jobs[kind] = job
        pending = set(jobs)
        while pending and time.monotonic() - started < 35:
            for kind in tuple(pending):
                result = app.AsyncResult(jobs[kind])
                if result.ready():
                    if result.state != "SUCCESS" or result.result != {
                        "status": "complete" if expected[kind] == "complete" else "failed", "code": expected[kind]
                    }:
                        print(json.dumps({"code": "verification_failed", "job": jobs[kind]}))
                        return 1
                    pending.remove(kind)
            if pending:
                time.sleep(0.2)
        if pending:
            print(json.dumps({"code": "verification_timeout"}))
            return 1
        print(json.dumps({"code": "verified", "jobs": jobs, "elapsed_seconds": round(time.monotonic() - started, 2)}))
        return 0
    except Exception:
        print(json.dumps({"code": "verification_unavailable"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
