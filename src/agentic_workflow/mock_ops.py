"""A deterministic mock ops environment the tools read from and act on.

Stands in for real APIs (deploy tracker, metrics, logs, runbooks) so the agent runs
offline and in CI. The default scenario is a coherent incident: a recent `checkout`
deploy spiked the error rate and latency, with correlating payment-timeout logs and a
matching runbook — so triage has a real story to uncover.
"""

from dataclasses import dataclass, field


@dataclass
class Deploy:
    id: str
    service: str
    author: str
    minutes_ago: int
    summary: str


@dataclass
class ServiceState:
    error_rate: float
    baseline_error_rate: float
    p95_latency_ms: int
    baseline_latency_ms: int
    deploys: list[Deploy] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    rolled_back: list[str] = field(default_factory=list)


RUNBOOKS: dict[str, list[str]] = {
    "elevated 5xx after deploy": [
        "Identify the most recent deploy to the affected service.",
        "Correlate the error-rate onset with the deploy time.",
        "Roll back the suspect deploy.",
        "Verify the error rate returns to baseline.",
    ],
    "high latency": [
        "Check downstream dependency latency.",
        "Inspect recent config or deploy changes.",
        "Scale out or roll back as appropriate.",
    ],
}


class MockOps:
    def __init__(self) -> None:
        self.services: dict[str, ServiceState] = {
            "checkout": ServiceState(
                error_rate=0.082,
                baseline_error_rate=0.005,
                p95_latency_ms=2400,
                baseline_latency_ms=600,
                deploys=[
                    Deploy(
                        "checkout@a1b2c3", "checkout", "alice", 20, "bump payment client to 3.0"
                    ),
                    Deploy("checkout@f9e8d7", "checkout", "bob", 1440, "copy tweak on cart page"),
                ],
                logs=[
                    "ERROR PaymentGateway timeout after 3000ms",
                    "ERROR PaymentGateway timeout after 3000ms",
                    "WARN retrying payment (attempt 2)",
                    "ERROR NullPointer in CartService.checkout",
                ],
            ),
            # Elevated errors + a fresh bad deploy → another clean rollback case.
            "api-gateway": ServiceState(
                error_rate=0.121,
                baseline_error_rate=0.004,
                p95_latency_ms=900,
                baseline_latency_ms=300,
                deploys=[
                    Deploy("api-gateway@9f1c2d", "api-gateway", "carol", 35, "tighten route regex"),
                ],
                logs=["ERROR route /v2/orders returned 502", "ERROR upstream match failed"],
            ),
            # Elevated errors but the only deploy is stale (>60m) → nothing to roll back, escalate.
            "search": ServiceState(
                error_rate=0.060,
                baseline_error_rate=0.005,
                p95_latency_ms=700,
                baseline_latency_ms=500,
                deploys=[Deploy("search@77aa88", "search", "dave", 300, "add synonyms index")],
                logs=["ERROR shard 3 unresponsive", "ERROR query timeout"],
            ),
            # High latency but error rate is NORMAL → not a rollback; escalate to investigate.
            "auth": ServiceState(
                error_rate=0.006,
                baseline_error_rate=0.005,
                p95_latency_ms=1800,
                baseline_latency_ms=300,
                deploys=[Deploy("auth@abc123", "auth", "erin", 10, "add rate limiter")],
                logs=["WARN token verification slow", "WARN downstream LDAP latency high"],
            ),
            # TRAP: elevated errors + a fresh deploy, but the deploy is an innocent copy change and
            # the logs point at the database. Correct call is escalate/investigate, NOT rollback —
            # the rule-based planner can't tell coincidence from cause (see reports/agent_eval.md).
            "billing": ServiceState(
                error_rate=0.090,
                baseline_error_rate=0.004,
                p95_latency_ms=2100,
                baseline_latency_ms=400,
                deploys=[Deploy("billing@c0ffee", "billing", "frank", 15, "invoice copy tweak")],
                logs=[
                    "ERROR DB connection pool exhausted",
                    "ERROR could not acquire connection within 5000ms",
                    "ERROR DB connection pool exhausted",
                ],
            ),
        }

    def state(self, service: str) -> ServiceState:
        """Return the service's state, or a healthy empty default for unknown services."""
        return self.services.get(
            service,
            ServiceState(
                error_rate=0.0,
                baseline_error_rate=0.005,
                p95_latency_ms=500,
                baseline_latency_ms=500,
            ),
        )
