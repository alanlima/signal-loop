"""Pure intake contract and explicit #6 canonical artifact adapter/validator.

project-feedback/1.0 is internal questionnaire intake; feedback/1.0 is the
canonical restricted persistence artifact. No ORM, identity or admission imports.
"""
from datetime import date, datetime, timedelta, timezone
import re


SCHEMA = "project-feedback/1.0"
PRIVACY_POLICY = "1.0"
ARTIFACT_SCHEMA = "feedback/1.0"
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


class InvalidFeedback(ValueError):
    def __init__(self):
        super().__init__("invalid_submission")


def normalize_sections(sections, *, versioned=False):
    if not isinstance(sections, (list, tuple)) or not 1 <= len(sections) <= 3:
        raise InvalidFeedback()
    expected = {"project", "week", "answers"}
    if versioned:
        expected |= {"schema", "privacy_policy"}
    result = []
    for section in sections:
        if not isinstance(section, dict) or set(section) != expected:
            raise InvalidFeedback()
        if versioned and (section["schema"] != SCHEMA or section["privacy_policy"] != PRIVACY_POLICY):
            raise InvalidFeedback()
        if (type(section["project"]) is not int or not 0 < section["project"] <= 2**63 - 1
                or not isinstance(section["week"], str)):
            raise InvalidFeedback()
        try:
            week = date.fromisoformat(section["week"])
        except ValueError:
            raise InvalidFeedback() from None
        if week.weekday() != 0 or week.isoformat() != section["week"]:
            raise InvalidFeedback()
        answers = section["answers"]
        if (not isinstance(answers, dict) or not answers or not set(answers) <= {"J1", "J2", "J3", "F1", "F2"}
                or any(not isinstance(value, str) for value in answers.values())):
            raise InvalidFeedback()
        answers = {key: value.replace("\r\n", "\n").replace("\r", "\n") for key, value in answers.items()}
        if (answers.get("J1") not in {"on_track", "at_risk", "blocked", "not_enough_context", "prefer_not_to_say"}
                or answers.get("J2") not in {"manageable", "stretched", "overloaded", "not_enough_context", "prefer_not_to_say"}
                or len(answers.get("J3", "")) > 320 or any(len(answers.get(key, "")) > 240 for key in ("F1", "F2"))
                or {"F1", "F2"} <= answers.keys()
                or ("F1" in answers and answers["J1"] not in {"at_risk", "blocked"})
                or ("F2" in answers and answers["J2"] not in {"stretched", "overloaded"})):
            raise InvalidFeedback()
        result.append({"project": section["project"], "week": section["week"],
                       "schema": SCHEMA, "privacy_policy": PRIVACY_POLICY, "answers": answers})
    if len({s["project"] for s in result}) != len(result):
        raise InvalidFeedback()
    if sum("F1" in s["answers"] or "F2" in s["answers"] for s in result) > 2:
        raise InvalidFeedback()
    return result


def is_substantive(section):
    answers = section["answers"]
    return (answers["J1"] not in {"not_enough_context", "prefer_not_to_say"}
            or answers["J2"] not in {"not_enough_context", "prefer_not_to_say"}
            or any(answers.get(key, "").strip() for key in ("J3", "F1", "F2")))


def validate_artifact(artifact):
    """Validate the exact #6 feedback/1.0 restricted envelope and data contract."""
    if not isinstance(artifact, dict) or set(artifact) != {
        "schema", "project", "week", "privacy_policy", "expires_at", "provenance", "data"
    }:
        raise InvalidFeedback()
    if artifact["schema"] != ARTIFACT_SCHEMA or artifact["privacy_policy"] != PRIVACY_POLICY:
        raise InvalidFeedback()
    if not isinstance(artifact["project"], str) or not _ID.fullmatch(artifact["project"]):
        raise InvalidFeedback()
    expiry = artifact["expires_at"]
    if not isinstance(expiry, str) or "T" not in expiry:
        raise InvalidFeedback()
    try:
        parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
    except ValueError:
        raise InvalidFeedback() from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise InvalidFeedback()
    provenance = artifact["provenance"]
    if not isinstance(provenance, dict) or set(provenance) != {"producer", "producer_version", "input_refs"}:
        raise InvalidFeedback()
    if (not isinstance(provenance["producer"], str) or not _ID.fullmatch(provenance["producer"])
            or not isinstance(provenance["producer_version"], str) or not 1 <= len(provenance["producer_version"]) <= 32
            or not isinstance(provenance["input_refs"], list) or len(provenance["input_refs"]) > 100
            or any(not isinstance(ref, str) or not _ID.fullmatch(ref) for ref in provenance["input_refs"])
            or len(set(provenance["input_refs"])) != len(provenance["input_refs"])):
        raise InvalidFeedback()
    data = artifact["data"]
    if (not isinstance(data, dict) or not {"source", "delivery", "workload"} <= data.keys()
            or not data.keys() <= {"source", "delivery", "workload", "note", "follow_up"}
            or not isinstance(data["source"], str) or not _ID.fullmatch(data["source"])):
        raise InvalidFeedback()
    answers = {"J1": data["delivery"], "J2": data["workload"]}
    if "note" in data:
        answers["J3"] = data["note"]
    if "follow_up" in data:
        follow_up = data["follow_up"]
        if (not isinstance(follow_up, dict) or set(follow_up) != {"question", "answer"}
                or follow_up["question"] not in ("F1", "F2")):
            raise InvalidFeedback()
        answers[follow_up["question"]] = follow_up["answer"]
    normalized = normalize_sections([{"project": 1, "week": artifact["week"], "answers": answers}])[0]
    if normalized["answers"] != answers or not is_substantive(normalized):
        raise InvalidFeedback()


def intake_to_artifact(section, *, source, expires_at):
    """Trusted persistence adapter; caller generates source, never admission/client."""
    section = normalize_sections([section], versioned=True)[0]
    answers = section["answers"]
    data = {"source": source, "delivery": answers["J1"], "workload": answers["J2"]}
    if "J3" in answers:
        data["note"] = answers["J3"]
    for question in ("F1", "F2"):
        if question in answers:
            data["follow_up"] = {"question": question, "answer": answers[question]}
    artifact = {"schema": ARTIFACT_SCHEMA, "project": str(section["project"]), "week": section["week"],
                "privacy_policy": PRIVACY_POLICY,
                "expires_at": expires_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "provenance": {"producer": "feedback-store", "producer_version": "1.0", "input_refs": []},
                "data": data}
    validate_artifact(artifact)
    return artifact
