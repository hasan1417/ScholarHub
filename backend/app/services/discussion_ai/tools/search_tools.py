from __future__ import annotations

from typing import Any, Dict, List

from .registry import ToolRegistry, ToolSpec


SEARCH_PAPERS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_papers",
        "description": "Search for academic papers online. Returns papers matching the query. Papers with PDF available are marked with 'OA' (Open Access) and can be ingested for AI analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'machine learning transformers'). For recent papers, add year terms like '2023 2024'.",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of papers to find",
                    "default": 5,
                },
                "open_access_only": {
                    "type": "boolean",
                    "description": "If true, only return papers with PDF available (Open Access). Use when user asks for 'only open access', 'only OA', 'papers with PDF', 'papers I can ingest', etc.",
                    "default": False,
                },
            },
            "required": ["query"],
        },
    },
}

DISCOVER_TOPICS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "discover_topics",
        "description": "Search the web to discover what specific topics/algorithms/methods exist for a broad area. Use when user asks about 'recent X', 'latest trends', 'new algorithms in Y', or vague topics where you don't know what specific things to search for. Returns a list of specific topics you can then search papers for.",
        "parameters": {
            "type": "object",
            "properties": {
                "area": {
                    "type": "string",
                    "description": "The broad area to discover topics in (e.g., 'AI algorithms 2025', 'computer vision advances 2025', 'NLP breakthroughs')",
                },
            },
            "required": ["area"],
        },
    },
}

BATCH_SEARCH_PAPERS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "batch_search_papers",
        "description": "Search for papers on MULTIPLE specific topics at once. Use after discover_topics to search for papers on each discovered topic. Returns papers grouped by topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "topics": {
                    "type": "array",
                    "description": "List of topics to search for",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string", "description": "Display name for the topic"},
                            "query": {"type": "string", "description": "Academic search query for this topic"},
                            "max_results": {"type": "integer", "description": "Max papers per topic", "default": 5},
                        },
                        "required": ["topic", "query"],
                    },
                },
            },
            "required": ["topics"],
        },
    },
}


def _handle_search_papers(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_search_papers(ctx, **args)


def _handle_discover_topics(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_discover_topics(**args)


def _handle_batch_search_papers(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_batch_search_papers(**args)


TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="search_papers",
        schema=SEARCH_PAPERS_SCHEMA,
        handler=_handle_search_papers,
    ),
    ToolSpec(
        name="discover_topics",
        schema=DISCOVER_TOPICS_SCHEMA,
        handler=_handle_discover_topics,
    ),
    ToolSpec(
        name="batch_search_papers",
        schema=BATCH_SEARCH_PAPERS_SCHEMA,
        handler=_handle_batch_search_papers,
    ),
]


def register(registry: ToolRegistry) -> None:
    for spec in TOOL_SPECS:
        registry.register(spec)
