"""Content-free local worker probe. Run as python -m signal_loop.pipeline.cli."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import django

from signal_loop.celery import app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("send", "status", "ping"))
    parser.add_argument("--kind", choices=("complete", "retry", "failure", "timeout"), default="complete")
    parser.add_argument("--job")
    args = parser.parse_args()
    django.setup()
    from .tasks import TASKS, valid_job
    try:
        if args.action == "ping":
            with app.connection_for_write() as connection:
                connection.ensure_connection(max_retries=0)
            print(json.dumps({"code": "broker_available"}))
            return 0
        job = args.job or (str(uuid4()) if args.action == "send" else None)
        if not valid_job(job):
            print(json.dumps({"code": "invalid_job"}))
            return 2
        if args.action == "send":
            TASKS[args.kind].apply_async(args=[job], task_id=job, retry=False,
                                        expires=datetime.now(timezone.utc) + timedelta(hours=24),
                                        argsrepr="(<job-reference>)", kwargsrepr="{}")
            print(json.dumps({"job": job, "code": "queued"}))
            return 0
        result = app.AsyncResult(job)
        state = result.state
        data = {"job": job, "code": "pending_or_unknown"}
        if state == "SUCCESS":
            value = result.result
            if isinstance(value, dict) and value.get("code") in {"complete", "permanent_failure", "retry_exhausted", "timeout", "invalid_job"}:
                data["code"] = value["code"]
        elif state == "RETRY":
            data["code"] = "retrying"
        elif state in {"FAILURE", "REVOKED"}:
            data["code"] = "worker_failed"
        print(json.dumps(data))
        return 0
    except Exception:
        print(json.dumps({"code": "broker_unavailable"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
