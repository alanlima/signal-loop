"""Exact audience-release/1.0 serialization; structural validation is not approval."""
from signal_loop.contracts.validation import array, enum, fields, string


def validate_content(content, audience):
    common = {"title", "overview", "themes", "trends"}
    extra = {"issues", "evidence", "recommendations"} if audience == "manager" else {"next_week_focus", "commitments"}
    enum(audience, {"manager", "team"})
    fields(content, common | extra)
    string(content["title"], 120)
    string(content["overview"], 800)
    for key in ("themes", "trends"):
        array(content[key], 50)
        for text in content[key]:
            string(text, 500)
    if audience == "team":
        for key in extra:
            array(content[key], 10)
            for text in content[key]:
                string(text, 500)
        return
    array(content["issues"], 50)
    for row in content["issues"]:
        fields(row, {"severity", "explanation"})
        enum(row["severity"], {"low", "moderate", "high", "critical"})
        string(row["explanation"], 800)
    array(content["evidence"], 100)
    for row in content["evidence"]:
        fields(row, {"form", "text"}, {"label"})
        enum(row["form"], {"paraphrase", "synthesis"})
        string(row["text"], 800)
        from signal_loop.contracts.validation import require
        require((row["form"] == "paraphrase" and "label" not in row)
                or (row["form"] == "synthesis" and row.get("label") == "Synthesized example from shared feedback"))
    array(content["recommendations"], 50)
    for row in content["recommendations"]:
        fields(row, {"action", "rationale"})
        string(row["action"], 500)
        string(row["rationale"], 800)


def unavailable(project, week, audience="manager", *, before_close=False):
    return {"schema": "audience-release/1.0", "project": project, "week": week, "audience": audience,
            "status": "not_yet_available" if before_close else "unavailable"}
