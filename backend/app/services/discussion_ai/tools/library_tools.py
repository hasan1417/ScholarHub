from __future__ import annotations

from typing import Any, Dict, List

from .registry import ToolRegistry, ToolSpec


GET_RECENT_SEARCH_RESULTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_recent_search_results",
        "description": "Get papers from the most recent search. Use this FIRST when user says 'these papers', 'these references', 'the 5 papers', 'use them', or refers to papers that were just searched/found. This contains the papers from the last search action.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}

GET_PROJECT_REFERENCES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_project_references",
        "description": "Get papers/references from the user's project library (permanently saved papers). Use when user mentions 'my library', 'saved papers', 'my collection'. Returns total_count (TOTAL papers in library), returned_count (papers in this response), ingested_pdf_count, has_pdf_available_count, and paper details. For ingested PDFs, includes summary, key_findings, methodology, limitations. For detailed info about a single paper, use get_reference_details instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "topic_filter": {
                    "type": "string",
                    "description": "Optional keyword to filter references by topic",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of references to return. Omit or set high to get all references.",
                },
            },
        },
    },
}

GET_REFERENCE_DETAILS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_reference_details",
        "description": "Get detailed information about a specific reference from the library by ID. Use when user asks about a specific paper's content, what it's about, key findings, methodology, or wants a summary. Returns full analysis data if PDF was ingested (summary, key_findings, methodology, limitations, page_count).",
        "parameters": {
            "type": "object",
            "properties": {
                "reference_id": {
                    "type": "string",
                    "description": "The ID of the reference to get details for",
                },
            },
            "required": ["reference_id"],
        },
    },
}

ANALYZE_REFERENCE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "analyze_reference",
        "description": "Re-analyze a reference to generate/update its summary, key_findings, methodology, and limitations. Use when get_reference_details returns empty analysis fields (null summary/key_findings) for an ingested PDF, or when user asks to 'analyze', 're-analyze', or 'summarize' a specific reference. Requires the reference to have an ingested PDF.",
        "parameters": {
            "type": "object",
            "properties": {
                "reference_id": {
                    "type": "string",
                    "description": "The ID of the reference to analyze",
                },
            },
            "required": ["reference_id"],
        },
    },
}

GET_CHANNEL_RESOURCES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_channel_resources",
        "description": "Get files/documents specifically attached to this discussion channel (uploaded PDFs, etc). NOT for papers added to library via this channel.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}

GET_CHANNEL_PAPERS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_channel_papers",
        "description": "Get papers that were added to the library through this discussion channel (the channel's paper history). Use for questions like 'papers we added in this discussion' or 'what papers did we add earlier in this channel'.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}

EXPORT_CITATIONS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "export_citations",
        "description": "Export citations from the project library in a specific format (BibTeX, APA, MLA, or Chicago). Use when user asks to 'export citations', 'get BibTeX', 'format references', etc. Can export selected references by ID, currently focused papers, or all library papers.",
        "parameters": {
            "type": "object",
            "properties": {
                "reference_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "UUIDs of specific references to export. If empty, uses scope parameter.",
                },
                "format": {
                    "type": "string",
                    "enum": ["bibtex", "apa", "mla", "chicago"],
                    "description": "Citation format to export in.",
                    "default": "bibtex",
                },
                "scope": {
                    "type": "string",
                    "enum": ["selected", "focused", "all"],
                    "description": "Which papers to export: 'selected' (by reference_ids), 'focused' (currently focused papers), 'all' (entire project library).",
                    "default": "all",
                },
            },
        },
    },
}

ANNOTATE_REFERENCE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "annotate_reference",
        "description": "Add a note or tags to a library reference for organization. Use when user asks to 'tag this paper', 'add a note to this reference', 'mark as key paper', etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "reference_id": {
                    "type": "string",
                    "description": "UUID of the library reference to annotate.",
                },
                "note": {
                    "type": "string",
                    "description": "Free-text note to add to the reference.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to add, e.g. ['methodology', 'key-paper'].",
                },
            },
            "required": ["reference_id"],
        },
    },
}

ADD_TO_LIBRARY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "add_to_library",
        "description": "Add papers to the project library AND ingest their PDFs for full-text AI analysis. Works with recent search results OR currently focused papers. IMPORTANT: Use this BEFORE creating a paper so you have full PDF content, not just abstracts. Returns which papers were added and their ingestion status.",
        "parameters": {
            "type": "object",
            "properties": {
                "paper_indices": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Indices of papers to add (0-based). Uses recent search results, or focused papers if no search results. Use [0,1,2,3,4] to add first 5 papers.",
                },
                "ingest_pdfs": {
                    "type": "boolean",
                    "description": "Whether to download and ingest PDFs for AI analysis. Default true.",
                    "default": True,
                },
            },
            "required": ["paper_indices"],
        },
    },
}


def _handle_get_recent_search_results(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_get_recent_search_results(ctx)


def _handle_get_project_references(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_get_project_references(ctx, **args)


def _handle_get_reference_details(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_get_reference_details(ctx, **args)


def _handle_analyze_reference(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_analyze_reference(ctx, **args)


def _handle_get_channel_resources(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_get_channel_resources(ctx)


def _handle_get_channel_papers(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_get_channel_papers(ctx)


def _handle_export_citations(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_export_citations(ctx, **args)


def _handle_annotate_reference(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_annotate_reference(ctx, **args)


def _handle_add_to_library(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_add_to_library(ctx, **args)


TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="get_recent_search_results",
        schema=GET_RECENT_SEARCH_RESULTS_SCHEMA,
        handler=_handle_get_recent_search_results,
    ),
    ToolSpec(
        name="get_project_references",
        schema=GET_PROJECT_REFERENCES_SCHEMA,
        handler=_handle_get_project_references,
    ),
    ToolSpec(
        name="get_reference_details",
        schema=GET_REFERENCE_DETAILS_SCHEMA,
        handler=_handle_get_reference_details,
    ),
    ToolSpec(
        name="analyze_reference",
        schema=ANALYZE_REFERENCE_SCHEMA,
        handler=_handle_analyze_reference,
    ),
    ToolSpec(
        name="get_channel_resources",
        schema=GET_CHANNEL_RESOURCES_SCHEMA,
        handler=_handle_get_channel_resources,
    ),
    ToolSpec(
        name="get_channel_papers",
        schema=GET_CHANNEL_PAPERS_SCHEMA,
        handler=_handle_get_channel_papers,
    ),
    ToolSpec(
        name="export_citations",
        schema=EXPORT_CITATIONS_SCHEMA,
        handler=_handle_export_citations,
    ),
    ToolSpec(
        name="annotate_reference",
        schema=ANNOTATE_REFERENCE_SCHEMA,
        handler=_handle_annotate_reference,
    ),
    ToolSpec(
        name="add_to_library",
        schema=ADD_TO_LIBRARY_SCHEMA,
        handler=_handle_add_to_library,
    ),
]


def register(registry: ToolRegistry) -> None:
    for spec in TOOL_SPECS:
        registry.register(spec)
