"""The concrete triage tools, bound to a MockOps backend.

Read tools (deploys, error rate, metrics, logs, runbook) are safe to call freely; the
`rollback_deploy` **action** mutates state and is the kind of tool that gets gated behind a
human-in-the-loop guardrail on Day 39.
"""

from dataclasses import asdict

from agentic_workflow.mock_ops import RUNBOOKS, MockOps
from agentic_workflow.tools import FunctionTool, ToolRegistry, ToolResult


def build_registry(ops: MockOps) -> ToolRegistry:
    def get_recent_deploys(service: str) -> ToolResult:
        deploys = ops.state(service).deploys
        return ToolResult(
            f"{len(deploys)} recent deploy(s)", {"deploys": [asdict(d) for d in deploys]}
        )

    def get_error_rate(service: str) -> ToolResult:
        st = ops.state(service)
        elevated = st.error_rate > 3 * st.baseline_error_rate
        return ToolResult(
            f"error rate {st.error_rate:.1%} (baseline {st.baseline_error_rate:.1%})"
            + (" — ELEVATED" if elevated else ""),
            {"error_rate": st.error_rate, "baseline": st.baseline_error_rate, "elevated": elevated},
        )

    def get_service_metrics(service: str) -> ToolResult:
        st = ops.state(service)
        return ToolResult(
            f"p95 latency {st.p95_latency_ms}ms (baseline {st.baseline_latency_ms}ms)",
            {"p95_latency_ms": st.p95_latency_ms, "baseline_latency_ms": st.baseline_latency_ms},
        )

    def search_logs(service: str, pattern: str = "") -> ToolResult:
        matches = [ln for ln in ops.state(service).logs if pattern.lower() in ln.lower()]
        return ToolResult(f"{len(matches)} matching log line(s)", {"matches": matches})

    def lookup_runbook(symptom: str) -> ToolResult:
        for key, steps in RUNBOOKS.items():
            if any(word in symptom.lower() for word in key.split()):
                return ToolResult(f"runbook: {key}", {"runbook": key, "steps": steps})
        return ToolResult("no matching runbook", {"steps": []})

    def rollback_deploy(service: str, deploy_id: str) -> ToolResult:
        ops.state(service).rolled_back.append(deploy_id)
        return ToolResult(f"rolled back {deploy_id} on {service}", {"rolled_back": deploy_id})

    return ToolRegistry(
        [
            FunctionTool(
                "get_recent_deploys", "List recent deploys for a service", get_recent_deploys
            ),
            FunctionTool(
                "get_error_rate", "Current vs baseline error rate for a service", get_error_rate
            ),
            FunctionTool(
                "get_service_metrics",
                "Latency metrics vs baseline for a service",
                get_service_metrics,
            ),
            FunctionTool(
                "search_logs", "Search a service's recent logs for a pattern", search_logs
            ),
            FunctionTool("lookup_runbook", "Find a runbook matching a symptom", lookup_runbook),
            FunctionTool(
                "rollback_deploy", "ACTION: roll back a deploy (mutates state)", rollback_deploy
            ),
        ]
    )
