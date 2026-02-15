"""Paper discovery package exposing the public service API."""

from .config import DiscoveryConfig
from .models import DiscoveredPaper, PaperSource
from .query import QueryIntent, understand_query

__all__ = [
    "DiscoveryConfig",
    "DiscoveredPaper",
    "PaperSource",
    "QueryIntent",
    "understand_query",
]
