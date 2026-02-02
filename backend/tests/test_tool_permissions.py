"""Tests for tool permission system."""

import pytest
from app.services.discussion_ai.tools.permissions import (
    can_use_tool,
    filter_tools_for_role,
    get_permission_error,
    normalize_role,
    TOOL_MIN_ROLE,
)
from app.services.discussion_ai.tools import build_tool_registry


class TestRoleNormalization:
    """Tests for role normalization."""

    def test_normalize_viewer(self):
        assert normalize_role("viewer") == "viewer"
        assert normalize_role("VIEWER") == "viewer"

    def test_normalize_editor(self):
        assert normalize_role("editor") == "editor"
        assert normalize_role("EDITOR") == "editor"

    def test_normalize_admin(self):
        assert normalize_role("admin") == "admin"
        assert normalize_role("ADMIN") == "admin"

    def test_normalize_owner_to_admin(self):
        # Owner is treated as admin for permissions
        assert normalize_role("owner") == "admin"
        assert normalize_role("OWNER") == "admin"

    def test_normalize_none_to_viewer(self):
        # Fail-closed: None becomes viewer
        assert normalize_role(None) == "viewer"

    def test_normalize_enum_string(self):
        # Handle enum-like strings
        assert normalize_role("ProjectRole.EDITOR") == "editor"
        assert normalize_role("ProjectRole.VIEWER") == "viewer"
        assert normalize_role("ProjectRole.ADMIN") == "admin"


class TestCanUseTool:
    """Tests for permission checking."""

    # Read-only tools (viewer can use)
    @pytest.mark.parametrize("tool", [
        "get_recent_search_results",
        "get_project_references",
        "search_papers",
        "discover_topics",
    ])
    def test_viewer_can_use_read_tools(self, tool):
        assert can_use_tool(tool, "viewer") is True

    # Write tools (viewer cannot use)
    @pytest.mark.parametrize("tool", [
        "add_to_library",
        "create_paper",
        "update_paper",
        "analyze_reference",
    ])
    def test_viewer_cannot_use_write_tools(self, tool):
        assert can_use_tool(tool, "viewer") is False

    # Editor can use write tools
    @pytest.mark.parametrize("tool", [
        "add_to_library",
        "create_paper",
        "update_paper",
        "analyze_reference",
    ])
    def test_editor_can_use_write_tools(self, tool):
        assert can_use_tool(tool, "editor") is True


    # Admin/owner tools
    def test_viewer_cannot_use_admin_tools(self):
        assert can_use_tool("update_project_info", "viewer") is False

    def test_editor_cannot_use_admin_tools(self):
        assert can_use_tool("update_project_info", "editor") is False

    def test_admin_can_use_admin_tools(self):
        assert can_use_tool("update_project_info", "admin") is True

    # Unknown tool - fail closed
    def test_unknown_tool_denied(self):
        assert can_use_tool("unknown_tool", "admin") is False

    # All roles verified in mapping
    def test_all_tools_have_permissions(self):
        """Ensure all tools in TOOL_MIN_ROLE are valid."""
        for tool, min_role in TOOL_MIN_ROLE.items():
            assert min_role in ("viewer", "editor", "admin"), f"Invalid role for {tool}"

    def test_registry_tools_have_permissions(self):
        """Ensure every registered tool is mapped in TOOL_MIN_ROLE."""
        registry = build_tool_registry()
        schemas = registry.get_schema_list()
        tool_names = {
            s.get("function", {}).get("name")
            for s in schemas
            if s.get("function", {}).get("name")
        }
        missing = tool_names - set(TOOL_MIN_ROLE.keys())
        assert not missing, f"Missing permissions for tools: {sorted(missing)}"


class TestFilterToolsForRole:
    """Tests for tool schema filtering."""

    def test_filter_removes_write_tools_for_viewer(self):
        schemas = [
            {"function": {"name": "search_papers"}},
            {"function": {"name": "add_to_library"}},
            {"function": {"name": "create_paper"}},
        ]

        filtered = filter_tools_for_role(schemas, "viewer")

        names = [s["function"]["name"] for s in filtered]
        assert "search_papers" in names
        assert "add_to_library" not in names
        assert "create_paper" not in names

    def test_filter_keeps_all_for_admin(self):
        schemas = [
            {"function": {"name": "search_papers"}},
            {"function": {"name": "add_to_library"}},
            {"function": {"name": "update_project_info"}},
        ]

        filtered = filter_tools_for_role(schemas, "admin")

        assert len(filtered) == 3

    def test_filter_handles_empty_list(self):
        filtered = filter_tools_for_role([], "viewer")
        assert filtered == []

    def test_filter_skips_malformed_schemas(self):
        schemas = [
            {"function": {"name": "search_papers"}},
            {"function": {}},  # No name
            {"other": "field"},  # No function
        ]

        filtered = filter_tools_for_role(schemas, "viewer")

        assert len(filtered) == 1
        assert filtered[0]["function"]["name"] == "search_papers"


class TestPermissionErrors:
    """Tests for error message generation."""

    def test_error_message_for_viewer(self):
        error = get_permission_error("add_to_library", "viewer")
        assert "add_to_library" in error
        assert "viewer" in error
        assert "editors" in error

    def test_error_message_for_editor(self):
        error = get_permission_error("update_project_info", "editor")
        assert "update_project_info" in error
        assert "editor" in error
        assert "admin" in error


class TestIntegration:
    """Integration tests with realistic scenarios."""

    def test_viewer_workflow(self):
        """Viewer can search but not modify."""
        role = "viewer"
        # Can search
        assert can_use_tool("search_papers", role) is True
        assert can_use_tool("get_project_references", role) is True
        # Cannot add
        assert can_use_tool("add_to_library", role) is False
        # Cannot create
        assert can_use_tool("create_paper", role) is False

    def test_editor_workflow(self):
        """Editor can search and modify, but not admin ops."""
        role = "editor"
        # Can search
        assert can_use_tool("search_papers", role) is True
        # Can add
        assert can_use_tool("add_to_library", role) is True
        # Can create
        assert can_use_tool("create_paper", role) is True
        # Cannot admin
        assert can_use_tool("update_project_info", role) is False

    def test_admin_workflow(self):
        """Admin can do everything."""
        role = "admin"
        assert can_use_tool("search_papers", role) is True
        assert can_use_tool("add_to_library", role) is True
        assert can_use_tool("create_paper", role) is True
        assert can_use_tool("update_project_info", role) is True
