"""Explicit synthetic fixture provider; no network, credentials, or real feedback."""
from dataclasses import dataclass, field
import json
import time

from .adapter import ProviderRejected, ProviderUnavailable


@dataclass(frozen=True)
class FakeProvider:
    response: dict | None = field(default=None, repr=False)
    script: tuple[str, ...] = ("valid",)
    delay: float = 0
    raw_response: str | None = field(default=None, repr=False)

    def invoke(self, operation, model, request, attempt):
        mode = self.script[min(attempt - 1, len(self.script) - 1)]
        if self.delay:
            time.sleep(self.delay)
        if mode == "timeout":
            raise TimeoutError("synthetic-private-provider-detail")
        if mode == "unavailable":
            raise ProviderUnavailable("synthetic-private-provider-detail")
        if mode == "rejected":
            raise ProviderRejected("synthetic-private-provider-detail")
        if mode == "malformed":
            return "synthetic malformed provider text"
        if mode == "error":
            print("synthetic-private-provider-detail")
            raise RuntimeError("synthetic-private-provider-detail")
        if self.raw_response is not None:
            return self.raw_response
        if self.response is not None:
            return json.dumps(self.response)
        if operation == "followup":
            return json.dumps({"schema": "followup-response/1.0", **{key: request[key] for key in (
                "project", "week", "privacy_policy", "question")}, "decision": "suppress" if mode == "suppress" else "show"})
        # Analysis requires the explicit complete #6 fixture requested by the test.
        raise ProviderRejected()
