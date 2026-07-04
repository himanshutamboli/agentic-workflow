"""The triage agent: a planner/executor loop.

Skeleton (Day 36): ask the planner for the next action; if it's a tool call, execute it and
record an observation; repeat until the planner finishes or `max_steps` is hit. Guardrails
(retries, timeouts, cost caps, human-in-the-loop) land on Day 39; a real LLM planner and
richer state on Day 38.

Run a demo with:  uv run python -m agentic_workflow.agent
"""

from dataclasses import dataclass

from agentic_workflow.domain import Incident, Observation, TriageResult
from agentic_workflow.logging_config import get_logger
from agentic_workflow.planner import Action, Planner
from agentic_workflow.tools import ToolRegistry

logger = get_logger(__name__)


@dataclass
class AgentConfig:
    max_steps: int = 8


class Agent:
    def __init__(
        self, planner: Planner, registry: ToolRegistry, config: AgentConfig | None = None
    ) -> None:
        self.planner = planner
        self.registry = registry
        self.config = config or AgentConfig()

    def run(self, incident: Incident) -> TriageResult:
        observations: list[Observation] = []
        for step in range(self.config.max_steps):
            action = self.planner.next_action(incident, observations, self.registry)
            if action.kind == "finish":
                result = action.result or self._inconclusive(incident, observations)
                result.observations = observations  # agent owns the full observation log
                logger.info("triage finished in %d step(s): %s", step, result.hypothesis)
                return result
            tool = self.registry.get(action.tool)
            result = tool.run(**action.args)
            observations.append(
                Observation(tool=action.tool, summary=result.summary, data=result.data)
            )
        logger.info("triage hit max_steps (%d); escalating", self.config.max_steps)
        return self._inconclusive(incident, observations)

    @staticmethod
    def _inconclusive(incident: Incident, observations: list[Observation]) -> TriageResult:
        return TriageResult(
            incident_id=incident.id,
            hypothesis="inconclusive (step budget exhausted)",
            recommended_action="escalate to on-call",
            confidence=0.0,
            observations=observations,
            escalate=True,
        )


def main() -> None:
    from agentic_workflow.mock_ops import MockOps
    from agentic_workflow.planner import ScriptedPlanner
    from agentic_workflow.tools_builtin import build_registry

    registry = build_registry(MockOps())
    incident = Incident(
        id="INC-1",
        title="Checkout 500s",
        description="Elevated 5xx on checkout",
        service="checkout",
        severity="SEV2",
    )
    planner = ScriptedPlanner(
        [
            Action(kind="tool", tool="get_error_rate", args={"service": "checkout"}),
            Action(kind="tool", tool="get_recent_deploys", args={"service": "checkout"}),
            Action(
                kind="tool",
                tool="search_logs",
                args={"service": "checkout", "pattern": "PaymentGateway"},
            ),
            Action(
                kind="tool",
                tool="lookup_runbook",
                args={"symptom": "elevated 5xx after deploy"},
            ),
            Action(
                kind="finish",
                result=TriageResult(
                    incident_id="INC-1",
                    hypothesis=(
                        "deploy checkout@a1b2c3 (20m ago) spiked errors — PaymentGateway timeouts"
                    ),
                    recommended_action="roll back checkout@a1b2c3",
                    confidence=0.72,
                ),
            ),
        ]
    )
    result = Agent(planner, registry).run(incident)
    logger.info(
        "hypothesis=%r action=%r confidence=%.2f obs=%d",
        result.hypothesis,
        result.recommended_action,
        result.confidence,
        len(result.observations),
    )


if __name__ == "__main__":
    main()
