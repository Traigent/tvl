# RFC 0012 — Release Acceptance: who lets a repaired configuration into production, and on which evidence

| | |
|---|---|
| **Status** | **DRAFT** — not accepted; syntax, codes and meaning may change before acceptance |
| **Target language version** | TVL 1.7 (with RFC 0011) |
| **Tracking** | to be linked when a pull request exists |
| **Builds on** | RFC 0003 §7.6 (deploy of an optimize candidate), §6.12 (episodes), §6.13 (recovery time); draft RFC 0008 (holdout declaration); RFC 0011 (external and schedule scopes) |
| **Companion** | `formalization/tvl-formal-semantics.md` §16.6–§16.8 |
| **Conformance** | `conformance/cases/runtime/release/*.yml`, `conformance/cases/runtime/semantic_traces/release-*.yml` (§5) |

Existing-text handles are repository paths at `origin/main` commit `674d9aa2a4340115600e837ac28d8538d2b57867`.

## 1. Motivation

RFC 0003 §7.6 lets an `optimize` rule deploy a promoted candidate with a human approval that "binds … the precondition by
which the platform detects a concurrent change of the deployed configuration (for example an expected head
generation)". Three things a regulated team needs are not fixed by that text.

1. **The approval record is undefined.** What an acceptance names, who may give it, and how a tool checks that a deploy
   used one, are left to the evaluator profile. Two platforms can both conform and record different things.
2. **The precondition is an example.** Without a normative head generation, an acceptance given for one production
   state can be applied after another deploy changed it.
3. **Recovery can be claimed on the old configuration.** Episode closure counts MET windows (§6.12); windows measured
   before the deploy, on the configuration that breached, can count towards closing the episode the deploy was meant
   to repair. (A rollback after a failed recovery is also unspecified; it is deferred to a later revision, §2.5.)

## 2. Design

### 2.1 The agent head (normative)

Each (agent, deployment environment) has a **head**: the configuration fingerprint serving production and a
**generation**, a non-negative integer. Every head move (deploy, rollback) increases the generation by exactly 1.
The head is platform state, not part of a module; this RFC fixes the properties TVL relies on.

### 2.2 Acceptance record (`tvl-release-acceptance/1`)

A closed record, hosted, with no customer content:

| Field | Type | Meaning |
|---|---|---|
| `format` | `"tvl-release-acceptance/1"` | |
| `acceptance_id` | opaque id | unique |
| `agent_ref`, `environment_ref` | opaque refs (the RFC 0003 §8.2 token-map references, never the environment label) | the head this acceptance may move |
| `occurrence` | closed record | (response ref, rule ref, scope kind, scope ref, occurrence j) of the deploy occurrence (RFC 0003 §7.6 item 1), all as hosted opaque references |
| `candidate_fingerprint` | fingerprint | the configuration accepted |
| `gate_result_digest` | `sha256:` digest | the promotion-gate result the approver saw |
| `contract_digest` | `sha256:` digest | the contract under which the gate ran |
| `holdout_digest` | `sha256:` digest, optional | RFC 0008 holdout identity, when the module declares one |
| `expected_head_generation` | non-negative integer | the generation the approver saw; the deploy writes only if the head is still at it |
| `rollback_target` | fingerprint | the head fingerprint the approver saw; MUST equal the head fingerprint at `expected_head_generation`. It binds the head this acceptance replaces; TVL 1.7 defines no rollback that uses it (§2.5) |
| `repairs_episode` | opaque ref, optional | the episode this release was deployed to repair (present when the occurrence's scope is an episode) |
| `approver_ref` | opaque ref | the person; their authority is checked by the platform at the time of the effect |
| `decision` | `"accept" | "reject"` | |
| `decided_at`, `expires_at` | UTC instants | `expires_at − decided_at ≤ 7 days`; the record is usable only for an effect at t with `decided_at ≤ t < expires_at` |

A `reject` record is subject to the same authentication, approver-authority and binding checks as an `accept` (§2.3);
a matching, valid `reject` closes the deploy occurrence without a deploy, is consumed like an accept (it never decides a second occurrence), and nothing in production changes. A record that
fails any check is ignored and recorded as `acceptance_invalid`.

### 2.3 Deploy semantics (normative refinement of RFC 0003 §7.6 items 2–3)

Under `approval: human`, a deploy occurrence takes effect only with an authenticated `accept` record whose `agent_ref`,
`environment_ref`, `occurrence`, `candidate_fingerprint`, `gate_result_digest` and `contract_digest` equal the
occurrence's (and `holdout_digest` its bundle's, when declared), that is usable at the effect time (§2.2), and whose
approver is authorized at the time of the effect. The platform then, **atomically** for that (agent, environment) head:
checks that the head generation equals `expected_head_generation` and that the head fingerprint equals
`rollback_target`; writes the candidate as head with generation + 1; consumes the record. If the
generation differs, nothing is written and the occurrence finishes as `deploy_refused` (RFC 0004 outcome) with reason
`stale_generation`. A consumed record never authorizes a second write. Under `approval: standing`, the grant record of
RFC 0003 §7.6 item 2 carries the same fields, `expected_head_generation` included.

### 2.4 Generation-scoped recovery (`closure_scope`)

```ebnf
episode = rec("closure_windows": pos_int, "closure_max_age_hours": pos_int,
              ["closure_scope": "any_generation" | "since_head_move"]) ;   (* default any_generation *)
```

Window reports carry `head_generation`, the generation that served the window's units. A window whose units span two
generations reports the later one and is UNKNOWN(mixed_generation) for closure under `since_head_move`. Under
`since_head_move`, only windows whose generation is greater than the episode's opening generation count towards
closure and towards `recovery_recovered`. So an episode is closed only by evidence about a configuration that moved the
head after it opened. `any_generation` keeps RFC 0003 meaning, which already requires `closure_windows` **consecutive** MET windows (RFC 0003 §6.12); the redelivery and gap rules of RFC 0011 §2.13 items 8–9 apply under both scopes.

**Counting.** All instants are whole seconds and windows are half-open `[start, end)` (RFC 0011 §2.13 items 8 and 12). A
window is *mixed* when the head moved inside it (the head generation at its start differs from the head generation at
its last second), or when its reported `head_generation` differs from the head generation at its start. A head
installed exactly at `end` did not serve the window. Closure under `since_head_move` needs `closure_windows`
**consecutive** qualifying windows of **one and the same** generation, where a qualifying window is MET, not mixed, and
of a generation greater than the opening generation. Any other window — BREACHED, UNKNOWN, mixed, or of an older
generation — resets the count, and a qualifying window whose generation differs from the previously counted window's
restarts the count at one: a generation change resets progress, so evidence about two different later configurations
never adds up.

**Opening generation.** The opening generation of an episode is the greatest generation that served the BREACHED window
that opened it, that is, the head generation at that window's last second. It is *not* the head generation at the
instant the breach report arrives: a report delivered after a deploy still names the configuration that breached, so a
later generation can close the episode.

### 2.5 Rollback of a release (deferred)

Release rollback is **not part of TVL 1.7**. An earlier draft added `target: release_rollback_target` for a `rollback`
rule on `recovery_overdue`, resolved to the `rollback_target` of the release that repaired the overdue episode. That
design contradicts itself. `rollback_target` is the head fingerprint at `expected_head_generation` (§2.2), which is the
configuration that was serving when the episode breached, and RFC 0011 §2.13 item 5 holds any target that breached in
an open episode. In the flow the rule exists for (a configuration breaches, an episode opens, a repair is deployed, the
episode is still open when recovery is overdue) the bound target is always one that breached in an open episode, so the
rollback could never take place. A later revision will define release rollback together with a target that is eligible
by construction (for example a configuration certified before the episode) and the positive eligibility evidence it
needs (formerly RFC 0011 §2.13 item 11).

In 1.7 a rule with `target: release_rollback_target` is rejected with `release_rollback_deferred`. Other rollback
targets (`last_certified`, a certified fingerprint) keep their RFC 0003 meaning. The `rollback_target` field of the
acceptance record stays: it binds the head the approver saw (§2.2, §2.3), which keeps an acceptance from being applied
to a different production state.

### 2.6 Diagnostics

| Code | Sev | Condition |
|---|---|---|
| `release_rollback_deferred` | E | `target: release_rollback_target` (release rollback is deferred out of TVL 1.7, §2.5) |
| `acceptance_record_invalid` | E | a `tvl-release-acceptance/1` document fails its schema or `expires_at − decided_at > 7 days` (tool `tvl-validate-acceptance`) |

## 3. Compatibility

Conservative: `closure_scope` defaults to `any_generation`, the RFC 0003 meaning; existing deploy approvals that already
bound a generation are conforming. The acceptance record is a new document type with its own schema. Projection: format
/4 (RFC 0011) carries `closure_scope`.

## 4. Semantics and proofs

Formal semantics §16.6–§16.8. Lean, `proofs/TVL/Runtime/Release.lean`:

- `deploy_needs_matching_acceptance` (substantive): in every reachable state each deploy move has an accept with equal
  bindings, usable at the effect time and consumed, and no acceptance wrote twice.
- `since_head_move_closure` (substantive): under `since_head_move`, the closure count never exceeds the number of
  qualifying windows (MET, not mixed, generation above the opening one); windows of old generations alone cannot close.
- By construction, read off the guards of `acceptStep` and `effect`: `consumed_record_writes_nothing`,
  `stale_acceptance_writes_nothing`, `stale_generation_refused` (a generation mismatch writes nothing),
  `write_advances_head` (a write moves the head by exactly one generation), `old_generation_resets`,
  `generation_change_resets` (under `since_head_move` a qualifying window of a generation different from the last
  counted one restarts the count at one) and `window_redelivery_noop`.

Not proved in Lean: signature verification and approver roles, `closure_max_age_hours`, the static diagnostics, and that
the Python reference implements these definitions; these are checked by the conformance cases of §5.

Release rollback has no statement in 1.7 (§2.5).

## 5. Conformance

Acceptance documents: valid accept, valid reject, expired, over-long expiry, unknown field. Semantic traces: (1) valid
acceptance advances the head once, a redelivery writes nothing; (2) an acceptance for generation g after another deploy
moved the head to g+1 is refused with `stale_generation`; (3) a reject closes the occurrence without a write; (4) under
`since_head_move`, MET windows from the old generation do not close the episode, MET windows from the new generation do;
(5) a head move inside a window makes that window mixed, whether the report names the later or the starting generation;
(6) a breach report delivered after a deploy opens the episode at the breaching generation, and the newer generation
closes it; (7) two consecutive MET windows of different later generations do not close the episode, two of one
generation do; lints: one case per diagnostic, including `release_rollback_deferred` for every former form of the
rollback target.

## 6. Alternatives considered

1. **Leave the record to profiles.** Rejected: a recorded human acceptance for every release is only checkable across
   platforms if the record is fixed.
2. **Generation-free compare (fingerprint compare).** Rejected: an ABA sequence (A → B → A) would pass.
3. **Automatic rollback to the pre-release head.** Rejected for 1.7 (§2.5): the pre-release head is the configuration that
   breached, so it can never be an eligible target while the episode is open. Restoring a configuration without a
   person is also a production change; a later design must say who authorizes it.

## 7. Open questions

1. Approver authority model (roles) is platform-defined; should TVL name a minimum (two-person rule for `critical`)?
2. Expiry bound: is 7 days the right maximum lifetime of an acceptance, and should a module be able to shorten it?
3. Release rollback (§2.5): which configuration is a sound target, and which evidence marks it eligible?
