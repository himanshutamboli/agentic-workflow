# agentic-workflow 🤖

[![CI](https://github.com/himanshutamboli/agentic-workflow/actions/workflows/ci.yml/badge.svg)](https://github.com/himanshutamboli/agentic-workflow/actions/workflows/ci.yml)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Ruff](https://img.shields.io/badge/lint-ruff-orange.svg)](https://github.com/astral-sh/ruff)
[![status](https://img.shields.io/badge/status-building-blue.svg)](#roadmap)

> An **AIOps incident-triage** agent: it ingests an incident, gathers signals through tools,
> forms a hypothesis, and recommends remediation — bounded by guardrails, measured by an eval,
> and **instrumented by [`llm-observatory`](https://github.com/himanshutamboli/llm-observatory)**
> so every run is a traceable, inspectable record.

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

📐 **Design rationale, component map, and eval methodology:** [`docs/architecture.md`](docs/architecture.md).

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
- **`tracing.py` + `observed.py`** — a pluggable `Tracer`: the agent emits one trace per
  incident and one span per planner decision + tool call. `NullTracer` is the no-op default;
  the hook is shaped so
  [`llm-observatory`](https://github.com/himanshutamboli/llm-observatory)'s `Tracer` plugs in
  unchanged (`observed.py`) — **the observability flagship watches the agent flagship**.
- **`evaluation.py`** — labeled triage `Scenario`s scored on whether the agent reaches the
  *correct call*. Headline **task-success-rate** + **false-rollback rate**; see below.
- **`cli.py`** — the interface an on-call engineer uses: `agentic-workflow triage` prints the
  agent's reasoning transcript + verdict; `agentic-workflow eval` runs the scenario set.
- **`tools_builtin.py` + `mock_ops.py`** — the concrete triage tools (recent deploys, error
  rate, metrics, log search, runbook lookup, and a side-effecting `rollback_deploy` action)
  over a deterministic mock ops backend seeded with a coherent incident scenario.

```bash
uv sync --dev
uv run agentic-workflow triage --scenario checkout   # triage one incident (transcript + verdict)
uv run agentic-workflow eval                          # task-success-rate over labeled scenarios
uv run pytest
```

```text
$ agentic-workflow triage --scenario checkout
🔎 Triaging INC-checkout (incident_triage)

  1. plan: call get_error_rate({'service': 'checkout'})
     └─ get_error_rate(...) → error rate 8.2% (baseline 0.5%) — ELEVATED
  2. plan: call get_recent_deploys({'service': 'checkout'})
     └─ get_recent_deploys(...) → 2 recent deploy(s)
  3. plan: call search_logs({'service': 'checkout', 'pattern': 'ERROR'})
     └─ search_logs(...) → 3 matching log line(s)
  4. plan: call lookup_runbook({'symptom': 'elevated 5xx after deploy'})
     └─ lookup_runbook(...) → runbook: elevated 5xx after deploy
  5. plan: finish → roll back checkout@a1b2c3
────────────────────────────────────────────────────────────
✅ ACTION  (confidence 75%)
  hypothesis: recent deploy checkout@a1b2c3 (20m ago) correlates with the elevated error rate
  recommend : roll back checkout@a1b2c3
────────────────────────────────────────────────────────────
```

## Evaluation

Does triage reach the *correct call* on labeled incidents? (`uv run python -m agentic_workflow.evaluation`)

**Task-success-rate: 83% (5/6) · False-rollback rate: 1/6** — rule-based `HeuristicPlanner`.

| Scenario | Expected | Got | ✓ |
|---|---|---|:-:|
| checkout / api-gateway | rollback | rollback | ✅ |
| search (stale deploy) / auth (latency only) / ghost | escalate | escalate | ✅ |
| billing | escalate | **rollback** | ❌ |

The one miss is the honest one: a fresh but *innocent* `billing` deploy coincides with a
database-driven incident, so the rule-based planner rolls back the wrong thing. It can't read
the logs to tell correlation from cause — exactly the gap the log-reading `ClaudePlanner`
closes. That's why the eval exists.

## Roadmap

| Day | Deliverable |
|---|---|
| 36 ✅ | Architecture: workflow chosen (AIOps triage), agent skeleton + tool interface |
| 37 ✅ | Real tools: deploys, error rate, metrics, log search, runbook, rollback action |
| 38 ✅ | Stateful orchestration loop + HeuristicPlanner (real reasoning) + ClaudePlanner |
| 39 ✅ | Guardrails: retries, cost cap, step budget, human-in-the-loop approval |
| 40 ✅ | **Instrumented with `llm-observatory`** — every run is a persisted trace (plan/tool spans) |
| 41 ✅ | Agent eval: task-success-rate (83%) + false-rollback rate over labeled scenarios |
| 42 ✅ | CLI (`triage` transcript + verdict, `eval`) + runnable demo |
| 43 ✅ | Docs: `docs/architecture.md` (design rationale + component map + eval methodology) |
| 44 | Final polish; ship v1.0 |

## License

MIT
