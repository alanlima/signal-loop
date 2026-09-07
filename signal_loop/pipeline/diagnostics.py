"""Allowlisted worker diagnostics: never format transport messages/tracebacks."""
import json
import logging
import re

from celery.signals import setup_logging


CODES = {"complete", "retrying", "permanent_failure", "retry_exhausted", "timeout", "invalid_job", "worker_event"}


class SafeFormatter(logging.Formatter):
    def format(self, record):
        data = {"code": "worker_event"}
        if record.name == "signal_loop.pipeline.safe":
            code = getattr(record, "safe_code", None)
            job = getattr(record, "safe_job", None)
            if code in CODES:
                data["code"] = code
            if isinstance(job, str) and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", job):
                data["job"] = job
        return json.dumps(data)


@setup_logging.connect
def configure_worker_logging(**kwargs):
    handler = logging.StreamHandler()
    handler.setFormatter(SafeFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for logger in logging.root.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            logger.handlers = []
            logger.propagate = True


def event(code, job):
    logging.getLogger("signal_loop.pipeline.safe").info("", extra={"safe_code": code, "safe_job": job})
