"""Pure anonymous transport contract. No ORM, identity or admission imports."""
from datetime import date


SCHEMA = "project-feedback/1.0"
PRIVACY_POLICY = "1.0"


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
