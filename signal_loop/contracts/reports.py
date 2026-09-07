"""Restricted composition shapes; never an audience release or renderer input."""
from .validation import array, boolean, fields, references, string


def validate_report_data(kind, data):
    if kind == "manager-report":
        fields(data, {"title", "overview", "themes", "issues", "evidence", "recommendations", "trends"})
        for key in ("themes", "issues", "evidence", "recommendations", "trends"):
            references(data[key], 100 if key == "evidence" else 50)
    else:
        fields(data, {"title", "overview", "themes", "next_week_focus", "commitments"}, {"trends"})
        references(data["themes"], 50)
        if "trends" in data:
            references(data["trends"], 50)
        array(data["next_week_focus"], 10)
        for text in data["next_week_focus"]:
            string(text, 500)
        array(data["commitments"], 10)
        for commitment in data["commitments"]:
            fields(commitment, {"text", "approved"})
            string(commitment["text"], 500)
            boolean(commitment["approved"])
    string(data["title"], 120)
    string(data["overview"], 800)
