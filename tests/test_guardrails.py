from agentic_workflow.agent import Agent
from agentic_workflow.domain import Action, Incident
from agentic_workflow.guardrails import AutoApprover, DenyAll, Guardrails
from agentic_workflow.planner import ScriptedPlanner
from agentic_workflow.tools import FunctionTool, ToolRegistry, ToolResult

INCIDENT = Incident(id="INC-1", title="500s", description="5xx spike", service="checkout")


def _registry(fail_times: int = 0):
    calls = {"n": 0}

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] <= fail_times:
            raise RuntimeError("transient timeout")
        return ToolResult("ok", {"attempts": calls["n"]})

    return ToolRegistry(
        [
            FunctionTool("errors", "error rate", lambda service: ToolResult("8%", {"rate": 0.08})),
            FunctionTool("flaky", "sometimes fails", flaky),
            FunctionTool(
                "rollback_deploy", "roll back a deploy", lambda **k: ToolResult("rolled back")
            ),
        ]
    )


def _plan(*tools):
    return ScriptedPlanner([Action(kind="tool", tool=t, args={}) for t in tools])


def test_retries_recover_from_transient_tool_failure():
    # fails twice, succeeds on the third attempt (max_retries=2 → 3 attempts)
    agent = Agent(_plan("flaky"), _registry(fail_times=2), Guardrails(max_retries=2, max_steps=2))
    result = agent.run(INCIDENT)
    assert result.observations[0].data["attempts"] == 3


def test_persistent_failure_is_observed_not_raised():
    agent = Agent(_plan("flaky"), _registry(fail_times=99), Guardrails(max_retries=1, max_steps=2))
    result = agent.run(INCIDENT)
    obs = result.observations[0]
    assert "failed after 2 attempts" in obs.summary and "error" in obs.data


def test_cost_cap_stops_the_loop_before_overspending():
    # each call costs 0.01; budget only affords one before escalating
    guards = Guardrails(default_cost=0.01, max_cost=0.015, max_steps=8)
    result = Agent(_plan("errors", "errors", "errors"), _registry(), guards).run(INCIDENT)
    assert result.escalate
    assert "cost budget" in result.hypothesis
    assert len(result.observations) == 1


def test_protected_tool_needs_approval():
    guards = Guardrails(max_steps=4)
    denied = Agent(_plan("rollback_deploy"), _registry(), guards, DenyAll()).run(INCIDENT)
    assert denied.escalate and "approval required for rollback_deploy" in denied.hypothesis

    approved = Agent(_plan("rollback_deploy"), _registry(), guards, AutoApprover()).run(INCIDENT)
    assert approved.observations[0].summary == "rolled back"
