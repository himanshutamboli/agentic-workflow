"""Tool interface + registry.

A tool is a named, described capability the agent can call with keyword args, returning a
`ToolResult`. `FunctionTool` adapts a plain callable into a tool (used for real tools on
Day 37 and for fakes in tests). The registry exposes tool *specs* (name + description) so
the planner can decide what to call.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ToolResult:
    summary: str
    data: dict = field(default_factory=dict)


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str

    def run(self, **kwargs) -> ToolResult: ...


class FunctionTool:
    """Adapt a callable ``fn(**kwargs) -> ToolResult | (str, dict) | str`` into a Tool."""

    def __init__(self, name: str, description: str, fn: Callable[..., object]) -> None:
        self.name = name
        self.description = description
        self._fn = fn

    def run(self, **kwargs) -> ToolResult:
        result = self._fn(**kwargs)
        if isinstance(result, ToolResult):
            return result
        if isinstance(result, tuple):
            summary, data = result
            return ToolResult(summary=summary, data=data)
        return ToolResult(summary=str(result))


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[dict]:
        """Name + description for each tool — the menu shown to the planner."""
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]
