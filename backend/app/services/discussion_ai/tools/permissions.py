"""Tool permission definitions for role-based access control.

This module defines which roles can access which tools. Permissions are
enforced at two levels:
1. Tool filtering: Tools are filtered before being sent to the LLM
2. Execution check: Registry verifies permission before executing

Fail-closed: Unknown tools or missing roles default to deny.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Set

if TYPE_CHECKING:
    from app.models import ProjectRole

logger = logging.getLogger(__name__)

# Role hierarchy (higher includes lower)
# owner/admin > editor > viewer
ROLE_HIERARCHY = {
    "owner": 3,
    "admin": 3,  # owner and admin are equivalent
    "editor": 2,
    "viewer": 1,
}

# Minimum role required for each tool
# "viewer" = all roles, "editor" = editor+, "admin" = admin/owner only
TOOL_MIN_ROLE: Dict[str, str] = {
    # === Read-only tools (all members) ===
    "get_recent_search_results": "viewer",
    "get_project_references": "viewer",
    "get_reference_details": "viewer",
    "search_papers": "viewer",
    "get_related_papers": "viewer",
    "semantic_search_library": "viewer",  # Semantic search within project library
    "discover_topics": "viewer",
    "batch_search_papers": "viewer",
    "trigger_search_ui": "viewer",
    "focus_on_papers": "viewer",
    "analyze_across_papers": "viewer",
    "compare_papers": "viewer",
    "suggest_research_gaps": "viewer",
    "get_project_papers": "viewer",
    "get_project_info": "viewer",
    "get_created_artifacts": "viewer",
    "get_channel_resources": "viewer",
    "get_channel_papers": "viewer",
    "export_citations": "viewer",

    # === Write tools (editor+) ===
    "add_to_library": "editor",
    "create_paper": "editor",
    "update_paper": "editor",
    "generate_section_from_discussion": "editor",
    "create_artifact": "editor",
    "analyze_reference": "editor",
    "annotate_reference": "editor",
    "generate_abstract": "editor",

    # === Admin tools (admin/owner only) ===
    "update_project_info": "admin",
}

# Tools that require explicit owner check (not just admin)
OWNER_ONLY_TOOLS: Set[str] = set()
# Add tools here that should be owner-only, not admin
# Currently none - update_project_info allows admin too


def normalize_role(role) -> str:
    """Normalize role to string format.

    Handles both string roles and ProjectRole enum.
    Returns lowercase string: 'viewer', 'editor', 'admin', or 'owner'.
    """
    if role is None:
        return "viewer"  # Fail-closed default

    role_str = str(role).lower()

    # Handle enum values like "ProjectRole.EDITOR"
    if "." in role_str:
        role_str = role_str.split(".")[-1]

    # Normalize variations
    if role_str in ("owner", "admin"):
        return "admin"  # Treat owner as admin for permission purposes
    elif role_str == "editor":
        return "editor"
    else:
        return "viewer"


def get_role_level(role: str) -> int:
    """Get numeric level for role comparison."""
    return ROLE_HIERARCHY.get(role.lower(), 0)


def can_use_tool(tool_name: str, user_role: str, is_owner: bool = False) -> bool:
    """Check if a user with the given role can use a tool.

    Args:
        tool_name: Name of the tool to check
        user_role: Normalized role string ('viewer', 'editor', 'admin')
        is_owner: Whether user is the project owner

    Returns:
        True if allowed, False otherwise (fail-closed)
    """
    # Owner-only tools require explicit owner flag
    if tool_name in OWNER_ONLY_TOOLS:
        return is_owner

    # Get minimum required role for tool
    min_role = TOOL_MIN_ROLE.get(tool_name)

    if min_role is None:
        # Unknown tool - fail closed, log warning
        logger.warning(f"Unknown tool '{tool_name}' - denying access (fail-closed)")
        return False

    # Compare role levels
    user_level = get_role_level(user_role)
    required_level = get_role_level(min_role)

    return user_level >= required_level


def filter_tools_for_role(
    tool_schemas: List[Dict],
    user_role: str,
    is_owner: bool = False,
) -> List[Dict]:
    """Filter tool schemas to only those the user can access.

    This should be called before sending tools to the LLM so the model
    only sees tools it's allowed to use.

    Args:
        tool_schemas: List of tool schema dictionaries
        user_role: Normalized role string
        is_owner: Whether user is the project owner

    Returns:
        Filtered list of tool schemas
    """
    filtered = []

    for schema in tool_schemas:
        # Extract tool name from schema
        tool_name = schema.get("function", {}).get("name")
        if not tool_name:
            continue

        if can_use_tool(tool_name, user_role, is_owner):
            filtered.append(schema)
        else:
            logger.debug(f"Filtered out tool '{tool_name}' for role '{user_role}'")

    return filtered


def get_permission_error(tool_name: str, user_role: str) -> str:
    """Generate a user-friendly permission error message.

    Returns a message that the AI can relay to the user.
    """
    min_role = TOOL_MIN_ROLE.get(tool_name, "admin")

    if tool_name in OWNER_ONLY_TOOLS:
        return f"Permission denied: '{tool_name}' can only be used by the project owner."

    role_names = {
        "viewer": "viewers",
        "editor": "editors or above",
        "admin": "project admins or owners",
    }

    required = role_names.get(min_role, "authorized users")

    return f"Permission denied: '{tool_name}' requires {required}. Your role is '{user_role}'."
