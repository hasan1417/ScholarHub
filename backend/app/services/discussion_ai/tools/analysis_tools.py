from __future__ import annotations

from typing import Any, Dict, List

from .registry import ToolRegistry, ToolSpec


TRIGGER_SEARCH_UI_SCHEMA = {
    "type": "function",
    "function": {
        "name": "trigger_search_ui",
        "description": "Trigger the frontend search interface for a research question. This does NOT perform the actual search - it sends an action to the frontend to display a search UI where the user can execute and review the search. Use when the user wants to explore papers but needs to review results before proceeding.",
        "parameters": {
            "type": "object",
            "properties": {
                "research_question": {
                    "type": "string",
                    "description": "The research question to search for (e.g., 'What are the main approaches to attention in transformers?')",
                },
                "max_papers": {
                    "type": "integer",
                    "description": "Maximum number of papers to suggest searching for",
                    "default": 10,
                },
            },
            "required": ["research_question"],
        },
    },
}

FOCUS_ON_PAPERS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "focus_on_papers",
        "description": "Load specific papers into focus for detailed discussion. For SEARCH RESULTS use paper_indices (0-based). For LIBRARY papers, you MUST first call get_project_references to get real UUIDs, then pass those UUIDs to reference_ids. NEVER invent or guess IDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "paper_indices": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Indices from recent search results (0-based). 'paper 1' = index 0, 'paper 2' = index 1, etc.",
                },
                "reference_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "REAL UUID reference IDs from get_project_references. NEVER make up IDs like 'ref1' or 'paper1' - always get real UUIDs first!",
                },
            },
        },
    },
}

ANALYZE_ACROSS_PAPERS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "analyze_across_papers",
        "description": "Analyze a topic across all focused papers, finding patterns, agreements, and disagreements. Use when user asks to compare papers, find commonalities, or synthesize findings across multiple papers. Requires papers to be focused first.",
        "parameters": {
            "type": "object",
            "properties": {
                "analysis_question": {
                    "type": "string",
                    "description": "The analysis question (e.g., 'How do their methodologies compare?', 'What are the common findings?', 'Where do they disagree?')",
                },
            },
            "required": ["analysis_question"],
        },
    },
}


def _handle_trigger_search_ui(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_trigger_search_ui(ctx, **args)


def _handle_focus_on_papers(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_focus_on_papers(ctx, **args)


def _handle_analyze_across_papers(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_analyze_across_papers(ctx, **args)


TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="trigger_search_ui",
        schema=TRIGGER_SEARCH_UI_SCHEMA,
        handler=_handle_trigger_search_ui,
    ),
    ToolSpec(
        name="focus_on_papers",
        schema=FOCUS_ON_PAPERS_SCHEMA,
        handler=_handle_focus_on_papers,
    ),
    ToolSpec(
        name="analyze_across_papers",
        schema=ANALYZE_ACROSS_PAPERS_SCHEMA,
        handler=_handle_analyze_across_papers,
    ),
]


def register(registry: ToolRegistry) -> None:
    for spec in TOOL_SPECS:
        registry.register(spec)
