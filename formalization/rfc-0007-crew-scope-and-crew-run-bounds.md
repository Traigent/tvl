# RFC 0007 — Crew Scope and Crew-Run Bounds: ownership metadata, per-run limits and a draft `halt_crew`

| | |
|---|---|
| **Status** | **DRAFT** — not accepted; syntax, codes and meaning may change before acceptance. `halt_crew` (§2.5) is a separately pending ruling. |
| **Target language version** | TVL 1.7 (conservative extension of 1.6; RFC 0006 is itself a draft, so the version number is provisional) |
| **Tracking** | link to the RFC pull request (to be added when opened) |
| **Builds on** | RFC 0001 (Accepted; ownership `scope`), RFC 0003 and RFC 0004 (Accepted; requirements, monitors, responses, local guards), RFC 0005 (Accepted; aggregates). Related, not required: RFC 0006 (Draft, branch `rfc/0006-tvl-1-6`; `halt_fleet`) |
| **Companion** | formal semantics §12 (runtime) would gain a crew-run section if accepted; none is written here |
| **Conformance** | none yet; proposed case names in §5 |
| **Implementation status** | Proposed specification only. No parser, evaluator, lint or controller is claimed. |

Numbering note: the next unused number on `main` is 0006, which an open draft branch already uses; 0007 is proposed and is confirmed in review (`formalization/README.md`, Numbering and review).

## 1. Motivation

A *crew* is a set of agents (or in-function units) that cooperate on one job: roles pass work to each other (a *handoff*) inside one *crew run* (one end-to-end execution for one input). Today TVL can bound one agent's rate, cost or tool calls (RFC 0003, RFC 0005) and can say who owns a declaration (RFC 0001 `scope`: `node`, `agent`, `workflow`). It cannot say:

- "this declaration belongs to crew C, role R" (ownership of a cooperating group), or
- "no single crew run may make more than 12 handoffs, loop back into a role more than 3 times, or cost more than 2.50 USD".

Per-agent bounds miss the failure that matters: each agent stays within its own limit while the group loops, because the cost is in the cycle, not in any member. Example: a planner and a critic hand a draft back and forth; every call is cheap and each agent's own daily bound holds, but one input consumes the budget of a hundred.

## 2. Design

All additions are sealed and require `tvl_version: "1.7"`. Omission is `runtime_version_required`; a lower declaration is `declared_version_below_constructs`, as in RFC 0005 §2.1.

### 2.1 `scope.crew` and `scope.role` (metadata only)

```ebnf
Scope ::= ⟨ node? : Ident, agent? : Ident, workflow? : Ident, crew? : Ident, role? : Ident ⟩   (* RFC 0001 §3.3 + 2 fields *)
```

Handle for the base: `formalization/rfc-0001-knob-bindings-cvars-policies.md:136` and `spec/grammar/tvl.schema.json:419-429` (`Scope`, `additionalProperties: false`, identifier pattern without hyphens) at `674d9aa`. Both new fields use the same identifier pattern.

Normative: like the existing fields, `crew` and `role` are informational ownership metadata (RFC 0001 §3.7(6)); they change no verdict, no validity and no response authority. They are **opaque references**: a producer MUST write a reference issued by its platform (for example a crew reference and a role token), and MUST NOT write a customer-chosen name, because TVL documents are stored, diffed and shared, and a name can carry text. The language cannot check this; it is a producer obligation, stated here so reviewers can hold producers to it. `role` without `crew` is the warning `scope_role_without_crew`. `invalid_scope` (RFC 0001) applies to the new fields' lexical domain.

### 2.2 Crew-run bound requirements

```ebnf
req       = …RFC 0003/0005 variants… | crew_req ;                                            (* SEALED *)
crew_req  = rec("name": ident, "kind": "crew_bound", "unit": "crew_run", "crew": ident,
                "metric": "handoffs" | "role_loops" | "cost_usd",
                ["source_digest": fp], "bound": rec("lte": number)) ;
decision  = …earlier variants… | rec("method": "exact_crew_run_v1") ;
```

`crew` is the reference of the crew the bound governs. `source_digest` is required exactly for `cost_usd` and forbidden otherwise; as in RFC 0005 §2.1 it is an opaque commitment to the declared cost source contract. Domains of `lte`: `handoffs` integer ≥ 1; `role_loops` integer ≥ 0; `cost_usd` finite nonnegative exact decimal (USD, per crew run). Equality meets the bound. Violations: `runtime_crew_bound_out_of_range`.

Metric meanings, per crew run, each counted once per distinct record (replays and duplicate deliveries add nothing):

1. `handoffs`: the number of requested handoffs, keyed by `(crew_run_id, hop_seq)`, counted when the transfer is requested, before the receiving role runs. The request that makes the count exceed `lte` is the breach.
2. `role_loops`: the number of entered handoffs whose receiving role was already entered earlier in the same run (the entry role counts as entered at run start). A→B→A is one loop. A retry of one invocation is not a handoff and adds nothing.
3. `cost_usd`: the sum of the exclusive (self) cost of every member execution in the run, exact decimal USD under the source contract. Costs are nonnegative. An unknown cost is never read as zero.

**Attempted versus entered.** A handoff has two recorded moments: *requested* (the sender asks to transfer, before dispatch) and *entered* (the receiving role actually starts). A request that is denied, dropped or times out is requested but never entered. Rules: `handoffs` counts requested transfers, so a denied request still counts and the count is the number of requests the sender made; `role_loops` counts entered roles only, so a request that never enters cannot add a loop; `cost_usd` counts executions that started. The sender allocates the transfer's `hop_seq` from the hop counter it carries, unique per run; a replay of the same `(crew_run_id, hop_seq)` changes nothing. Concurrent transfers that receive the same `hop_seq` are one transfer.

The bound limits **recorded** quantities; it is not a bound on provider invoices or on damage done by an already-dispatched call.

### 2.3 Monitor profile and verdicts

A `crew_bound` requirement is checked by a primary monitor with `evidence: {source: customer_side, deployment_environment: …}` and `decision: {method: exact_crew_run_v1}`. `window`, `sampling`, `burn`, `episode`, `min_samples`, `profile: backend_v1` and statistical decision fields are forbidden: evaluation is per run, over every run (census), not over windows (`runtime_invalid_profile`).

Verdict per (monitor revision, crew run):

| State | Verdict |
|---|---|
| a counted quantity exceeds `lte` at any time | `BREACHED`, at that moment, final for the run |
| run ended, all quantities within `lte`, evidence complete | `MET` |
| run ended, within `lte`, but a required record is missing or a cost is unknown | `UNKNOWN(incomplete)` |

A partial sum of known nonnegative costs that already exceeds the bound is `BREACHED` even if other costs are unknown. This is breach-first and applies only to this new kind; it does not change RFC 0005 §14 precedence for existing aggregates (open question 3).

New event `crew_run_breached`, scope kind `crew_run`, keyed by contract, monitor revision, crew and `crew_run_id`. Exactly one per run and monitor; replays emit nothing. It has no episode, persistence or recovery meaning. Only `notify` and `halt_crew` may consume it.

### 2.4 Interaction with agent-level scope and other controls

- `crew_bound` and `scope.agent` are independent. A role bound to an agent keeps every agent-level requirement, monitor and guard; a crew bound neither relaxes nor replaces them. Stricter control wins; no response releases another control.
- `scope.crew` on an agent-level declaration does not turn it into a crew bound and does not make the agent's monitors evaluate per run.
- If a requirement carries `scope.crew` and its `crew` field differs, lint `crew_scope_mismatch` (warning).
- A crew run that cannot be attributed to a declared crew (unresolved reference) is not evaluated by this kind; an implementation that cannot attribute runs MUST NOT report `MET` for them.

### 2.5 `halt_crew` — DRAFT, ruling pending

```ebnf
action_addition = "halt_crew" ;
crew_trigger    = rec("monitor": ident, "event": "crew_run_breached") ;
halt_crew_rule  = rec("id": ident, "trigger": crew_trigger, "do": "halt_crew",
                      "approval": "none", "on_check_error": "block") ;
```

Proposed normative effect, local and customer-side (the same family as `block_action`/`halt_unit`, RFC 0003 guards): for that `crew_run_id` only, the controller denies every further handoff and every further member dispatch. Already-dispatched external operations may complete. It does not affect other runs, other crews, the agents involved, or any fleet-level control; it kills no process and changes no credential. The halted run is terminal and records a closed halt reason; there is no latch beyond the run and no resume.

Fail-closed rules (proposed): `approval` is `none` (a per-run automatic stop; `standing` and `human` are refused). `on_check_error` is required and `allow` is refused (`response_halt_crew_on_check_error_allow`): if the controller cannot establish the counters, the crew binding or the run identity, further handoffs are denied. No repeat, `persist`, target, severity or fallback fields. An implementation that cannot enforce `halt_crew` MUST refuse to activate a contract containing it (`unsupported_construct`) and MUST NOT degrade it to `notify`.

Halt reason mapping. When a run is halted by `halt_crew`, the implementation records a closed halt reason derived from the breached metric: `handoffs` gives `handoffs_exceeded`, `role_loops` gives `role_loops_exceeded`, `cost_usd` gives `budget_exceeded`. These names are this RFC's proposal; the implementing platform's schema enum is authoritative for the stored values, and a mismatch is resolved there, not here. No free-text reason is recorded.

Fail-closed precedence. When a `halt_crew` rule with `on_check_error: block` is active for a crew, a handoff whose identity cannot be established (missing crew binding, missing role identity, unresolved run) is denied. This overrides any telemetry rule that would drop attribution and let the work continue: dropping telemetry never overrides an active enforcement deny. Without an active `halt_crew` rule, missing identity only drops attribution and the work continues.

Relation to `halt_fleet` (RFC 0006 draft): different scope and strength. `halt_crew` is bounded to one run and self-expiring; it neither requires nor implies a fleet latch; both can be present and the stricter control wins.

### 2.6 Example

```yaml
# Fragment; references are opaque platform-issued values, not names.
tvl_version: "1.7"
tvars:
  - name: planner_temperature
    scope: { crew: crew_9a2f4c7e1b3d5f60a8c2e4d6f8b0a1c3, role: rtk_q4zt7c2wmhxbv3jkdsa5npe6rf }
requirements:
  - { name: run_handoffs, kind: crew_bound, unit: crew_run, crew: crew_9a2f4c7e1b3d5f60a8c2e4d6f8b0a1c3,
      metric: handoffs, bound: { lte: 12 } }
  - { name: run_loops, kind: crew_bound, unit: crew_run, crew: crew_9a2f4c7e1b3d5f60a8c2e4d6f8b0a1c3,
      metric: role_loops, bound: { lte: 3 } }
  - { name: run_spend, kind: crew_bound, unit: crew_run, crew: crew_9a2f4c7e1b3d5f60a8c2e4d6f8b0a1c3,
      metric: cost_usd, source_digest: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      bound: { lte: 2.5 } }
monitors:
  - name: run_loops_prod
    requirement: run_loops
    phase: runtime
    evidence: { source: customer_side, deployment_environment: production }
    decision: { method: exact_crew_run_v1 }
responses:
  - { id: stop_looping_run, trigger: { monitor: run_loops_prod, event: crew_run_breached },
      do: halt_crew, approval: none, on_check_error: block }
```

## 3. Compatibility

Additive. `scope` gains two optional fields; a 1.0–1.6 document without them keeps its meaning, and the added fields are metadata. The new requirement kind, decision method, event, action and diagnostics appear only in documents that declare `tvl_version: "1.7"`; older readers refuse them through closed shapes or `unsupported_construct`, never by ignoring them. In `tvl_pack`, `crew_bound` and `halt_crew` are refused with `unsupported_construct` until a separate design (as RFC 0005 does for its additions). No existing diagnostic changes meaning. Promotion does not evaluate crew bounds and cannot treat them as deployment evidence.

## 4. Semantics and proofs

No formal-semantics text or Lean update is written. Open obligations: per-run counter definitions as a function of the recorded handoff and execution records; monotonicity (counts never decrease, so `BREACHED` is stable); and conservative embedding of 1.6 documents. No theorem is claimed.

## 5. Conformance

Proposed cases (names only, none exist): `crew-scope-metadata-only`, `crew-scope-role-without-crew`, `crew-bound-handoffs-out-of-range`, `crew-bound-cost-needs-source-digest`, `crew-bound-window-forbidden`, `crew-bound-loop-counting` (A→B→A is 1; retry adds 0), `crew-bound-unknown-cost-breach-first`, `halt-crew-on-check-error-allow-rejected`, `halt-crew-unsupported-refused`, `halt-crew-missing-identity-denies`, `crew-bound-requested-not-entered` (denied request counts for handoffs, adds no loop), `old-version-refuses-crew-bound`. New diagnostics: `scope_role_without_crew` (W), `crew_scope_mismatch` (W), `runtime_crew_bound_out_of_range` (E), `response_halt_crew_on_check_error_allow` (E).

## 6. Alternatives considered

- Reuse `halt_unit` with a crew-run unit: rejected for now; it ties a per-run stop to `unit_violation` patterns and would blur what a run is.
- Make `scope.crew` enforcing: rejected; RFC 0001 keeps `scope` informational and enforcement belongs in requirements.
- Per-agent bounds only: misses cycles (§1).
- Window-based crew rates: deferred; a runaway run needs an in-run stop, not a daily rate.

## 7. Open questions

1. **`halt_crew` ruling (pending).** Whether `halt_crew` is accepted at all, and with the fail-closed rules above, is undecided and needs the maintainers' decision. Until then §2.5 is a draft that may be dropped without affecting §§2.1–2.4.
2. Count `handoffs` at request (proposed) or at completion.
3. Breach-first on partial known cost (proposed) versus RFC 0005's `UNKNOWN(incomplete)` precedence.
4. Nested crews: does a nested crew run count toward the parent's bounds, or is it a separate run?
5. Should `role_loops` be per role (`max per role`) in addition to the run total?
6. Is `approval: none` acceptable for an automatic per-run stop, or should a human-approved mode exist?
7. Should `scope.crew`/`scope.role` values be validated against a reserved prefix grammar to discourage names?
