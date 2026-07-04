"""Guardrails that keep the agent bounded, safe, and affordable.

The executor enforces these *around* the planner, so no planner — heuristic or LLM — can
escape them:

* **step budget** (`max_steps`) — the loop can't run forever.
* **retries** (`max_retries`) — a transient tool failure is retried, not fatal.
* **cost cap** (`max_cost`) — each action has an estimated cost; the loop stops before the
  cumulative spend exceeds the budget.
* **human-in-the-loop** — a `protected` (destructive) tool call must be approved before it
  runs; the default `AutoApprover` is CI-safe, real deployments wire a human via `Approver`.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from agentic_workflow.domain import Action, AgentState


@dataclass
class Guardrails:
    max_steps: int = 8
    max_retries: int = 2  # extra attempts per tool call on exception
    max_cost: float = 1.0  # cumulative action-cost budget (USD-ish, deterministic)
    default_cost: float = 0.01  # cost charged per tool call...
    action_costs: dict[str, float] = field(default_factory=dict)  # ...unless overridden here
    protected_tools: set[str] = field(default_factory=lambda: {"rollback_deploy"})

    def cost_of(self, tool: str) -> float:
        return self.action_costs.get(tool, self.default_cost)

    def is_protected(self, action: Action) -> bool:
        return action.kind == "tool" and action.tool in self.protected_tools


class Approver(Protocol):
    """Decides whether a protected action may run (the human-in-the-loop gate)."""

    def approve(self, action: Action, state: AgentState) -> bool: ...


class AutoApprover:
    """CI-safe default: approves every protected action."""

    def approve(self, action: Action, state: AgentState) -> bool:
        return True


class DenyAll:
    """Refuses every protected action — the loop must escalate instead of acting."""

    def approve(self, action: Action, state: AgentState) -> bool:
        return False


class CallbackApprover:
    """Wraps a callable (e.g. a CLI prompt) for real human-in-the-loop approval."""

    def __init__(self, ask: Callable[[Action, AgentState], bool]) -> None:
        self._ask = ask

    def approve(self, action: Action, state: AgentState) -> bool:
        return bool(self._ask(action, state))
