from __future__ import annotations

from typing import Dict, List

from .registry import ToolRegistry, ToolSpec
from . import library_tools, search_tools, project_tools, paper_tools, artifact_tools, analysis_tools


ORDERED_TOOL_NAMES: List[str] = [
    "get_recent_search_results",
    "get_project_references",
    "get_reference_details",
    "analyze_reference",
    "search_papers",
    "get_project_papers",
    "get_project_info",
    "update_project_info",
    "get_channel_resources",
    "create_paper",
    "update_paper",
    "create_artifact",
    "get_created_artifacts",
    "discover_topics",
    "batch_search_papers",
    "export_citations",
    "annotate_reference",
    "add_to_library",
    "trigger_search_ui",
    "focus_on_papers",
    "analyze_across_papers",
    "compare_papers",
    "suggest_research_gaps",
    "generate_section_from_discussion",
    "generate_abstract",
]


def _collect_specs() -> Dict[str, ToolSpec]:
    specs: Dict[str, ToolSpec] = {}
    modules = [
        library_tools,
        search_tools,
        project_tools,
        paper_tools,
        artifact_tools,
        analysis_tools,
    ]
    for module in modules:
        for spec in module.TOOL_SPECS:
            if spec.name in specs:
                raise ValueError(f"Duplicate tool spec: {spec.name}")
            specs[spec.name] = spec
    return specs


def build_tool_registry() -> ToolRegistry:
    specs = _collect_specs()
    registry = ToolRegistry()

    for name in ORDERED_TOOL_NAMES:
        spec = specs.pop(name, None)
        if spec:
            registry.register(spec)

    return registry


def get_discussion_tools() -> List[dict]:
    return build_tool_registry().get_schema_list()
