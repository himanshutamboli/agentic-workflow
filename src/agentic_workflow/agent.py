"""The triage agent: a stateful planner/executor loop.

Each step: ask the planner for the next action given the current `AgentState`; if it's a
tool call, execute it, record an `Observation` + `Step`, and loop; if it's `finish`, return
the `TriageResult`. Bounded by `max_steps` (escalates to on-call if exhausted). Guardrails —
retries, timeouts, cost caps, human-in-the-loop — land on Day 39.

Run a demo with:  uv run python -m agentic_workflow.agent
"""

from dataclasses import dataclass

from agentic_workflow.domain import AgentState, Incident, Observation, Step, TriageResult
from agentic_workflow.logging_config import get_logger
from agentic_workflow.planner import Planner
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
        state = AgentState(incident=incident)
        for step in range(self.config.max_steps):
            action = self.planner.next_action(state, self.registry)
            if action.kind == "finish":
                result = action.result or self._inconclusive(state)
                result.observations = state.observations  # agent owns the log
                logger.info("triage finished in %d step(s): %s", step, result.hypothesis)
                return result
            tool = self.registry.get(action.tool)
            outcome = tool.run(**action.args)
            observation = Observation(tool=action.tool, summary=outcome.summary, data=outcome.data)
            state.observations.append(observation)
            state.steps.append(Step(tool=action.tool, args=action.args, observation=observation))
        logger.info("triage hit max_steps (%d); escalating", self.config.max_steps)
        return self._inconclusive(state)

    @staticmethod
    def _inconclusive(state: AgentState) -> TriageResult:
        return TriageResult(
            incident_id=state.incident.id,
            hypothesis="inconclusive (step budget exhausted)",
            recommended_action="escalate to on-call",
            confidence=0.0,
            observations=state.observations,
            escalate=True,
        )


def main() -> None:
    from agentic_workflow.mock_ops import MockOps
    from agentic_workflow.planner import HeuristicPlanner
    from agentic_workflow.tools_builtin import build_registry

    registry = build_registry(MockOps())
    incident = Incident(
        id="INC-1",
        title="Checkout 500s",
        description="Elevated 5xx on checkout",
        service="checkout",
        severity="SEV2",
    )
    result = Agent(HeuristicPlanner(), registry).run(incident)
    logger.info("hypothesis=%r", result.hypothesis)
    logger.info(
        "action=%r confidence=%.2f obs=%d",
        result.recommended_action,
        result.confidence,
        len(result.observations),
    )


if __name__ == "__main__":
    main()
