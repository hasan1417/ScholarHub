"""
Tests for new tool registration: verify all 5 new tools are properly
registered in the tool registry, permissions, and schema list.
"""

from app.services.discussion_ai.tools import build_tool_registry, ORDERED_TOOL_NAMES
from app.services.discussion_ai.tools.permissions import (
    TOOL_MIN_ROLE,
    can_use_tool,
    filter_tools_for_role,
)


NEW_TOOLS = [
    "export_citations",
    "compare_papers",
    "suggest_research_gaps",
    "generate_abstract",
    "annotate_reference",
]


class TestNewToolRegistration:
    """Verify new tools are in ORDERED_TOOL_NAMES."""

    def test_all_new_tools_in_ordered_names(self):
        for tool in NEW_TOOLS:
            assert tool in ORDERED_TOOL_NAMES, f"{tool} missing from ORDERED_TOOL_NAMES"

    def test_all_new_tools_in_registry(self):
        registry = build_tool_registry()
        schema_list = registry.get_schema_list()
        tool_names = [s["function"]["name"] for s in schema_list]
        for tool in NEW_TOOLS:
            assert tool in tool_names, f"{tool} missing from registry schema list"


class TestNewToolPermissions:
    """Verify new tools have correct permissions."""

    def test_all_new_tools_have_permissions(self):
        for tool in NEW_TOOLS:
            assert tool in TOOL_MIN_ROLE, f"{tool} missing from TOOL_MIN_ROLE"

    def test_viewer_tools(self):
        viewer_tools = ["export_citations", "compare_papers", "suggest_research_gaps"]
        for tool in viewer_tools:
            assert TOOL_MIN_ROLE[tool] == "viewer"
            assert can_use_tool(tool, "viewer") is True
            assert can_use_tool(tool, "editor") is True
            assert can_use_tool(tool, "admin") is True

    def test_editor_tools(self):
        editor_tools = ["generate_abstract", "annotate_reference"]
        for tool in editor_tools:
            assert TOOL_MIN_ROLE[tool] == "editor"
            assert can_use_tool(tool, "viewer") is False
            assert can_use_tool(tool, "editor") is True
            assert can_use_tool(tool, "admin") is True

    def test_filter_tools_viewer_excludes_editor_tools(self):
        registry = build_tool_registry()
        all_schemas = registry.get_schema_list()

        viewer_schemas = filter_tools_for_role(all_schemas, "viewer")
        viewer_names = {s["function"]["name"] for s in viewer_schemas}

        # Viewer should see read-only tools
        assert "export_citations" in viewer_names
        assert "compare_papers" in viewer_names
        assert "suggest_research_gaps" in viewer_names

        # Viewer should NOT see editor tools
        assert "generate_abstract" not in viewer_names
        assert "annotate_reference" not in viewer_names

    def test_filter_tools_editor_sees_all_new_tools(self):
        registry = build_tool_registry()
        all_schemas = registry.get_schema_list()

        editor_schemas = filter_tools_for_role(all_schemas, "editor")
        editor_names = {s["function"]["name"] for s in editor_schemas}

        for tool in NEW_TOOLS:
            assert tool in editor_names, f"Editor should see {tool}"
