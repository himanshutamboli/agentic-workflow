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
                                    guardrails (Day 39): max steps, retries, cost cap, HITL
```

- **`domain.py`** — `Incident`, `Observation`, `TriageResult`.
- **`tools.py`** — `Tool` protocol + `ToolRegistry`; `FunctionTool` adapts any callable. The
  registry exposes tool *specs* (name + description) as the planner's menu.
- **`planner.py`** — `Planner` protocol + `Action` (a tool call or `finish`). A deterministic
  `ScriptedPlanner` drives the skeleton and tests; an LLM planner arrives with the loop (Day 38).
- **`agent.py`** — the planner/executor loop: plan → execute → observe → repeat, bounded by a
  step budget (escalates to on-call if exhausted).

```bash
uv sync --dev
uv run python -m agentic_workflow.agent   # scripted triage demo
uv run pytest
```

## Roadmap

| Day | Deliverable |
|---|---|
| 36 ✅ | Architecture: workflow chosen (AIOps triage), agent skeleton + tool interface |
| 37 | Real tools (deploys, metrics, logs, runbooks, actions) |
| 38 | Orchestration loop with state + an LLM planner |
| 39 | Guardrails: retries, timeouts, cost caps, human-in-the-loop |
| 40 | **Instrument the agent with `llm-observatory`** (every run traced + scored) |
| 41 | Agent eval: task-success-rate over a test-task set |
| 42 | Interface (CLI/UI) + runnable demo |
| 43–44 | Docs + diagram + demo; ship v1.0 |

## License

MIT
