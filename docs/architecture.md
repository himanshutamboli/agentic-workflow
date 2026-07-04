# Architecture — agentic-workflow

An **AIOps incident-triage agent**: it ingests an incident, gathers signals through tools,
forms a hypothesis, and recommends remediation — bounded by guardrails, observable end to end,
and measured by an eval. This document is the design rationale; the [README](../README.md) is
the quickstart.

## The problem

On-call triage is a tight, repetitive loop: pull recent deploys, check error rates and latency,
grep logs, correlate onset with a change, hypothesize, and act (usually a rollback). It is a
textbook **planner/executor loop over tools** — but only useful in production if it is *bounded*
(no runaway loops or cost, no unapproved rollbacks) and *evaluated* (does it reach the right
call?). This repo builds that agent as real software, not a prompt.

## System diagram

```
                     ┌─────────────────────────── Agent.run(incident) ───────────────────────────┐
                     │                                                                            │
   Incident ─────────▶  loop (≤ max_steps):                                                       │
                     │     Planner.next_action(AgentState, ToolRegistry) ── Action                │
                     │            │                                                                │
                     │            ├─ "tool"  ─▶ guardrails ─▶ ToolRegistry.get(tool).run(**args)   │
                     │            │              (cost cap · HITL approval · retries)   │          │
                     │            │                                              Observation ──┐    │
                     │            │            AgentState.observations/steps ◀────────────────┘    │
                     │            └─ "finish" ─▶ TriageResult (hypothesis, action, confidence)     │
                     │                                                                            │
                     │     every step → Tracer.span(...)  ──────────────▶  (llm-observatory)      │
                     └────────────────────────────────────────────────────────────────────────────┘

   Planners:  HeuristicPlanner (default, rule-based)  ·  ClaudePlanner (LLM)  ·  ScriptedPlanner (tests)
   Tools:     get_error_rate · get_recent_deploys · get_service_metrics · search_logs · lookup_runbook
              · rollback_deploy (destructive → HITL-gated)   [over a deterministic MockOps backend]
```

## Components

| Module | Responsibility |
|---|---|
| `domain.py` | Core types: `Incident`, `Observation`, `TriageResult`, `Action`, `Step`, `AgentState` (the loop's memory). |
| `tools.py` | `Tool` protocol + `ToolRegistry`; `FunctionTool` adapts any callable. `specs()` is the planner's menu. |
| `tools_builtin.py` | The concrete triage tools bound to a `MockOps` backend (read tools + the `rollback_deploy` action). |
| `mock_ops.py` | Deterministic ops environment (deploys, error rates, metrics, logs, runbooks) seeded with coherent scenarios. |
| `planner.py` | `Planner` protocol → `Action`. `HeuristicPlanner` (default), `ClaudePlanner` (LLM), `ScriptedPlanner` (tests). |
| `agent.py` | The planner/executor loop; the executor **owns the guardrails** so no planner can escape them. |
| `guardrails.py` | `Guardrails` (step budget, retries, cost cap) + `Approver` gate for destructive tools. |
| `tracing.py` | Pluggable `Tracer` (one trace/incident, spans per step). `NullTracer` default; shape matches `llm-observatory`. |
| `observed.py` | Wires the real `llm-observatory` `Tracer(DBWriter)` in (lazy, optional dep) — the flagship cross-link. |
| `evaluation.py` | Labeled `Scenario`s + `run_eval` → **task-success-rate** and **false-rollback rate**. |
| `cli.py` | `triage` (reasoning transcript + verdict) and `eval` subcommands. |
| `logging_config.py` | Structured logger setup shared across the package. |

## The planner/executor loop

Each step the agent asks the planner for the next `Action` given the current `AgentState`
(incident + all prior observations). A `"tool"` action is executed and its `Observation`
appended to state; a `"finish"` action returns the `TriageResult`. The state accumulation is
what makes it an *agent* rather than a script — a planner reads what it has already learned to
decide what to look at next.

Three planners implement one protocol:
- **`HeuristicPlanner`** (CI-safe default) — deterministic rule-based triage: error rate →
  deploys → logs → runbook → conclude. Rolls back the most-recent deploy (≤60m) when the error
  rate is elevated, else escalates. No network, fully reproducible.
- **`ClaudePlanner`** — Claude (`claude-opus-4-8`) picks the next tool from the registry menu
  given the incident + observations, returning a JSON action. Lazy `anthropic` import.
- **`ScriptedPlanner`** — a fixed action sequence for tests.

## Guardrails (why the executor, not the planner, owns them)

A planner — especially an LLM — cannot be trusted to bound itself. So the **executor** enforces
every limit around the planner call:

- **Step budget** — the loop can't run forever; exhaustion escalates.
- **Retries** — a tool that throws is retried (`max_retries`); a persistent failure becomes an
  `Observation` (`"tool failed after N attempts"`), so triage degrades instead of crashing.
- **Cost cap** — each action has an estimated cost; the loop escalates before cumulative spend
  exceeds `max_cost`.
- **Human-in-the-loop** — a `protected` (destructive) tool like `rollback_deploy` runs only if
  the `Approver` agrees. `AutoApprover` is the CI-safe default; `CallbackApprover` wires a real
  prompt; `DenyAll` forces escalation. This is the difference between an agent that *suggests* a
  rollback and one that *performs* one.

## Observability — the flagship cross-link

The agent emits one **trace** per incident and one **span** per step (planner decision + tool
call) through a pluggable `Tracer`. The default `NullTracer` is a no-op (CI needs no backend),
but the hook is deliberately shaped to match
[`llm-observatory`](https://github.com/himanshutamboli/llm-observatory)'s `Tracer`, so the real
observability backend plugs in **unchanged** (`observed.py`). Every triage run then becomes a
persisted, inspectable trace in the observatory dashboard — the observability flagship watching
the agent flagship, with no hard dependency between the repos.

## Evaluation methodology

"The agent runs" is not "the agent is right." `evaluation.py` scores the agent against labeled
`Scenario`s on whether it reaches the **correct call** (roll back the right deploy, or escalate):

- **Task-success-rate** — the headline: fraction of scenarios triaged correctly.
- **False-rollback rate** — the asymmetric, costly failure: rolling back an *innocent* deploy.

The rule-based planner scores **83% (5/6)** with **1 false rollback**. The single miss is
deliberate: the `billing` scenario pairs a fresh-but-innocent deploy with a database-driven
outage. The heuristic sees "elevated + recent deploy" and rolls back the wrong thing — it can't
read the logs to separate correlation from cause. That gap is the concrete, measured argument
for the log-reading `ClaudePlanner`, and it proves the eval measures capability rather than
rubber-stamping the agent.

## Key design decisions

1. **Everything behind a protocol with a deterministic default.** `Planner`, `Tool`, `Approver`,
   `Tracer` — each has a CI-safe, offline default and an optional real/LLM drop-in. The whole
   system runs and is tested with zero external dependencies; production swaps implementations,
   not call sites.
2. **The executor owns the guardrails.** Bounds live where they can't be bypassed, not in the
   planner's discretion.
3. **Recommend vs. act is a guardrail decision.** The agent triages and recommends; executing a
   destructive action is a separate, approved step. Safe by default.
4. **No cross-repo hard dependency for the observability link.** Duck-typed tracer shape +
   lazy import keeps CI dependency-free while making the integration real (verified end-to-end).
5. **An honest eval with a built-in miss.** A 100% score proves nothing; the seeded trap makes
   the metric meaningful and motivates the next capability.

## Limitations & future work

- The `HeuristicPlanner` can't reason over log *content*; the `billing` miss is the direct
  consequence. Closing it is the `ClaudePlanner`'s job (needs an API key; untested in CI).
- `MockOps` is a deterministic stand-in for real deploy/metrics/log APIs — the tool boundary is
  designed so real adapters drop in without touching the agent.
- Cost is modeled per-action rather than from real token usage; wiring `ClaudePlanner` token
  counts into the cost cap and into trace spans is a natural next step.
- Alerting/auto-remediation policies (when is autonomous rollback ever allowed?) are out of
  scope for v1.0 and left to the HITL gate.
