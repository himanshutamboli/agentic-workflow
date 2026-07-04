# agentic-workflow 🤖

[![CI](https://github.com/himanshutamboli/agentic-workflow/actions/workflows/ci.yml/badge.svg)](https://github.com/himanshutamboli/agentic-workflow/actions/workflows/ci.yml)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Ruff](https://img.shields.io/badge/lint-ruff-orange.svg)](https://github.com/astral-sh/ruff)
[![status](https://img.shields.io/badge/status-building-blue.svg)](#roadmap)

> A multi-agent **AIOps incident-triage** workflow: an agent ingests an incident, gathers
> signals through tools, forms a hypothesis, and recommends remediation — with guardrails,
> evals, and (Day 40) **instrumented by [`llm-observatory`](https://github.com/himanshutamboli/llm-observatory)**.

## Why this exists

Incident triage is repetitive and time-pressured: pull recent deploys, check error rates and
logs, correlate, hypothesize, act. That's a planner/executor loop with tools — a great fit for
an agent, *if* it has guardrails (no runaway loops or cost) and is evaluated (does it reach the
right call?). This repo builds that agent as real software, not a prompt.

## Architecture (planner → tools → executor)

```
 Incident ─► Agent loop ──► Planner.next_action(incident, observations, tools)
                 │              │
                 │              ├─ "tool"   → execute tool → record Observation ─┐
                 │              └─ "finish" → TriageResult (hypothesis, action)   │
                 └───────────────────────────◄─────────────────────────────────┘
                    guardrails: max steps · retries · cost cap · human-in-the-loop approval
```

- **`domain.py`** — `Incident`, `Observation`, `TriageResult`.
- **`tools.py`** — `Tool` protocol + `ToolRegistry`; `FunctionTool` adapts any callable. The
  registry exposes tool *specs* (name + description) as the planner's menu.
- **`planner.py`** — `Planner` protocol deciding the next `Action` from `AgentState`.
  `HeuristicPlanner` (CI-safe default) does real rule-based triage — check error rate → recent
  deploys → logs → runbook → conclude, reading prior observations; `ClaudePlanner` (LLM) picks
  the next tool from the registry menu; `ScriptedPlanner` drives tests.
- **`agent.py`** — the planner/executor loop: plan → execute → observe → repeat. The executor
  enforces the guardrails so no planner can escape them; it escalates to on-call whenever a
  bound is hit or a conclusion can't be reached.
- **`guardrails.py`** — `Guardrails` (step budget, per-tool retries on transient failure,
  cumulative cost cap) + an `Approver` gate for destructive tools (`rollback_deploy`).
  `AutoApprover` is the CI-safe default; `CallbackApprover` wires a real human-in-the-loop.
- **`tools_builtin.py` + `mock_ops.py`** — the concrete triage tools (recent deploys, error
  rate, metrics, log search, runbook lookup, and a side-effecting `rollback_deploy` action)
  over a deterministic mock ops backend seeded with a coherent incident scenario.

```bash
uv sync --dev
uv run python -m agentic_workflow.agent   # scripted triage demo
uv run pytest
```

## Roadmap

| Day | Deliverable |
|---|---|
| 36 ✅ | Architecture: workflow chosen (AIOps triage), agent skeleton + tool interface |
| 37 ✅ | Real tools: deploys, error rate, metrics, log search, runbook, rollback action |
| 38 ✅ | Stateful orchestration loop + HeuristicPlanner (real reasoning) + ClaudePlanner |
| 39 ✅ | Guardrails: retries, cost cap, step budget, human-in-the-loop approval |
| 40 | **Instrument the agent with `llm-observatory`** (every run traced + scored) |
| 41 | Agent eval: task-success-rate over a test-task set |
| 42 | Interface (CLI/UI) + runnable demo |
| 43–44 | Docs + diagram + demo; ship v1.0 |

## License

MIT
