"""Abstract base classes defining the discovery contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .models import DiscoveredPaper


class PaperSearcher(ABC):
    """Interface implemented by source-specific searchers."""

    @abstractmethod
    def get_source_name(self) -> str:  # pragma: no cover - interface only
        """Return the canonical name for this source."""

    @abstractmethod
    async def search(self, query: str, max_results: int) -> List[DiscoveredPaper]:
        """Execute the search and return a list of discovered papers."""


class PaperEnricher(ABC):
    """Interface for metadata enrichers (Crossref, Unpaywall, ...)."""

    @abstractmethod
    async def enrich(self, papers: List[DiscoveredPaper]) -> None:
        """Mutate the supplied list adding extra metadata as needed."""


class PaperRanker(ABC):
    """Interface for ranking strategies."""

    @abstractmethod
    async def rank(self, papers: List[DiscoveredPaper], query: str, **kwargs) -> List[DiscoveredPaper]:
        """Return papers sorted by relevance."""
