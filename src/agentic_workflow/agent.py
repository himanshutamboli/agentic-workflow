"""The triage agent: a stateful planner/executor loop with guardrails.

Each step: ask the planner for the next action given the current `AgentState`; if it's a
tool call, enforce the guardrails (cost cap, human-in-the-loop approval, retries), execute it,
record an `Observation` + `Step`, and loop; if it's `finish`, return the `TriageResult`.

The executor owns the guardrails so no planner — heuristic or LLM — can escape them:
step budget, retries on transient failure, a cumulative cost cap, and approval for
destructive (`protected`) tools. See `guardrails.py`.

Run a demo with:  uv run python -m agentic_workflow.agent
"""

from agentic_workflow.domain import Action, AgentState, Incident, Observation, Step, TriageResult
from agentic_workflow.guardrails import Approver, AutoApprover, Guardrails
from agentic_workflow.logging_config import get_logger
from agentic_workflow.planner import Planner
from agentic_workflow.tools import ToolRegistry
from agentic_workflow.tracing import NullTracer, Tracer

logger = get_logger(__name__)


class Agent:
    def __init__(
        self,
        planner: Planner,
        registry: ToolRegistry,
        guardrails: Guardrails | None = None,
        approver: Approver | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.planner = planner
        self.registry = registry
        self.guardrails = guardrails or Guardrails()
        self.approver = approver or AutoApprover()
        self.tracer = tracer or NullTracer()

    def run(self, incident: Incident) -> TriageResult:
        state = AgentState(incident=incident)
        spent = 0.0
        model = getattr(self.planner, "model", None)  # set by ClaudePlanner, absent otherwise
        with self.tracer.trace("incident_triage", session_id=incident.id, model=model) as tr:
            for step in range(self.guardrails.max_steps):
                with tr.span(
                    "plan", kind="llm" if model else "function", input=incident.title
                ) as ps:
                    action = self.planner.next_action(state, self.registry)
                    ps.set_output(self._describe(action))
                if action.kind == "finish":
                    return self._finish(state, action.result, step)

                cost = self.guardrails.cost_of(action.tool)
                if spent + cost > self.guardrails.max_cost:
                    logger.warning(
                        "cost cap ($%.2f) would be exceeded; escalating", self.guardrails.max_cost
                    )
                    return self._escalate(state, "cost budget exhausted before a conclusion")

                if self.guardrails.is_protected(action) and not self.approver.approve(
                    action, state
                ):
                    logger.info("protected action %r denied; escalating to human", action.tool)
                    return self._escalate(state, f"human approval required for {action.tool}")

                with tr.span(action.tool, kind="tool", input=str(action.args)) as sp:
                    observation = self._execute(action)
                    sp.set_output(observation.summary)
                spent += cost
                state.observations.append(observation)
                state.steps.append(
                    Step(tool=action.tool, args=action.args, observation=observation)
                )

            logger.info("triage hit max_steps (%d); escalating", self.guardrails.max_steps)
            return self._escalate(state, "step budget exhausted")

    @staticmethod
    def _describe(action: Action) -> str:
        if action.kind == "finish":
            rec = action.result.recommended_action if action.result else "escalate"
            return f"finish → {rec}"
        return f"call {action.tool}({action.args})"

    def _execute(self, action: Action) -> Observation:
        """Run a tool with retries; a persistent failure is observed, not raised."""
        tool = self.registry.get(action.tool)
        last_error: Exception | None = None
        for attempt in range(self.guardrails.max_retries + 1):
            try:
                outcome = tool.run(**action.args)
                return Observation(tool=action.tool, summary=outcome.summary, data=outcome.data)
            except Exception as exc:  # noqa: BLE001 — tool failures are data, not crashes
                last_error = exc
                logger.warning("tool %r failed (attempt %d): %s", action.tool, attempt + 1, exc)
        return Observation(
            tool=action.tool,
            summary=f"tool failed after {self.guardrails.max_retries + 1} attempts: {last_error}",
            data={"error": str(last_error)},
        )

    def _finish(self, state: AgentState, result: TriageResult | None, step: int) -> TriageResult:
        result = result or self._escalate(state, "inconclusive")
        result.observations = state.observations  # agent owns the log
        logger.info("triage finished in %d step(s): %s", step, result.hypothesis)
        return result

    @staticmethod
    def _escalate(state: AgentState, reason: str) -> TriageResult:
        return TriageResult(
            incident_id=state.incident.id,
            hypothesis=reason,
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
        "action=%r confidence=%.2f obs=%d escalate=%s",
        result.recommended_action,
        result.confidence,
        len(result.observations),
        result.escalate,
    )


if __name__ == "__main__":
    main()
