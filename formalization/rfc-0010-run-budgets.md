# RFC 0010 — Run Budgets: caps with a defined meaning and a checkable report

| | |
|---|---|
| **Status** | **DRAFT** — not accepted; syntax, codes and meaning may change before acceptance |
| **Target language version** | TVL 1.6 (conservative extension of 1.5) |
| **Tracking** | to be linked when a pull request exists |
| **Builds on** | existing `exploration.budgets` (legacy, deprecated); `tvl-check-operational`; `tvl-compose` budget narrowing |
| **Companion** | `formalization/tvl-formal-semantics.md` §1.5 (semantic layers), new §15 (run budgets); `docs/reference/language.md` ("Legacy Implementation Hints") |
| **Conformance** | `conformance/cases/budget/*.yml` (§5), a run-report check beside the runtime case registry |

Existing-text handles are repository paths at `origin/main` commit `674d9aa2a4340115600e837ac28d8538d2b57867`.
Number 0010 is a proposal; the number is confirmed in review.

## 1. Motivation

A module can already say "at most 64 trials, 50 US dollars, one hour": `exploration.budgets` has `max_trials`,
`max_spend_usd` and `max_wallclock_s` (`spec/grammar/tvl.schema.json`). But `exploration` is marked
`deprecated: true` and described as "legacy, non-semantic implementation hints for a runtime", and the reference
adds "their operational meaning and enforcement belong to the runtime executing the search; they are not part of
TVL conformance". So the one limit a user most needs to rely on, that a run will not cost more or take longer than
the number they wrote, is the one the language declines to mean anything.

That has three concrete costs:

- The words are ambiguous. "Maximum wall-clock duration in seconds allowed for the exploration run" can be read
  as the whole run or as a limit on each trial or each example. A tool can read the field and apply it to the wrong
  thing, and no one can say it is wrong.
- Failure is silent. `docs/reference/language.md` says `max_spend_usd: 0` "means no paid spending is allowed" and
  that a runtime "should refuse every trial whose cost is positive or unknown ... This is guidance for executing
  runtimes, not a TVL conformance requirement." If the runtime does otherwise, nothing is breached on paper.
- A user cannot tell, from a finished run, which cap stopped it, or whether it stopped within the cap.

The guide says that a TVL field such as an exploration budget does not establish a sample-efficiency guarantee.
That stays true. This RFC does not promise that a run finds anything within its budget; it promises that the run
**stays within** the limits it was given, and defines what the run reports so that anyone can check.

## 2. Design

### 2.1 Syntax

A new optional top-level block, `run_budget`, outside the deprecated `exploration` block:

```yaml
tvl_version: "1.6"
run_budget:
  max_trials: 64
  max_spend_usd: 50.0
  max_wallclock_s: 3600
```

At least one of the three keys is present (`minProperties: 1`); each present key is a cap. Types and ranges are
those of `exploration.budgets`: `max_trials` integer at least 1, `max_spend_usd` number at least 0, `max_wallclock_s`
integer at least 1.

Why a new block and not a change inside `exploration`: the legacy block is declared non-semantic as a whole, and
search strategy, sampling, parallelism and convergence stay hints. A budget is different in kind. It is a
requirement on the run, as a chance constraint is a requirement on a candidate. Giving it its own block lets 1.5
modules keep their meaning (§3).

### 2.2 Definitions

A **run** is one execution of a search against a module, from its first admitted operation to its terminal state.
A **trial** is the evaluation of one candidate configuration on the tuning evidence (all its examples, all its repeated
evaluations), counted from the moment the runtime admits it.

**`max_trials` = N.** At no time are more than N trials admitted. A trial that fails or is cancelled still counts. A
default or incumbent configuration that the runtime evaluates as part of the run counts. An evaluation of the
declared holdout for the gate (RFC 0008, if accepted) is a measurement for the gate, not a trial, and does not
count here (it counts toward spend and wall-clock below).

**`max_spend_usd` = S.** The run's **spend** at time `t` is the metered cost, in US dollars, of every billable
call the runtime has made on behalf of the run by `t`: model calls of the agent, evaluator or judge calls, tool
calls with a price, retries, calls of failed or cancelled trials, and gate evaluations the run performs. A call in
flight is charged at the upper bound the runtime holds for it. The cap means: **the spend at the run's terminal
state is at most S**, and so it is at every earlier time. Equality is allowed.

**`max_wallclock_s` = W.** The run's elapsed time is the time from its start to its terminal state on a monotonic
clock, in seconds. The cap means: **the elapsed time at the terminal state is at most W**. It bounds the whole run. It
is never a per-trial, per-example or per-call timeout; a runtime that wants one must use its own setting.

### 2.3 What "stop within the cap" means: admission, not noticing

A cap is kept by **refusing to start work that might break it**, not by noticing afterward. A runtime that
declares a cap MUST, before admitting each trial or call, hold an upper bound on what it can still add to the
capped quantity and admit it only if the capped quantity so far plus that bound is within the cap:

- trials: `admitted + 1 ≤ N`;
- spend: `spend_so_far + reserve(trial) ≤ S`, where `reserve` is an upper bound on the trial's spend the runtime
  can justify (for instance output-token limit times the price of the model). If the runtime has no finite upper
  bound, the cost is **unknown** and the trial is not admitted. This is the rule the existing text already gives for
  `max_spend_usd: 0`, applied to every positive cap. A call whose price is unknown, for example a model with no price
  in the runtime's table, is unknown cost;
- wall-clock: `elapsed + max_duration(trial) + F ≤ W`, where `F` is the runtime's stated bound on finalization (writing the report, releasing resources, `finalization_bound_s`) and `max_duration` is an upper bound the runtime can
  justify, including any waiting the operation does (queueing, backoff, rate-limit sleeps); if none exists the runtime must be able to cancel the trial at the deadline and must do so, and the run
  must reach its terminal state by `W`.

An **overrun** is any case where the quantity at the terminal state exceeds its cap. **An overrun is a defect of the
runtime, never an acceptable outcome of the module.** A run that overran is non-conforming however useful its result.

Admission alone does not bound the whole run's time: a run that admits one operation of bound 1 at `t=0` under `W=10` and then sits idle until `t=11` satisfied every admission test and still overran. So the runtime must also **not idle**: it MUST enter its terminal state within `F` after its last admitted operation ends (or after the cap's deadline, whichever is first), and any waiting it needs is part of an admitted operation's `max_duration`, not time between operations. The report carries `F` so this is checkable (`budget_finalization_exceeded`).

A run can stop before a cap is exactly reached, because the next trial would not fit under the cap. That is a
normal stop, with the reason below.

### 2.4 What the run reports

A runtime that declares support for run budgets MUST emit a **run report** for every run that ends, including runs
that end by error or cancellation. It is a new document with its own closed schema, `spec/grammar/tvl-run-report.schema.json`:

```yaml
report_version: 1
module_id: corp.support.bot
started_at: "2026-11-01T09:00:00Z"
ended_at:   "2026-11-01T09:41:12Z"
stop_reason: max_spend_usd
caps: {max_trials: 64, max_spend_usd: "50.00", max_wallclock_s: 3600}
usage:
  trials_admitted: 37
  trials_completed: 36
  spend_usd: "49.62"
  wallclock_s: "2472"
caps_reached: [max_spend_usd]
unpriced_calls: 0
finalization_bound_s: "5"
trials:
  - {index: 1, admitted_at: "2026-11-01T09:00:03Z", ended_at: "2026-11-01T09:01:10Z", spend_usd: "1.31", status: completed,
     evaluation: {role: tuning, dataset: support-tickets/tuning-v3}}
  # ... one entry per admitted trial
```

| Field | Meaning |
|---|---|
| `stop_reason` | one of `max_trials`, `max_spend_usd`, `max_wallclock_s` (a declared cap ended the run), `search_exhausted` (nothing left to try), `converged`, `cancelled`, `error` |
| `caps` | the caps the run was given, echoed, so the report can be read alone |
| `usage` | trials admitted and completed, spend and wall-clock at the terminal state |
| `caps_reached` | every cap that no further admission could have gone under, in the order `max_trials`, `max_spend_usd`, `max_wallclock_s`; `stop_reason` is the first of them when a cap ended the run |
| `finalization_bound_s` | the runtime's stated upper bound on the time from its last operation ending to its terminal state; required when `max_wallclock_s` is declared |
| `unpriced_calls` | calls of unknown cost the run made; must be 0 when `max_spend_usd` is declared |
| `trials` | one entry per admitted trial: index, times, spend, status, and optionally the evidence role (RFC 0008) |

Amounts of money and seconds are decimal strings, compared exactly as rational numbers, as other exact
quantities in the existing runtime reports are.

A cap that stops a run is a **normal terminal state**, not an error. Trials finished before the stop remain valid
evidence for the search. The stop is not a `Promote` and not a `Reject`; whether anything is promoted is decided by the gate,
as today.

### 2.5 Checks and diagnostics

New reference function and CLI behaviour: `check_run_report(module, report)`, exposed as a case kind in the runtime
conformance registry and as `tvl-check-run <module> <report>` (name provisional, §7).

| Code | Severity | When |
|---|---|---|
| `budget_trials_exceeded` | error | `trials_admitted` > `max_trials` |
| `budget_spend_exceeded` | error | `spend_usd` > `max_spend_usd` |
| `budget_wallclock_exceeded` | error | `wallclock_s` > `max_wallclock_s` |
| `budget_unpriced_spend` | error | `max_spend_usd` declared and `unpriced_calls` > 0 |
| `budget_stop_reason_inconsistent` | error | `stop_reason` names a cap the module does not declare; or `max_trials` with `trials_admitted` ≠ N; or, **for a cap-based stop only** (`stop_reason` one of the three cap names), a stop reason not in `caps_reached`. For `search_exhausted`, `converged`, `cancelled` and `error`, `caps_reached` may be empty or hold any caps; no membership is required |
| `budget_usage_inconsistent` | error | `usage` differs from the sums over `trials` (`trials_admitted` = number of entries, `spend_usd` ≥ sum of trial spends, since gate evaluations are not trials) |
| `budget_finalization_exceeded` | error | `max_wallclock_s` declared and `ended_at` minus the latest trial `ended_at` exceeds `finalization_bound_s` (idle time before the terminal state, §2.3) |
| `budget_cap_invalid` | error | cap out of range (the `tvl-check-operational` rule, now also for `run_budget`) |
| `budget_declared_twice` | warning | both `run_budget` and `exploration.budgets` declare a cap with different values; `run_budget` governs |
| `budget_cap_removed` | error (`tvl-compose`) | an overlay removes a cap the base declares |
| `construct_version_required` / `declared_version_below_constructs` | error | `run_budget` without `tvl_version`, or below `"1.6"` |

`tvl.validation.skip_budget_checks` (schema: "skip validation of exploration budget constraints") continues to skip
only the well-formedness check of `budget_cap_invalid`. It never excuses an overrun in a report.

### 2.6 The legacy block

`exploration.budgets` keeps its 1.5 meaning: valid, shape-checked, non-semantic. If a module has both, `run_budget`
governs. This RFC adds no meaning to the legacy block, and recommends that new modules use `run_budget`.

### 2.7 Overlays

`tvl-compose` narrowing, now for `run_budget`: a cap may not increase; removing a cap present in the base is
`budget_cap_removed` (today removal in the legacy block is "not checked here"). Adding a cap an overlay's base lacks is
always allowed.

### 2.8 Grammar diff

`spec/grammar/tvl.schema.json`, new optional root property `run_budget` (the root stays closed):

```diff
+    "run_budget": {
+      "type": "object",
+      "additionalProperties": false,
+      "minProperties": 1,
+      "description": "Caps the run must stay within. Defined in RFC 0010; unlike exploration.budgets this block is semantic.",
+      "properties": {
+        "max_trials": { "type": "integer", "minimum": 1 },
+        "max_spend_usd": { "type": "number", "minimum": 0 },
+        "max_wallclock_s": { "type": "integer", "minimum": 1 }
+      }
+    },
```

New file `spec/grammar/tvl-run-report.schema.json` (closed; abridged):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://tvl-lang.org/schemas/tvl-run-report.schema.json",
  "title": "TVL Run Report",
  "type": "object",
  "additionalProperties": false,
  "required": ["report_version", "module_id", "started_at", "ended_at", "stop_reason", "caps", "usage", "caps_reached", "unpriced_calls", "trials"],
  "properties": {
    "report_version": { "const": 1 },
    "module_id": { "type": "string" },
    "started_at": { "type": "string", "format": "date-time" },
    "ended_at": { "type": "string", "format": "date-time" },
    "stop_reason": { "enum": ["max_trials", "max_spend_usd", "max_wallclock_s", "search_exhausted", "converged", "cancelled", "error"] },
    "caps": { "type": "object", "additionalProperties": false,
      "properties": { "max_trials": { "type": "integer", "minimum": 1 },
                      "max_spend_usd": { "$ref": "#/$defs/decimal" },
                      "max_wallclock_s": { "type": "integer", "minimum": 1 } } },
    "usage": { "type": "object", "additionalProperties": false,
      "required": ["trials_admitted", "trials_completed", "spend_usd", "wallclock_s"],
      "properties": { "trials_admitted": { "type": "integer", "minimum": 0 },
                      "trials_completed": { "type": "integer", "minimum": 0 },
                      "spend_usd": { "$ref": "#/$defs/decimal" },
                      "wallclock_s": { "$ref": "#/$defs/decimal" } } },
    "caps_reached": { "type": "array", "items": { "enum": ["max_trials", "max_spend_usd", "max_wallclock_s"] }, "uniqueItems": true },
    "unpriced_calls": { "type": "integer", "minimum": 0 },
    "finalization_bound_s": { "$ref": "#/$defs/decimal" },
    "trials": { "type": "array", "items": { "$ref": "#/$defs/trial" } }
  },
  "$defs": {
    "decimal": { "type": "string", "pattern": "^(0|[1-9][0-9]*)(\\.[0-9]+)?$" },
    "trial": { "type": "object", "additionalProperties": false,
      "required": ["index", "admitted_at", "spend_usd", "status"],
      "properties": { "index": { "type": "integer", "minimum": 1 },
                      "admitted_at": { "type": "string", "format": "date-time" },
                      "ended_at": { "type": "string", "format": "date-time" },
                      "spend_usd": { "$ref": "#/$defs/decimal" },
                      "status": { "enum": ["completed", "failed", "cancelled"] },
                      "evaluation": { "type": "object", "additionalProperties": false,
                        "required": ["role", "dataset"],
                        "properties": { "role": { "enum": ["tuning", "holdout"] }, "dataset": { "type": "string" } } } } }
  }
}
```

`tvl.ebnf`: `run_budget = rec(["max_trials": integer], ["max_spend_usd": number], ["max_wallclock_s": integer])`
with at least one key present.

## 3. Compatibility

A conservative extension. A 1.5 module has no `run_budget`, so nothing changes for it: `exploration.budgets` is still
shape-checked and still not enforced by the language. A 1.5 reader refuses `run_budget` as an unknown root key. The
run report is a new document; no existing tool reads it. Runtimes that do not declare run-budget support keep
today's behaviour and are not required to emit reports; this RFC changes what a runtime that **claims** the
support must do.

## 4. Semantics and proofs

New formal-semantics section (provisionally §15, "Run budgets"):

**Definition 15.1 (Run, trial, usage).** A run is a finite sequence of admissions `a_1..a_m` with admission times
`τ_1 ≤ .. ≤ τ_m`, each carrying `spend(a_k) ≥ 0` (the amount charged to it, in rational dollars), a start and a
terminal state at time `τ_end`. `Trials(R) = m`, `Spend(R, t) = Σ_{k: τ_k ≤ t} spend(a_k)` (plus gate
evaluations), `Elapsed(R) = τ_end − τ_0`.

**Definition 15.2 (Within budget).** For `B = {N?, S?, W?}`, a run `R` is within `B` iff `Trials(R) ≤ N`,
`Spend(R, τ_end) ≤ S` and `Elapsed(R) ≤ W` for each declared cap.

**Definition 15.3 (Admission rule and termination premise).** An admission policy keeps `B` iff it admits `a_{m+1}` only if
`Spend(R, now) + reserve(a_{m+1}) ≤ S`, `Trials(R) + 1 ≤ N` and `Elapsed(R, now) + maxdur(a_{m+1}) + F ≤ W`, where
`reserve ≥ spend`, `maxdur ≥ duration` of the admitted operation (waiting included) and `F ≥` the time the run takes to finalize, and a missing bound means not admissible.
**(T) No idle:** `τ_end ≤ max_k(τ_k + duration(a_k)) + F`; between operations the run waits only inside an admitted operation.

**Proposition 15.1 (Admission and no-idle imply within budget).** If every admission obeys Definition 15.3, premise (T) holds and the bounds
are true upper bounds, then `R` is within `B`. Trials and spend: by induction on admissions, since an admitted
operation never exceeds the bounds used at its admission. Time: `τ_end ≤ max_k(τ_k + duration(a_k)) + F ≤ max_k(τ_k + maxdur(a_k)) + F ≤ τ_0 + W`, the last step by the admission test. Without (T) the time claim is false (the idle-run counterexample of §2.3).
**Corollary 15.2.** An overrun implies a violated premise: a missing upper bound that was treated as finite, a
bound that was not an upper bound, or idle time before the terminal state. That is the sense in which an overrun is a runtime defect.

**Proposition 15.3 (Report check is decidable and exact).** For a module and a report, `within budget` as read
from the report is computed with exact rationals in time linear in the number of trials.

TVL cannot prove that a runtime keeps Definition 15.3; the language-level result is the check on reports. Whether
a report is truthful is an audit question, like the truthfulness of any evidence bundle, and is outside this
RFC. The Lean proofs do not cover this section, and the RFC states that instead of claiming a mechanized result.

## 5. Conformance

Run-report cases use the existing case envelope in `conformance/cases/runtime/` style: inline `module`, inline
`report`, `expected` diagnostics.

| Case | Input | Expected |
|---|---|---|
| `budget/within-all-caps.yml` | report under all three caps | no diagnostic |
| `budget/spend-equal-cap.yml` | `spend_usd` equals the cap | no diagnostic (equality allowed) |
| `budget/spend-over.yml` | `spend_usd` above the cap | `budget_spend_exceeded` |
| `budget/trials-over.yml`, `budget/wallclock-over.yml` | usage above the cap | `budget_trials_exceeded`, `budget_wallclock_exceeded` |
| `budget/spend-zero-unpriced.yml` | `max_spend_usd: 0`, `unpriced_calls: 1` | `budget_unpriced_spend` |
| `budget/stop-reason-undeclared.yml` | `stop_reason: max_spend_usd`, no such cap declared | `budget_stop_reason_inconsistent` |
| `budget/stop-before-cap.yml` | stop reason `max_spend_usd`, spend below cap (next trial would not fit) | no diagnostic |
| `budget/usage-mismatch.yml` | `trials_admitted` differs from entries | `budget_usage_inconsistent` |
| `budget/decimal-exactness.yml` | `"0.1" + "0.2"` against cap `"0.3"` | no diagnostic (exact rationals) |
| `budget/legacy-ignored.yml` | both blocks, different values | `budget_declared_twice`; `run_budget` governs |
| `compose/budget-cap-removed.yml`, `compose/budget-cap-raised.yml` | overlay removes or raises a cap | `budget_cap_removed`; narrowing error |
| `budget/stop-reason-converged-empty-caps.yml` | `stop_reason: converged`, `caps_reached: []` | no diagnostic |
| `budget/idle-before-terminal.yml` | `W=10`, last trial ended at 1, `ended_at` at 11, `finalization_bound_s: "1"` | `budget_finalization_exceeded` |
| `budget/wallclock-is-not-per-trial.yml` | one trial longer than a tenth of W, run within W | no diagnostic |

For runtimes (not part of the language registry, but published with it): a **scenario suite** of runs with a
scripted evaluator whose per-call cost and duration are fixed, so a harness can run a runtime against a cap and
feed the produced report to the check. Passing the report check shows a runtime's report is consistent with its
caps; the scenario suite is how a runtime shows it also keeps them against a known load. This suite is deferred
(§7).

## 6. Alternatives considered

1. **Restore meaning in place (remove `deprecated` from `exploration.budgets`).** It would give meaning to a block
   whose other fields stay hints, so a reader could not tell which fields bind. A separate block keeps "hint" and
   "promise" apart.
2. **A run-plan document outside the module.** The module declares what the user needs to rely on (the limit); a
   separate document could still hold how to search. Rejected for budgets: a limit that is not in the module cannot be
   narrowed by an overlay or checked against a report that names the module.
3. **Soft caps (stop when the cap is noticed).** Cheaper for runtimes, but then the number the user wrote is
   an estimate, and an overrun is not a defect. The cap must be a promise.
4. **Only a report check, no admission rule.** The report would show an overrun after it happened. The admission
   rule makes the check a consequence of how a conforming runtime behaves, and gives implementers the missing
   rule for unknown cost.
5. **Floats for money in the report.** `0.1 + 0.2` is not `0.3`; exact decimal strings avoid disputes at the cap.

## 7. Open questions

1. Name and form of the checker: a new CLI `tvl-check-run`, a mode of `tvl-check-operational`, or only a library
   function and case kind.
2. Should `max_spend_usd` accept a decimal string in the module too, for exactness? Today it is a number.
3. Should gate evaluation on the holdout be charged to the run's budget (this draft says yes) or have a separate cap?
4. Should a run report carry the optional `ranking` record (method, normalisation, weights as used) that RFC 0009
   mentions, or leave it to profiles?
5. Parallel trials: the admission rule reserves spend for every in-flight trial, so parallelism reduces how much
   can be started. Is there a case for allowing optimistic admission with a stated, bounded overshoot? This draft
   says no: that is a soft cap.
6. The scenario suite for runtimes: in this repository, or published separately?
