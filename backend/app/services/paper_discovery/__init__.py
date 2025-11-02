"""Paper discovery package exposing the public service API."""

from .config import DiscoveryConfig
from .models import DiscoveredPaper, PaperSource
from .query import QueryEnhancer

__all__ = [
    "DiscoveryConfig",
    "DiscoveredPaper",
    "PaperSource",
    "QueryEnhancer",
]
