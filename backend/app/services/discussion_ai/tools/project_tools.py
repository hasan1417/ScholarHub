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
The project has exactly three editable fields: "Description", "Objectives", and "Keywords". Always refer to them by these names.
IMPORTANT RULES:
1. When the user asks to fill, write, or set project info, FIRST propose your suggested content in your response text and ask the user to confirm or adjust BEFORE calling this tool. Do NOT call this tool until the user approves.
2. If the user provides EXACT content to set (e.g. 'set description to X'), you may call this tool directly.
3. For small edits like 'add keyword X' or 'remove objective 2', you may call this tool directly.
4. Only include parameters the user explicitly asked to change. Omit fields not mentioned.
5. NEVER ask user about 'replace' vs 'append' modes - infer from intent:
   - 'add keyword X' or 'also include Y' -> append mode
   - 'set keywords to X,Y,Z' or 'change to...' -> replace mode
   - 'remove keyword X' -> remove mode
6. Use preview=true to show what would change without committing (recommended for large changes).""",
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
