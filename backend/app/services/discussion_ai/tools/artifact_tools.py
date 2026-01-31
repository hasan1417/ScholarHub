from __future__ import annotations

from typing import Any, Dict, List

from .registry import ToolRegistry, ToolSpec


CREATE_ARTIFACT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_artifact",
        "description": "Create a downloadable artifact (document, summary, review) that doesn't get saved to the project. Use when user wants content they can download without cluttering their project papers. Good for literature reviews, summaries, exports.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title/filename for the artifact",
                },
                "content": {
                    "type": "string",
                    "description": "Content of the artifact (markdown or LaTeX format)",
                },
                "format": {
                    "type": "string",
                    "description": "Format of the artifact: 'markdown', 'latex', 'text', or 'pdf'. Use 'pdf' when user asks for PDF.",
                    "enum": ["markdown", "latex", "text", "pdf"],
                    "default": "markdown",
                },
                "artifact_type": {
                    "type": "string",
                    "description": "Type of artifact: 'literature_review', 'summary', 'notes', 'export', 'report'",
                    "default": "document",
                },
            },
            "required": ["title", "content"],
        },
    },
}

GET_CREATED_ARTIFACTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_created_artifacts",
        "description": "Get artifacts (PDFs, documents) that were created in this discussion channel. Use when user asks about 'the PDF I created', 'the file you generated', 'my artifacts', or refers to previously created downloadable content.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of artifacts to return",
                    "default": 10,
                },
            },
        },
    },
}


def _handle_create_artifact(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_create_artifact(ctx, **args)


def _handle_get_created_artifacts(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_get_created_artifacts(ctx, **args)


TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="create_artifact",
        schema=CREATE_ARTIFACT_SCHEMA,
        handler=_handle_create_artifact,
    ),
    ToolSpec(
        name="get_created_artifacts",
        schema=GET_CREATED_ARTIFACTS_SCHEMA,
        handler=_handle_get_created_artifacts,
    ),
]


def register(registry: ToolRegistry) -> None:
    for spec in TOOL_SPECS:
        registry.register(spec)
