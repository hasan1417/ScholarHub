"""Shared utilities for parsing project/paper URL identifiers."""

from uuid import UUID


def is_valid_uuid(val: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        UUID(str(val))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def parse_short_id(url_id: str) -> str | None:
    """Extract short_id from a URL identifier (slug-shortid or just shortid)."""
    if not url_id or is_valid_uuid(url_id):
        return None
    if len(url_id) == 8 and url_id.isalnum():
        return url_id
    last_hyphen = url_id.rfind("-")
    if last_hyphen > 0:
        potential = url_id[last_hyphen + 1 :]
        if len(potential) == 8 and potential.isalnum():
            return potential
    return None
