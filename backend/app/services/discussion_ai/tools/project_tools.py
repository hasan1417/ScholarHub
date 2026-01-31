from __future__ import annotations

from typing import Any, Dict, List

from .registry import ToolRegistry, ToolSpec


GET_PROJECT_INFO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_project_info",
        "description": "Get information about the current research project (title, description, goals, keywords). Use when user asks about 'the project', 'project goals', or needs project context.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}

UPDATE_PROJECT_INFO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "update_project_info",
        "description": """Update project description, objectives, and/or keywords. IMPORTANT: NEVER ask user about 'replace' vs 'append' modes - these are internal parameters. Instead, infer the mode from user intent:
- User says 'add keyword X' or 'also include Y' -> use append mode
- User says 'set keywords to X,Y,Z' or 'change keywords to...' or project is empty -> use replace mode
- User says 'remove keyword X' -> use remove mode
For new/empty projects, just use replace mode and apply the content directly without asking for confirmation.""",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "New project description (replaces existing). Omit to keep unchanged.",
                },
                "objectives": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of objectives. Each should be concise (max 150 chars).",
                },
                "objectives_mode": {
                    "type": "string",
                    "enum": ["replace", "append", "remove"],
                    "description": "Internal: infer from user intent. 'add' -> append, 'set/change to' -> replace, 'remove' -> remove.",
                    "default": "replace",
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of keywords/tags. Each should be 1-3 words.",
                },
                "keywords_mode": {
                    "type": "string",
                    "enum": ["replace", "append", "remove"],
                    "description": "Internal: infer from user intent. 'add' -> append, 'set/change to' -> replace, 'remove' -> remove.",
                    "default": "replace",
                },
            },
        },
    },
}


def _handle_get_project_info(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_get_project_info(ctx)


def _handle_update_project_info(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_update_project_info(ctx, **args)


TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="get_project_info",
        schema=GET_PROJECT_INFO_SCHEMA,
        handler=_handle_get_project_info,
    ),
    ToolSpec(
        name="update_project_info",
        schema=UPDATE_PROJECT_INFO_SCHEMA,
        handler=_handle_update_project_info,
    ),
]


def register(registry: ToolRegistry) -> None:
    for spec in TOOL_SPECS:
        registry.register(spec)
