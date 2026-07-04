from agentic_workflow.agent import Agent
from agentic_workflow.domain import AgentState, Incident
from agentic_workflow.mock_ops import MockOps
from agentic_workflow.planner import HeuristicPlanner, _parse_action
from agentic_workflow.tools_builtin import build_registry


def test_heuristic_planner_triages_recent_deploy():
    registry = build_registry(MockOps())
    incident = Incident("INC-1", "Checkout 500s", "elevated 5xx", "checkout")
    result = Agent(HeuristicPlanner(), registry).run(incident)

    assert not result.escalate
    assert "checkout@a1b2c3" in result.recommended_action
    assert result.confidence >= 0.5
    # it gathered signals before concluding
    assert {o.tool for o in result.observations} >= {
        "get_error_rate",
        "get_recent_deploys",
        "search_logs",
        "lookup_runbook",
    }


def test_heuristic_planner_escalates_healthy_service():
    registry = build_registry(MockOps())
    incident = Incident("INC-2", "Noise", "nothing obvious", "ghost")  # unknown -> healthy default
    result = Agent(HeuristicPlanner(), registry).run(incident)
    assert result.escalate
    assert "escalate" in result.recommended_action


def test_parse_action_handles_tool_finish_and_garbage():
    state = AgentState(incident=Incident("i", "t", "d", "s"))

    tool = _parse_action('{"kind":"tool","tool":"get_error_rate","args":{"service":"s"}}', state)
    assert tool.kind == "tool" and tool.tool == "get_error_rate"

    finish = _parse_action(
        'sure: {"kind":"finish","hypothesis":"h",'
        '"recommended_action":"roll back","confidence":0.6}',
        state,
    )
    assert finish.kind == "finish"
    assert finish.result.recommended_action == "roll back" and finish.result.confidence == 0.6

    garbage = _parse_action("no json here", state)
    assert garbage.kind == "finish" and garbage.result.escalate
