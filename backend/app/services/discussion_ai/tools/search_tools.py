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

GET_RELATED_PAPERS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_related_papers",
        "description": "Find papers related to a specific paper. Use when user asks 'find similar papers to X', 'what papers cite X', 'what does X cite', 'related work to paper X'. Requires a paper identifier (DOI, OpenAlex ID, or title from recent search results). Can return: (1) similar papers algorithmically related, (2) citing papers that cite this work, (3) references that this paper cites.",
        "parameters": {
            "type": "object",
            "properties": {
                "paper_identifier": {
                    "type": "string",
                    "description": "DOI (e.g., '10.1038/s41586-021-03819-2'), OpenAlex ID (e.g., 'W3177828909'), or paper title from recent search results.",
                },
                "relation_type": {
                    "type": "string",
                    "enum": ["similar", "citing", "references"],
                    "description": "'similar' = algorithmically related papers, 'citing' = papers that cite this work, 'references' = papers this work cites.",
                    "default": "similar",
                },
                "count": {
                    "type": "integer",
                    "description": "Maximum number of related papers to return.",
                    "default": 10,
                },
            },
            "required": ["paper_identifier"],
        },
    },
}

SEMANTIC_SEARCH_LIBRARY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "semantic_search_library",
        "description": "Search the project library using semantic similarity. Unlike keyword search, this finds papers based on meaning and concepts. Use when user asks 'find papers in my library about X', 'which of my papers relate to Y', 'semantically similar papers to this concept'. Only searches papers already in the project library.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query describing the concept or topic to search for (e.g., 'papers about transformer architectures for protein folding').",
                },
                "count": {
                    "type": "integer",
                    "description": "Maximum number of papers to return.",
                    "default": 10,
                },
                "similarity_threshold": {
                    "type": "number",
                    "description": "Minimum similarity score (0.0-1.0). Higher = more relevant but fewer results. Default 0.5 is good balance.",
                    "default": 0.5,
                },
            },
            "required": ["query"],
        },
    },
}


def _handle_search_papers(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_search_papers(ctx, **args)


def _handle_discover_topics(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_discover_topics(**args)


def _handle_batch_search_papers(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_batch_search_papers(ctx=ctx, **args)


def _handle_get_related_papers(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_get_related_papers(ctx, **args)


def _handle_semantic_search_library(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_semantic_search_library(ctx, **args)


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
    ToolSpec(
        name="get_related_papers",
        schema=GET_RELATED_PAPERS_SCHEMA,
        handler=_handle_get_related_papers,
    ),
    ToolSpec(
        name="semantic_search_library",
        schema=SEMANTIC_SEARCH_LIBRARY_SCHEMA,
        handler=_handle_semantic_search_library,
    ),
]


def register(registry: ToolRegistry) -> None:
    for spec in TOOL_SPECS:
        registry.register(spec)
