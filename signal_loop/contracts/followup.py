"""One reserved #5 catalog slot; allocation remains checkins/#19 ownership."""
from .validation import enum, fields, identifier, monday, require, string


def validate_request(request):
    fields(request, {"schema", "project", "week", "privacy_policy", "question", "data"})
    enum(request["schema"], {"followup-request/1.0"})
    identifier(request["project"])
    monday(request["week"])
    enum(request["privacy_policy"], {"1.0"})
    enum(request["question"], {"F1", "F2"})
    data = request["data"]
    fields(data, {"delivery", "workload"}, {"note"})
    enum(data["delivery"], {"on_track", "at_risk", "blocked", "not_enough_context", "prefer_not_to_say"})
    enum(data["workload"], {"manageable", "stretched", "overloaded", "not_enough_context", "prefer_not_to_say"})
    if "note" in data:
        string(data["note"], 320, 0)
    require((request["question"] == "F1" and data["delivery"] in {"blocked", "at_risk"})
            or (request["question"] == "F2" and data["workload"] in {"overloaded", "stretched"}), "ineligible_question")


def validate_response(response, request):
    fields(response, {"schema", "project", "week", "privacy_policy", "question", "decision"})
    enum(response["schema"], {"followup-response/1.0"})
    for key in ("project", "week", "privacy_policy", "question"):
        require(response[key] == request[key], "cross_scope_reference")
    enum(response["decision"], {"show", "suppress"})
