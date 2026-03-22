from __future__ import annotations

from typing import Any, Dict, List

from .registry import ToolRegistry, ToolSpec


GET_PROJECT_INFO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_project_info",
        "description": "Get information about the current research project (title, description, objectives, keywords). Use when user asks about 'the project', 'project goals', or needs project context. Returns: title, description, objectives, keywords, status.",
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
        "description": """Update project description, objectives, and/or keywords.
The project has exactly three editable fields: "Description", "Objectives", and "Keywords".
RULES:
1. When the user asks to update, set, or change project info, call this tool DIRECTLY — do NOT preview or ask for confirmation first. Just do it, then summarize what you changed.
2. Only include parameters the user explicitly asked to change. Omit fields not mentioned.
3. Infer mode from intent: 'add keyword X' -> append, 'set keywords to X,Y,Z' -> replace, 'remove keyword X' -> remove.
4. Do NOT stream explanatory text before calling this tool. Call the tool first, then describe what was updated.""",
        "parameters": {
            "type": "object",
            "properties": {
                "preview": {
                    "type": "boolean",
                    "description": "If true, return what would change without saving. Use for large updates so the user can review first.",
                    "default": False,
                },
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
