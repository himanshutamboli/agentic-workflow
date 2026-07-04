"""Command-line interface — how an on-call engineer actually drives the triage agent.

    agentic-workflow triage --scenario checkout      # run a labeled scenario
    agentic-workflow triage --service payments --title "p95 spike"
    agentic-workflow triage --scenario billing --json
    agentic-workflow eval                             # task-success-rate over all scenarios

`triage` prints the agent's reasoning transcript (each plan → tool → observation) and a
verdict. A `rollback_deploy` is gated by the human-in-the-loop guardrail: you're prompted to
approve unless `--yes` is passed. The transcript is rendered from a `RecordingTracer`, the same
hook `llm-observatory` plugs into.
"""

import argparse
import json
import sys

from agentic_workflow.agent import Agent
from agentic_workflow.domain import Incident, TriageResult
from agentic_workflow.evaluation import render_markdown, run_eval, scenarios
from agentic_workflow.guardrails import AutoApprover, CallbackApprover
from agentic_workflow.mock_ops import MockOps
from agentic_workflow.planner import ClaudePlanner, HeuristicPlanner
from agentic_workflow.tools_builtin import build_registry
from agentic_workflow.tracing import RecordedTrace, RecordingTracer


def _incident(args: argparse.Namespace) -> Incident:
    if args.scenario:
        by_id = {s.id: s for s in scenarios()}
        if args.scenario not in by_id:
            raise SystemExit(f"unknown scenario {args.scenario!r}; choose from {sorted(by_id)}")
        return by_id[args.scenario].incident
    if not args.service:
        raise SystemExit("provide --scenario or --service")
    return Incident(
        id=f"INC-{args.service}",
        title=args.title or args.service,
        description=args.title or "",
        service=args.service,
    )


def _approver(auto: bool):
    if auto:
        return AutoApprover()

    def ask(action, state) -> bool:
        reply = input(f"⚠  Approve action {action.tool}({action.args})? [y/N] ").strip().lower()
        return reply in {"y", "yes"}

    return CallbackApprover(ask)


def render_transcript(trace: RecordedTrace) -> str:
    lines = [f"🔎 Triaging {trace.session_id} ({trace.name})", ""]
    step = 0
    for span in trace.spans:
        if span.kind == "tool":
            lines.append(f"     └─ {span.name}({span.input}) → {span.output}")
        else:  # a planner decision
            step += 1
            lines.append(f"  {step}. plan: {span.output}")
    return "\n".join(lines)


def render_verdict(result: TriageResult) -> str:
    tag = "🚨 ESCALATE" if result.escalate else "✅ ACTION"
    return "\n".join(
        [
            "",
            "─" * 60,
            f"{tag}  (confidence {result.confidence:.0%})",
            f"  hypothesis: {result.hypothesis}",
            f"  recommend : {result.recommended_action}",
            "─" * 60,
        ]
    )


def cmd_triage(args: argparse.Namespace) -> int:
    incident = _incident(args)
    planner = ClaudePlanner() if args.planner == "claude" else HeuristicPlanner()
    tracer = RecordingTracer()
    result = Agent(
        planner, build_registry(MockOps()), approver=_approver(args.yes), tracer=tracer
    ).run(incident)

    if args.json:
        print(
            json.dumps(
                {
                    "incident_id": result.incident_id,
                    "hypothesis": result.hypothesis,
                    "recommended_action": result.recommended_action,
                    "confidence": result.confidence,
                    "escalate": result.escalate,
                    "observations": [
                        {"tool": o.tool, "summary": o.summary} for o in result.observations
                    ],
                },
                indent=2,
            )
        )
    else:
        print(render_transcript(tracer.traces[0]))
        print(render_verdict(result))
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    print(render_markdown(run_eval()))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic-workflow", description="AIOps triage agent")
    sub = parser.add_subparsers(dest="command", required=True)

    t = sub.add_parser("triage", help="triage one incident")
    t.add_argument("--scenario", help="a labeled scenario id (e.g. checkout, billing)")
    t.add_argument("--service", help="service name for an ad-hoc incident")
    t.add_argument("--title", help="incident title/description")
    t.add_argument("--planner", choices=["heuristic", "claude"], default="heuristic")
    t.add_argument("--yes", action="store_true", help="auto-approve destructive actions")
    t.add_argument("--json", action="store_true", help="machine-readable output")
    t.set_defaults(func=cmd_triage)

    e = sub.add_parser("eval", help="run the triage eval set")
    e.set_defaults(func=cmd_eval)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
