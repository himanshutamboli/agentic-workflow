from agentic_workflow.agent import Agent
from agentic_workflow.domain import Incident
from agentic_workflow.mock_ops import MockOps
from agentic_workflow.planner import HeuristicPlanner
from agentic_workflow.tools_builtin import build_registry
from agentic_workflow.tracing import NullTracer, RecordingTracer

INCIDENT = Incident("INC-1", "Checkout 500s", "elevated 5xx", "checkout", "SEV2")


def test_agent_emits_one_trace_with_plan_and_tool_spans():
    tracer = RecordingTracer()
    Agent(HeuristicPlanner(), build_registry(MockOps()), tracer=tracer).run(INCIDENT)

    assert len(tracer.traces) == 1
    trace = tracer.traces[0]
    assert trace.name == "incident_triage" and trace.session_id == "INC-1"

    kinds = [s.kind for s in trace.spans]
    # heuristic planner → 4 tool calls, each preceded by a plan span, plus a final plan(finish)
    assert kinds.count("tool") == 4
    assert kinds.count("function") == 5  # one plan per step incl. the finishing decision
    assert trace.spans[0].name == "plan"

    tool_spans = [s for s in trace.spans if s.kind == "tool"]
    assert {s.name for s in tool_spans} >= {"get_error_rate", "get_recent_deploys"}
    assert all(s.output for s in tool_spans)  # every tool span captured a summary
    assert trace.spans[-1].output.startswith("finish →")


def test_null_tracer_is_the_default_and_no_ops():
    # no tracer passed → runs identically, records nothing observable
    result = Agent(HeuristicPlanner(), build_registry(MockOps())).run(INCIDENT)
    assert "checkout@a1b2c3" in result.recommended_action

    with NullTracer().trace("x") as t, t.span("s") as s:
        s.set_output("ignored")
        s.set_usage(prompt_tokens=10)  # accepts the llm-observatory signature, does nothing
