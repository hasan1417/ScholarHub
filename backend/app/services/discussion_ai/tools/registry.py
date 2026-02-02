from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from .permissions import can_use_tool, filter_tools_for_role, get_permission_error

logger = logging.getLogger(__name__)

ToolHandler = Callable[[Any, Dict[str, Any], Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    schema: Dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}
        self._order: List[str] = []

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec
        self._order.append(spec.name)

    def get_schema_list(self) -> List[Dict[str, Any]]:
        """Get all tool schemas (unfiltered)."""
        return [self._tools[name].schema for name in self._order]

    def get_schema_list_for_role(
        self,
        user_role: str,
        is_owner: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get tool schemas filtered by user role.

        This should be used when building the tools list for the LLM,
        so the model only sees tools it's allowed to use.
        """
        all_schemas = self.get_schema_list()
        return filter_tools_for_role(all_schemas, user_role, is_owner)

    def execute(
        self,
        name: str,
        orchestrator: Any,
        ctx: Dict[str, Any],
        args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a tool with permission checking.

        Permission is checked before execution (fail-closed).
        If permission denied, returns an error dict instead of raising.
        """
        spec = self._tools.get(name)
        if not spec:
            raise KeyError(name)

        # Extract role info from ctx (fail-closed defaults)
        user_role = ctx.get("user_role", "viewer")
        is_owner = ctx.get("is_owner", False)

        # Fail-closed: if role is missing, log warning and treat as viewer
        if "user_role" not in ctx:
            logger.warning(
                f"user_role missing from ctx when executing '{name}' - "
                "treating as viewer (fail-closed)"
            )

        # Check permission
        if not can_use_tool(name, user_role, is_owner):
            error_msg = get_permission_error(name, user_role)
            logger.warning(f"Permission denied for tool '{name}': {error_msg}")
            return {"error": error_msg}

        # Permission granted - execute
        return spec.handler(orchestrator, ctx, args)
