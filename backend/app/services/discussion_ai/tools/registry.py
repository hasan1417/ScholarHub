from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List


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
        return [self._tools[name].schema for name in self._order]

    def execute(self, name: str, orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
        spec = self._tools.get(name)
        if not spec:
            raise KeyError(name)
        return spec.handler(orchestrator, ctx, args)
