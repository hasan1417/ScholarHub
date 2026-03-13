"""Shared DOI normalization helpers."""

from __future__ import annotations


def normalize_doi(doi: str | None) -> str | None:
    """Normalize a DOI for comparisons and downstream lookups."""
    if not doi:
        return None

    normalized = doi.strip().lower()
    prefixes = (
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "https://doi.org/",
        "http://doi.org/",
        "doi.org/",
        "doi:",
    )

    changed = True
    while changed and normalized:
        changed = False
        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):].strip()
                changed = True
                break

    return normalized or None
