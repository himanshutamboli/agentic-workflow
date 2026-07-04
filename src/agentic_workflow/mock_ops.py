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
            )
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
