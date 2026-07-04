import pytest

from agentic_workflow.agent import Agent, AgentConfig
from agentic_workflow.domain import Incident, TriageResult
from agentic_workflow.planner import Action, ScriptedPlanner
from agentic_workflow.tools import FunctionTool, ToolRegistry, ToolResult

INCIDENT = Incident(id="INC-1", title="500s", description="5xx spike", service="checkout")


def _registry():
    return ToolRegistry(
        [
            FunctionTool(
                "deploys", "recent deploys", lambda service: ("1 deploy", {"svc": service})
            ),
            FunctionTool("errors", "error rate", lambda service: ToolResult("8%", {"rate": 0.08})),
        ]
    )


def test_function_tool_adapts_return_shapes():
    assert FunctionTool("a", "d", lambda: "hi").run().summary == "hi"
    tupled = FunctionTool("b", "d", lambda: ("s", {"k": 1})).run()
    assert tupled.summary == "s" and tupled.data == {"k": 1}


def test_registry_specs_and_errors():
    reg = _registry()
    assert reg.names() == ["deploys", "errors"]
    assert {s["name"] for s in reg.specs()} == {"deploys", "errors"}
    with pytest.raises(KeyError):
        reg.get("missing")
    with pytest.raises(ValueError):
        reg.register(FunctionTool("deploys", "dup", lambda: "x"))


def test_agent_runs_scripted_plan_and_records_observations():
    planner = ScriptedPlanner(
        [
            Action(kind="tool", tool="deploys", args={"service": "checkout"}),
            Action(kind="tool", tool="errors", args={"service": "checkout"}),
            Action(
                kind="finish",
                result=TriageResult("INC-1", "recent deploy", "roll back", 0.7),
            ),
        ]
    )
    result = Agent(planner, _registry()).run(INCIDENT)
    assert result.recommended_action == "roll back"
    assert not result.escalate
    # the agent attaches the full observation log, regardless of what the planner returned
    assert [o.tool for o in result.observations] == ["deploys", "errors"]
    assert result.observations[0].data == {"svc": "checkout"}


def test_agent_escalates_when_step_budget_exhausted():
    # planner keeps asking for a tool; agent should stop and escalate
    looping = ScriptedPlanner([Action(kind="tool", tool="deploys", args={"service": "x"})] * 10)
    result = Agent(looping, _registry(), AgentConfig(max_steps=3)).run(INCIDENT)
    assert result.escalate
    assert "budget" in result.hypothesis
    assert len(result.observations) == 3  # exactly max_steps tool calls
