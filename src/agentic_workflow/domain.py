"""Domain model for AIOps incident triage.

An `Incident` comes in; the agent gathers `Observation`s by calling tools, accumulating an
`AgentState` (the loop's memory), then produces a `TriageResult`. An `Action` is the planner's
decision each step: call a tool, or finish.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Incident:
    id: str
    title: str
    description: str
    service: str
    severity: str = "unknown"  # SEV1..SEV4 / unknown
    signals: dict = field(default_factory=dict)


@dataclass
class Observation:
    """The outcome of one tool call during triage."""

    tool: str
    summary: str
    data: dict = field(default_factory=dict)


@dataclass
class TriageResult:
    incident_id: str
    hypothesis: str
    recommended_action: str
    confidence: float
    observations: list[Observation] = field(default_factory=list)
    escalate: bool = False


@dataclass
class Action:
    kind: Literal["tool", "finish"]
    tool: str | None = None
    args: dict = field(default_factory=dict)
    result: TriageResult | None = None  # set when kind == "finish"


@dataclass
class Step:
    tool: str
    args: dict
    observation: Observation


@dataclass
class AgentState:
    """The loop's memory: the incident plus everything observed so far."""

    incident: Incident
    observations: list[Observation] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)

    @property
    def tool_calls(self) -> int:
        return len(self.steps)

    def tools_called(self) -> set[str]:
        return {s.tool for s in self.steps}

    def last(self, tool: str) -> Observation | None:
        """Most recent observation from a given tool, if any."""
        for step in reversed(self.steps):
            if step.tool == tool:
                return step.observation
        return None
