# Requirements, Monitors and Responses (TVL 1.3)

!!! note "TVL 1.3"
    This guide describes TVL 1.3, accepted on 2026-10-21. Every snippet below was checked with the reference tools
    in this repository (`tvl-validate`, `tvl-lint`, `tvl-compose`, `tvl-compile-runtime`, `tvl-ci-gate`).

TVL up to 1.2 says what an agent configuration is allowed to be and how a candidate earns promotion.
TVL 1.3 adds the other half: **what the agent must keep doing once it is running, and what should happen
when it stops doing it.**

TVL stays a *specification* language. You write requirements, monitors and responses.
`tvl-validate` and `tvl-lint` check the document, and `tvl-compile-runtime` turns it into two
compiled files for a platform. A platform evaluates runtime evidence and carries out responses;
`tvl-ci-gate` additionally evaluates fully resolved promotion counts (section 3).
The platform supports only the constructs it can honour: a
declaration the platform cannot honour should be refused at registration, never silently ignored
(`runtime_unsupported_capability`, `response_action_unsupported`). This guide therefore explains what each
declaration *means* and how to check that it is well formed, not how a platform computes anything.

## 1. The three blocks

A TVL 1.3 module may carry three new optional blocks next to the 1.2 ones.

| Block | It says | Typical fields | It never has |
|---|---|---|---|
| `requirements` | what must hold for one *unit* of behaviour (a trace or an invocation) | `kind`, `unit`, `violation`, `max_rate` | where the evidence comes from, schedules, statistics, actions |
| `monitors` | which evidence checks one requirement, how often, and with what statistics | `requirement`, `phase`, `evidence`, `window`, `decision`, `episode` | its own predicate, actions |
| `responses` | what happens when a monitor reports an event | `rules` of `trigger` and `do` | statistics, predicates |

The blocks point at each other by name:

```text
requirement  <--  monitor  <--  response rule
 (what must       (which evidence,   (when this event happens
  hold)            which statistics)  on that monitor, do this)
```

A monitor names exactly one requirement. A response rule names exactly one monitor and one event that
monitor can emit. Two requirement kinds (`recovery_time`, `evidence_liveness`) are *obligations over a
monitor*: they point at a monitor with `of`.

Requirement, monitor and response names are plain identifiers (`[A-Za-z_][A-Za-z0-9_]*`, no dots). They live
in their own three namespaces, and a runtime name equal to a tvar, cvar, policy or composite name is rejected
(`runtime_name_collision`).

!!! pitfall "Write the version as a string"
    A module that uses any of these blocks must declare `tvl_version: "1.3"` **with quotes**. An unquoted
    `1.3` is a YAML number, and `tvl-validate` rejects it with `declared_version_below_constructs`.
    A missing version is `runtime_version_required`.

## 2. A first requirement

The smallest useful 1.3 module checks one latency promise on the production traces your platform already
records: *at most 5% of traces may take longer than 2 seconds.*

The top half of the file is the ordinary [TVL module header](../reference/language.md) you already know; everything from `requirements:` down is new in 1.3.
The later examples in this guide leave the header out and say so.

<!-- snippet: first-module kind=module -->
```yaml title="support-latency.tvl.yml"
tvl:
  module: acme.support_latency
tvl_version: "1.3"
environment:
  snapshot_id: "2026-10-16T00:00:00Z"
evaluation_set:
  dataset: support_eval_v4
tvars:
  - name: model
    type: enum[str]
    domain: [m_small, m_large]
objectives:
  - name: quality
    direction: maximize
promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  min_effect:
    quality: 0.02

requirements:
  - name: fast_enough
    kind: rate_bound
    unit: trace
    violation: { metric: wall_clock_latency_ms, exceeds: 2000 }
    max_rate: 0.05
  - name: fast_enough_evidence
    kind: evidence_liveness
    unit: window
    of: fast_enough_prod
    max_stale_windows: 4

monitors:
  - name: fast_enough_prod
    requirement: fast_enough
    phase: runtime
    profile: backend_v1
    evidence: { source: backend_trace_metadata }
    decision: { method: clopper_pearson_exact_v1 }
  - name: fast_enough_evidence_check
    requirement: fast_enough_evidence
    phase: runtime
    evidence: { source: windows }
    decision: { method: exact_count_v1 }
```

Read it from the bottom up:

* **The monitor `fast_enough_prod`** checks the requirement `fast_enough` in production (`phase: runtime`).
  `profile: backend_v1` is a frozen profile that mirrors the hosting platform's built-in latency requirement:
  it fixes the evidence source (`backend_trace_metadata`: the status and timestamps the platform already
  records for each trace), the decision method, the sampling and the units. Because everything is frozen, all
  statistical fields can be left out and take their defaults (see [section 6](#6-windows-and-confidence-in-plain-words)).
* **The requirement `fast_enough`** is a `rate_bound`: at most `max_rate` (5%) of units may violate.
  A trace *violates* when `wall_clock_latency_ms` is strictly greater than `exceeds` (2000 ms).
* **The second requirement, `fast_enough_evidence`**, is an `evidence_liveness` obligation on the first
  monitor. It says the monitoring itself must keep working: if the last five windows (`max_stale_windows` plus one)
  all produce no usable evidence, the monitor is `STALE`. Without it, a monitor that silently stops receiving traces looks
  like a quiet, healthy system. TVL warns about this (`runtime_liveness_missing`). The warning
  remains visible but does not fail validation: `tvl-validate` exits 0 when there are no errors,
  including when a primary monitor has no liveness requirement.

```bash
tvl-validate support-latency.tvl.yml
# Schema + lint checks passed.
```

Delete the `fast_enough_evidence` requirement and its monitor and the same command prints:

```text
[runtime_liveness_missing] monitors.0.name: Primary runtime monitor 'fast_enough_prod' is not covered by an evidence_liveness requirement
```

and exits 2.

## 3. One requirement, checked before release and in production

The same requirement can gate a release on your evaluation set *and* watch production, with two
monitors and no copy of the predicate. The module below adds a promotion monitor, a recovery promise and a
response ladder to the latency requirement.

<!-- snippet: support-bot kind=module -->
```yaml title="support-bot.tvl.yml"
tvl:
  module: acme.support_bot
tvl_version: "1.3"
environment:
  snapshot_id: "2026-10-16T00:00:00Z"
evaluation_set:
  dataset: support_eval_v4
tvars:
  - name: model
    type: enum[str]
    domain: [m_small, m_large]
objectives:
  - name: quality
    direction: maximize
promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  min_effect:
    quality: 0.02

requirements:
  - name: fast_enough
    kind: rate_bound
    unit: trace
    violation: { metric: wall_clock_latency_ms, exceeds: 2000 }
    max_rate: 0.05
  - name: fast_again_within_2_days
    kind: recovery_time
    unit: episode
    of: fast_enough_prod
    within_hours: 48
  - name: fast_enough_evidence
    kind: evidence_liveness
    unit: window
    of: fast_enough_prod
    max_stale_windows: 4

monitors:
  - name: fast_enough_gate            # before release, on the evaluation set
    requirement: fast_enough
    phase: promotion
    evidence: { source: evaluation_set }
    decision:
      method: clopper_pearson_rational_v2
      confidence: 0.95
      false_alarm_budget: 0.05
  - name: fast_enough_prod            # after release, on live traffic
    requirement: fast_enough
    phase: runtime
    evidence: { source: customer_side, deployment_environment: production }
    window: { tumbling_hours: 6, grace_minutes: 30 }
    decision:
      method: clopper_pearson_rational_v2
      confidence: 0.95
      false_alarm_budget: 0.05
      horizon_days: 30
      min_samples: 200
      max_unresolved_fraction: 0.05
    episode: { closure_windows: 2, closure_max_age_hours: 24 }
  - name: fast_again_check
    requirement: fast_again_within_2_days
    phase: runtime
    evidence: { source: episodes }
    decision: { method: exact_count_v1 }
  - name: fast_enough_evidence_check
    requirement: fast_enough_evidence
    phase: runtime
    evidence: { source: windows }
    decision: { method: exact_count_v1 }

responses:
  - name: latency_ladder
    rules:
      - id: warn_on_open
        trigger: { monitor: fast_enough_prod, event: episode_opened }
        do: notify
        severity: warning
      - id: next_step_on_open
        trigger: { monitor: fast_enough_prod, event: episode_opened }
        do: open_next_step
      - id: roll_back_after_6h
        trigger: { monitor: fast_enough_prod, event: episode_open_for, hours: 6 }
        do: rollback
        target: last_certified
        approval: standing
      - id: suspend_if_overdue
        trigger: { monitor: fast_again_check, event: recovery_overdue }
        do: suspend
        approval: human
        fallback: static_unavailable
      - id: tell_when_resolved
        trigger: { monitor: fast_enough_prod, event: episode_resolved }
        do: notify
        severity: info
```

In words:

1. **Before release** the monitor `fast_enough_gate` (`phase: promotion`) looks at the candidate's results
   on the evaluation set. It joins the promotion gate you already have: a `BREACHED` result becomes `Reject`,
   an `UNKNOWN` result becomes `NoDecision`, a `MET` result passes. Without promotion monitors the gate is
   exactly the 1.2 gate.
2. **In production** the monitor `fast_enough_prod` evaluates one 6-hour window at a time (section 6).
   A `BREACHED` window opens an *episode*; two clean windows in a row close it (section 7).
3. **If the breach lasts**, the response ladder escalates: warn and issue a next step at once; after the
   episode has been open for 6 hours, ask for a rollback to the last certified configuration under a standing
   grant; if the recovery promise (back to normal within 48 hours) is overdue, ask for the agent to be suspended,
   which always needs a human; when the episode resolves, tell people.

A promotion `MET` and a runtime `MET` are separate facts about separate populations. A candidate that
passes the gate can still breach in production, and a runtime `BREACHED` does not undo a promotion.

### Running the gate

`tvl-ci-gate` takes the module, the incumbent's measurement bundle and the candidate's. Promotion monitors read their counts from
`monitor_outcomes.<monitor name>`: `n` resolved units, `k` of them violating (optional `u` unresolved,
`pl` unplaceable, `complete`). The evaluation harness produces these counts; TVL does not collect the events or run checkers.
The gate evaluates them only when `u = 0` and `pl = 0` (both default to zero). Otherwise that monitor
returns `UNKNOWN(engine_required)`, mapped to `NoDecision`, even if `k` is positive; an evaluator outside TVL is
needed to interpret partial evidence. Any `Reject` from another monitor or the legacy gate still wins.

<!-- snippet: cand-ok kind=yaml-plain -->
```yaml title="candidate-ok.yml"
bundle_id: candidate-ok
objective_values:
  quality: { mean: 0.86, std: 0.05, n: 200 }
monitor_outcomes:
  fast_enough_gate: { n: 500, k: 5 }
```

```bash
tvl-ci-gate support-bot.tvl.yml incumbent.yml candidate-ok.yml
```

Assuming the legacy gate passes and all other monitors pass:

| Candidate counts for `fast_enough_gate` | Result | Why |
|---|---|---|
| `n: 500, k: 5` (1.0% violating) | `Promote` (exit 0) | clearly under 5% |
| `n: 500, k: 60` (12% violating) | `Reject` (exit 2), reason "Promotion monitors breached: fast_enough_gate" | clearly over 5% |
| `n: 100, k: 8` (8% violating) | `NoDecision` (exit 2), reason "Promotion monitors inconclusive: fast_enough_gate" | too few units to tell |
| no `monitor_outcomes` entry | not promotion-ready (exit 2), issue `missing_monitor_counts` | missing evidence fails closed |

!!! info "NoDecision is not a failure of the candidate"
    8 violations in 100 traces is *neither* clearly good nor clearly bad at 95% confidence. The monitor says so
    (`NoDecision`) instead of guessing. Note that a 1.2 `chance_constraints` entry on the same counts would
    reject, because a 1.2 chance constraint passes only when its upper confidence bound is under the limit.
    Promotion monitors are opt-in, so adding them never changes a module that does not use them; if a chance constraint
    carries the same name as a promotion monitor or its requirement, the chance constraint's `Reject` still wins and `chance_constraint_shadowed` warns.

For a *zero-tolerance* promotion monitor, `monitor_outcomes` must say `complete: true`: only the harness
knows whether the evaluation set was run to the end, and counts alone never establish it. Without it a
clean `k: 0` result is `NoDecision`.

## 4. What MET, BREACHED and UNKNOWN mean

Every runtime verdict is one of three values.

| Verdict | Meaning |
|---|---|
| `MET` | the evidence in the window was strong enough to say the requirement holds, at the confidence you asked for |
| `BREACHED` | the evidence was strong enough to say the requirement is violated, within the false-alarm budget you set |
| `UNKNOWN(reason)` | the evidence could not support either statement |

**Absence of evidence is never `MET`.** An empty window, a window with too few units or a window whose units could not
be classified is `UNKNOWN`, never quietly fine. `UNKNOWN` always carries one reason from a closed list:

| Reason | Plain meaning | Fix |
|---|---|---|
| `insufficient` | fewer than `min_samples` units in the window (or none) | more traffic, a longer window, or a lower `min_samples` (not below what lets `MET` be reached) |
| `unresolved` | too large a fraction of units could not be classified (above `max_unresolved_fraction`) | repair the evidence (unfinished traces, checker errors) or raise the fraction |
| `unplaceable` | too many units had no start time, so they could not be placed in the window | fix the producer so every unit carries a start time |
| `inconclusive` | enough data, but the counts sit between "clearly fine" and "clearly violated" | wait for more windows; the middle band is normal |
| `late_evaluation` | the window was evaluated far too late (more than two window lengths after it closed plus grace) | a platform scheduling problem, not a spec problem |
| `sampling_biased` | with head sampling, a unit was kept *after* seeing how it turned out | sample before the outcome exists, or use the committed hash mode |
| `incomplete` | zero tolerance: the window could not be shown to be complete | see "zero tolerance" below |
| `revision_gap` | a profile revision interrupted the hosted latency window | check the profile's revision history |

Obligations (recovery and liveness) have their own states and reasons (section 7): `pending`, `cancelled`,
`lifecycle_unavailable`, `awaiting`.

The monitor's health (is evidence still flowing), the verdict of a window, the state of an episode, the state
of an obligation and the state of an action are reported **separately** and are never inferred from each other.

### Zero tolerance is stricter

A `zero_tolerance` requirement has no rate. One established violation makes the window `BREACHED`, however many
units there were. To say `MET`, the platform must be sure it saw *everything*: the evidence must be a census
(not a sample), no unit unresolved, and the report must attest that unit histories, producers, event order and
deadlines were all complete. An empty window, even a complete one, is `UNKNOWN(insufficient)`: an idle or
suspended agent has no traffic, and "no traffic" must not look like "no violations".

## 5. The pattern menu

A requirement's `violation` says what counts as a bad unit. There are seven predicates: two measure a number, five
describe event sequences.

| `violation` | Bad unit when... | Allowed under | Can a local guard stop it before it happens? |
|---|---|---|---|
| `metric` | a number is over a limit (`wall_clock_latency_ms`, `cost_usd`, `total_tokens`, `tool_calls`) | `rate_bound` | no |
| `checker` | a checker labels the unit with one of `label_in` | `rate_bound` | no (output is only checked) |
| `pattern: absence` | the event ever happens | `zero_tolerance`, `rate_bound` | yes |
| `pattern: bounded_existence` | the event happens more than `max_count` times | `zero_tolerance`, `rate_bound` | yes, at the (max_count+1)-th |
| `pattern: precedence` | `b` happens with no unused `a` before it | `zero_tolerance`, `rate_bound` | yes, by suppressing `b` |
| `pattern: bounded_response` | an `a` is not followed by a `b` within `within_ms` | `zero_tolerance`, `rate_bound` | no (a missing event cannot be blocked) |
| `pattern: protocol` | the unit's events drive a state machine into a rejecting state, or it ends in a non-accepting one | `zero_tolerance`, `rate_bound` | yes, on the rejecting event |

A **unit** is the thing you count. A `trace` is the end-to-end handling of one request, including all model calls,
tool calls and handoffs in contributing components. An `invocation` is one execution of the monitored agent itself;
a trace can contain several invocations. An individual tool or model call is an event within a unit, not a unit by itself
(RFC §6.2).

Use `rate_bound` when a few bad units are acceptable ("at most 1% of invocations"). Use `zero_tolerance` when
one is too many. `zero_tolerance` accepts only the five patterns (not a metric and not a checker), because a
rule with no tolerance needs a violation that is certain, not estimated. The sections below give one example
of each. The snippets are *fragments*: each is one entry of the `requirements:` list. They are checked by
placing them in a complete module with a matching monitor and liveness requirement.

### Numbers: `metric`

<!-- snippet: pat-metric kind=req -->
```yaml
# Fragment: one entry of `requirements:`
- name: short_answers_only
  kind: rate_bound
  unit: invocation
  violation: { metric: total_tokens, exceeds: 8000 }
  max_rate: 0.01
```

At most 1% of invocations may use more than 8000 tokens. A unit violates when the number is *strictly* greater
than `exceeds`. Metrics are a closed list: `wall_clock_latency_ms` and `total_tokens` and `tool_calls` take whole numbers,
`cost_usd` takes a decimal.

### Labels: `checker`, and `among`

<!-- snippet: pat-checker kind=req -->
```yaml
# Fragment: one entry of `requirements:`
- name: refuses_disallowed
  kind: rate_bound
  unit: invocation
  among:     { checker: traigent.refusal.v1, label_in: [must_refuse] }
  violation: { checker: traigent.refusal.v1, label_in: [complied] }
  max_rate: 0.01
```

Of the invocations that *should* be refused (`among`), at most 1% may be answered (`complied`). A checker is
a named classifier: the catalogue checker `traigent.refusal.v1` has exactly two labels, `must_refuse` and `complied`.
The `among` and `violation` positions ask separate questions; in each position the other label is a negative answer.
You can bind your own checker as `customer:<name>` (section 10). Checkers run on your side with your own model key;
a checker can never run against platform-recorded metadata (`runtime_content_on_backend_source`).

`among` narrows the population a requirement is about. A unit outside it is *excluded*: it is not counted at all.
If population membership is unknown, the unit is unresolved; an observed violation alone cannot establish membership.
`among` is allowed on `rate_bound` and `zero_tolerance` monitors outside the `backend_v1` profile.

### Never: `absence`

<!-- snippet: pat-absence kind=req -->
```yaml
# Fragment: one entry of `requirements:`
- name: never_write_sql
  kind: zero_tolerance
  unit: invocation
  violation:
    pattern: absence
    a: { event: tool_call, tool: warehouse.run_write_sql }
```

The agent never calls this tool. Selectors (`a`, `b`, `when`) name an event type and may narrow it with
`tool`, `status` and `ref` (table below). `{ event: tool_call }` with no `tool` matches every tool call.

### At most N: `bounded_existence`

<!-- snippet: pat-bounded kind=req -->
```yaml
# Fragment: one entry of `requirements:`
- name: at_most_three_failed_test_runs
  kind: zero_tolerance
  unit: invocation
  violation:
    pattern: bounded_existence
    a: { event: tool_result, tool: sandbox.run_tests, status: failed }
    max_count: 3
```

The fourth failed test result in one unit is the violation. `max_count: 0` is the same as `absence`.
This pattern counts over the whole unit; it takes no `correlate_by` field.

### Only after: `precedence`

<!-- snippet: pat-precedence kind=req -->
```yaml
# Fragment: one entry of `requirements:`
- name: charge_needs_authorization
  kind: zero_tolerance
  unit: invocation
  violation:
    pattern: precedence
    a: { event: authorization_granted, ref: payment_auth }
    b: { event: tool_call, tool: payments.charge }
    mode: single_use
    correlate_by: correlation_id
```

Every `b` (the charge) needs an earlier `a` (an authorization) it can use up. `mode: single_use` (the default) means
one authorization pays for one charge; `mode: reusable` lets one authorization cover several `b` events until an
`authorization_revoked` event with the same `ref` and correlation key invalidates it. Revocations affect only
`authorization_granted` events; a tool call used as `a` cannot be revoked. `correlate_by` says which key ties an `a` to a `b`: `unit`
(the whole unit, default), `correlation_id` or `tool_call_id`. An event missing the chosen key matches nothing;
a unit whose classification needs that match remains unresolved.

### Within a deadline: `bounded_response`

<!-- snippet: pat-response kind=req -->
```yaml
# Fragment: one entry of `requirements:`
- name: handoff_within_five_minutes
  kind: zero_tolerance
  unit: trace
  violation:
    pattern: bounded_response
    a: { event: tool_call, tool: support.flag_needs_human }
    b: { event: handoff }
    within_ms: 300000
    correlate_by: unit
```

Every `a` needs a matching `b` no later than `within_ms` milliseconds after it (exactly at the deadline still counts).
Matching is one-to-one within the chosen correlation key, and `b` must follow `a` in event order as well as
meet the time limit. A complete history without such a match violates. A platform that cannot establish what
happened must leave the unit unresolved; the evidence procedure belongs to its evaluator profile.

### An allowed sequence: `protocol`

<!-- snippet: pat-protocol kind=req -->
```yaml
# Fragment: one entry of `requirements:`
- name: authorize_then_reserve
  kind: zero_tolerance
  unit: trace
  violation:
    pattern: protocol
    alphabet:
      - { event: authorization_granted, ref: booking_auth }
      - { event: tool_call, tool: booking.reserve }
    states: [idle, authorized, done]
    start: idle
    transitions:
      - { from: idle, when: { event: authorization_granted, ref: booking_auth }, to: authorized }
      - { from: authorized, when: { event: tool_call, tool: booking.reserve }, to: done }
    accepting: [idle, authorized, done]
    rejecting: []
    unlisted: reject
```

A protocol is a small state machine over the events in `alphabet`. The unit is bad if the machine reaches a
`rejecting` state, or if the unit ends in a state that is not `accepting`. With `unlisted: reject` (the default)
any in-alphabet event with no transition from the current state is a violation: here, reserving before
authorizing, authorizing twice, or anything after `done`. With `unlisted: ignore` such events are skipped.
The machine must be deterministic: at most one transition per (state, alphabet entry), and no event may match two alphabet
entries (`runtime_protocol_nondeterministic`).

!!! pitfall "State names are YAML too"
    TVL loads YAML 1.1, where unquoted `yes`, `no`, `on`, `off`, `true` and `false` are booleans. A state called
    Both `tvl-lint` and `tvl-validate` explain that state identifiers must be strings and recommend quoting YAML yes/no.
    Pick state names like `idle` or `done`, or quote them. Run `tvl-validate` for the full schema check.

### Rates over events

`rate_bound` also takes an event pattern, which turns "never" into "rarely":

<!-- snippet: pat-rate-absence kind=req -->
```yaml
# Fragment: one entry of `requirements:`
- name: tool_failure_rate
  kind: rate_bound
  unit: trace
  violation: { pattern: absence, a: { event: tool_result, status: failed } }
  max_rate: 0.03
```

At most 3% of traces may contain a failed tool result.

### Events and selectors

Events come from a closed alphabet. A selector is `{ event, [tool], [status], [ref] }`:

The agent's instrumentation (its SDK, framework or own code) emits them. `ref` names a kind of authorization,
such as `payment_auth`, rather than one grant. Instrumentation uses `correlation_id` for one logical transaction
inside the unit, and `tool_call_id` for one tool call and its result. Neither is an author-selected tool name.

| Field | Allowed with event | Meaning |
|---|---|---|
| `event` | always | one of `unit_start`, `unit_end`, `tool_call`, `tool_result`, `model_call`, `handoff`, `error`, `authorization_granted`, `authorization_revoked` |
| `tool` | `tool_call`, `tool_result` | a function or qualified name such as `payments.charge`: letters, digits, `_`, dots, at most 128 characters. A list or a wildcard is rejected (`runtime_tool_not_code_identifier`). |
| `status` | `unit_end`, `tool_result` | `running`, `completed`, `failed` or `rejected` |
| `ref` | `authorization_granted`, `authorization_revoked` | a plain identifier naming which grant is meant |

`{ event: error }` matches every error. You cannot select an error class.

### Stateful patterns need `limits`

`precedence`, `bounded_response` and `protocol` remember things across events, so a `customer_side` monitor
that uses one must declare how much it may remember:

<!-- snippet: limits kind=monitorfrag -->
```yaml
# Fragment: the monitor entry for a stateful requirement
- name: charge_needs_authorization_prod
  requirement: charge_needs_authorization
  phase: runtime
  evidence: { source: customer_side, deployment_environment: production }
  window: { tumbling_hours: 24, grace_minutes: 60 }
  decision: { method: exact_count_v1 }
  episode: { closure_windows: 1, closure_max_age_hours: 48 }
  limits: { max_active_obligations: 64, max_tracked_correlations: 1024 }
```

If a unit overflows a limit it may be unresolved (`unres`), and any local guard uses its `on_check_error`
rule (section 8). `single_producer: true` is available on monitors with an event pattern and declares that
only one component emits the unit's events; a unit that contradicts the declaration is unresolved.

## 6. Windows and confidence in plain words

A runtime monitor does not judge a single unit; it judges a **window** of units.

* **Window.** `tumbling_hours` is the window length. Windows are back-to-back, never overlap, and line up with the UTC
  day, so the length must divide 24: 1, 2, 3, 4, 6, 8, 12 or 24 (under `backend_v1`: 1, 3, 6, 12, 24).
* **Grace.** `grace_minutes` is how long after a window ends the platform waits for late evidence before it decides the
  window. 0 to 360.

### The fields that decide a window

| Field | Where | What it means | Default |
|---|---|---|---|
| `max_rate` | requirement | the largest acceptable fraction of bad units, strictly between 0 and 1 | none |
| `confidence` | monitor `decision` | how sure the data must make you before you say `MET`: "if the true rate were exactly `max_rate`, seeing this few bad units would happen at most `1 - confidence` of the time" | none (`backend_v1`: 0.95; allowed 0.90, 0.95, 0.99) |
| `min_samples` | monitor `decision` | the fewest units a window needs before it can say anything | none (`backend_v1`: 200; zero tolerance and promotion: 1) |
| `false_alarm_budget` | monitor `decision` | the chance you accept of *one or more* false `BREACHED` alarms over the whole horizon, assuming the true rate is within `max_rate`. Above 0, at most 0.5 | none (`backend_v1`: 0.05) |
| `horizon_days` | monitor `decision` | the period the false-alarm budget is spread over (1 to 365) | none (`backend_v1`: 30) |
| `max_unresolved_fraction` | monitor `decision` | how many units may be unclassifiable before the window gives up (0 to 0.5) | none (`backend_v1`: 0.05) |
| `closure_windows` | monitor `episode` | how many clean windows in a row close an episode (1 to 24) | none (`backend_v1`: 2) |
| `closure_max_age_hours` | monitor `episode` | how fresh those clean windows must be when the episode closes (1 to 720) | none (`backend_v1`: 24) |

Outside `backend_v1` and the promotion and zero-tolerance cases there are **no defaults**: omit a statistical
field and you get `runtime_invalid_profile`, not a silent value.

A window is `BREACHED` when so many units were bad that it is very unlikely the true rate is within `max_rate`,
and `MET` when so few were bad that it is very unlikely the true rate is above it. In between it is
`UNKNOWN(inconclusive)`. The false-alarm budget is shared among all windows in the horizon: a 6-hour window with a 30-day horizon is one of 120,
so each window gets one hundred-and-twentieth of the budget. More windows per horizon (shorter windows or a longer horizon) therefore
make `BREACHED` slightly harder to reach in each window.

!!! example "Where the lines fall"
    For `max_rate: 0.05`, `confidence: 0.95`, `false_alarm_budget: 0.05`, `horizon_days: 30`, 6-hour windows and
    no unresolved or unplaceable units and timely admissible evidence. Each row assumes `min_samples` is at most
    that row's unit count; below `min_samples` the result is `UNKNOWN(insufficient)` instead:

    | Units in the window | `BREACHED` from this many bad units | `MET` up to this many bad units | In between |
    |---|---|---|---|
    | 100 | 15 | 1 | `UNKNOWN(inconclusive)` |
    | 200 | 23 | 4 | `UNKNOWN(inconclusive)` |
    | 500 | 44 | 16 | `UNKNOWN(inconclusive)` |
    | 1000 | 75 | 38 | `UNKNOWN(inconclusive)` |
    | 3000 | 192 | 130 | `UNKNOWN(inconclusive)` |

    More traffic narrows the middle band. `MET` needs a margin well below the 5% line: a window sitting right at 5% is never `MET`.
    The window length matters a little: at 200 units, 24-hour windows breach from 21 bad units and 1-hour windows from 25.

### How to choose

1. **`max_rate`: the promise.** Take it from the business need ("at most 5% slower than 2 seconds"). The smaller it
   is, the more traffic you need to *prove* it.
2. **`confidence`: leave it at 0.95** unless you have a reason. 0.99 needs about 50% more units to reach `MET`; 0.90 needs
   about a quarter fewer.
3. **`min_samples`: no smaller than what lets `MET` be reached.** If a window of exactly that many units can never be
   `MET`, even with zero bad units, no window of that size can close an episode (windows with more units still can).
   TVL checks this (`runtime_met_unreachable_at_min_samples`).
   The smallest sizes that pass the check:

    | `max_rate` | `confidence` 0.90 | `confidence` 0.95 | `confidence` 0.99 |
    |---|---|---|---|
    | 0.10 | 22 | 29 | 44 |
    | 0.05 | 45 | 59 | 90 |
    | 0.02 | 114 | 149 | 228 |
    | 0.01 | 230 | 299 | 459 |
    | 0.005 | 460 | 598 | 919 |
    | 0.001 | 2302 | 2995 | 4603 |

    Under `backend_v1` the default `min_samples` is 200, so a `max_rate` below about 1.5% at 0.95 only warns (the profile has to stay valid
    for requirements that already exist).
4. **Check your traffic.** A window needs at least `min_samples` units, or it is `UNKNOWN(insufficient)` forever.
   With 10% sampling, you need ten times as many eligible units. If traffic is thin, lengthen the window (24 hours) before
   weakening anything else.
5. **Window and grace.** Short windows react sooner but need more traffic per window. Grace should cover how late
   your evidence normally arrives.
6. **`false_alarm_budget` and `horizon_days`.** 0.05 over 30 days is a reasonable start: at most a 5% chance of any false
   page in a 30-day period while the agent is healthy (under the model's assumptions below). A smaller budget means fewer false pages and slower real ones.
7. **`max_unresolved_fraction`.** 0.05 is typical. It limits the fraction of units that cannot be classified.
   Missing or unresolved evidence must never strengthen a verdict; its treatment belongs to the evaluator profile.
8. **Episode closure.** `closure_max_age_hours` must leave room for the clean windows themselves:
   `closure_max_age_hours * 60 >= closure_windows * tumbling_hours * 60 + grace_minutes + 60`, otherwise
   `closure_unreachable`.

!!! tip "Do not retype the statistics"
    Outside `backend_v1` every primary monitor repeats the same seven or eight numbers. YAML anchors and aliases (`&name`, `*name`) work in TVL files,
    so one block can serve several monitors, here production and staging:

    <!-- snippet: anchors kind=body -->
    ```yaml
    # Fragment: add under the module header of section 2
    requirements:
      - name: fast_enough
        kind: rate_bound
        unit: trace
        violation: { metric: wall_clock_latency_ms, exceeds: 2000 }
        max_rate: 0.05
      - name: fast_enough_evidence
        kind: evidence_liveness
        unit: window
        of: fast_enough_prod
        max_stale_windows: 4
      - name: fast_enough_staging_evidence
        kind: evidence_liveness
        unit: window
        of: fast_enough_staging
        max_stale_windows: 4

    monitors:
      - name: fast_enough_prod
        requirement: fast_enough
        phase: runtime
        evidence: { source: customer_side, deployment_environment: production }
        window: &window { tumbling_hours: 6, grace_minutes: 30 }
        decision: &stats
          method: clopper_pearson_rational_v2
          confidence: 0.95
          false_alarm_budget: 0.05
          horizon_days: 30
          min_samples: 200
          max_unresolved_fraction: 0.05
        episode: &closing { closure_windows: 2, closure_max_age_hours: 24 }
      - name: fast_enough_staging
        requirement: fast_enough
        phase: runtime
        evidence: { source: customer_side, deployment_environment: staging }
        window: *window
        decision: *stats
        episode: *closing
      - name: fast_enough_evidence_check
        requirement: fast_enough_evidence
        phase: runtime
        evidence: { source: windows }
        decision: { method: exact_count_v1 }
      - name: fast_enough_staging_evidence_check
        requirement: fast_enough_staging_evidence
        phase: runtime
        evidence: { source: windows }
        decision: { method: exact_count_v1 }
    ```

### What the guarantee does and does not say

For `clopper_pearson_rational_v2`, under the model `iid_bernoulli_within_window_v1` (each window's bad units behave like
independent coin flips at a rate no higher than `max_rate` while it is healthy, sampling does not depend on how a unit
turned out, and classifications are sound):

* in each window the chance of a false `BREACHED` is at most the window's share of the budget;
* over the horizon the chance of *any* false `BREACHED` is at most `false_alarm_budget`;
* in each window the chance of a false `MET` is at most `1 - confidence` when the true rate is at least `max_rate`.

Not claimed: any bound on closing an episode wrongly; any guarantee at all for the float method
`clopper_pearson_exact_v1` (its verdicts are the hosting platform's floating-point computation, matched against test
vectors, not proved); guarantees when units differ a lot from each other; "sequential" guarantees for watching
continuously; that sampled checks prevent anything; or that a repair works.

### Choosing a method

| `decision.method` | Use it for |
|---|---|
| `clopper_pearson_rational_v2` | every `rate_bound` monitor except the frozen profile (exact arithmetic; the method the formal semantics reasons about) |
| `clopper_pearson_exact_v1` | only with `profile: backend_v1` (floating point, mirrors the platform's built-in latency requirement; no statistical guarantee is claimed) |
| `exact_count_v1` | `zero_tolerance`, `recovery_time` and `evidence_liveness` (counting, no statistics) |

### Sampling

A `customer_side` `rate_bound` monitor may look at a sample instead of every unit:

<!-- snippet: sampling kind=evidence -->
```yaml
# Fragment: the `evidence` of a customer_side rate_bound monitor
evidence:
  source: customer_side
  deployment_environment: production
  sampling: { mode: hash_bernoulli_committed_v1, rate: 0.25 }
```

* no `sampling`: every unit in scope is checked (a census);
* `head_sampled_declared`: the keep-or-drop choice is made when the unit starts and stamped on it. If a unit was kept
  *after* seeing its outcome, the window is `UNKNOWN(sampling_biased)`;
* `hash_bernoulli_committed_v1`: the keep-or-drop choice is committed before the window starts, cannot depend on how
  any unit turns out, and can be checked afterwards. How the choice is made and committed is up to the platform's
  evaluator; use this mode only where your platform supports it.

`zero_tolerance` monitors take no sampling (`runtime_zero_tolerance_incomplete`): a sampled window can never be complete, so `MET` would be
unreachable. `backend_trace_metadata` is always `unverified`: the platform's census of the traces it ingested.

### A faster alarm: burn monitors

A *burn monitor* is a second `rate_bound` monitor on the same requirement with its own short window and a `threshold_factor` b
(b > 1, with b times `max_rate` still below 1). It breaches when the rate is running at b times the allowed rate, so a severe
problem pages quickly while the main monitor stays calm and statistical.

<!-- snippet: burn kind=addmon -->
```yaml
# Fragment: an extra entry of `monitors:` for the requirement `fast_enough`
- name: fast_enough_burn
  requirement: fast_enough
  phase: runtime
  evidence: { source: customer_side, deployment_environment: production }
  window: { tumbling_hours: 1, grace_minutes: 15 }
  decision:
    method: clopper_pearson_rational_v2
    false_alarm_budget: 0.05
    horizon_days: 7
    min_samples: 200
    max_unresolved_fraction: 0.10
    threshold_factor: 5
```

A burn monitor has no episode and no `confidence`, and it can never say `MET`: a window that does not breach is
`UNKNOWN(inconclusive)`. It emits one event, `burn_breached`, on the first breached window of each run of breached windows.

## 7. Episodes, recovery and liveness

### Episodes

An **episode** is one stretch of trouble for one primary monitor:

* a `BREACHED` window **opens** it (`episode_opened`); further `BREACHED` windows **continue** it (`episode_continued`);
* it **resolves** (`episode_resolved`) after `closure_windows` clean (`MET`) windows in a row, all of them recent enough
  when the episode closes (`closure_max_age_hours`);
* it is **withdrawn** (`episode_withdrawn`) when the requirement is loosened or retired. Withdrawal is never the same as recovery.

How the platform tracks episodes over time, including when a monitor's parameters change mid-episode, is up to its
evaluator; TVL fixes what the events mean.

`episode_open_for` fires once, when an episode has stayed open for `hours` hours (set on the trigger).

### Recovery time

`recovery_time` turns "we will be back to normal soon" into a checkable promise:

<!-- snippet: recovery kind=addreq -->
```yaml
# Fragment: add to `requirements:` (and a monitor with `evidence: { source: episodes }` for it)
- name: fast_again_within_2_days
  kind: recovery_time
  unit: episode
  of: fast_enough_prod
  within_hours: 48
```

The clock is **window time**: the promise is kept when the closing clean window *ends* within `within_hours` of the
end of the window that opened the episode. The endpoints define the duration; scheduling can still affect whether
fresh enough windows are available to close the episode. The obligation is

| State | Plain meaning | Verdict shown |
|---|---|---|
| `RECOVERED` | closed in time | `MET` |
| `OVERDUE` | evidence establishes no closure by the deadline; missing evidence alone is not a breach | `BREACHED` |
| `PENDING` | not decided yet | `UNKNOWN(pending)` |
| `CANCELLED` | the episode was withdrawn before the promise was decided | `UNKNOWN(cancelled)` |
| not decidable | the evidence needed to decide is not available | `UNKNOWN(lifecycle_unavailable)` |

`RECOVERED`, `OVERDUE` and `CANCELLED` are final: once reached, the promise keeps that state. Events:
`recovery_recovered`, `recovery_overdue`, `recovery_cancelled`, one for reaching each state. The promise cannot be shorter
than the episode can close: `within_hours` must be at least `closure_windows * tumbling_hours` (`recovery_deadline_impossible`; equal is fine).
Window time makes the deadline reproducible, but closing an episode still needs the clean windows to be fresh when they are evaluated, so a
late evaluation can leave a promise `OVERDUE` even though the windows themselves were clean in time. The platform records that case
(`closure_blocked_by_lag`) and reports the wall-clock length of the episode beside the verdict, never instead of it.

### Evidence liveness

`evidence_liveness` watches the watcher: is usable evidence still arriving for a monitor's windows?
`max_stale_windows` is how many due windows in a row may go without usable evidence. A window decided from real data
counts as usable even when its verdict is `UNKNOWN(inconclusive)`: liveness is about evidence arriving, not about the
requirement being met. A window for which nothing arrived never counts. Exactly which other windows count is up to the
platform's evaluator.

| State | When | Verdict shown |
|---|---|---|
| `LIVE` | at least one of the last `max_stale_windows + 1` due windows had usable evidence | `MET` |
| `STALE` | none of them had usable evidence | `BREACHED` |
| not enough history yet | fewer than `max_stale_windows + 1` windows are due | `UNKNOWN(insufficient)` |
| waiting | neither `LIVE` nor `STALE` can be told yet | `UNKNOWN(awaiting)` |

Events: `stale` when the monitor becomes `STALE`, `live_again` when it is `LIVE` again afterwards.

### Which events does a monitor emit?

| Monitor role | Events a response rule can trigger on |
|---|---|
| primary `rate_bound` or `zero_tolerance` | `episode_opened`, `episode_continued`, `episode_open_for`, `episode_resolved`, `episode_withdrawn` |
| primary, `customer_side` | additionally `unit_violation` (a unit in the population established as violating a pattern fixed by a prefix) |
| burn | `burn_breached` |
| `recovery_time` obligation | `recovery_overdue`, `recovery_cancelled`, `recovery_recovered` |
| `evidence_liveness` obligation | `stale`, `live_again` |
| promotion | none (its verdict joins the gate) |

A rule that triggers on an event its monitor cannot emit is `runtime_ref_kind_mismatch`.

## 8. Responses and approvals

A response is a named list of rules. Each rule has an `id` (unique within its response), a `trigger` and one action, `do`.

<!-- snippet: rule kind=rules -->
```yaml
# Fragment: the rules of a response
- id: roll_back_after_6h
  trigger: { monitor: fast_enough_prod, event: episode_open_for, hours: 6 }
  do: rollback
  target: last_certified
  approval: standing
```

!!! pitfall "The key is `trigger`, not `on`"
    YAML 1.1 reads an unquoted `on:` key as the boolean `true`, so a rule written with `on:` fails the closed shape.
    The rule key is `trigger`, and the protocol transition key is `when`.

The action menu is sealed. Actions are ordered by how much they affect production; `record` (writing the event down) happens for every
event automatically and cannot be declared.

| Action | Asks for | Extra fields | Approval (default) |
|---|---|---|---|
| `notify` | an alert to be delivered, even after the episode has closed | optional `severity`: `info`, `warning`, `critical` (default `critical`) | `none` only |
| `open_next_step` | a recommended next step to be issued for the people or coding agent who maintain the agent | none | `none` only |
| `optimize` | an optimisation run within a bounded grant (cost ceiling, scope, expiry). The candidate still has to pass the promotion gate | optional `deploy`: `never` (default) or `if_promoted` (below) | `standing` or `human` (default `human`) |
| `rollback` | a return to an earlier certified configuration | **`target`**: `last_certified` or a 64-hex fingerprint | `standing` or `human` (default `human`) |
| `throttle` | a cap on how much traffic is admitted | **`rate_floor`**: a number strictly between 0 and 1 | `standing` or `human` (default `human`) |
| `degrade` | traffic routed to a fallback configuration | **`fallback`**: a 64-hex fingerprint of a certified configuration | `standing` or `human` (default `human`) |
| `suspend` | new requests refused (drained), answered with a fallback | **`fallback`**: `static_unavailable` or `route_to_human` | explicit `approval: human` required |
| `block_action` | the offending event suppressed before it takes effect | **`on_check_error`**: `block` or `allow` | `none` only |
| `halt_unit` | the unit stopped before it takes effect | **`on_check_error`**: `block` or `allow` | `none` only |

`rate_floor` is a fraction of the deployment's unthrottled admission rate: `0.25` caps admissions at a quarter
of that rate. A smaller value throttles harder; the smallest of several active throttles applies.

Fields not listed for an action are rejected (`runtime_invalid_ladder`). Two more rule fields apply to any action:
`repeat_after_hours` re-fires the rule while its scope is still active, and `max_repeats` bounds that. Any action except `notify` that repeats
**must** declare `max_repeats` (`response_rule_repeat_unbounded`).

### Who decides: approvals

* **`none`**: no approval is needed, which is not the same as no authority check. `notify` rests on its recorded event
  alone, which stays authority after the scope closes. `open_next_step` still needs its originating scope to be current
  (for an episode, still open) at the time of the effect; `none` does not waive that. The local guards (`block_action`,
  `halt_unit`) act on their own unit event.
* **`standing`**: a *standing grant* covers it. A grant is a signed authority record that lives **outside** TVL documents: it
  names the agent, the scope, the configurations it may target, an expiry at most 30 days away, a maximum number of
  uses and, for `optimize`, a cost limit. Each occurrence uses up the grant. The module cannot say who signs grants
  or check that one exists.
* **`human`**: a person approves each occurrence. For `suspend` this is per episode, always.

`suspend` is the one rung that is human-only and **latched**: once active, only a person's explicit `resume` releases it;
resolution or withdrawal of the episode makes `resume` *possible* but never performs it. A standing grant never authorizes `suspend`.
Installed `throttle` and `degrade` controls also need an authorized human `release`; scope closure leaves them in place.
`rollback`, `optimize`, `throttle` and `degrade` with `approval: none` are rejected (`response_irreversible_without_approval`).

**Fix and deploy.** `deploy: if_promoted` on an `optimize` rule says: if the optimisation finds a candidate that passes
the promotion gate, deploy it. The deploy is a second, separate effect. A person approves it on its own (approving the
optimisation does not approve the deploy), or a standing grant must name the deploy itself. At the moment of the deploy
the episode must still be open, the contract unchanged, and the candidate's promotion result `Promote`, which needs a
promotion monitor on the same requirement (without one the rule is rejected with
`response_deploy_without_promotion_monitor`). If anything that authorizes it is unreachable, the deploy holds. A
deploy never closes the episode: the episode closes only when production windows are healthy again. Only episode events
(`episode_opened`, `episode_continued`, `episode_open_for`) may trigger it, and an overlay may only turn
`if_promoted` into `never`.

A service-level action is meaningful only while the episode (or other scope) that caused it still needs intervention: if the episode closes first, the
queued action is cancelled. If the people or records that authorize an action cannot be reached, the rule **holds**: nothing new happens. `notify` is different:
it is delivered even after the scope has closed.

Remote service actions on `episode_resolved`, `episode_withdrawn`, `recovery_cancelled`, `recovery_recovered`,
`live_again` or `unit_violation` are rejected with `runtime_invalid_ladder`. Terminal events can still `notify`;
`unit_violation` can also trigger a local guard. `open_next_step` additionally needs an open episode to have an effect.

!!! info "Escalation events for `suspend`"
    `suspend` may only be triggered by an event that shows trouble has persisted: `episode_continued`, `episode_open_for` or
    `recovery_overdue`. `episode_opened` alone is not enough (`response_suspend_unconfirmed`).

### Local guards: `block_action` and `halt_unit`

A local guard acts inside your own process, before the effect, once a violation is established that no later event
can undo (a violation *fixed by a prefix* of the unit). It is available only when:

* the monitor is `customer_side` and its violation is `absence`, `bounded_existence`, `precedence` or `protocol`;
* the rule triggers on `unit_violation`.

Anything else is `response_guard_not_enforceable`. If the guard cannot decide at that moment (the population is unknown, a
checker errored, the evidence is not yet complete), the rule's **`on_check_error`** decides: `block` stops the action (fail
closed), `allow` lets it through and the unit is recorded as unresolved. There is no default, because it is a safety decision
you must make on purpose. A unit outside `among` is never blocked.

<!-- snippet: guard kind=body -->
```yaml
# Fragment: add under the module header of section 2
requirements:
  - name: never_write_sql
    kind: zero_tolerance
    unit: invocation
    violation:
      pattern: absence
      a: { event: tool_call, tool: warehouse.run_write_sql }
  - name: write_guard_evidence
    kind: evidence_liveness
    unit: window
    of: never_write_sql_prod
    max_stale_windows: 2

monitors:
  - name: never_write_sql_prod
    requirement: never_write_sql
    phase: runtime
    evidence: { source: customer_side, deployment_environment: production }
    window: { tumbling_hours: 24, grace_minutes: 60 }
    decision: { method: exact_count_v1 }
    episode: { closure_windows: 1, closure_max_age_hours: 48 }
  - name: write_guard_evidence_check
    requirement: write_guard_evidence
    phase: runtime
    evidence: { source: windows }
    decision: { method: exact_count_v1 }

responses:
  - name: write_guard
    rules:
      - id: block_write
        trigger: { monitor: never_write_sql_prod, event: unit_violation }
        do: block_action
        on_check_error: block
      - id: page
        trigger: { monitor: never_write_sql_prod, event: episode_opened }
        do: notify
        severity: critical
```

A checker violation is never blocked in-process in 1.3: checkers see output after the fact.

## 9. Organisation floors with packs

A platform team often wants rules every agent must meet. Put them in a separate **`tvl_pack`** document, not in each module. A pack has no
`tvl`, `environment`, `tvars` or `objectives`; it carries `pack`, `requirements`, `monitors` and (optionally) `responses`. Every pack
monitor says `applies_to: tenant_floor` and `phase: runtime`.

<!-- snippet: org-floors kind=pack -->
```yaml title="org-floors.pack.yml"
tvl_version: "1.3"
pack:
  module: acme.org_floors

requirements:
  - name: floor_fast_enough
    kind: rate_bound
    unit: trace
    violation: { metric: wall_clock_latency_ms, exceeds: 2000 }
    max_rate: 0.10
  - name: floor_no_recursive_delete
    kind: zero_tolerance
    unit: invocation
    violation: { pattern: absence, a: { event: tool_call, tool: shell.rm_recursive } }
  - name: floor_delete_evidence
    kind: evidence_liveness
    unit: window
    of: floor_no_recursive_delete_prod
    max_stale_windows: 2
  - name: floor_latency_evidence
    kind: evidence_liveness
    unit: window
    of: floor_fast_enough_prod
    max_stale_windows: 4

monitors:
  - name: floor_fast_enough_prod
    requirement: floor_fast_enough
    phase: runtime
    applies_to: tenant_floor
    evidence: { source: customer_side, deployment_environment: production }
    window: { tumbling_hours: 6, grace_minutes: 30 }
    decision:
      method: clopper_pearson_rational_v2
      confidence: 0.95
      false_alarm_budget: 0.05
      horizon_days: 30
      min_samples: 200
      max_unresolved_fraction: 0.05
    episode: { closure_windows: 2, closure_max_age_hours: 24 }
  - name: floor_no_recursive_delete_prod
    requirement: floor_no_recursive_delete
    phase: runtime
    applies_to: tenant_floor
    evidence: { source: customer_side, deployment_environment: production }
    window: { tumbling_hours: 24, grace_minutes: 60 }
    decision: { method: exact_count_v1 }
    episode: { closure_windows: 1, closure_max_age_hours: 48 }
  - name: floor_delete_evidence_check
    requirement: floor_delete_evidence
    phase: runtime
    applies_to: tenant_floor
    evidence: { source: windows }
    decision: { method: exact_count_v1 }
  - name: floor_latency_evidence_check
    requirement: floor_latency_evidence
    phase: runtime
    applies_to: tenant_floor
    evidence: { source: windows }
    decision: { method: exact_count_v1 }

responses:
  - name: floor_alerts
    rules:
      - id: block_delete
        trigger: { monitor: floor_no_recursive_delete_prod, event: unit_violation }
        do: block_action
        on_check_error: block
      - id: page_on_delete
        trigger: { monitor: floor_no_recursive_delete_prod, event: episode_opened }
        do: notify
        severity: critical
      - id: warn_floor_latency
        trigger: { monitor: floor_fast_enough_prod, event: episode_opened }
        do: notify
        severity: warning
```

Compose a module with the pack to see what an agent actually has to meet:

```bash
tvl-compose support-bot.tvl.yml --pack org-floors.pack.yml --validate -o composed.tvl.yml
# Composed: composed.tvl.yml
```

The rules of composition:

* **Floors can only be tightened.** A module monitor that checks "the same thing" as a floor monitor (same predicate, evidence source,
  environment and method) is *paired* with it. The module's numbers must be at least as strict: `max_rate` no higher, `confidence` no lower,
  `min_samples` no lower, `max_unresolved_fraction` no higher, `closure_windows` no lower, `closure_max_age_hours` no higher,
  `within_hours` no higher, `max_stale_windows` no higher. A weaker module fails with `requirement_weaker_than_floor`.
* **The schedule must be identical:** window length, grace, horizon and false-alarm budget (`evaluation_schedule_mismatch`).
* **Identity cannot change:** predicate, population, method, sampling, limits (`runtime_incompatible_replacement`).
* **A floor with no counterpart applies on its own** ("floor-only"), starting at the agent's first attributed traffic.
* **Responses survive.** A module may add rules to a floor's response but cannot drop or weaken one: approvals no weaker, severities
  no lower, repeats no wider (`runtime_overlay_weakens`).

With `--format json`, `tvl-compose` also prints `floor_provenance`: for every monitor that came from a pack, whether it was `merged` into a
module monitor or carried `floor_only`.

A pack never activates by itself: the language has no import. You hand packs to the tools (`--pack`), and in production an authorized
person activates a pack.

### Tightening a module with an overlay

`tvl-compose` over an *overlay* (`_tvl_overlay`) applies the same tighten-only rule to the three runtime blocks. As for every
overlay, the new blocks go under `overrides:`, where a list replaces the base list instead of merging into it
([language reference](../reference/language.md)). An overlay that supplies one of
them must therefore list **every** base declaration by name (and every base rule by `id`); a missing one counts as a drop, and loosening a
number does too: both are `runtime_overlay_weakens`. A block the overlay leaves out is kept unchanged.

This overlay makes the latency promise of `support-bot.tvl.yml` (section 3) stricter. It restates all three requirements, because it
supplies the `requirements` block, and leaves `monitors` and `responses` as they are:

<!-- snippet: overlay-tighten kind=overlay -->
```yaml title="support-bot.strict.overlay.yml"
_tvl_overlay:
  extends: support-bot.tvl.yml

overrides:
  requirements:
    - name: fast_enough
      kind: rate_bound
      unit: trace
      violation: { metric: wall_clock_latency_ms, exceeds: 2000 }
      max_rate: 0.03                    # was 0.05: at most 3% of traces may be slow
    - name: fast_again_within_2_days
      kind: recovery_time
      unit: episode
      of: fast_enough_prod
      within_hours: 48
    - name: fast_enough_evidence
      kind: evidence_liveness
      unit: window
      of: fast_enough_prod
      max_stale_windows: 4
```

```bash
tvl-compose support-bot.strict.overlay.yml --validate -o strict.tvl.yml
# Composed: strict.tvl.yml
```

The same overlay with `max_rate: 0.10` loosens the promise and is rejected (exit 2):

```text
Error: runtime_overlay_weakens at requirements.0.max_rate: runtime_overlay_weakens
```

Leaving out `fast_again_within_2_days` is a drop and fails the same way, at `requirements`.

## 10. Validating and compiling

### Check the document

```bash
tvl-validate support-bot.tvl.yml       # JSON Schema, then the lints; works on modules and on packs
tvl-lint support-bot.tvl.yml           # the lints only (no schema)
tvl-validate --format json file.yml    # machine-readable issues: {code, message, path, severity}
```

`tvl-validate` exits 0 when there are no errors; warnings remain visible and do not fail validation. Any error exits 2.
Use `tvl-validate` rather than `tvl-lint` alone: `tvl-lint` does not run the JSON Schema.
The other 1.2 tools accept a module with these blocks and ignore them (`tvl-check-structural`, `tvl-check-operational`,
`tvl-config-validate`); the ones that cannot honour a 1.3 construct refuse it with `unsupported_construct` instead of silently dropping it.

Common first mistakes and what the tools print:

| You wrote | The tool says | Fix |
|---|---|---|
| `tvl_version: 1.3` | `declared_version_below_constructs` | quote it: `"1.3"` |
| no `tvl_version` | `runtime_version_required` | add `tvl_version: "1.3"` |
| `on:` in a rule | `schema_error` with a hint to use `trigger:` / `when:` | rename to `trigger` |
| `tumbling_hours: 5` | `runtime_window_out_of_range` | a divisor of 24 |
| `max_rate: 1.5` | `runtime_rate_out_of_range` | strictly between 0 and 1 |
| a monitor field in the wrong role | `runtime_invalid_profile` with the missing or forbidden field's path | check the role table in the [reference](../reference/language.md#tvl-13-requirements-monitors-responses) |
| `kind: drift_bound` | `runtime_unknown_kind` | use a kind from the sealed list |
| `do: suspend` triggered by `episode_opened` | `response_suspend_unconfirmed` | trigger on `episode_continued`, `episode_open_for` or `recovery_overdue` |
| `tool: [a.b, c.d]` | `schema_error` with `expected type: string` | one tool per selector |
| a violation selector `tool: db.*` | `runtime_tool_not_code_identifier` | no wildcards; name the tool |

### Compile for a platform

`tvl-compile-runtime` checks the module, composes it with any packs, and writes two files.
It needs a **token map**: a JSON file, kept on your side, that gives every name you chose (module, requirement, monitor, response,
rule, environment label, selector `ref`, protocol state) an opaque reference. The compiled hosted file carries the references, not your names.

Start by asking the compiler to list the required entries:

```bash
tvl-compile-runtime support-latency.tvl.yml --emit-token-map-template > tokens.json
```

This prints local-only JSON with empty `hosted` placeholders, including the default `production` environment.
Add `--pack org-floors.pack.yml` for a module's pack entries. It validates the documents but mints no tokens and
writes no compiled files; fill every placeholder before compiling. Do not combine the flag with `--token-map`
or `--out-dir`. Keep the template and completed map on your side.

<!-- snippet: tokens kind=tokenmap-first -->
```json
{
  "format": "tvl-token-map/1",
  "tokens": [
    { "namespace": "module",      "local": "acme.support_latency",       "hosted": "mod-001" },
    { "namespace": "requirement", "local": "fast_enough",                "hosted": "req-001" },
    { "namespace": "requirement", "local": "fast_enough_evidence",       "hosted": "req-002" },
    { "namespace": "monitor",     "local": "fast_enough_prod",           "hosted": "mon-001" },
    { "namespace": "monitor",     "local": "fast_enough_evidence_check", "hosted": "mon-002" },
    { "namespace": "environment", "local": "production",                 "hosted": "env-001" }
  ]
}
```

That is the whole map for the module in section 2. Two details that cost first-time users time:

* the default environment `production` needs an entry even though the module never writes it;
* TVL never mints tokens for you. Any missing entry fails the whole compile with `runtime_unresolved_alias`, identifying the namespace
  and source field path without echoing the customer-chosen name.
  Real references should be random, or a keyed commitment under a key you hold, never a plain hash of the name.

```bash
tvl-compile-runtime support-latency.tvl.yml --token-map tokens.json --out-dir out/
# Compiled runtime contract: <sha-256 digest of the contract>
```

| File | For |
|---|---|
| `out/runtime-contract.json` | the document you register with a platform: references instead of your names |
| `out/runtime-local.json` | stays with you: the local forms the customer-side monitors and guards need |

In compilation mode exit 0 means both files were written; in template mode it means the template was printed. Nothing is written if any step fails. Warnings (such as `runtime_liveness_missing`) do not
block. Add `--format json` for `{ok, file, contract_digest, issues}`.
Add `--pack org-floors.pack.yml` (repeatable) to compile a module against its floors, and
`--checkers registry.json` when you use your own checkers.

What goes where: requirement, monitor, response and rule names, protocol states, selector `ref` names and environment labels are
replaced by opaque references; checker ids become keyed commitments; **tool names are kept as written** (they are code identifiers);
numbers, enums and counts are kept. Opaque references hide names; they are not a promise about the data a platform records about your traces.

**Your own checkers.** A checker you write is named `customer:<name>` and described in a registry that stays on your side:

<!-- snippet: checkers kind=checker-registry -->
```json
{
  "format": "tvl-checker-registry/1",
  "checkers": [
    { "checker": "customer:pii_scan", "labels": ["clean", "leaked"] }
  ]
}
```

A requirement uses it as `violation: { checker: "customer:pii_scan", label_in: [leaked] }`. `tvl-validate` only checks the name's form;
`tvl-compile-runtime` also checks that the registry binds it and that every label is in its list. Compile without `--checkers` when a customer checker occurs and it
fails with `runtime_unknown_kind` (no label or name is mentioned). What the checker *does* is outside TVL.
The token map gets one `checker`-namespace entry whose hosted form is `customer:` followed by 64 hex characters.

**Capability.** A platform may support only part of the catalogue. The compiler in this repository does not know what any particular platform
supports. A platform refuses a registration with `runtime_unsupported_capability` for a monitor kind, source, method or predicate class it has
not enabled, and with `response_action_unsupported` for an action it cannot carry out. Ask your platform what it supports before you depend on a rung.

### Quick reference: exit codes and who runs what

| Tool | Reads | Exit 2 means |
|---|---|---|
| `tvl-validate` | module or pack | any error (warnings exit 0) |
| `tvl-lint` | module or pack | any error; warnings exit 0 (no schema check) |
| `tvl-compose --pack` / `--meet` | module + pack(s) | any composition error |
| `tvl-ci-gate module incumbent candidate` | module + two bundles | not `Promote` (including `NoDecision` and not ready) |
| `tvl-compile-runtime` | module or pack + token map | any error, or unreadable input |

## 11. What TVL 1.3 cannot express

These were tried against the validator and are rejected. Each has the closest workaround that works today.

| You want | Why not | Closest workaround |
|---|---|---|
| a percentile ("p95 under 2 s") | the metric list is closed to four numbers, and a requirement is a *rate over a threshold* | "at most 5% of traces over 2 s" says the same thing |
| an average or a sum ("mean quality at least 0.8", "spend under 500 USD a day") | a rate of bad units is the only quantity bounded | a checker that labels each unit, then bound the rate of the bad label |
| anything per user, per session or per day across traces | a unit is one trace or one invocation, with no state between units | keep such limits in the agent or platform |
| a condition on what an event carries (refund over 500) | a selector has only event type, `tool`, `status`, `ref` | expose a separate tool name for the case |
| a set or wildcard of tools | one tool per selector | one requirement per tool, or a two-state `protocol` with `unlisted: ignore` |
| "A and B" or "A or B" in one violation | a violation is one predicate | encode it as a `protocol` |
| the user's message or the receiver of a handoff | the event list is closed; `handoff` takes no `tool` | have the agent emit its own marker as a tool call |
| two thresholds or two window lengths on one predicate | two monitors with the same predicate, source and environment collide (`runtime_duplicate_key`) | a burn monitor gives a second tier at a fixed multiple |
| groups against each other, drift week over week, time of day | windows are independent and UTC-aligned | one requirement per group |
| "never leak X" about content as a hard rule | content is judged by a checker, which is an estimate, and `zero_tolerance` needs a certain violation (`runtime_zero_tolerance_inexact`) | a `rate_bound` on the checker's bad label, with enough traffic |
| sliding windows | reserved; any `window` key besides `tumbling_hours` and `grace_minutes` is a schema error | shorter tumbling windows |
| who gets paged, which channel, who approves | `notify` carries a severity and nothing else | handle routing in the platform |

Also outside the language: standing grants, human approvers, the certified-configuration fingerprints used by `rollback` and `degrade`,
the token map, the checker bodies and which constructs a platform has enabled. TVL names them; it does not provide them.

## Where to go next

* [Language reference: TVL 1.3 section](../reference/language.md#tvl-13-requirements-monitors-responses): every field, type, default and allowed value
* [Error codes](../reference/error-codes.md#tvl-13-diagnostics): what each diagnostic means and what to do
* The examples in [`spec/examples/runtime-1.3/`](https://github.com/Traigent/tvl/tree/main/spec/examples/runtime-1.3): 23 worked modules, from a latency promise to refund workflows and consent-gated exports
* [Chapter 6 of the book](https://github.com/Traigent/tvl/blob/main/tvl_book/website_content/book/chapter-06-requirements-in-production.md): the same ideas as stories


## Reactive notifications (TVL 1.4)

With `tvl_version: "1.4"`, a notification may report an optimize rule's terminal outcome:
`trigger: {rule: fix, event: optimize_no_candidate}`. Other outcomes are `optimize_failed`,
`deploy_refused`, `deploy_failed`; the latter two require `deploy: if_promoted` on fix.
The rule must be in the same response. Outcome notifications cannot repeat.

Use `trigger: {monitor: latency, event: unknown_for, hours: 6}` to report prolonged UNKNOWN
verdicts with usable evidence on a primary monitor (hours ≥ its tumbling duration).
`stale` still means missing usable evidence; both may fire.

Notifications can use `only_while: [{monitor: errors, state: episode_open}]` or
`unless: [{monitor: provider, state: episode_open}, {rule: fix, state: attempt_open}]`.
Only a known FALSE conjunction or known TRUE inhibition suppresses: UNDECIDED still delivers.
Use `episode_continued` or repeats to recheck; a suppressed occurrence is not replayed later.
Mutual/self monitor inhibition is rejected. Attempt guards do not add inhibition graph edges.
Packs may use their own monitor guards, but no outcome triggers or attempt guards.
These constructs are notify-only; they add no production effect authority. See the language
reference and formal semantics §13 for the attempt lifecycle, evaluation ordering and limits.
