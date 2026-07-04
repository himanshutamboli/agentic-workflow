"""Agent eval: does triage reach the *correct call* on labeled incidents?

Running isn't the same as being right. Each `Scenario` pairs an incident with the correct
outcome — roll back a specific deploy, or escalate — and `run_eval` scores the agent's actual
`TriageResult` against it. The headline metric is **task-success-rate**; we also report the
**false-rollback rate** (rolling back an innocent deploy is the costly, risky failure).

The rule-based `HeuristicPlanner` deliberately *misses* one scenario (`billing`) where a recent
deploy coincides with a database-driven incident — it can't tell correlation from cause. That
honest gap is the case for a log-reading `ClaudePlanner`. Deterministic → runs in CI.

Run it with:  uv run python -m agentic_workflow.evaluation
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from agentic_workflow.agent import Agent
from agentic_workflow.domain import Incident, TriageResult
from agentic_workflow.logging_config import get_logger
from agentic_workflow.mock_ops import MockOps
from agentic_workflow.planner import HeuristicPlanner, Planner
from agentic_workflow.tools_builtin import build_registry

logger = get_logger(__name__)

Outcome = Literal["rollback", "escalate"]


@dataclass
class Scenario:
    id: str
    incident: Incident
    expected: Outcome
    target: str | None = None  # for rollback: the deploy that should be rolled back
    note: str = ""


def scenarios() -> list[Scenario]:
    """The labeled triage test set (services are seeded in `MockOps`)."""

    def inc(service: str, title: str, desc: str) -> Incident:
        return Incident(id=f"INC-{service}", title=title, description=desc, service=service)

    return [
        Scenario(
            "checkout",
            inc("checkout", "Checkout 500s", "elevated 5xx on checkout"),
            "rollback",
            "checkout@a1b2c3",
            "fresh bad deploy correlates with the error spike",
        ),
        Scenario(
            "api-gateway",
            inc("api-gateway", "Gateway 502s", "routes returning 502"),
            "rollback",
            "api-gateway@9f1c2d",
            "fresh deploy tightened a route regex",
        ),
        Scenario(
            "search",
            inc("search", "Search errors", "elevated errors, shards flaky"),
            "escalate",
            None,
            "elevated but the only deploy is stale — nothing to roll back",
        ),
        Scenario(
            "auth",
            inc("auth", "Auth slow", "login latency high"),
            "escalate",
            None,
            "high latency but normal error rate — not a rollback",
        ),
        Scenario(
            "billing",
            inc("billing", "Billing errors", "payment writes failing"),
            "escalate",
            None,
            "TRAP: recent deploy is innocent; logs point at the database",
        ),
        Scenario(
            "ghost",
            inc("ghost", "Unknown noise", "nothing obvious"),
            "escalate",
            None,
            "healthy service — no signal to act on",
        ),
    ]


def classify(result: TriageResult) -> Outcome | Literal["other"]:
    if result.escalate:
        return "escalate"
    if "roll back" in result.recommended_action.lower():
        return "rollback"
    return "other"


@dataclass
class ScenarioResult:
    scenario: Scenario
    got: str
    success: bool
    action: str


@dataclass
class EvalReport:
    rows: list[ScenarioResult] = field(default_factory=list)

    @property
    def task_success_rate(self) -> float:
        return sum(r.success for r in self.rows) / len(self.rows) if self.rows else 0.0

    @property
    def false_rollbacks(self) -> int:
        """Rolled back when the correct call was to escalate — the costly failure."""
        return sum(r.got == "rollback" and r.scenario.expected == "escalate" for r in self.rows)


def run_eval(planner: Planner | None = None) -> EvalReport:
    report = EvalReport()
    for sc in scenarios():
        registry = build_registry(MockOps())  # fresh state per scenario (rollback mutates)
        result = Agent(planner or HeuristicPlanner(), registry).run(sc.incident)
        got = classify(result)
        success = got == sc.expected and (
            sc.target is None or sc.target in result.recommended_action
        )
        report.rows.append(ScenarioResult(sc, got, success, result.recommended_action))
    return report


def render_markdown(report: EvalReport) -> str:
    passed = sum(r.success for r in report.rows)
    total = len(report.rows)
    lines = [
        "# Agent evaluation — triage task-success-rate\n",
        f"- **Task-success-rate:** {report.task_success_rate:.0%} ({passed}/{total})",
        f"- **False-rollback rate:** {report.false_rollbacks}/{total}\n",
        "| Scenario | Expected | Got | ✓ | Note |",
        "|---|---|---|:-:|---|",
    ]
    for r in report.rows:
        mark = "✅" if r.success else "❌"
        lines.append(
            f"| {r.scenario.id} | {r.scenario.expected} | {r.got} | {mark} | {r.scenario.note} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    report = run_eval()
    out = Path("reports/agent_eval.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text(render_markdown(report))
    logger.info(
        "task_success_rate=%.0f%% false_rollbacks=%d → %s",
        report.task_success_rate * 100,
        report.false_rollbacks,
        out,
    )


if __name__ == "__main__":
    main()
