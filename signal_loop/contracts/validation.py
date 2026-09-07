"""Strict, ORM-free primitives for the version 1.0 transport contracts."""
from datetime import date, datetime, timedelta
import re


class InvalidContract(ValueError):
    def __init__(self, code="invalid_contract"):
        self.code = code
        super().__init__(code)


def require(condition, code="invalid_type"):
    if not condition:
        raise InvalidContract(code)


def fields(value, required, optional=()):
    require(type(value) is dict)
    require(not set(value) - set(required) - set(optional), "unknown_field")
    require(set(required) <= set(value), "missing_field")


def string(value, maximum, minimum=1):
    require(type(value) is str and minimum <= len(value) <= maximum and "\r" not in value)


def identifier(value):
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is not None)


def integer(value, minimum=0, maximum=10000):
    require(type(value) is int and minimum <= value <= maximum)


def boolean(value):
    require(type(value) is bool)


def enum(value, choices):
    require(type(value) is str and value in choices, "invalid_enum")


def monday(value):
    require(type(value) is str)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise InvalidContract("invalid_date") from None
    require(parsed.isoformat() == value and parsed.weekday() == 0, "invalid_date")
    return parsed


def utc_time(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value) is not None)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InvalidContract("invalid_date") from None
    require(parsed.utcoffset() == timedelta(0), "invalid_date")
    return parsed


def array(value, maximum, minimum=0):
    require(type(value) is list and minimum <= len(value) <= maximum)


def references(value, maximum=10000, minimum=0):
    array(value, maximum, minimum)
    for item in value:
        identifier(item)
    require(len(set(value)) == len(value), "duplicate_reference")


def items(value, maximum):
    array(value, maximum)
    ids = []
    for item in value:
        require(type(item) is dict)
        require("id" in item, "missing_field")
        identifier(item["id"])
        ids.append(item["id"])
    require(len(ids) == len(set(ids)), "duplicate_reference")
