# RFC 0004 — Reactive Outcomes and Guards: telling people when the repair loop needs them

| | |
|---|---|
| **Status** | **Accepted** 2026-10-21 (TVL 1.4.0) |
| **Target language version** | TVL 1.4 (conservative extension of 1.3) |
| **Tracking** | not assigned |
| **Builds on** | RFC 0003 (Accepted 2026-10-21, TVL 1.3) |
| **Companion** | [formal semantics §13](tvl-formal-semantics.md#13-reactive-outcomes-and-notification-guards-tvl-14) |
| **Conformance** | `conformance/cases/runtime/` (cases listed in §5) |

## 1. Motivation

TVL 1.3 lets a module say what must keep holding in production and how to respond when it does not: notify, open a
next step, optimize, deploy the optimized candidate if it is promoted, roll back, throttle, degrade, suspend. Three
things a team running that loop needs cannot be written.

1. **A repair cannot report its own failure.** An `optimize` rule may find no promotable candidate, stop at its cost
   limit, or have its deploy refused at the time of the effect (RFC 0003 §7.6 item 5). Each outcome is recorded only as
   the action state of the occurrence (RFC 0003 §11.6); no trigger event exists for it (RFC 0003 §4.1 `event_name`).
   "Tell the on-call engineer when the fix did not work" is not expressible.
2. **An undecided requirement is silent.** When evidence keeps arriving but windows stay `UNKNOWN`, `evidence_liveness`
   can stay LIVE and no episode opens. A window decided `UNKNOWN(inconclusive)` from real units carries usable
   evidence; whether a window with too few units or too many unresolved units does is up to the evaluator profile
   (RFC 0003 §6.14). A requirement can stay
   undecided for days without anyone being told.
3. **A notification sees one monitor.** A trigger names exactly one monitor (RFC 0003 §4.1 `trigger`). "Page only if
   latency and the error rate are both breached" and "do not page about latency while the upstream-provider monitor is
   breached, or while a fix is already running" cannot be written.

All three are about **telling people**. This RFC therefore adds new reasons to `notify` and conditions on `notify`,
and nothing else: no new action, no new authority, no window shape, no statistic. Every construct is borrowed from an
established alerting or deployment system (§6).

**Scope study.** The constructs were selected from a 38-scenario expressiveness study of TVL 1.3 against alerting and
repair practice (site reliability engineering (SRE) burn-rate alerting, Prometheus/Alertmanager, Datadog monitors, complex event processing, Dwyer's
specification patterns, progressive-delivery analysis). Deliberately out of scope, with reasons in §6: sliding windows and
exact multi-window burn alerts, K-of-N persistence (notify only after at least K breached windows among the last N), comparison against a previous configuration (canary analysis),
success notifications, and guards on any action other than `notify`. Also out of scope, without a §6 entry: aggregate
budgets, anomaly detection and calendars.

## 2. Design

### 2.1 Grammar (normative additions)

Productions not shown are those of RFC 0003 §4.1.

```ebnf
rule          = rec("id": ident, "trigger": trigger, "do": action, …RFC 0003 fields…,
                    ["only_while": list(guard)], ["unless": list(guard)]) ;          (* §2.4 *)
trigger       = monitor_trigger | outcome_trigger ;
monitor_trigger = rec("monitor": ident, "event": event_name, ["hours": pos_int]) ;   (* RFC 0003 *)
outcome_trigger = rec("rule": ident, "event": outcome_event) ;                      (* §2.2 *)
event_name    = …RFC 0003 events… | "unknown_for" ;                                  (* §2.3 *)
outcome_event = "optimize_no_candidate" | "optimize_failed"
              | "deploy_refused" | "deploy_failed" ;                                 (* SEALED *)
guard         = rec("monitor": ident, "state": "episode_open")
              | rec("rule": ident, "state": "attempt_open") ;                        (* SEALED *)
```

**Version.** A module or pack that uses any construct of this RFC declares `tvl_version: "1.4"`. Omitting
`tvl_version` is `runtime_version_required` (unchanged); declaring `"1.3"` is `declared_version_below_constructs`.

**All new constructs are `notify`-only.** A rule with an outcome trigger, an `unknown_for` trigger, `only_while` or
`unless` has `do: notify` (`runtime_notify_only`). `notify` has event authority (RFC 0003 §7.4 item 2): it needs no open
scope, no grant and no approval, and it changes nothing in production. This is what keeps the RFC free of new
authority rules.

### 2.2 Repair outcomes (`outcome_trigger`)

**Attempt.** An attempt is one occurrence of an `optimize` rule (RFC 0003 §7.4 item 1) together with the deploy
occurrence it may yield (RFC 0003 §7.6 item 1). Its identity is (response, response revision, rule id, originating
scope, optimize occurrence j). It is **open** from the moment the optimize occurrence fires, whether or not its
approval has been given, until the first of:

- its last applicable outcome below is recorded (the deploy outcome if the rule declares `deploy: if_promoted` and the
  optimization produced a promoted candidate; otherwise the optimize outcome);
- the optimization succeeds with a promoted candidate under `deploy: never`, or the deploy takes place;
- its originating scope closes or its response revision changes before its pending effect takes place (RFC 0003
  §7.4);
- the approval of the effect that is next — the optimization, or later the deploy, which has its own approval (RFC 0003
  §7.6 item 2) — is declined or expires **before that effect starts**. Expiry after an effect has started does not
  close the attempt; that effect still records its outcome.

If the originating scope closes or the response revision changes after the optimization or deploy has started, the attempt stays open until that effect records its outcome or succeeds, and then closes; no later effect starts.

The last two closures (scope closure or revision change before the pending effect, and approval declined or expired
before the effect starts) record **no outcome**: either nothing is left to repair, or a person decided. Waiting for approval or
holding while authority is unreachable (RFC 0003 §7.3) keeps the attempt open and records nothing.

**Outcomes.** Each attempt records at most one optimize outcome and at most one deploy outcome. Outcomes are terminal
for their occurrence: a controller records one only when no retry of the same occurrence can change it (a retry of one
occurrence is the same occurrence, RFC 0003 §7.4 item 1). How a controller retries one occurrence is defined by its evaluator profile (RFC 0003 §3.5), but
a profile that supports this RFC states a **finite** retry bound (a count or a time) for deploy occurrences; reaching it
records `deploy_failed`.

**Precedence for one optimization.** The optimize outcome is decided in this order, and the table below describes
each outcome only within it: (1) if the gate returned `Promote` for any candidate, the optimization records no failure
outcome; (2) otherwise, if the run did not finish normally (error, cancellation, cost limit) or any candidate's
promotion evidence was invalid, `optimize_failed`; (3) otherwise `optimize_no_candidate`.

| Event | Recorded when (all while the attempt is open) |
|---|---|
| `optimize_no_candidate` | the optimization finished, its candidates' promotion evidence was valid, and the joined promotion gate (RFC 0003 §6.11) returned `Reject` or `NoDecision` for every candidate, or it produced none |
| `optimize_failed` | no candidate was promoted, and the optimization errored, was cancelled by a person or the controller, stopped at its cost limit, or had a candidate whose promotion evidence was invalid (`missing_monitor_counts`, RFC 0003 §5.9). Other candidates may already have returned `Reject` or `NoDecision` |
| `deploy_refused` | the deploy occurrence reached the time of its effect and an effect-time check of RFC 0003 §7.6 item 3 did not hold; nothing was deployed |
| `deploy_failed` | the checks held but the deployment write did not succeed and the controller has stopped retrying this occurrence; nothing changed in production (RFC 0003 §7.6 item 5) |

`optimize_failed` is not `NoDecision`: invalid or missing evidence is a failure of the repair, not an inconclusive
gate. A held or unreachable state is never an outcome.

**Triggering.** `trigger: {rule: r, event: e}` fires once per attempt of r when e is recorded. Constraints:

- `r` names an `optimize` rule of the **same response** (`runtime_missing_ref`, `runtime_ref_kind_mismatch`); it is
  not the rule itself;
- a `deploy_*` event requires `r` to declare `deploy: if_promoted` (`runtime_invalid_ladder`);
- `do: notify` (`runtime_notify_only`); `repeat_after_hours` and `max_repeats` are forbidden on outcome triggers
  (`runtime_invalid_ladder`): an outcome is a fact, not a persisting state;
- a `tvl_pack` declares no outcome trigger (`runtime_invalid_ladder`): packs do not own a module's repair rules.

No outcome can start, retry or escalate a repair. A failed repair keeps holding (RFC 0003 §7.6 item 5); a person
decides what happens next, and the original episode's own rules (for example `open_next_step`, or `suspend` on
`episode_open_for`) keep their meaning.

```yaml
responses:
  - name: latency_repair
    rules:
      - id: fix
        trigger: {monitor: latency_prod, event: episode_opened}
        do: optimize
        approval: human
        deploy: if_promoted
      - id: fix_found_nothing
        trigger: {rule: fix, event: optimize_no_candidate}
        do: notify
        severity: critical
      - id: deploy_blocked
        trigger: {rule: fix, event: deploy_refused}
        do: notify
        severity: warning
```

### 2.3 Prolonged undecided verdicts (`unknown_for`)

`trigger: {monitor: m, event: unknown_for, hours: h}` is allowed only for a **primary** runtime monitor m
(`runtime_invalid_ladder`; burn monitors are UNKNOWN whenever they do not breach, RFC 0003 §6.10).

**Counted windows.** A window of m counts toward an undecided run iff its verdict is `UNKNOWN` **and** it carried usable
evidence (RFC 0003 §6.14, formal semantics Definition 12.20). An `UNKNOWN` window without usable evidence is liveness's fact: it
neither counts toward nor ends a run. Any MET or BREACHED window ends a run, whether or not it carried usable evidence.

**Run.** Order m's windows by window start (not by evaluation time). A run begins at the first counted window after
m's latest `MET` or `BREACHED` window (or at m's first counted window, if m has no decided window) and continues across windows that do
not count; it ends at the next `MET` or `BREACHED` window, or when m's effective key changes (a revision, RFC 0003
§9.4). The event fires once per run, at the first evaluation at which the window time from the start of the run's first
counted window to the end of its latest counted window is at least h hours. A later correction of a window's verdict (RFC 0003 §3.5) changes the
run only through the evaluator's corrected records; a fired notification is not withdrawn.

- `hours` is required and at least the monitor's `tumbling_hours` (`runtime_trigger_hours_out_of_range`).
- Scope kind `unknown_run`, identity (monitor ref, first counted window of the run).
- `do: notify` (`runtime_notify_only`). `repeat_after_hours` re-notifies while the run persists.

`unknown_for` and `stale` report different facts — no decision despite usable evidence, versus no usable evidence —
and both may fire over the same period when evidence is intermittent. Neither implies the other.

### 2.4 Guards on notifications (`only_while`, `unless`)

A guard is a condition on a monitor's episode (usually another monitor's) or on a repair attempt, checked when a `notify` rule fires. A
guard never changes the rule's trigger, scope or occurrence identity (RFC 0003 §7.4).

**Evaluation (three-valued).** Each guard evaluates to TRUE, FALSE or UNDECIDED:

| Guard | TRUE iff | FALSE iff |
|---|---|---|
| `{monitor: m, state: episode_open}` | m has an open episode (RFC 0003 §6.12) for the same agent and environment | m is evaluated for them and has no open episode (a withdrawn or resolved episode is closed) |
| `{rule: r, state: attempt_open}` | an attempt of `optimize` rule r (same response) is open (§2.2) | no attempt of r is open |

An `attempt_open` guard must name an `optimize` rule in the current response revision; an open attempt from an earlier revision still counts when that rule id exists in the current revision.

UNDECIDED otherwise: the controller cannot establish the state (m not registered or not yet evaluated, records
unavailable). For example, a pack rule absorbed into an agent's contract may keep an `only_while` guard on a floor
monitor that the agent's own program does not evaluate; locally that guard is UNDECIDED and so never suppresses. The lists combine with Kleene's strong three-valued logic: `only_while` is the conjunction of its guards,
`unless` the disjunction of its guards.

**Resolution for `notify`.** The occurrence is delivered unless `only_while` is FALSE or `unless` is TRUE. An UNDECIDED
result never suppresses a notification.

**When.** Guards are evaluated once per occurrence, at its trigger, over the recorded state after every occurrence that
the same evaluation fires (so a rule triggered by `episode_opened` sees an attempt that the same `episode_opened`
started). The decision is recorded with the event; delivery keeps event authority. Each repeat occurrence
(`repeat_after_hours`) evaluates its guards anew.

**Limits, stated.** Guards are not a composite monitor with its own lifecycle.

- A suppressed occurrence is not re-delivered when the guard later changes. To re-check, trigger on
  `episode_continued` (every further breached window) or declare `repeat_after_hours`.
- The conjunction pattern below pages when the second episode opens. If, when the first episode opened, the other
  monitor was UNDECIDED, the first rule also pages: undecided never suppresses.

**References.** A guard's `monitor` names a primary runtime monitor of the same document or of a composed pack (as
RFC 0003 T7 for triggers); its `rule` names an `optimize` rule of the same response (`runtime_missing_ref`,
`runtime_ref_kind_mismatch`). An `only_while` guard on the rule's own source monitor is redundant
(`runtime_guard_redundant`, a warning); an `unless` guard on it is a self-loop (`runtime_guard_cycle`).

**No mutual silencing.** Give every guarded `notify` rule a source monitor: its trigger monitor, or, for an outcome
trigger `{rule: r, …}`, the trigger monitor of r. Build the directed graph over monitors with an edge from a rule's
source monitor to each monitor named by an `episode_open` guard in its `unless`. A cycle, including a self-loop, is an
error (`runtime_guard_cycle`): two monitors whose pages silence each other could both stay silent while both breach,
and a page silenced by its own episode is suppressed for as long as that episode is open. Alertmanager documents the same trap for inhibit rules.
`attempt_open` guards add no edge: an attempt is a repair, not a notification, and silencing a page while its own
repair runs (the inhibition pattern below) is intended.

**Conjunction pattern.** "Page when latency and errors are both breached":

```yaml
      - id: page_latency_with_errors
        trigger: {monitor: latency_prod, event: episode_opened}
        only_while: [{monitor: errors_prod, state: episode_open}]
        do: notify
        severity: critical
      - id: page_errors_with_latency
        trigger: {monitor: errors_prod, event: episode_opened}
        only_while: [{monitor: latency_prod, state: episode_open}]
        do: notify
        severity: critical
```

**Inhibition pattern.** "Do not page about latency while the provider is down or a fix is running":

```yaml
      - id: page_latency
        trigger: {monitor: latency_prod, event: episode_continued}
        unless:
          - {monitor: provider_prod, state: episode_open}
          - {rule: fix, state: attempt_open}
        do: notify
        severity: critical
```

Triggering on `episode_continued` re-checks at each further breached window, so the page arrives
once the provider has recovered and no repair attempt remains open, while latency stays breached.

### 2.5 Diagnostics

| Code | Severity | Condition |
|---|---|---|
| `runtime_notify_only` | E | an outcome trigger, an `unknown_for` trigger, `only_while` or `unless` on a rule whose action is not `notify` |
| `runtime_guard_cycle` | E | a cycle, including a self-loop, in the `unless` graph of §2.4 |
| `runtime_guard_redundant` | W | an `only_while` guard on the rule's own source monitor |
| existing codes, extended | E | `runtime_missing_ref` and `runtime_ref_kind_mismatch` (outcome `rule`, guard `monitor` and `rule`); `runtime_invalid_ladder` (`deploy_*` without `deploy: if_promoted`; repeats on an outcome trigger; outcome trigger in a pack; `unknown_for` on a non-primary monitor; `hours` present iff `episode_open_for` or `unknown_for`); `runtime_trigger_hours_out_of_range` (`unknown_for` hours below `tumbling_hours`); `runtime_version_required`, `declared_version_below_constructs` (§2.1) |

### 2.6 Composition and projection

- **Canonical references (RFC 0003 §9.4).** Step 4 ("rewrite references") also rewrites every pack `guard.monitor`
  that names an absorbed pack monitor. Guard lists are compared as sets of canonical guards (order and duplicates are
  not significant).
- **Immutability.** A rule's outcome trigger, `only_while` set and `unless` set are immutable coordinates: an overlay
  or meet that changes them is an incompatible replacement (`runtime_incompatible_replacement`). New rules may be
  added, subject to §2.2–§2.4. A pack may declare guards over its own monitors; it declares no outcome trigger and no
  `attempt_open` guard.
- **Projection (RFC 0003 §8.2).** Outcome events, `unknown_for` and guard states project as closed enums; monitor and
  rule references as hosted references. Nothing customer-authored crosses beyond what RFC 0003 already projects.
- **`backend_v1`.** Unchanged; it carries no responses.

## 3. Compatibility

A conservative extension of TVL 1.3: every 1.3 module, pack and diagnostic keeps its meaning, and no 1.3 document gains
a diagnostic. A 1.3 reader rejects 1.4 constructs through its closed schemas and `unsupported_construct`
(RFC 0003 §11.2). Compiled contracts carrying an outcome trigger, `unknown_for`, `only_while` or `unless` use
`tvl-runtime-contract/2` and `tvl-runtime-local/2`, with the closed `tvl-runtime-contract-v2.schema.json` and
`tvl-runtime-local-v2.schema.json` schemas. The `/1` schemas retain their exact TVL 1.3.0 bytes and refuse all 1.4
fields; readers select the schema by `format` and refuse unknown tags.

Format selection depends only on projected constructs: an outcome trigger, `unknown_for`, or a nonempty
`only_while`/`unless` guard list selects `/2` with `tvl_version: "1.4"`. Without these constructs, even an authored
`"1.4"` module or pack compiles to `/1` with `tvl_version: "1.3"`. Empty guard lists are omitted by projection.
A `/2` artifact without a projected 1.4 construct is refused, including one carrying version `"1.4"`.

For every input accepted by TVL 1.3.0 (commit `bcd20f6dd`), canonical hosted and local artifacts, including digests,
remain byte-identical for the same token map, checker registry, packs and toolchain version. This includes authored
`"1.4"` modules without runtime blocks, which 1.3.0 accepted and compiled to version `"1.3"` and `/1`.
The TVL 1.4.0 compiler defaults `toolchain.version` to `"1.4.0"`, rather than `"1.3.0"`. With otherwise identical
inputs, a 1.3 module's hosted artifact is byte-identical except for this field and any checked packs' derived
`pack_contract_digest` values; its local artifact differs only in the derived `contract_digest`. With no checked
packs, the hosted artifact differs only in `toolchain.version`. Consumers that pin accepted toolchain versions
must add `"1.4.0"`. Explicitly pinning `toolchain_version="1.3.0"` preserves the historical canonical bytes and digests.
Verdict, episode, liveness, obligation and action states stay separate facts (RFC 0003 §11.6); an outcome event is a
recorded action state, never a verdict.

## 4. Semantics and proofs

Formal semantics §13 defines the attempt lifecycle and its outcome function (§2.2), the undecided-run relation
over window records (§2.3), and guard evaluation as a function into {TRUE, FALSE, UNDECIDED} with Kleene connectives
and the `notify` resolution of §2.4.

Lean (`proofs/TVL/Runtime/Guards.lean`) formalizes the following statements, each with its recorded class
(`proofs/PROOF_SUMMARY.md`: SUBSTANTIVE means proved with content beyond its definitions; BY-CONSTRUCTION means proved
but true by definition or by the chosen representation):

- `undecided_never_suppresses` (SUBSTANTIVE, small): for every guard valuation, replacing any guard's value by
  UNDECIDED never turns "delivered" into "suppressed". A truth-table property of the resolution; it says nothing
  about delivery mechanics.
- `notify_only` (BY-CONSTRUCTION): every rule using a construct of this RFC is a `notify` rule, so no construct of this
  RFC authorizes or starts an effect.
- `guards_preserve_identity` (BY-CONSTRUCTION): guard evaluation does not change a rule's occurrence identity or scope.
- `no_mutual_silencing` (SUBSTANTIVE): if the `unless` graph is acyclic, then for any nonempty set S of `notify` rules
  triggered by the same evaluation, each of whose `only_while` is not FALSE, whose `attempt_open` guards in `unless` are not
  TRUE, and whose `episode_open` guards in `unless` name only source monitors of S, at least one rule of S is
  delivered. Silencing by a monitor outside S (the provider pattern) is intended and not excluded.

## 5. Conformance

Lints (each with its expected code): valid `outcome-trigger-notify.yml`; `outcome-trigger-not-notify.yml`
(`runtime_notify_only`); `outcome-deploy-needs-if-promoted.yml`; `outcome-ref-not-optimize.yml`;
`outcome-ref-self.yml`; `guard-unless-own-attempt-valid.yml`; `guard-unless-self-loop.yml`;
`guard-cycle-through-outcome-rule.yml`; `outcome-repeat-forbidden.yml`; `outcome-trigger-in-pack.yml`; valid `unknown-for-primary.yml`;
`unknown-for-burn-rejected.yml`; `unknown-for-hours-below-window.yml`; `unknown-for-not-notify.yml`;
valid `guard-only-while-notify.yml`; `guard-on-optimize-rejected.yml`; `guard-unless-cycle.yml`
(`runtime_guard_cycle`); `guard-redundant-warning.yml`; `guard-ref-missing.yml`; `version-1-4-required.yml`;
`version-omitted.yml`. Composition: `guard-immutable-under-overlay.yml`, `guard-set-order-insensitive.yml`,
`pack-guard-absorbed-monitor-rewritten.yml`, `outcome-trigger-immutable.yml`. Projection:
`outcome-and-guard-closed-enums.yml` (`/2`); `deploy-mode-closed.yml` (`/1`, frozen 1.3.0 canonical digest);
`format-v1-refuses-reactive-fields.yml`; `format-v2-refuses-13-without-reactive-construct.yml`;
`format-v1-version-14-without-reactive-construct.yml` (authored 1.4 without projected new constructs).

Semantic traces (relational cases: a recorded history and the expected events, no engine),
executable under [`conformance/cases/runtime/semantic_traces/`](../conformance/cases/runtime/semantic_traces/):

- [attempt closed by episode closure records no outcome](../conformance/cases/runtime/semantic_traces/attempt-closed-by-episode-closure-records-no-outcome.yml);
- [attempt closed by response revision while awaiting deploy approval records no outcome and closes `attempt_open`](../conformance/cases/runtime/semantic_traces/attempt-closed-by-response-revision-awaiting-deploy-approval.yml);
- [deploy write fails then succeeds on a retry of the same occurrence records no `deploy_failed`](../conformance/cases/runtime/semantic_traces/deploy-write-fails-then-succeeds-on-same-occurrence-retry.yml);
- [invalid promotion evidence gives `optimize_failed`, not `optimize_no_candidate`](../conformance/cases/runtime/semantic_traces/invalid-promotion-evidence-gives-optimize-failed.yml);
- [one promoted and one invalid candidate give no failure outcome](../conformance/cases/runtime/semantic_traces/one-promoted-and-one-invalid-candidate-give-no-failure.yml);
- [optimization approval expiring after the optimization started still records its outcome](../conformance/cases/runtime/semantic_traces/optimization-approval-expires-after-start-still-records-outcome.yml);
- [deploy approval declined before the deploy closes the attempt with no deploy outcome](../conformance/cases/runtime/semantic_traces/deploy-approval-declined-before-start-closes-without-outcome.yml);
- [an initial counted window followed by MET fires `unknown_for` when `hours` equals `tumbling_hours`](../conformance/cases/runtime/semantic_traces/initial-counted-window-followed-by-met-fires-unknown-for.yml);
- [unreachable authority gives no outcome](../conformance/cases/runtime/semantic_traces/unreachable-authority-gives-no-outcome.yml);
- [undecided run continues across a window without usable evidence and fires](../conformance/cases/runtime/semantic_traces/undecided-run-continues-across-window-without-usable-evidence.yml);
- [`unknown_for` and `stale` both fire on intermittent evidence](../conformance/cases/runtime/semantic_traces/unknown-for-and-stale-both-fire-on-intermittent-evidence.yml);
- [an UNDECIDED guard does not suppress](../conformance/cases/runtime/semantic_traces/undecided-guard-does-not-suppress.yml);
- [`attempt_open` is seen by a rule fired by the same evaluation](../conformance/cases/runtime/semantic_traces/attempt-open-visible-to-rule-fired-by-same-evaluation.yml).

A trace records every due repeat instant; when and how a late controller delivers missed repeats is outside this relation.

Every 1.3 case passes unchanged.

## 6. Alternatives considered

| Alternative | Borrowed from | Why not (now) |
|---|---|---|
| Outcome-triggered `open_next_step` or `suspend` | Argo Rollouts abort/escalate | An outcome closes its attempt, so a follow-up service effect would need authority from a closed scope (RFC 0003 §7.4); `suspend` needs an escalation trigger (RFC 0003 §7.2). The episode's own rules already cover the next step and suspension. |
| Success outcomes (`optimize_promoted`, `deploy_done`) | Argo AnalysisRun `Successful` | Already recorded as action states; not needed to tell people a repair needs them. A later revision may add them. |
| Guards on service effects and local guards | Datadog composite monitors | Needs re-evaluation at the effect, interaction with `on_check_error` (RFC 0003 §7.5) and with the deploy's own checks (RFC 0003 §7.6). The motivating cases are all notifications. |
| Composite monitors with their own lifecycle | Datadog composite monitors | Needs a composite occurrence identity, freshness and re-arming model, and repair rules would lose their single episode anchor. |
| Exact SRE multi-window, multi-burn-rate alerts | Google SRE Workbook | The rule is `(1h ∧ 5m at 14.4) ∨ (6h ∧ 30m at 6)`; TVL has no minute windows and burn monitors have no episode or MET test (RFC 0003 §6.10). Needs sliding windows: a separate RFC. |
| "Breached for K windows in a row" | Prometheus `for:` | The false-alarm budget already suppresses threshold flapping; K-of-N needs adjacency and UNKNOWN rules. Deferred. |
| Comparison against the previous configuration after a deploy | Kayenta, Argo AnalysisTemplate | Evidence is attributed to agents, not configurations (RFC 0003 §6.2); needs attribution, baseline selection and multiplicity design. Separate RFC. |
| Folding undecided verdicts into liveness | CloudWatch `INSUFFICIENT_DATA` | Liveness is about missing usable evidence; merging the two would merge distinct facts (RFC 0003 §11.6). |

Borrowed directly: outcome events follow progressive-delivery analysis phases (Argo Rollouts AnalysisRun
Failed/Inconclusive, Flagger promotion-failed alerts, the Kubernetes Job `Failed` condition); `unknown_for` follows
CloudWatch's separate `INSUFFICIENT_DATA` alarm state; guards use Kleene's strong three-valued logic, with
`only_while` following Datadog composite conjunction and `unless` following Alertmanager inhibition, which mutes
notifications only and documents the mutual-inhibition trap.

## 7. Recorded decisions and limitations

1. **Success outcomes** (§6): deferred beyond 1.4; no success notification trigger.
2. **Contract format tags — closed (owner decision).** Projected new constructs use `/2` and version `"1.4"`; without them,
   artifacts use frozen `/1` and version `"1.3"`, regardless of authored version. Refusal rules are recorded in §3.
3. **Guards in packs over module monitors.** Disallowed in 1.4; pack guards may name only pack monitors.
4. **`attempt_open` for `deploy: never`.** The attempt closes when a promoted candidate exists; the candidate's later
   manual deployment is outside the response and untracked in 1.4.
