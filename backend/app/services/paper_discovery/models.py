"""Domain models used by paper discovery."""

from __future__ import annotations

import hashlib
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
        """Return a key used to deduplicate entries across sources."""

        if self.doi:
            return f"doi:{self.doi.lower()}"

        title_normalized = self.title.lower().strip()
        digest = hashlib.md5(title_normalized.encode()).hexdigest()
        return f"title:{digest}"
