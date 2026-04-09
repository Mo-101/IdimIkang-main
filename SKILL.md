## Skill: Idim Ikang Master Architect Skill ##

## Purpose

This skill enables the Master Architect AI to audit, harden, build, and validate the Idim Ikang capital extraction engine.
It is designed for Idim Ikang development and operational work only.
It orchestrates specialized sub-agents to:
review system structure
verify signal doctrine and gate behavior
validate outcome truth
confirm execution flow
audit schemas and migrations
monitor service health
expand strategy safely
enforce mathematical correctness
The end goal is to move Idim Ikang toward a state that is:
truthful
deterministic
stable
execution-ready
build-ready
---

## Scope

### In Scope

`scanner.py`
`scoring.py`
`config.py`
`auto_executor.py`
`outcome_tracker.py`
`api.py` and dashboard stats endpoints
state machine / machine-state logic
migrations affecting Idim Ikang
PM2 runtime processes for Idim Ikang
signal truth ladder
market data routing
paper/live execution validation
strategy shadow deployment

### Out of Scope

MoStar symbolic platform work not directly affecting Idim Ikang runtime
Ibibio voice/audio systems
unrelated Neo4j ontology work
FlameBorn, AfroTrack, and other non-Idim domains
frontend work unrelated to Idim Ikang stats, controls, or execution visibility
---

## Operating Doctrine

Idim Ikang must satisfy these five conditions before it can be considered stable:
Signal truth — a signal must mean what the system says it means.
Outcome truth — a win/loss/partial must be mathematically defensible.
Execution truth — live trades must be distinguishable from simulated trades.
State truth — open, closed, expired, and partial states must be coherent.
Math truth — sizing, R-multiples, expectancy, and edge calculations must be correct
---

## Workflow

1. Initial Audit
Spawn all relevant sub-agents to perform a baseline review of the Idim Ikang repo, services, database, and runtime state.
2. Prioritize Findings
Classify findings into:
Critical — blocks safe trading, truthful data, or further progress
Warning — should be fixed before production confidence
Info — optional improvement or cleanup
3. Fix Critical Issues
Implement code changes, migrations, or config adjustments required to restore:
truthful outcomes
correct routing
safe execution
valid schema
stable services
mathematical correctness
4. Re-Audit Affected Areas
Run only the affected sub-agents again after each fix.
5. Repeat
Continue the cycle of:
audit
prioritize
fix
re-audit
until all Critical issues are removed and Warning issues are either fixed or explicitly accepted.
6. Build Phase
After stability is restored:
add new gates
add machine-state monitoring
add truth-ladder fields and reporting
add new strategies
add shadow-mode validation
add better telemetry and risk controls
7. Final Verification
Run a complete audit pass and produce one of:
`BUILD_READY`
`NOT_READY`

---

## Severity Rules

### Critical

Use Critical when the issue causes any of the following:
false signal generation
false win/loss settlement
wrong market routing
bad SL/TP logic
invalid position sizing
impossible trade-state math
schema drift that corrupts truth
stale or crashed core daemons
inability to distinguish simulated from live results

### Warning

Use Warning when:
engine still runs, but confidence is impaired
logging is incomplete
stats are ambiguous
gates are soft where they should be hard
thresholds are inconsistent
live execution exists but is not fully reconciled
strategy expansion is premature

### Info

Use Info when:
issue is cosmetic
cleanup only
optional refactor
future enhancement
documentation-only gap
---

## Sub-Agent Definitions

### 1. Structure Reviewer

Role: Examine Idim Ikang project layout, service boundaries, and file organization.
Input: Path to project root.
Output:

```json
{
  "missing_directories": [],
  "orphaned_files": [],
  "circular_imports": [],
  "recommended_restructure": {}
}

2. File Integrity Checker
Role: Validate required Idim Ikang files for existence, readability, and expected presence.
Input: List of expected files.
Output:
```json
{
  "missing_files": [],
  "corrupt_files": [],
  "permission_issues": []
}
```

---

1. Mechanism Validator
Role: Verify signal-scoring logic, regime classification, gate doctrine, cooldowns, and Q-functional behavior.
Input: Relevant source files.
Output:

```json
{
  "doctrine_violations": [],
  "parameter_drift": {},
  "determinism_check": "PASS"
}
```

---

1. Integration Flow Analyzer
Role: Trace data flow across scanner, executor, tracker, API, and dashboard.
Input: Source code of all Idim Ikang services.
Output:

```json
{
  "broken_links": [],
  "latency_bottlenecks": [],
  "missing_error_handlers": []
}
```

---

1. Database Schema Auditor
Role: Compare actual database schema against expected Idim Ikang schema.
Input: Database connection string and expected schema.
Output:

```json
{
  "missing_tables": [],
  "missing_indexes": [],
  "type_mismatches": [],
  "constraint_violations": []
}
```

---

1. Market Data & Outcome Truth Auditor
Role: Verify that outcome settlement is using correct market data and correct trade-resolution logic.
Input: Outcome tracker, signal rows, logs, market routing config.
Output:

```json
{
  "routing_errors": [],
  "outcome_math_errors": [],
  "truth_level": "SIMULATED",
  "inconsistent_rows": []
}
```

---

1. Execution Stub Tester
Role: Simulate or inspect exchange execution behavior in paper mode or live-ready mode.
Input: Execution stub file, executor config, test credentials or paper-mode settings.
Output:

```json
{
  "order_placement_success": false,
  "sl_tp_validation": "PASS",
  "execution_linkage": "PASS",
  "error_logs": []
}
```

---

1. State Machine Auditor
Role: Verify signal state, machine state, and lifecycle integrity.
Input: State machine logic, database rows, logs.
Output:

```json
{
  "current_state": "FLAT_LEARNING",
  "integrity_score": 0.0,
  "edge_score": 0.0,
  "transition_history": []
}
```

---

1. Service Health Auditor
Role: Verify the health, freshness, and synchronization of all Idim Ikang daemons and APIs.
Input: PM2 service list, logs, health endpoints, scheduler intervals.
Output:

```json
{
  "stale_services": [],
  "restart_loops": [],
  "missing_env": [],
  "health_status": "DEGRADED"
}
```

---

1. Strategy Expansion Auditor
Role: Decide whether the current engine is ready for new strategies or shadow deployments.
Input: Signals, outcomes, regime coverage, opportunity flow, performance stats.
Output:

```json
{
  "ready_for_new_strategy": false,
  "coverage_gap": {},
  "recommended_next_strategy": "ranging_mean_reversion",
  "deployment_mode": "shadow"
}
```

---
Math Skills
11. Risk Math Verifier
Role: Verify stop distance, position sizing, risk-per-trade, and leverage math.
Checks:
position size derived from risk and stop distance
invalid zero or negative size
stop-distance normalization
leverage cap logic
live bracket consistency
Input: `scanner.py`, `auto_executor.py`, config, sample signals.
Output:

```json
{
  "risk_per_trade_check": "PASS",
  "position_size_errors": [],
  "sl_tp_distance_errors": [],
  "leverage_math_errors": []
}
```

---

1. Outcome Math Consistency Auditor
Role: Verify that trade outcomes are mathematically consistent.
Checks:
LOSS implies stop truly reached
WIN implies TP truly reached
PARTIAL_WIN aligns with TP1 logic
`r_multiple` matches stored entry/stop/exit logic
`adverse_excursion` and outcome are coherent
Input: `signals` table, tracker logic, historical rows.
Output:

```json
{
  "inconsistent_losses": [],
  "inconsistent_wins": [],
  "partial_logic_errors": [],
  "r_multiple_errors": []
}
```

---

1. Performance Statistics Auditor
Role: Recompute strategy performance directly from raw rows and compare with dashboard/API output.
Checks:
total wins/losses/partials
simulated vs live counts
win rate
profit factor
expectancy
drawdown
regime-specific performance
score-bucket performance
Input: `signals` table, API stats endpoint, dashboard payload.
Output:

```json
{
  "api_stat_mismatches": [],
  "dashboard_stat_mismatches": [],
  "recomputed_expectancy_r": 0.0,
  "recomputed_pf": 0.0,
  "stat_truth_level": "SIMULATED"
}
```

---

1. Regime & Gate Mathematics Auditor
Role: Verify that the gating stack matches the actual doctrinal math.
Checks:
G0 minimum score
G1 local regime side validity
G5 BTC regime side validity
G6 higher-timeframe structure bias
G_sq squeeze gate enforcement
soft vs hard gate behavior
boolean signal admission logic
Input: Scanner logic, gate code, logs.
Output:

```json
{
  "implemented_gates": [],
  "missing_gates": [],
  "gate_bypass_paths": [],
  "admission_formula_verified": "PASS"
}
```

---

1. Edge Estimation Auditor
Role: Quantify whether the current engine has positive, negative, or indeterminate edge.
Checks:
smoothed win probability
average win R
average loss R
expectancy
score-bucket edge
regime-specific edge
post-fix cohort edge
confidence of sample
Input: Post-fix resolved trades, regime labels, outcome rows.
Output:

```json
{
  "edge_state": "NEGATIVE",
  "expectancy_r": 0.0,
  "profit_factor": 0.0,
  "sample_size": 0,
  "confidence": "LOW"
}
```

---

1. Machine-State Math Auditor
Role: Compute a formal machine-state vector for Idim Ikang.
Checks:
Infrastructure health `H`
Outcome integrity `I`
Opportunity flow `O`
Edge estimate `E`
Macro risk pressure `R`
Active exposure `A`
Input: Logs, DB rows, service heartbeats, market dispersion inputs.
Output:

```json
{
  "state": "FLAT_LEARNING",
  "H": 0.0,
  "I": 0.0,
  "O": 0.0,
  "E": 0.0,
  "R": 0.0,
  "A": 0
}
```

---

Build-Phase Features Allowed
After all Critical issues are resolved, the Master Architect may build:
hard or conditional gate changes
truth-ladder schema and reporting
split dashboard stats (`simulated` vs `live`)
machine-state monitors
risk-pressure sizing modifiers
shadow-mode strategy modules
improved telemetry
zero-downtime migrations
execution reconciliation
strategy ranking and coverage analysis
---

Output Format
For each cycle, output the following:

```json
{
  "cycle": 1,
  "reports": {
    "structure_reviewer": {},
    "file_integrity": {},
    "mechanism_validator": {},
    "integration_flow": {},
    "database_schema": {},
    "outcome_truth": {},
    "execution_stub": {},
    "state_machine": {},
    "service_health": {},
    "strategy_expansion": {},
    "risk_math": {},
    "outcome_math": {},
    "performance_stats": {},
    "gate_math": {},
    "edge_estimation": {},
    "machine_state_math": {}
  },
  "synthesis": {
    "critical": [],
    "warning": [],
    "info": []
  },
  "actions_taken": [],
  "next_step": "re-audit affected services"
}
```

---

Example Prompts
"Audit the Idim Ikang scanner and confirm whether the five gates are actually enforced at runtime."
"Validate the database schema against the truth ladder doctrine."
"Recompute wins, losses, partials, profit factor, and expectancy directly from the raw signals rows."
"Audit outcome math and identify impossible LOSS rows."
"Verify the execution stub attaches SL and TP correctly using the scanner-calculated position size."
"Determine whether the current engine is ready for a new shadow strategy."
"Run a full build-readiness audit for Idim Ikang and return BUILD_READY or NOT_READY."
---

Build Ready Rule
Only return `BUILD_READY` when all of the following are true:
no Critical issues remain
service health is stable
schema is aligned with doctrine
outcome truth is mathematically coherent
simulated vs live truth is distinguishable
gate doctrine is enforced as intended
machine-state integrity is acceptable
performance reporting is internally consistent
no unresolved execution truth blockers remain
Otherwise return `NOT_READY`
---

Related Customizations
Zero-downtime migration skill
Truth ladder migration generator
Strategy shadow deployment skill
Outcome math validation skill
Execution reconciliation skill
Machine-state monitor skill
Risk sizing optimizer skill
Performance verification skill
---

Final Framing
This skill is for Idim Ikang development, verification, and operational hardening.
Its mission is:
make the engine truthful
make the engine deterministic
make the engine mathematically coherent
make the engine safe to extend
and only then make it more aggressive
