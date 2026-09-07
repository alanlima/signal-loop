"""Explicit local preview seam. Never asserts actual admission or storage."""
from signal_loop.contracts.feedback import is_substantive, normalize_sections


def preview_submission(sections):
    normalized = normalize_sections(sections)
    if not any(is_substantive(section) for section in normalized):
        return "no_feedback"
    return "preview_complete"
