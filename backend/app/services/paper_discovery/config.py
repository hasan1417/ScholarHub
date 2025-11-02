"""Configuration objects used by the paper discovery subsystem."""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class DiscoveryConfig:
    """Centralized configuration for discovery behaviour and limits."""

    max_concurrent_searches: int = 3
    max_concurrent_enrichments: int = 5
    max_concurrent_pdf_checks: int = 3
    search_timeout: float = 60.0
    pdf_check_timeout: float = 5.0
    total_timeout: float = 30.0
    cache_max_size: int = 1000
    cache_ttl_seconds: float = 3600.0
    simple_scoring: bool = True

    source_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "openalex": 3.0,
            "semantic_scholar": 3.0,
            "sciencedirect": 3.0,
            "arxiv": 2.0,
            "pubmed": 2.0,
            "crossref": 1.0,
        }
    )

    ranking_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "title_overlap": 0.5,
            "abstract_overlap": 0.3,
            "keyword_title": 0.1,
            "keyword_body": 0.05,
            "recency_max": 0.10,
            "citations_max": 0.08,
            "pdf_bonus": 0.01,
            "oa_bonus": 0.02,
        }
    )

    ncbi_email: Optional[str] = None
    sciencedirect_api_key: Optional[str] = None
