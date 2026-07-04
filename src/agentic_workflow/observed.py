"""Run the triage agent instrumented by `llm-observatory` — the flagship cross-link.

The agent's tracing hook (`tracing.py`) is shaped to match `llm-observatory`'s `Tracer`, so
the real observability backend plugs in unchanged: every triage run becomes a persisted trace
(one span per planner decision + tool call) you can inspect in the observatory dashboard.

`llm-observatory` is an *optional* dependency — CI and the default agent don't need it. Install
it alongside this repo, then:

    uv run python -m agentic_workflow.observed        # writes traces to the observatory DB
    # then, in the llm-observatory repo:  uv run streamlit run src/llm_observatory/app.py
"""

from agentic_workflow.agent import Agent
from agentic_workflow.domain import Incident
from agentic_workflow.logging_config import get_logger
from agentic_workflow.mock_ops import MockOps
from agentic_workflow.planner import HeuristicPlanner
from agentic_workflow.tools_builtin import build_registry

logger = get_logger(__name__)

INCIDENTS = [
    Incident("INC-1", "Checkout 500s", "Elevated 5xx on checkout", "checkout", "SEV2"),
    Incident("INC-2", "Payments latency", "p95 latency spike", "payments", "SEV3"),
    Incident("INC-3", "Ghost noise", "nothing obvious", "ghost", "SEV4"),
]


def _observatory_tracer():
    """Build a real `llm-observatory` Tracer, or explain how to enable it."""
    try:
        from llm_observatory.db import get_engine, init_db, session_factory
        from llm_observatory.sdk import Tracer
        from llm_observatory.writer import DBWriter
    except ImportError as exc:  # optional dependency
        raise SystemExit(
            "llm-observatory is not installed. Install it in this environment to record "
            "traces (e.g. `uv pip install -e ../llm-observatory`)."
        ) from exc

    engine = get_engine()
    init_db(engine)
    return Tracer(DBWriter(session_factory(engine)))


def main() -> None:
    tracer = _observatory_tracer()
    registry = build_registry(MockOps())
    for incident in INCIDENTS:
        result = Agent(HeuristicPlanner(), registry, tracer=tracer).run(incident)
        logger.info(
            "traced %s → %s (escalate=%s)", incident.id, result.recommended_action, result.escalate
        )
    logger.info("Done. Open the llm-observatory dashboard to inspect the traces.")


if __name__ == "__main__":
    main()
