"""Planner interface: given the incident and observations so far, decide the next action.

An `Action` is either a tool call or a `finish` carrying the `TriageResult`. Day 36 ships a
`ScriptedPlanner` (follows a fixed plan) so the skeleton is runnable and testable without an
LLM; a real LLM-backed planner arrives with the orchestration loop (Day 38).
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal, Protocol

from agentic_workflow.domain import Incident, Observation, TriageResult
from agentic_workflow.tools import ToolRegistry


@dataclass
class Action:
    kind: Literal["tool", "finish"]
    tool: str | None = None
    args: dict = field(default_factory=dict)
    result: TriageResult | None = None  # set when kind == "finish"


class Planner(Protocol):
    def next_action(
        self, incident: Incident, observations: list[Observation], registry: ToolRegistry
    ) -> Action: ...


class ScriptedPlanner:
    """Yields a predefined sequence of actions — deterministic, for the skeleton and tests."""

    def __init__(self, actions: Iterable[Action]) -> None:
        self._actions = list(actions)
        self._i = 0

    def next_action(
        self, incident: Incident, observations: list[Observation], registry: ToolRegistry
    ) -> Action:
        if self._i < len(self._actions):
            action = self._actions[self._i]
            self._i += 1
            return action
        # Ran out of scripted steps -> finish, escalating (nothing conclusive).
        return Action(
            kind="finish",
            result=TriageResult(
                incident_id=incident.id,
                hypothesis="inconclusive",
                recommended_action="escalate to on-call",
                confidence=0.0,
                observations=observations,
                escalate=True,
            ),
        )
