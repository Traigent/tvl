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
   to repair. Rollback after a failed recovery has no bound target.

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
| `rollback_target` | fingerprint | the configuration a rollback of this release restores; MUST equal the head fingerprint at `expected_head_generation` |
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

Window reports carry `head_generation`, the generation that served the window's units (a window whose units span two
generations reports the later one and is UNKNOWN(mixed_generation) for closure under `since_head_move`). Under
`since_head_move`, only windows whose generation is greater than the episode's generation at opening count towards
closure and towards `recovery_recovered`. So an episode is closed only by evidence about a configuration that moved the
head after it opened. `any_generation` keeps RFC 0003 meaning, which already requires `closure_windows` **consecutive** MET windows (RFC 0003 §6.12); the redelivery and gap rules of RFC 0011 §2.13 items 8–9 apply under both scopes.

**Counting.** A window is *mixed* when its reported `head_generation` differs from the head generation at the window's
start. Closure under `since_head_move` needs `closure_windows` **consecutive** qualifying windows (MET, not mixed, and of
a generation greater than the opening generation); any other window — BREACHED, UNKNOWN, mixed, or of an older
generation — resets the count. The opening generation is the head generation at the instant the episode opens.


### 2.5 Rollback of a release

A `rollback` rule with `target: release_rollback_target` (new target value) is allowed only on `recovery_overdue` of a
`recovery_time` requirement whose `of` monitor has `closure_scope: since_head_move`
(`release_rollback_needs_since_head_move`, `release_rollback_wrong_trigger`). Its target is resolved from the
**release that repaired the overdue obligation's episode**: the consumed accept record whose `repairs_episode` is that
episode and whose write is the current head. If there is none (the head was moved since by another release or
rollback), the rollback does not take place and is recorded as `rollback_no_bound_release`. The bound
`rollback_target` must still pass every eligibility check of RFC 0003 §7.2 at the time of the effect — in particular it
is not a configuration that breached in an open episode; otherwise the rollback holds (`held(target_ineligible)`) and
the rule's outcome is notified, never substituted by another target. Its effect uses the same atomic compare: expected
generation = the generation written by that release. A rollback is terminal for its episode's repairs: no `optimize`
of the same episode starts after it (the episode stays open until closed by §2.4). Rolling back a rollback is not
expressible.

### 2.6 Diagnostics

| Code | Sev | Condition |
|---|---|---|
| `release_rollback_needs_since_head_move` | E | `target: release_rollback_target` without `closure_scope: since_head_move` on the trigger's monitor |
| `release_rollback_wrong_trigger` | E | `target: release_rollback_target` on a trigger other than `recovery_overdue` |
| `acceptance_record_invalid` | E | a `tvl-release-acceptance/1` document fails its schema or `expires_at − decided_at > 7 days` (tool `tvl-validate-acceptance`) |

## 3. Compatibility

Conservative: `closure_scope` defaults to `any_generation`, the RFC 0003 meaning; existing deploy approvals that already
bound a generation are conforming. The acceptance record is a new document type with its own schema. Projection: format
/4 (RFC 0011) carries `closure_scope` and the new rollback target.

## 4. Semantics and proofs

Formal semantics §16.6–§16.8. Lean, `proofs/TVL/Runtime/Release.lean`:

- `deploy_needs_matching_acceptance`: every head move by a deploy is preceded by exactly one consumed accept record with
  equal bindings.
- `stale_acceptance_writes_nothing`: if the head moved after the approver's generation, the deploy writes nothing.
- `since_head_move_closure`: under `since_head_move`, no window from a generation at or below the opening generation
  contributes to closure.
- `no_rollback_of_rollback`.

## 5. Conformance

Acceptance documents: valid accept, valid reject, expired, over-long expiry, unknown field. Semantic traces: (1) valid
acceptance advances the head once, a redelivery writes nothing; (2) an acceptance for generation g after another deploy
moved the head to g+1 is refused with `stale_generation`; (3) a reject closes the occurrence without a write; (4) under
`since_head_move`, MET windows from the old generation do not close the episode, MET windows from the new generation do;
(5) recovery overdue → rollback restores `rollback_target`, then no further optimize in the episode; lints: one case per
diagnostic.

## 6. Alternatives considered

1. **Leave the record to profiles.** Rejected: the owner rule that every release has a recorded human acceptance must be
   checkable across platforms.
2. **Generation-free compare (fingerprint compare).** Rejected: an ABA sequence (A → B → A) would pass.
3. **Automatic rollback without acceptance.** Kept bounded: rollback restores only the target bound by the human who
   accepted the release, so no new configuration enters production without a person.

## 7. Open questions

1. Approver authority model (roles) is platform-defined; should TVL name a minimum (two-person rule for `critical`)?
2. Expiry bound (7 days) — owner input.
