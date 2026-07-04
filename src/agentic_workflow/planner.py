"""Planners decide the next `Action` from the current `AgentState`.

* `ScriptedPlanner` — fixed sequence; deterministic, for tests.
* `HeuristicPlanner` — rule-based triage reasoning (the CI-safe default): check error rate →
  recent deploys → logs → runbook → conclude. Reads prior observations to decide.
* `ClaudePlanner` — an LLM (claude-opus-4-8) chooses the next tool from the registry menu.
"""

import json
from collections.abc import Iterable
from typing import Protocol

from agentic_workflow.domain import Action, AgentState, TriageResult
from agentic_workflow.tools import ToolRegistry


class Planner(Protocol):
    def next_action(self, state: AgentState, registry: ToolRegistry) -> Action: ...


class ScriptedPlanner:
    """Yields a predefined sequence of actions; finishes (escalating) when exhausted."""

    def __init__(self, actions: Iterable[Action]) -> None:
        self._actions = list(actions)
        self._i = 0

    def next_action(self, state: AgentState, registry: ToolRegistry) -> Action:
        if self._i < len(self._actions):
            action = self._actions[self._i]
            self._i += 1
            return action
        return _escalate(state, "inconclusive")


class HeuristicPlanner:
    """Rule-based triage: gather signals in order, then conclude from what was found."""

    def next_action(self, state: AgentState, registry: ToolRegistry) -> Action:
        service = state.incident.service
        called = state.tools_called()

        if "get_error_rate" not in called:
            return Action("tool", "get_error_rate", {"service": service})
        if "get_recent_deploys" not in called:
            return Action("tool", "get_recent_deploys", {"service": service})
        if "search_logs" not in called:
            return Action("tool", "search_logs", {"service": service, "pattern": "ERROR"})
        if "lookup_runbook" not in called:
            symptom = "elevated 5xx after deploy" if self._elevated(state) else "high latency"
            return Action("tool", "lookup_runbook", {"symptom": symptom})
        return self._conclude(state)

    def _elevated(self, state: AgentState) -> bool:
        obs = state.last("get_error_rate")
        return bool(obs and obs.data.get("elevated"))

    def _recent_deploy(self, state: AgentState) -> dict | None:
        obs = state.last("get_recent_deploys")
        deploys = (obs.data.get("deploys") if obs else None) or []
        recent = [d for d in deploys if d.get("minutes_ago", 9999) <= 60]
        return min(recent, key=lambda d: d["minutes_ago"]) if recent else None

    def _conclude(self, state: AgentState) -> Action:
        deploy = self._recent_deploy(state)
        if self._elevated(state) and deploy:
            return Action(
                "finish",
                result=TriageResult(
                    incident_id=state.incident.id,
                    hypothesis=f"recent deploy {deploy['id']} ({deploy['minutes_ago']}m ago) "
                    "correlates with the elevated error rate",
                    recommended_action=f"roll back {deploy['id']}",
                    confidence=0.75,
                ),
            )
        return _escalate(state, "no clear cause found in signals")


class ClaudePlanner:
    """LLM planner: Claude picks the next tool (or finishes) given the state + tool menu."""

    def __init__(self, model: str = "claude-opus-4-8", max_tokens: int = 1024) -> None:
        self.model = model
        self.max_tokens = max_tokens

    def next_action(self, state: AgentState, registry: ToolRegistry) -> Action:
        import anthropic

        tools = "\n".join(f"- {s['name']}: {s['description']}" for s in registry.specs())
        history = "\n".join(f"[{o.tool}] {o.summary}" for o in state.observations) or "(none yet)"
        system = (
            "You are an incident-triage planner. Given the incident, the tools available, and "
            "observations so far, decide the next step. Respond with ONLY a JSON object: either "
            '{"kind":"tool","tool":"<name>","args":{...}} to gather more signal, or '
            '{"kind":"finish","hypothesis":"...","recommended_action":"...","confidence":0.0-1.0}.'
        )
        user = (
            f"Incident: {state.incident.title} on {state.incident.service}\n"
            f"{state.incident.description}\n\nTools:\n{tools}\n\nObservations:\n{history}"
        )
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        return _parse_action(text, state)


def _parse_action(text: str, state: AgentState) -> Action:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return _escalate(state, "planner returned no action")
    data = json.loads(text[start : end + 1])
    if data.get("kind") == "tool":
        return Action("tool", data["tool"], data.get("args", {}))
    return Action(
        "finish",
        result=TriageResult(
            incident_id=state.incident.id,
            hypothesis=data.get("hypothesis", "inconclusive"),
            recommended_action=data.get("recommended_action", "escalate to on-call"),
            confidence=float(data.get("confidence", 0.0)),
        ),
    )


def _escalate(state: AgentState, reason: str) -> Action:
    return Action(
        "finish",
        result=TriageResult(
            incident_id=state.incident.id,
            hypothesis=reason,
            recommended_action="escalate to on-call",
            confidence=0.0,
            escalate=True,
        ),
    )
