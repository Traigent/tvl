# RFC 0011 — Tuning Conditions: schedules, external events and the conditions that start a repair

| | |
|---|---|
| **Status** | **DRAFT** — not accepted; syntax, codes and meaning may change before acceptance |
| **Target language version** | TVL 1.7 (conservative extension of 1.6; the minor after RFCs 0008–0010, set at acceptance) |
| **Tracking** | to be linked when a pull request exists |
| **Builds on** | RFC 0003 (Accepted, TVL 1.3: requirements, monitors, responses, occurrences §7.4, deploy §7.6); RFC 0004 (Accepted, TVL 1.4: outcome triggers, notify guards); RFC 0005 (Accepted, TVL 1.5); draft RFC 0010 (run budgets); draft RFC 0006 (fail-closed guards) for Part B |
| **Companion** | `formalization/tvl-formal-semantics.md` new §16 (conditions); RFC 0012 (release acceptance) |
| **Conformance** | `conformance/cases/runtime/conditions/*.yml`, `conformance/cases/runtime/semantic_traces/external-*.yml` (§5) |

Existing-text handles are repository paths at `origin/main` commit `674d9aa2a4340115600e837ac28d8538d2b57867`.

This RFC has two parts. **Part A** (§2.1–§2.7) is the first slice and is complete on its own: a sealed external-event
trigger and a schedule trigger that start an `optimize` repair, with new-model admission and one open repair per
agent. **Part B** (§2.8–§2.12) adds the condition algebra (composition, sequence, absence, rate) and anti-oscillation
controls. Part B may be split into its own RFC at review; Part A does not depend on it.

## 1. Motivation

TVL 1.3–1.5 start a repair only from a monitor event: an episode opens, stays open, or recovery is overdue
(RFC 0003 §4.1 `event_name`, §4.7). Three situations a team running an agent in production needs cannot be written.

1. **A new model is released.** Teams re-optimize when a provider releases a model that may be better or cheaper than
   the one in production, before anything breaches. Nothing in production has failed, so no monitor event exists.
   RFC 0004 §1 lists calendars and external events as out of scope; the 1.6 discovery notes defer "maintenance and
   external events" behind an event catalogue.
2. **A periodic re-check.** "Re-optimize every 30 days on fresh audited cases" is a backstop against slow drift that no
   window detects. The only clocks today are episode-relative (`episode_open_for`, `repeat_after_hours`, `unknown_for`).
3. **Conditions over several signals.** "Re-optimize after a model release only if the quality floor is met" or "after a
   breach that began within 48 hours of a deploy" cannot be written; guards (RFC 0004 §2.4) are notify-only and see
   only `episode_open` and `attempt_open`.

A trigger that spends money must also be safe under the usual failure modes of event systems: duplicate delivery,
late delivery, a forged event, two triggers firing for one agent at once, and a periodic tick missed during an outage.

## 2. Design

### 2.1 Grammar (normative additions, Part A)

Productions not shown are those of RFC 0003 §4.1 and RFC 0004 §2.1.

```ebnf
trigger          = monitor_trigger | outcome_trigger | external_trigger | schedule_trigger ;
external_trigger = rec("external": external_kind, ["match": ext_match]) ;                       (* §2.3 *)
external_kind    = "model_released" ;                                                            (* SEALED, catalogue v1 *)
ext_match        = rec(["provider_family": list(provider_family)], ["tier": list(model_tier)]) ;
provider_family  = "anthropic" | "openai" | "google" | "meta" | "mistral" | "amazon" ;           (* SEALED, catalogue v1 *)
model_tier       = "small" | "medium" | "large" ;                                                (* SEALED, catalogue v1 *)
schedule_trigger = rec("schedule": rec("every_days": pos_int, "anchor": utc_instant)) ;           (* §2.4 *)
utc_instant      = string ;                         (* RFC 3339, "Z" offset, whole seconds: 2026-12-01T00:00:00Z *)

rule             = rec(…RFC 0003/0004 fields…, ["admit": admit], ["protects": list(ident)]) ;   (* §2.5, §2.6 *)
admit            = rec("tvar": ident) ;
```

**Version.** A module or pack that uses any construct of this RFC declares `tvl_version: "1.7"` (or the version fixed at
acceptance). Omitting it is `runtime_version_required`; declaring a lower version is `declared_version_below_constructs`.

**Actions.** A rule with an external or schedule trigger has `do: notify | open_next_step | optimize`
(`trigger_action_unsupported` otherwise). Rollback, throttle, degrade and suspend respond to evidence about the running
configuration; an external event or a clock tick is not such evidence.

### 2.2 Time model and event envelope (normative)

1. **One clock.** Every instant in this RFC is a UTC instant on the evaluator's clock, in whole seconds. Lifecycle hours
   (RFC 0003) are derived from it as today.
2. **Event envelope.** An external event is a closed record
   `{kind, event_id, issuer, issued_at, catalogue_revision, subject}` where `event_id` is an opaque id unique per
   issuer, `issuer` is a platform issuer ref, `issued_at` a UTC instant, `catalogue_revision` a positive integer and
   `subject` a closed record of the kind (§2.3). Events carry no free text.
3. **Authentic events only.** An event counts only if its issuer is a platform issuer whose signature the evaluator
   verified (profile-defined mechanism). Customer code cannot inject a `model_released` event. An unverifiable event is
   recorded as `rejected(unauthenticated)` and fires nothing.
4. **Arrival, lateness and duplicates.** An event is *admitted* at its arrival instant a, if `a − issued_at ≤ 72 h`;
   a later event is recorded as `rejected(late)` and fires nothing. Two events with the same (issuer, event_id) are one
   event; the second is a redelivery (RFC 0003 §7.4 item 1).
5. **Order.** Events and evaluations at the same instant are ordered: evaluations first (window verdicts, episodes),
   then admitted events in (issued_at, issuer, event_id) order. This makes every trace a total order.

### 2.3 External trigger `model_released`

The subject of a `model_released` event is `{model_ref, provider_family, tier}`: `model_ref` is an opaque catalogue id
(for example `anthropic/claude-sonnet-5-5`), `provider_family` and `tier` are catalogue enums. A rule with
`trigger: {external: model_released, match: m}` fires for an admitted event whose subject matches `m`: every present
`match` field contains the subject's value; an absent field matches any value.

**Scope.** A new scope kind `external` with identity (response, rule id, issuer, event_id). Occurrence 0 is the first
firing; `repeat_after_hours` is rejected on external triggers (`trigger_repeat_unsupported`): one event, one occurrence.
The scope **requires intervention** (RFC 0003 §7.4 item 2) until its occurrence's attempt finishes or until 30 days after
admission, whichever is first; after that a service effect of the occurrence never takes place.

### 2.4 Schedule trigger

`trigger: {schedule: {every_days: d, anchor: t0}}` defines ticks t_k = t0 + k·d days for k ≥ 0. A tick fires when the
evaluator's clock reaches t_k.

1. **Scope.** Scope kind `schedule`, identity (response, rule id, k). A tick fires at most once (theorem
   `schedule_tick_unique`, §4).
2. **Missed ticks coalesce.** If the evaluator was unable to evaluate while several ticks passed, only the latest passed
   tick fires, once, at the first evaluation after it; earlier missed ticks are recorded as `skipped(coalesced)`.
   Ticks are never replayed.
3. The scope requires intervention until the next tick, or until the attempt finishes, whichever is first.
4. `every_days` is at least 1 and at most 366; `anchor` is not later than 1 year after the module's
   `environment.snapshot_id` (`schedule_anchor_out_of_range`).

### 2.5 New-model admission (`admit`)

A newly released model is, by definition, not in a configuration space declared before its release. `admit` says how it
enters the search of one occurrence.

1. `admit: {tvar: v}` is allowed only on an `optimize` rule with an external `model_released` trigger
   (`admit_without_model_event`). `v` names a tvar of type `enum[str]` whose domain lists model refs
   (`admit_tvar_type`).
2. For the occurrence fired by event e, the search domain of `v` is `domain(v) ∪ {e.subject.model_ref}`. No other tvar
   changes. The contract digest is unchanged: the rule, including its `match` selector, is already in the contract, and
   the module author's approval of the contract is the authority to admit matching models.
3. The candidate configuration fingerprint covers the admitted value, so a candidate using the new model is
   distinguishable from every candidate of the declared space.
4. `admit` requires a `match` with at least one present, non-empty field (`admit_needs_match`; an absent `match`,
   `match: {}` or an empty list all fail): admission without a selector would let any released model enter.
5. A model that the customer's own allowlist (customer side, outside TVL) refuses is not searched; the occurrence
   finishes with `optimize_no_candidate` (RFC 0004 outcome) if nothing else is promotable.

### 2.6 What an externally started repair must protect (`protects`)

A monitor-started `optimize` with `deploy: if_promoted` needs a promotion monitor on the trigger monitor's requirement
(RFC 0003 §7.6 item 3.3). An external or schedule trigger has no trigger monitor. Such a rule with
`deploy: if_promoted` declares `protects: [r1, …]`, a non-empty list of runtime requirement names
(`protects_required`), each of which has at least one promotion monitor (`protects_without_promotion_monitor`).
`protects` is a **minimum-coverage** requirement only: the candidate's promotion decision is still the full gate join of
RFC 0003 §6.11 — the existing promotion decision joined with **every** promotion monitor of the module — so listing fewer
requirements never narrows the gate. `protects` is rejected on monitor triggers (`protects_on_monitor_trigger`), whose
protected requirement is fixed.

**Originating scope replaces the episode.** For a rule with an external or schedule trigger, every episode-specific
condition of RFC 0003 §7.4 item 2 and §7.6 item 3 is read with the rule's originating scope (§2.3, §2.4) in place of
the episode: the scope still requires intervention (item 3.1); the candidate was produced by an optimize occurrence of
this rule **in this scope** (item 3.2); and the same substitution applies to the precondition of `open_next_step`.
Item 3.4 ("not a configuration that breached in an open episode") is checked against every open episode of the agent.
RFC 0012 makes the deployment precondition normative.

### 2.7 One open repair per agent

For an agent whose registered contract declares `tvl_version` 1.7 or later, at most one `optimize` attempt is open per
(agent, deployment environment), whatever triggered it. An attempt is the optimization **and its possible deploy**
(RFC 0004 §2.2): it stays open while a deploy occurrence awaits approval and closes when the deploy is written, refused
or never takes place. Contracts of earlier versions keep the RFC 0003 meaning unchanged (§3). A trigger that fires
while another attempt is open does not start an attempt: its occurrence is recorded as `held(repair_open)`, and

- for a monitor trigger, the occurrence remains pending and starts when the open attempt finishes, if its scope still
  requires intervention;
- for an external or schedule trigger, the occurrence remains pending under the same rule;
- pending occurrences start in (trigger instant, response name, rule id) order.

This serializes spending: two triggers can never run two concurrent optimizations of one agent. Budgets per occurrence
are those of RFC 0010 (`run_budget`); a rolling per-agent cap is proposed as an RFC 0010 amendment.

### 2.8 Part B — conditions (`when`)

```ebnf
rule       = rec(…, ["when": cond], ["hold_timeout_hours": pos_int], ["cooldown_hours": pos_int]) ;
cond       = rec("all": list(cond)) | rec("any": list(cond)) | rec("not": cond) | atom ;
atom       = rec("monitor": ident, "state": "episode_open" | "met")
           | rec("rule": ident, "state": "attempt_open")
           | rec("external": external_kind, "within_hours": pos_int, ["match": ext_match])
           | rec("head_moved_within_hours": pos_int) ;
```

`when` is evaluated at the trigger instant with strong-Kleene three-valued logic (TRUE, FALSE, UNDECIDED). An atom is
UNDECIDED when its source is UNKNOWN or unreachable. The effect depends on the action class:

- **notify** (event authority): delivered unless `when` is FALSE (UNDECIDED never suppresses, as RFC 0004
  `undecided_never_suppresses`). `only_while`/`unless` remain valid and mean `when: {all: …}` / `when: {not: {any: …}}`.
- **spending actions** (`optimize`, `open_next_step`): `when` is evaluated at the trigger instant **and again
  immediately before the effect starts**, including after every hold (§2.7, §2.10). The effect starts only if it is TRUE
  at that last evaluation. FALSE finishes the occurrence as `skipped(condition_false)` with no spend. UNDECIDED keeps the
  occurrence `held(undecided)`, re-evaluated at each evaluation; after `hold_timeout_hours` (default 24) from the trigger
  instant it finishes as `held_expired` and emits the RFC 0004 outcome event `optimize_held_expired` (new, notify-only),
  so a hold is never silent.

`{external: k, within_hours: h}` is TRUE iff an admitted event of kind k matching `match` arrived in (t − h, t];
`head_moved_within_hours: h` is TRUE iff the agent's head moved (deploy or rollback) in (t − h, t]. Together with a
monitor trigger these express sequences ("a breach opened within 48 h of a deploy").

### 2.9 Part B — absence and rate triggers

```ebnf
monitor_trigger = rec("monitor": ident, "event": event_name, ["hours": pos_int]) ;
event_name      = … | "silent_for" | "fired_count" ;
```

- `silent_for` with `hours: h`: no window report of the monitor was admitted for h hours. Scope (monitor ref, start of
  silence). Notify-only. (It differs from `evidence_liveness`, which needs a separate requirement.)
- `fired_count` on an outcome trigger: `trigger: {rule: r, event: fired_count, count: n, days: d}` fires when rule r has
  started its n-th attempt within d days. Notify-only. This is the escalation for flapping repairs.

### 2.10 Part B — cooldown

`cooldown_hours: c` on an `optimize` rule: an occurrence is `held(cooldown)` while the agent's last optimize ATTEMPT
(started by any rule) finished less than c hours ago, or its head moved less than c hours ago. Measuring from the
attempt, not the deploy, keeps a series of rejected candidates from spending repeatedly. Under composition the larger
cooldown wins.

### 2.11 Part B — simultaneous rules

When several rules of one agent fire at one instant, service effects are ordered by action rank
`rollback > suspend > degrade > throttle > optimize > open_next_step > notify`, then by (response name, rule id). An
optimize that would start while a rollback of the same instant is pending is `held(repair_open)` under §2.7.

### 2.12 Diagnostics

| Code | Sev | Condition |
|---|---|---|
| `trigger_action_unsupported` | E | an external or schedule trigger with an action other than notify, open_next_step, optimize |
| `trigger_repeat_unsupported` | E | `repeat_after_hours` or `max_repeats` on an external trigger |
| `schedule_anchor_out_of_range` | E | anchor not a whole-second UTC instant, or more than one year after `snapshot_id` |
| `admit_without_model_event` | E | `admit` on a rule that is not `optimize` with an external `model_released` trigger |
| `admit_tvar_type` | E | `admit.tvar` missing or not `enum[str]` |
| `admit_needs_match` | E | `admit` without a `match` that has at least one present, non-empty field |
| `protects_required` | E | external or schedule `optimize` with `deploy: if_promoted` and no `protects` |
| `protects_without_promotion_monitor` | E | a `protects` requirement with no promotion monitor |
| `protects_on_monitor_trigger` | E | `protects` on a monitor trigger |
| `protects_unknown_requirement` | E | a `protects` name that is not a runtime requirement of the module |
| `when_on_unsupported_action` | E | `when` on rollback, throttle, degrade, suspend, block_action, halt_unit (Part B) |
| `cooldown_not_optimize` | E | `cooldown_hours` on a rule that is not `optimize` (Part B) |


### 2.13 Clarifications fixed by the reference relation (normative)

1. **Order of event checks.** An arriving event is checked in this order: authentication (an unauthenticated copy is
   recorded `rejected(unauthenticated)` and not remembered, so a later authentic copy with the same id is admitted);
   redelivery of an admitted (issuer, event_id); lateness; then matching.
2. **Order within an instant.** Window reports, recovery facts, the schedule clock, attempt facts, acceptances, then
   admitted events in (issued_at, issuer, event_id) order; finally pending occurrences start in
   (trigger instant, response name, rule id) order.
3. **Schedule shape.** `every_days` outside 1–366 and malformed schedule mappings are `runtime_invalid_profile`.
4. **Gate at effect time.** A candidate whose gate join is not `Promote` when its optimization finishes yields no deploy
   occurrence; if the gate result is recomputed at the time of the effect and is no longer `Promote`, the deploy is
   refused with reason `gate_not_promote`.
5. **Breached configurations.** For each open episode, the configurations that *breached in it* are the head fingerprint
   serving when the episode opened and every head fingerprint that served during a BREACHED window of the episode. A
   deploy whose candidate is one of them is refused (`candidate_breached_in_open_episode`); a rollback whose target is
   one of them holds (RFC 0012 §2.5). Eligibility is computed from the recorded history; the absence of a recorded
   eligibility fact never makes a target eligible.
6. **Scope end releases the lock.** When an external or schedule scope stops requiring intervention while its attempt
   awaits a deploy, the deploy never takes place (RFC 0003 §7.4 item 2) and the attempt closes (`scope_expired`),
   releasing the one-open-repair lock of §2.7.
7. **Timing of derived closures.** A scope end or expiry that falls between evaluations takes effect at the first
   evaluation at or after it, **before** that evaluation's acceptances. A pending deploy whose scope has closed never takes
   place and produces no outcome event (RFC 0004 §2.2); a later acceptance for it is recorded as ignored
   (`scope_closed`), not as `deploy_refused`.
8. **Spanning windows.** Windows are half-open `[start, end)` (RFC 0003 §6.2). A BREACHED window counts as having been
   served by every head generation in effect at some instant in `[start, end)`; a generation installed exactly at `end`
   did not serve it.
9. **Window redelivery.** A second report for the same (monitor, window start) is a redelivery: the first report stands,
   whatever the second says, and the redelivery changes no count.
10. **External scope refs.** The hosted `scope_ref` of an external scope is `ext:` followed by the lowercase hex SHA-256
    of `{"event_id": …, "issuer": …}` under the canonical digest of RFC 0003 §11.4 (`tvl.canonical.canonical_json_digest`): fixed length, injective for all practical purposes, and
    within the 128-character reference limit.
11. **Rollback eligibility needs positive evidence.** A rollback target is eligible only if the history records positive
    eligibility evidence for it at the time of the effect (`target_eligible: true`, standing for the RFC 0003 §7.2 target
    checks: certificate validity, compatibility with current requirements, presence in the store) **and** it did not
    breach in an open episode (item 5). Missing evidence holds the rollback (`held(target_ineligible)`).

## 3. Compatibility

Conservative extension of 1.6: every 1.6 document keeps its meaning and its compiled artifacts byte-for-byte. The
execution rules that are new here (one open repair per agent, §2.7; action ranking, §2.11) apply only to agents whose
registered contract declares 1.7 or later. Readers of
1.6 and earlier refuse every construct of this RFC with `unsupported_construct`. A new projection format,
`tvl-runtime-contract/4` and `tvl-runtime-local/4`, is selected only when a construct of this RFC is projected; earlier
formats stay frozen. External and schedule scopes, the event envelope and `admit` project as closed enums, integers,
UTC instants and opaque ids only; `model_ref` is a platform catalogue id, never customer content.

## 4. Semantics and proofs

Formal semantics §16 defines: the merged, totally ordered input stream (§2.2 item 5); scopes `external` and `schedule`;
the firing relation of each trigger; the pending-occurrence queue of §2.7; and (Part B) the three-valued evaluation of
`when`. Lean, `proofs/TVL/Runtime/Conditions.lean`:

- `schedule_tick_unique`: in any trace, each tick index fires at most once.
- `external_event_unique`: redeliveries of one (issuer, event_id) produce one occurrence.
- `one_open_repair`: in any trace, at most one optimize attempt per agent is open at any instant.
- `admit_extends_only_named_tvar`: the occurrence's search space differs from the declared space only in the admitted
  tvar, and only by the event's model ref.
- `when_restricts_instances` (Part B): for a fixed sequence of trigger instances (before cooldown and serialization),
  adding a conjunct to `when` of a spending rule never adds a started attempt. (The statement over full traces is false:
  suppressing an attempt removes its cooldown and can enable a later one.)
- `conservative_extension` extended to 1.7.

## 5. Conformance

Part A, at least: valid modules (external optimize with admit+protects; schedule optimize; schedule notify); invalid
modules, one per Part A diagnostic of §2.12; semantic traces: (1) duplicate delivery gives one occurrence; (2) a late
event fires nothing; (3) an unauthenticated event fires nothing; (4) three missed ticks coalesce into one; (5) a breach
during an open external repair is held and starts after it; (6) admitted model appears in the candidate's search
domain only for that occurrence; (7) deploy of an external repair refused when a `protects` promotion monitor is
`NoDecision`; projection: format /4 selected only when a 1.7 construct is projected; old reader refuses.

## 6. Alternatives considered

1. **Customer-declared events.** Rejected for v1: an arbitrary customer event that starts spending is an authority and
   injection risk; customer signals enter as monitors, which already have statistical semantics.
2. **Cron syntax.** Rejected: time zones, DST and day-of-month rules complicate the proofs; a fixed interval and a UTC
   anchor cover the backstop use.
3. **Replaying missed ticks.** Rejected: an outage would trigger a burst of repairs.
4. **Admitting by changing the module.** Requires a new contract revision per release; that is a human edit, which this
   construct exists to avoid while keeping the selector in the contract.
5. **A general CEP language (Esper/Siddhi style).** Rejected: unbounded state defeats decidable checking and the Lean
   work. Part B is a closed, bounded-state algebra.

## 7. Open questions

1. The issuer and signing mechanism for platform events (profile-defined here).
2. Whether `price_changed` and `model_deprecated` join the catalogue (v2).
3. Whether Part B moves to its own RFC.
4. Interaction with draft RFC 0006 (fail-closed guards) once that is accepted.
