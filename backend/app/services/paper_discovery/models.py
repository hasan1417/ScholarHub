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
    GOOGLE_SCHOLAR = "google_scholar"
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
    # Strip URL prefixes possibly layered multiple times (seen in OpenAlex responses)
    changed = True
    while changed:
        changed = False
        for prefix in ['https://doi.org/', 'http://doi.org/', 'doi:', 'doi.org/']:
            if doi.startswith(prefix):
                doi = doi[len(prefix):].strip()
                changed = True
    return doi if doi else None


def _is_arxiv_doi(doi: Optional[str]) -> bool:
    """True for arXiv-assigned DOIs (preprint identifiers), not publisher DOIs."""
    if not doi:
        return False
    nd = _normalize_doi(doi) or ""
    return nd.startswith("10.48550/arxiv")


def _normalize_title(title: str) -> str:
    """Normalize title for fuzzy matching - removes punctuation, normalizes whitespace."""
    if not title:
        return ""
    # Convert to lowercase and normalize unicode (é -> e, etc.)
    title = title.lower().strip()
    title = unicodedata.normalize('NFKD', title)
    title = ''.join(c for c in title if not unicodedata.combining(c))
    # Drop trailing arXiv version markers (" v1", " v2", "-v2") before other cleanup
    title = re.sub(r'[\s\-_]+v\d+\s*$', '', title)
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
    # Populated by ArxivSearcher; lets us merge preprint vs published records
    # even when the preprint doesn't carry the published DOI yet.
    arxiv_id: Optional[str] = None
    # Populated by the dedup step; records every source that returned this work.
    merged_sources: List[str] = field(default_factory=list)

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

    def match_keys(self) -> List[str]:
        """All keys under which this paper can collide with a duplicate.

        A paper is considered the same as another if they share ANY match key.
        Order isn't meaningful; uniqueness across keys is.
        """
        keys: List[str] = []
        nd = _normalize_doi(self.doi)
        if nd:
            keys.append(f"doi:{nd}")
        if self.arxiv_id:
            keys.append(f"arxiv:{self.arxiv_id.lower()}")
        nt = _normalize_title(self.title)
        if nt and self.year:
            # Title + year is stronger than title alone: distinct papers sometimes
            # share a title but almost never a title+year.
            digest = hashlib.md5(f"{nt}|{self.year}".encode()).hexdigest()
            keys.append(f"ty:{digest}")
        elif nt:
            # No year — fall back to pure title hash (less precise but necessary
            # for sources that don't return a year).
            digest = hashlib.md5(nt.encode()).hexdigest()
            keys.append(f"t:{digest}")
        return keys or [f"title:{hashlib.md5(self.title.encode()).hexdigest()}"]
