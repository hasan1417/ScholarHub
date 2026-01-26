"""Domain models used by paper discovery."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PaperSource(Enum):
    """Enumeration of supported discovery sources."""

    ARXIV = "arxiv"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    CROSSREF = "crossref"
    PUBMED = "pubmed"
    OPENALEX = "openalex"
    SCIENCEDIRECT = "sciencedirect"
    CORE = "core"
    EUROPE_PMC = "europe_pmc"


def _normalize_doi(doi: Optional[str]) -> Optional[str]:
    """Normalize DOI to a consistent lowercase format without URL prefix."""
    if not doi:
        return None
    doi = doi.strip().lower()
    # Remove common URL prefixes
    for prefix in ['https://doi.org/', 'http://doi.org/', 'doi:', 'doi.org/']:
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    doi = doi.strip()
    return doi if doi else None


def _normalize_title(title: str) -> str:
    """Normalize title for fuzzy matching - removes punctuation, normalizes whitespace."""
    if not title:
        return ""
    # Convert to lowercase and normalize unicode (é -> e, etc.)
    title = title.lower().strip()
    title = unicodedata.normalize('NFKD', title)
    title = ''.join(c for c in title if not unicodedata.combining(c))
    # Remove punctuation and special characters, keep only alphanumeric and spaces
    title = re.sub(r'[^\w\s]', '', title)
    # Normalize whitespace to single spaces
    title = re.sub(r'\s+', ' ', title).strip()
    return title


@dataclass
class DiscoveredPaper:
    """Representation of a paper returned by any discovery source."""

    title: str
    authors: List[str]
    abstract: str
    year: Optional[int]
    doi: Optional[str]
    url: Optional[str]
    source: str
    relevance_score: float = 0.0
    citations_count: Optional[int] = None
    journal: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    is_open_access: bool = False
    open_access_url: Optional[str] = None
    pdf_url: Optional[str] = None

    def get_unique_key(self) -> str:
        """Return a key used to deduplicate entries across sources.

        Uses normalized DOI as primary key, falls back to normalized title hash.
        """
        # Try DOI first (normalized)
        normalized_doi = _normalize_doi(self.doi)
        if normalized_doi:
            return f"doi:{normalized_doi}"

        # Fall back to normalized title hash
        normalized_title = _normalize_title(self.title)
        if normalized_title:
            digest = hashlib.md5(normalized_title.encode()).hexdigest()
            return f"title:{digest}"

        # Last resort: use original title
        digest = hashlib.md5(self.title.encode()).hexdigest()
        return f"title:{digest}"
