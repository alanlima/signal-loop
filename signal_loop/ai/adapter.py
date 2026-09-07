"""Bounded synchronous provider calls in disposable, joined worker processes."""
from dataclasses import dataclass, field
from enum import StrEnum
import json
import math
import multiprocessing
import os
import time
from typing import Protocol

from signal_loop.contracts.analysis import validate_artifact
from signal_loop.contracts.followup import validate_request, validate_response
from signal_loop.contracts.validation import InvalidContract, fields, require
from signal_loop.contracts.versions import ANALYSIS_SCHEMAS


class Failure(StrEnum):
    INVALID_REQUEST = "invalid_request"
    INVALID_OUTPUT = "invalid_output"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    REJECTED = "rejected"
    RETRIES_EXHAUSTED = "retries_exhausted"
    INTERNAL = "internal_failure"


class ProviderUnavailable(Exception):
    """Transient failure; exception text is never propagated."""


class ProviderRejected(Exception):
    """Permanent failure; exception text is never propagated."""


class Provider(Protocol):
    def invoke(self, operation: str, model: str, request: dict, attempt: int) -> str:
        """Return JSON text. Must be spawn-picklable, and must not spawn children."""


@dataclass(frozen=True)
class Limits:
    timeout: float = 5.0
    total_timeout: float = 10.0
    max_attempts: int = 2

    def __post_init__(self):
        if (type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 5
                or any(type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 60
                       for value in (self.timeout, self.total_timeout))):
            raise ValueError("invalid_configuration")


@dataclass(frozen=True)
class Configuration:
    followup_model: str = "synthetic-followup-v1"
    analysis_model: str = "synthetic-analysis-v1"
    followup: Limits = field(default_factory=lambda: Limits(2.0, 2.0, 1))
    analysis: Limits = field(default_factory=Limits)

    def __post_init__(self):
        if (not isinstance(self.followup, Limits) or not isinstance(self.analysis, Limits)
                or self.followup.max_attempts != 1 or self.followup.total_timeout > 2
                or any(type(value) is not str or not 1 <= len(value) <= 128
                       or any(ord(char) < 32 for char in value)
                       for value in (self.followup_model, self.analysis_model))):
            raise ValueError("invalid_configuration")


@dataclass(frozen=True)
class Result:
    candidate: dict | None = field(default=None, repr=False)
    failure: Failure | None = None
    attempts: int = 0


def _worker(connection, provider, operation, model, request, attempt):
    # Silence provider diagnostics and traceback bodies, including direct fd writes.
    with open(os.devnull, "w") as null:
        os.dup2(null.fileno(), 1)
        os.dup2(null.fileno(), 2)
        try:
            output = provider.invoke(operation, model, request, attempt)
            message = {"output": output} if type(output) is str and len(output.encode("utf-8")) <= 1_000_000 else {"error": "invalid_output"}
        except TimeoutError:
            message = {"error": "timeout"}
        except ProviderUnavailable:
            message = {"error": "unavailable"}
        except ProviderRejected:
            message = {"error": "rejected"}
        except BaseException:
            message = {"error": "internal_failure"}
        try:
            connection.send_bytes(json.dumps(message).encode("utf-8"))
        finally:
            connection.close()


def _invoke(provider, operation, model, request, attempt, deadline):
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(writer, provider, operation, model, request, attempt), daemon=True)
    try:
        process.start()
        writer.close()
        while not reader.poll(max(0, deadline - time.monotonic())):
            if time.monotonic() >= deadline:
                return {"error": "timeout"}
        message = json.loads(reader.recv_bytes(maxlength=1_100_000))
        return message if time.monotonic() < deadline else {"error": "timeout"}
    except Exception:
        return {"error": "internal_failure"}
    finally:
        writer.close()
        reader.close()
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=0.1)
            if process.is_alive():
                process.kill()
                process.join(timeout=0.1)
            process.close()


def _json(text):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise InvalidContract()
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(InvalidContract()))


class Adapter:
    def __init__(self, provider: Provider, configuration: Configuration | None = None):
        self._provider = provider
        self.configuration = configuration or Configuration()

    def follow_up(self, request) -> Result:
        try:
            validate_request(request)
        except Exception:
            return Result(failure=Failure.INVALID_REQUEST)
        return self._run("followup", request, self.configuration.followup_model, self.configuration.followup,
                         lambda response: validate_response(response, request))

    def structured_analysis(self, request, *, scope) -> Result:
        try:
            fields(request, {"schema", "output_schema", "inputs"})
            require(request["schema"] == "analysis-request/1.0")
            require(type(request["output_schema"]) is str and request["output_schema"] in ANALYSIS_SCHEMAS)
            require(type(request["inputs"]) is list and 1 <= len(request["inputs"]) <= 100)
            seen = set()
            for artifact in request["inputs"]:
                validate_artifact(artifact, scope)
                data = artifact["data"]
                identifiers = [data["source"]] if "source" in data else [row["id"] for row in data.get("items", [])]
                for identifier in identifiers:
                    require(identifier not in seen, "duplicate_reference")
                    seen.add(identifier)
            require(len({json.dumps(value, sort_keys=True) for value in request["inputs"]}) == len(request["inputs"]), "duplicate_reference")
        except Exception:
            return Result(failure=Failure.INVALID_REQUEST)

        def output(response):
            validate_artifact(response, scope)
            require(response["schema"] == request["output_schema"])
            from signal_loop.contracts.validation import utc_time
            require(utc_time(response["expires_at"]) <= min(utc_time(item["expires_at"]) for item in request["inputs"]), "expired_source")

        return self._run("analysis", request, self.configuration.analysis_model, self.configuration.analysis, output)

    def _run(self, operation, request, model, limits, validate):
        # JSON copying rejects objects before spawn; no provider can mutate caller state.
        try:
            encoded = json.dumps(request, allow_nan=False)
            require(len(encoded.encode("utf-8")) <= 1_000_000)
            request = _json(encoded)
        except Exception:
            return Result(failure=Failure.INVALID_REQUEST)
        deadline = time.monotonic() + limits.total_timeout
        for attempt in range(1, limits.max_attempts + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return Result(failure=Failure.TIMEOUT, attempts=attempt - 1)
            message = _invoke(self._provider, operation, model, request, attempt,
                              min(deadline, time.monotonic() + limits.timeout))
            if "output" in message:
                try:
                    candidate = _json(message["output"])
                    validate(candidate)
                except Exception:
                    return Result(failure=Failure.INVALID_OUTPUT, attempts=attempt)
                if time.monotonic() >= deadline:
                    return Result(failure=Failure.TIMEOUT, attempts=attempt)
                return Result(candidate=candidate, attempts=attempt)
            failure = Failure(message["error"])
            if failure not in {Failure.TIMEOUT, Failure.UNAVAILABLE}:
                return Result(failure=failure, attempts=attempt)
            if time.monotonic() >= deadline:
                return Result(failure=Failure.TIMEOUT, attempts=attempt)
            if attempt == limits.max_attempts:
                return Result(failure=Failure.RETRIES_EXHAUSTED if attempt > 1 else failure, attempts=attempt)
