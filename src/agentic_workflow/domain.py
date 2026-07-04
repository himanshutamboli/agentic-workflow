"""Domain model for AIOps incident triage.

An `Incident` comes in; the agent gathers `Observation`s by calling tools, then produces a
`TriageResult` (hypothesis + recommended action + confidence).
"""

from dataclasses import dataclass, field


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
