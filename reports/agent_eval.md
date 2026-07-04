# Agent evaluation — triage task-success-rate

- **Task-success-rate:** 83% (5/6)
- **False-rollback rate:** 1/6

| Scenario | Expected | Got | ✓ | Note |
|---|---|---|:-:|---|
| checkout | rollback | rollback | ✅ | fresh bad deploy correlates with the error spike |
| api-gateway | rollback | rollback | ✅ | fresh deploy tightened a route regex |
| search | escalate | escalate | ✅ | elevated but the only deploy is stale — nothing to roll back |
| auth | escalate | escalate | ✅ | high latency but normal error rate — not a rollback |
| billing | escalate | rollback | ❌ | TRAP: recent deploy is innocent; logs point at the database |
| ghost | escalate | escalate | ✅ | healthy service — no signal to act on |
