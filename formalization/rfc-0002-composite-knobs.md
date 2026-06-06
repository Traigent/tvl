# RFC 0002 — Composite Knobs: a sealed control-flow algebra and a named pattern catalog

| | |
|---|---|
| **Status** | **DRAFT v2** — under cross-model review; owner acceptance pending |
| **Target language version** | TVL 1.2 (conservative extension of 1.1) |
| **Tracking** | `FR-TVL-COMPOSITE-KNOBS-V1` · ChangeSession `cs_aef1b9d2edfa5200` |
| **Builds on** | RFC 0001 (ACCEPTED): one-Knob model, cvars, certificates, policies, strict promotion |
| **Downstream gate** | Acceptance of this RFC + green model checking unblock the validators packet and all SDK implementation |

## 1. Motivation

Agentic systems repeat a small number of control-flow patterns whose variables
travel together: a *cascade* runs a cheap arm and escalates past a calibrated
gate; an *ensemble* fans out `k` samples and aggregates; a *self-debug loop*
generates, critiques, and revises under a stop rule. Today TVL can declare the
individual variables (RFC 0001: tvars, cvars, one cascade policy strategy) but
has no construct that says *"these members form one reusable pattern with its
own dependency structure, calibratable surface, cost model, and telemetry."*
Each consumer rebuilds the bundle by convention; conventions drift.

This RFC introduces the **CompositeKnob**: a named bundle of member variables
and policies with a declared control-flow shape. The design is two-layered
(design review 2026-06-06; codex gpt-5.5 + gemini concurring):

- a **sealed structural algebra** — three disjoint **structural constructors**
  (`CompositeKind ∈ {cascade, ensemble, loop}`), closed under nesting — that
  machines consume: the optimizer's projection, the certificate coverage fold,
  the freshness dependency compilation, cost models, and the model checker;
- an **open, curated pattern catalog** — procedurally named factories
  (`binary_cascade`, `n_cascade`, `self_consistency`, `best_of_n`,
  `self_debug`, `self_refine`) — that humans consume: each pattern is a
  **macro** that expands deterministically into the algebra, stamping every
  emitted node with provenance. Patterns are never subclasses; the algebra
  never grows because a pattern was added.

The split resolves the classic tension: disjointness where it buys theorems
and fail-closed governance; procedural, plural naming where adoption lives.

## 2. Scope freeze (Phase 0)

**In scope for TVL 1.2 and this program increment:**

- the sealed three-constructor algebra with nesting closure (§3.2);
- per-constructor calibratable surfaces (§3.3) and cost models (§3.4);
- dependency-coverage compilation onto leaf TVARs (§3.5);
- the certificate coverage fold extending RFC 0001 §3.6 strict promotion
  (§3.6);
- the pattern-catalog contract and the v1 catalog (§3.7);
- the `Loop → NCascade` bounded-unroll **compilation relation** (§3.8);
- a `composites:` surface block as a conservative grammar extension (§3.9);
- subsumption of `policies.strategy: cascade` by exact expansion mapping (§4).

**Explicitly deferred** (out of scope for TVL 1.2 and this increment):

- any wire/schema crossing: composites do not ride the typed session wire,
  TraigentSchema is untouched, backend/FE see no new fields (contract
  decision v1; a content-free composite summary is a recorded revisit
  trigger);
- CVAR→CVAR dependencies (`depends_on` still names TVARs only — the RFC 0001
  deferral stands; composite structure compiles to leaf-TVAR coverage
  obligations, §3.5);
- in-loop CVAR re-fitting and CVAR optimizers (RFC 0001 deferrals stand);
- learned routers / dispatch functions as calibrators (would extend the
  calibrator registry, not this algebra);
- selective composite consumption (per-candidate enable/disable of declared
  composites — v1 uses the conservative all-roots rule, §3.6);
- a pattern marketplace or third-party catalog mechanism (the v1 catalog is
  in-repo and curated);
- changes to configuration documents (`tvl-configuration.schema.json`
  untouched, as in RFC 0001).

## 3. Formal model (Phase 1)

### 3.1 What a composite is — and is not

RFC 0001's **one-Knob model is unchanged**: every configuration variable is a
knob with exactly one typed binding — `Tuned | Fixed | Calibrated` — and the
binding partition `N = N_T ⊎ N_F ⊎ N_C` is untouched. A **CompositeKnob is
not a binding kind**: it is a **namespace/expansion/provenance unit** that
*groups* member knobs and gate declarations under a declared control-flow
shape. A composite never binds, carries, or defaults a value; a module that
attempts to bind a value on a composite is rejected
(`composite_binds_value`).

Composite names form a new declaration class `N_X` in the **same scoped
namespace** as tvars/cvars/policies: shadowing across classes is rejected
exactly as in RFC 0001 P6 (`binding_partition_collision` generalizes;
surfaced as `composite_shadows_name`, with `duplicate_composite` for
collisions within `N_X`). `N_X` never enters `Γ`, `Config(Δ, E_τ)`, `F^str`,
or the optimizer projection `Σ` (§3.2 of RFC 0001 is unchanged): the
optimizer sees member TVARs individually; the composite is invisible to
search exactly as cvars are (Property P2/P5 preserved).

### 3.2 The sealed algebra

```
Composite ::= ⟨ name : Ident,
                kind : CompositeKind,            (* CLOSED registry *)
                body : Cascade | Ensemble | Loop,(* discriminated by kind *)
                scope? : Scope,                  (* RFC 0001 §3.7 scope_spec,
                                                    same semantics as PolicyDecl *)
                parameters? : Map,               (* opaque operational map —
                                                    OUTSIDE the P8 surface, exactly
                                                    as PolicyDecl.parameters *)
                provenance? : Provenance ⟩       (* closed shape, §3.7 *)

CompositeKind ::= cascade | ensemble | loop      (* SEALED: a fourth kind is a
                                                    new RFC, not a registry entry *)

Arm ::= stage(StageRef, tuned_params : Ident*)   (* TAGGED. tuned_params declares
                                                    the TVARs parameterizing this
                                                    opaque stage — possibly empty;
                                                    the author's declaration, since
                                                    stages are opaque (§3.5) *)
      | composite(CompositeName)                 (* TAGGED nesting reference;
                                                    exact-match into N_X *)

Cascade   ::= ⟨ arms : Arm+,                     (* |arms| = m ≥ 1 *)
                gates : GateDecl*,               (* |gates| = m − 1 *)
                placement : pre | post ⟩         (* DEFAULT post *)

Ensemble  ::= ⟨ arms : Arm+,                     (* |arms| ≥ 1 *)
                cardinality? : Ident,            (* REQUIRED iff |arms| = 1
                                                    (sampling form); FORBIDDEN if
                                                    |arms| > 1 (committee form).
                                                    Namespace ref → TVAR or CVAR
                                                    of TVL type int; resolved
                                                    values MUST satisfy k ≥ 1 *)
                aggregate : AggregateDecl ⟩

Loop      ::= ⟨ body : Arm,
                state_keys : Ident*,             (* the DECLARED threaded-state
                                                    keys; [] ⟺ body treated pure.
                                                    Keys are content-free
                                                    identifiers; the runtime
                                                    supplies state operationally
                                                    (environment.bindings
                                                    precedent) *)
                stop : StopDecl,
                max_iters : ℕ≥1 ⟩                (* REQUIRED bound — totality *)

GateDecl  ::= ⟨ kind : margin_below | signal_below,   (* v1 registry *)
                threshold : Ident,               (* MUST resolve to a CVAR
                                                    (kind-checked), as RFC 0001 §3.8 *)
                signal? : SignalSourceRef ⟩      (* REQUIRED iff kind=signal_below *)

AcceptDecl ::= ⟨ kind : stat_at_least,           (* v1 registry — acceptance
                                                    direction is ≥, deliberately
                                                    DISTINCT from cascade
                                                    escalation's < (no semantic
                                                    drift between the two) *)
                 stat : vote_margin | vote_agreement,
                 threshold : Ident ⟩             (* MUST resolve to a CVAR *)

AggregateDecl ::= ⟨ kind : majority_vote | judge_max,  (* v1 registry *)
                    judge? : Arm,                (* REQUIRED iff kind=judge_max;
                                                    stage- or composite-tagged *)
                    accept? : AcceptDecl ⟩

StopDecl  ::= ⟨ kind : signal_accept | external_accept | exhausted,
                threshold? : Ident,              (* REQUIRED iff kind=signal_accept:
                                                    MUST resolve to a CVAR *)
                signal? : SignalSourceRef,       (* REQUIRED iff kind=signal_accept;
                                                    a function of state_keys only *)
                predicate? : Ident ⟩             (* REQUIRED iff kind=external_accept:
                                                    OPAQUE runtime predicate id,
                                                    StageRef-style — outside P8 *)

SignalSourceRef ::= Ident    (* a calibration-source id from the SAME operational
                                registry RFC 0001 cvars use
                                (calibration_source_id, §3.5 there): an
                                implementation-defined identifier, opaque to the
                                module namespace — NOT a new declaration surface *)
```

**Well-formedness (statically checked; error codes in §3.11):**

1. `kind` ∈ the closed registry (`unknown_composite_kind`); exactly the body
   fields of the declared kind are present — unknown or cross-kind fields
   reject (closed shapes, exact diagnostics).
2. Cascade arity: `|gates| = |arms| − 1`; the degenerate `m = 1` cascade has
   no gates and always returns its arm (RFC 0001 rule carries over).
   `arms` must be non-empty for every constructor (`empty_arms`).
3. **Arm resolution is tag-driven and unambiguous**: `composite(x)` must
   resolve (exact match, RFC 0001 §3.7) into `N_X`
   (`missing_composite_ref`); `stage(s)` is opaque and never consults the
   namespace. In the surface syntax (§3.9) a BARE identifier in an arm
   position is ALWAYS a stage (back-compatible with `policies.stages`);
   nesting REQUIRES the tagged form. A bare arm identifier that collides
   with a declared composite name is rejected (`ambiguous_arm`) rather than
   silently resolved.
4. The `composite(·)` reference graph over `N_X` must be acyclic
   (`composite_cycle`); composition depth is therefore finite. Nesting is
   the ONLY composition mechanism — DAG-shaped configurations are the
   **closure of nesting**; there is no fourth "DAG kind".
5. `placement: pre` requires EVERY gate to be `signal_below` with a declared
   signal (`pre_gate_requires_signal`); `margin_below` is valid only with
   `placement: post` (it consumes the executed arm's vote statistics).
6. Gate/accept/stop thresholds resolve to CVARs (kind-checked, reusing
   RFC 0001's gate rule — `missing_ref` family); `stage(·)` duplicates
   within one composite are rejected (`duplicate_stage`).
7. Ensemble cardinality: present iff `|arms| = 1`
   (`cardinality_arity_mismatch`); must reference a TVAR or CVAR whose
   declared TVL type is `int` (`invalid_cardinality_type`); resolution-time
   values `k < 1` are rejection **R9** (`invalid_cardinality_value`),
   extending RFC 0001 §3.4's rejection family.
8. Loop: `stop.signal`, when present, may reference only declared
   `state_keys` inputs (`stop_signal_outside_state`); `max_iters ≥ 1`
   (`invalid_max_iters`).

**Execution semantics.**

- **`placement: post` cascade** is EXACTLY RFC 0001 §3.8 cascade execution
  (normative text incorporated by reference): run arm `i`, vote over `k_i`
  samples, escalate iff `margin < θ_i`; totality/determinism/error rules
  unchanged, including fail-closed propagation of stage exceptions under
  strict modes. Nested-composite arms execute their own semantics and
  contribute their selected output as the arm output.
- **`placement: pre` cascade (dispatch)**: no arm runs before routing. Gates
  are evaluated LEFT TO RIGHT, first match wins:

  ```
  route(x) = arm_j  where  j = min{ i < m : σ_i(x) ≥ θ_i } ∪ {m}
  ```

  Gate `i` asks "is arm `i` adequate for x?" — adequate ⟺
  `σ_i(x) ≥ θ_i` selects `arm_i`; otherwise evaluation proceeds to the next
  gate; `arm_m` is the **fallback arm** and needs no gate. Exactly one arm
  executes. An absent/abstaining signal value is INADEQUATE (routes onward
  — fail-toward-the-stronger-arm); a signal-evaluation exception fails the
  item's evaluation (never silently routes), feeding the fail-closed law
  under strict modes. Each gate may carry a DISTINCT signal; cost
  accounting is per-gate (§3.4).
- **`ensemble`**: in the sampling form (`|arms| = 1`, cardinality `k`), the
  single arm runs `k` times; in the committee form (`|arms| > 1`), each arm
  runs once. Aggregation:
  - `majority_vote`: votes over caller-defined equivalence keys with the
    RFC 0001 tie/abstain rules (deterministic total order over serialized
    keys).
  - `judge_max`: the judge arm is invoked once per candidate output and
    MUST yield a **finite numeric score** (the judge output contract). A
    candidate whose judging raises, or yields NaN/±∞/non-numeric, is
    EXCLUDED from selection; if ALL candidates are excluded the ensemble
    evaluation FAILS (propagates as an evaluation error — never a silent
    pick), feeding the fail-closed law under strict modes. Selection is the
    maximum score; ties break by the RFC 0001 deterministic total order
    over the candidates' serialized equivalence keys.
  - `accept` (optional, either aggregate kind): `stat_at_least` evaluates
    the named content-free vote statistic; failing it is an honest
    no-accept outcome that propagates to the consumer (under strict modes
    it feeds the fail-closed law). The acceptance inequality is `stat ≥ θ`
    — deliberately the OPPOSITE direction of cascade escalation
    (`margin < θ`), and a distinct registry, so the two cannot drift into
    each other.
- **`loop`**: execute `body`; the runtime threads the declared `state_keys`
  (iteration `i+1` observes exactly the keys iteration `i` produced —
  operationally supplied, like stage bindings; an undeclared key is simply
  invisible to `stop`); evaluate `stop`; repeat up to `max_iters`.
  `exhausted` always runs `max_iters` iterations; `signal_accept` stops
  when `σ(state) ≥ θ` (acceptance direction, lint-pinned);
  `external_accept` delegates to an opaque runtime predicate (outside the
  P8 surface, like `parameters`). A body/stop exception fails the item's
  evaluation (no partial-iteration output), feeding the fail-closed law
  under strict modes.

### 3.3 Calibratable surface

Each constructor *defines* which members admit calibration and with what
target-property shape — this is the machine-facing payoff of sealing:

| Constructor | Calibratable members | Target-property shape |
|---|---|---|
| `cascade` (post) | each gate threshold `θ_i` | conditional property of the ACCEPTANCE REGION the gate induces (e.g. `P(arm_i correct │ margin ≥ θ_i) ≥ p`) — exactly RFC 0001 §3.5's per-CVAR scope |
| `cascade` (pre) | each routing threshold `θ_i` | conditional property of the ROUTE the signal induces (e.g. `P(arm_i adequate │ σ_i ≥ θ_i) ≥ p`) |
| `ensemble` | `accept.threshold`; `cardinality` when bound Calibrated | acceptance: `P(aggregate correct │ stat ≥ θ) ≥ p`; cardinality: cost-bounded sufficiency |
| `loop` | `stop.threshold` (signal_accept) | stop adequacy: `P(accepted state meets target │ σ ≥ θ) ≥ p` |

The **claim scope** paragraph of RFC 0001 §3.5 (2026-06-06 clarification)
applies verbatim: each certificate is a per-variable, procedural claim about
the conditional, component-level property the variable controls under the
documented assumptions. **A composite's end-to-end metrics remain
observations** under the promotion judgment; nothing in this RFC creates a
config-level guarantee, and user-facing copy MUST NOT present a composite as
one.

### 3.4 Cost models and compositionality

Each constructor carries a normative expected-cost form over its members,
with nested composites contributing their own cost recursively:

```
cost(stage s)                            = c(s)                  (runtime-supplied)
cost(Cascade_post(a₁..a_m, θ₁..θ_{m−1}))  = cost(a₁) + Σ_{i=1}^{m−1} P(esc₁..esc_i) · cost(a_{i+1})
cost(Cascade_pre (a₁..a_m, σ/θ pairs))    = Σ_{i=1}^{m−1} P(reach gate i) · c(σ_i)
                                            + Σ_{i=1}^{m} P(route = i) · cost(a_i)
cost(Ensemble_sampling(a, k, agg))        = k · cost(a) + c(agg)
cost(Ensemble_committee(a₁..a_j, agg))    = Σ_j cost(a_j) + c(agg)
   where c(judge_max agg) = (candidates evaluated) · cost(judge arm)
cost(Loop(b, stop, K))                    = E[iters] · (cost(b) + c(stop)),  E[iters] ≤ K
```

Escalation/route/stop probabilities are *operational estimates* (observed
telemetry or calibration-split estimates) — the cost model is a structured
estimator, not a guarantee (§3.3 claim scope applies). **Compositionality
(claim C4)**: `cost(X)` for a nested composite arm is the arm's own cost
form — the equations close over the algebra. This is what makes
frontier/constrained search over composites structurally informed instead of
black-box.

### 3.5 Dependency coverage compiled onto leaf TVARs

RFC 0001 defers CVAR→CVAR dependencies; this RFC **keeps that deferral**.
Because StageRefs are opaque, leaf parentage cannot be inferred — it is
**declared**: each stage-tagged arm carries `tuned_params`, the TVARs
parameterizing that stage (the author's knowledge; possibly empty). Define:

```
leafT(stage(s, ps))     = ps
leafT(composite(x))     = ⋃_{a ∈ arms/body/judge(x)} leafT(a)
```

The compilation then emits **coverage OBLIGATIONS over the EXISTING
`depends_on` mechanism** (never automatic edge insertion, never a new
dependency kind):

```
required_parents(θ_i in Cascade_post)  = leafT(a₁) ∪ … ∪ leafT(a_i)
required_parents(θ_i in Cascade_pre)   = leafT(a_i)            (the arm the gate
                                                                 admits; the signal's
                                                                 parents come via the
                                                                 CVAR's own calibration
                                                                 context as in RFC 0001)
required_parents(θ in Ensemble.accept) = ⋃_j leafT(a_j) ∪ leafT(judge if present)
                                          ∪ ({cardinality} ∩ N_T)
required_parents(θ in Loop.stop)       = leafT(body)
```

A new lint (`missing_composite_parent`) checks
`required_parents(θ) ⊆ depends_on(θ)` for every threshold CVAR — purely
static, since both sides are declared identifier sets. `depends_on` entries
themselves remain TVAR-only and remain validated by the RFC 0001
`missing_ref` lint, which stays the **single authority** on entry validity
(claim C6: no rule in this RFC can introduce a non-TVAR edge). The payoff is
that the freshness cascade becomes structural: swap the TVAR assignment
parameterizing an arm, and every gate whose obligation covers that arm reads
stale through the existing `tuned_parent_values` core — by declaration, not
convention.

### 3.6 Certificate coverage fold (extends RFC 0001 §3.6)

```
Cal : Composite → ℘(N_C)
Cal(Cascade(arms, gates, _)) = ⋃ Cal(arms) ∪ { g.threshold : g ∈ gates }
Cal(Ensemble(arms, k, agg))  = ⋃ Cal(arms) ∪ Cal(agg.judge if present)
                               ∪ { agg.accept.threshold if present }
                               ∪ ({k} ∩ N_C)
Cal(Loop(body, stop, _))     = Cal(body) ∪ { stop.threshold if kind=signal_accept }
Cal(stage(·))                = ∅
Cal(composite(x))            = Cal(body(x))
```

**Root consumption (v1, conservative).** The composites a candidate `c`
consumes are the **roots** of the module's `N_X` reference DAG — every
declared composite not referenced as a nested arm of another. v1 has no
selective-consumption mechanism (§2 deferral): all roots are consumed by
every candidate. This is deliberately fail-closed — it can only
over-require certificates, never under-require.

Under `strict(M, c)` (RFC 0001 §3.6, unchanged), `CalibrationPass(c, M)`
extends to require a valid, fresh certificate for **every** CVAR in
`⋃_{r ∈ roots(M)} Cal(r)` in addition to RFC 0001's consumed-CVAR set. The
fold is **fail-closed** (claim C3): any uncertified or stale member ⇒ no
certified selection — never a partial pass, never a silent skip of a nested
level.

### 3.7 The pattern catalog contract

```
Pattern    ::= ⟨ name : Ident,
                 params : ParamSchema,
                 expand : params → Composite ⟩   (* DETERMINISTIC, TOTAL on
                                                    validated params *)

Provenance ::= ⟨ pattern : Ident,                (* the catalog name *)
                 pattern_version? : Ident,
                 param_hash? : Hash,             (* H_c(canonical validated
                                                    params) — raw params NEVER
                                                    serialize *)
                 node_path? : Ident ⟩            (* source-map position within
                                                    the expansion *)
```

A pattern is a **macro**: `expand` emits algebra nodes, every one stamped
with a `Provenance` value. **Provenance is a CLOSED shape** (identifiers
and one canonical hash — no raw-params field, no content-typed field
exists), so it can ride operational metadata and any future content-free
summary without widening the P8 surface; a canary test (sentinel in a
pattern param must never appear in serialized provenance/metadata) is part
of the admission contract. Adding a pattern is an SDK release, not a
language or schema change.

**Admission contract** — a pattern enters the catalog only with ALL of:

1. an expansion into the sealed algebra (no pattern-private node kinds);
2. closed-shape provenance on every emitted node + the P8 canary test
   (sentinel param never serializes);
3. a calibration recipe for every CVAR the expansion introduces (which
   signal, which split, which target-property shape from §3.3);
4. standard telemetry names (§3.10);
5. a byte-stable **golden expansion test** (known-answer fixture);
6. demonstrated fail-closed behavior under the §3.6 fold (a red-first test
   in the consuming SDK).

**Catalog v1:**

| Pattern | Expansion (sketch) | Notes |
|---|---|---|
| `binary_cascade` | `Cascade(arms=[stage(base), stage(expert)], gates=[margin_below θ], post)` | the RFC 0001 cascade policy's exact shape; migration target (§4) |
| `n_cascade` | `Cascade(arms=[stage(a₁)..stage(a_m)], gates=[θ₁..θ_{m−1}], post)` | ordered escalation |
| `self_consistency` | `Ensemble(arms=[stage(a)], cardinality=k, majority_vote, accept: stat_at_least(vote_margin, θ)?)` | k tuned or calibrated |
| `best_of_n` | `Ensemble(arms=[stage(a)], cardinality=k, judge_max(stage(judge)))` | judge output contract §3.2 |
| `self_debug` | `Loop(body=stage(a), state_keys=[attempt, critique], stop=external_accept(tests), max_iters=K)` | "2-step knob" at K=1 |
| `self_refine` | `Loop(body=stage(a), state_keys=[draft], stop=signal_accept(σ, θ), max_iters=K)` | calibrated stop |

The catalog is curated in-repo; growth follows the admission contract, never
ad-hoc (the documented failure mode of open chain taxonomies).

### 3.8 Loop → NCascade: a compilation relation

For a bounded loop, define the unrolling
`Unroll(Loop(b, S, stop, K)) = Cascade_post(arms=[b₍₁₎..b₍K₎], gates=[¬stop₍₁₎..¬stop₍K−1₎])`
where `b₍ᵢ₎` is the body specialized to iteration `i`'s threaded state over
the declared `state_keys`, and each gate escalates exactly when the stop
rule does NOT accept.

This is a **compilation relation, not semantic equality** (design review,
codex): it is meaning-preserving **only under all of**:

1. the body's state flows exclusively through the declared `state_keys`
   (`state_keys = []` ⟺ pure body) — no ambient mutation;
2. the stop rule is a deterministic function of the declared state
   (structurally enforced for `signal_accept` by
   `stop_signal_outside_state`; asserted-by-contract for
   `external_accept`);
3. iterations are bounded by `max_iters` (always true in this algebra —
   `max_iters` is required);
4. telemetry and side effects are observationally accounted:
   `iterations_used` maps to "index of the selected arm", `stop_reason`
   maps to the final gate decision, and per-iteration effects are declared
   effects of the corresponding arm.

Implementations MAY offer the unrolled compilation (e.g. `unroll=K` on loop
patterns). Verification is split by mechanism (claim C5): the model checker
verifies output/selection preservation under conditions 1–3 at small
scopes; the telemetry/effect accounting of condition 4 is verified by the
golden expansion fixtures and SDK property tests for every pattern that
offers `unroll`. Outside the conditions no equivalence is claimed.

### 3.9 Surface syntax (draft normative for the validators packet)

```yaml
composites:
  - name: answerer
    kind: cascade            # cascade | ensemble | loop (closed)
    placement: post          # cascade only; default post
    arms:                    # bare identifier = STAGE (always);
      - cheap_stage          #   nesting REQUIRES the tagged form
      - strong_stage
    arm_params:              # optional: per-stage tuned_params declaration
      cheap_stage: [cheap_model, temperature]
      strong_stage: [strong_model]
    gates:
      - kind: margin_below
        threshold: router.margin_threshold     # MUST resolve to a CVAR
    pattern: binary_cascade  # provenance annotation (closed shape §3.7)

  - name: coder
    kind: loop
    body: { composite: answerer }              # tagged nesting
    state_keys: [attempt, critique]
    stop: { kind: external_accept, predicate: run_unit_tests }
    max_iters: 3
    pattern: self_debug
```

Closed shapes with exact diagnostics throughout (RFC 0001 grammar
discipline); the EBNF and `tvl.schema.json` deltas land in the validators
packet, gated on this RFC's acceptance. Modules with no `composites:` block
parse byte-identically to TVL 1.1 (§4).

### 3.10 Standard telemetry (content-free)

Per-constructor measure names every implementation emits (counts, rates,
enums, finite numbers only — nothing content-typed; P8 discipline):

- cascade: `escalation_rate`, `stage_selected` (index), per-gate
  `gate_margin_pass_rate`;
- ensemble: `vote_agreement`, `vote_margin`, `candidates_evaluated`,
  `candidates_excluded` (judge contract violations);
- loop: `iterations_used`, `stop_reason` (enum over StopDecl kinds ∪
  `exhausted`).

### 3.11 Error-code surface (exact diagnostics)

New codes introduced by this RFC (each with a happy + rejecting conformance
fixture in the validators packet):

`unknown_composite_kind` · `composite_binds_value` ·
`composite_shadows_name` · `duplicate_composite` · `empty_arms` ·
`ambiguous_arm` · `missing_composite_ref` · `composite_cycle` ·
`pre_gate_requires_signal` · `cardinality_arity_mismatch` ·
`invalid_cardinality_type` · `invalid_cardinality_value` (R9) ·
`missing_judge` · `unknown_aggregate_kind` · `unknown_stop_kind` ·
`missing_stop_threshold` · `missing_stop_predicate` ·
`stop_signal_outside_state` · `invalid_max_iters` ·
`missing_composite_parent` · `duplicate_stage` (extended scope) — plus the
RFC 0001 `missing_ref` family reused unchanged for every CVAR/threshold
reference.

## 4. Compatibility and migration (P1 argument)

**Conservative extension.** The `composites:` block is additive: every valid
TVL 1.1 module parses identically with the same meaning (no existing block's
grammar changes; the namespace rule extends by adding `N_X` to the same
collision discipline). The shipped canonical examples remain green unchanged.

**Cascade-policy subsumption.** The RFC 0001 policy form maps exactly on
ALL fields:

```
PolicyDecl⟨name, "policy", "cascade", stages = s₁..s_m,
           gates = g₁..g_{m−1}, parameters?, scope?⟩
  ≡ Composite⟨name, cascade,
              arms = stage(s₁,[])..stage(s_m,[]), gates = g₁..g_{m−1},
              placement = post, parameters?, scope?⟩
```

`stages` map to stage-tagged arms with empty `tuned_params` (the policy form
never declared parentage — the obligation lint §3.5 is vacuous on migrated
forms until authors declare `arm_params`, an explicit and intended
ratchet); `parameters?` and `scope?` carry over verbatim with identical
semantics and the identical outside-P8 categorization. StageRef opacity, the
gate→CVAR rule, and execution semantics are unchanged (§3.2 incorporates
RFC 0001 §3.8 by reference). `policies` with `strategy: cascade` remains
VALID in TVL 1.2 (no deprecation this increment); the
`binary_cascade`/`n_cascade` patterns are its forward form, and a future
increment may add a migration lint. The SDK's shipped `CascadePolicy` is
the execution target for cascade composites; the binary `Router` (unmerged)
is a future *pattern/adapter* over it, and nothing in this RFC assumes its
API.

## 5. Property claims (Phase 2)

| Claim | Statement | Verification plan |
|---|---|---|
| **C1** Constructor disjointness | every composite node has exactly one kind from the closed registry; cross-kind/unknown fields reject | model checking (kind partition); lints with exact diagnostics (§3.11) |
| **C2** Nesting well-formedness | the `N_X` reference graph is acyclic; expansion terminates; depth finite; arm resolution unambiguous (tag-driven + `ambiguous_arm`) | model checking (acyclicity + a MUST-BE-SAT cyclic counterexample); `composite_cycle`/`ambiguous_arm` lints |
| **C3** Coverage-fold soundness | `Cal` over all roots collects EXACTLY the calibratable members of the whole expansion (no over-, no under-collection, judge and nested levels included); strict selection fails closed on any gap | model checking (fold vs. ground-truth member walk + a MUST-BE-SAT uncertified-gate violation); red-first SDK tests |
| **C4** Cost compositionality | the cost forms close over nesting: substituting an arm's cost form yields the composite's, for all five forms (§3.4) | model checking at small scopes (structural induction skeleton); SDK property tests |
| **C5** Loop→NCascade compilation | under §3.8 conditions 1–3, `Unroll` preserves the selected output at small scopes (model-checked); condition 4's telemetry accounting holds for every catalog pattern offering `unroll` (golden fixtures + SDK property tests) | split by mechanism as stated |
| **C6** Dependency-compilation soundness | `required_parents` obligations land in `N_T` only and are checkable statically; no rule of this RFC can emit or require a non-TVAR `depends_on` entry; `missing_ref` remains the single entry-validity authority | model checking (codomain check + MUST-BE-SAT violation transition); `missing_composite_parent` lint tests |

Model-checking discipline: every UNSAT assertion is paired with a
deliberately-broken transition that MUST be SAT (vacuity teeth — program
convention).

## 6. Documented assumptions

The claims above hold under, and only under:

1. **RFC 0001's assumption set** (§5 there) for everything
   certificate/freshness related — split independence, dataset-hash
   stability, canonical hashing, exchangeability for statistical targets.
2. **Stage cost stability** — `c(stage)` is a runtime-supplied estimate;
   cost-model outputs are estimators, never guarantees.
3. **Probability estimates are operational** — escalation/route/stop
   probabilities come from observed telemetry or calibration splits;
   distribution shift degrades the estimate and is surfaced through the same
   freshness context keys as RFC 0001 (no new drift detection is
   introduced).
4. **Declared parentage honesty** — `tuned_params` on stage arms is the
   author's declaration of an opaque stage's parameterization; an
   under-declared arm under-states `required_parents`. The lint can enforce
   consistency of what is declared, not completeness of the declaration
   (same epistemic position as RFC 0001's `depends_on` itself).
5. **Loop state discipline** — §3.8 condition 1 is structurally encouraged
   (`state_keys` + `stop_signal_outside_state`) but ambient-effect freedom
   is the implementation's responsibility; `external_accept` determinism
   (condition 2) is asserted by contract, not proven.
6. **Judge contract** — the judge's finite-numeric-score obligation is a
   runtime contract; violations are detected per §3.2 (exclusion /
   fail-closed), not prevented.
7. **Pattern determinism** — `expand` is a pure function of validated
   params; catalog entries violating this are rejected at admission.

## 7. Field categorization (P8 alignment)

Composites introduce **no content-typed fields**: kinds, placements, arity,
identifiers (names, StageRefs, predicate ids, state keys, signal-source
ids), one required integer (`max_iters`), and namespace references.
`Provenance` is a CLOSED shape (identifiers + one canonical hash; raw
pattern params never serialize — admission-contract canary). Telemetry
(§3.10) is counts/rates/enums/finite numbers. The opaque escape hatches
(`StageRef`, `external_accept.predicate`, `parameters`) follow RFC 0001's
`environment.bindings` precedent and sit outside the P8 surface exactly as
`policies[].parameters` does. Nothing in this RFC crosses the wire this
increment (§2).

## 8. Prior art (informative)

- **Model cascades / FrugalGPT** (Chen et al. 2023) and draft-verify
  pipelines: the post-cascade with calibrated acceptance is the productized
  core of RFC 0001's cascade policy; this RFC generalizes arity and nesting.
- **Self-consistency** (Wang et al. 2022), best-of-n / judge selection: the
  ensemble constructor with `majority_vote`/`judge_max`; the program's own
  margin-routing study (vote-margin AUC 0.71) supplies the calibration
  recipe shape for `accept` gates.
- **Self-Refine** (Madaan et al. 2023), **Reflexion** (Shinn et al. 2023),
  CRITIC: the loop constructor; "self-debug as a 2-step knob" is
  `self_debug` at `max_iters = 1..K`.
- **Composition-over-inheritance** in API design (Effective Java items
  18–20; React's component model) and the LangChain-Chains →
  LCEL/DSPy migration: the empirical case for sealing structure and naming
  recipes — taxonomy-as-inheritance collapsed under exactly the pressure the
  pattern catalog absorbs.

## 9. Acceptance criteria for this RFC

1. Cross-model review converged: anchored codex (gpt-5.5, xhigh) rounds to
   ACCEPT **plus** one fresh unanchored full-document pass with all blocking
   findings dispositioned in §10.
2. Model-checking packet green for C1–C6, including every paired MUST-BE-SAT
   vacuity check, on a re-run executed by the integrating agent.
3. The §3.9 surface syntax validated against the §4 subsumption mapping (the
   policy form and its composite form lint identically on the shared
   examples), with explicit degenerate fixtures: `m=1` cascade, `k=1`
   sampling ensemble, committee ensemble, `max_iters=1` loop, empty-arms
   rejection, tagged-nesting under an ensemble judge, and an
   `ambiguous_arm` rejection.
4. Owner acceptance recorded in this header and §10 (human-only gate).
5. No semantic change to any RFC 0001 construct: the RFC 0001 conformance
   fixtures pass unchanged.

## 10. Review log

| Round | Reviewer | Verdict | Disposition |
|---|---|---|---|
| 1 | codex (gpt-5.5, xhigh, read-only) — 2026-06-06 | **REJECT** — 10 blocking, 5 non-blocking | All addressed in Draft v2: (1) arm resolution made tag-driven (`stage`/`composite` tags; bare = stage always; `ambiguous_arm` rejection); (2) pre-cascade made total (first-match-wins routing with fallback arm, per-gate signals + per-gate cost, absent-signal routes onward, `pre_gate_requires_signal`); (3) ensemble cardinality: required iff single-arm, int-typed, R9 rejection for k<1, both cost forms; (4) judge output contract (finite numeric score, exclusion rules, all-excluded fails, deterministic tie-break); (5) loop state formalized (`state_keys` + `stop_signal_outside_state`; pure ⟺ empty); (6) dependency compilation rebuilt as DECLARED parentage (`tuned_params` on stage arms) + static coverage obligations (`missing_composite_parent`), `missing_ref` stays single authority, judge/signal parents included; (7) root-consumption rule (all N_X roots, conservative fail-closed; selective consumption deferred); (8) subsumption made exact (scope?/parameters? carried onto Composite verbatim; empty tuned_params on migrated stages stated as intended ratchet); (9) Provenance closed shape (param_hash only, canary in admission contract); (10) C5 verification split by mechanism incl. condition 4. Non-blocking: full error-code surface §3.11; SignalSourceRef clarified as the RFC 0001 calibration-source registry (no new declaration surface); degenerate fixtures added to §9; AcceptDecl separated from GateDecl with opposite inequality; P6 note absorbed. |

Design pre-review (before Draft v1): Option E architecture ACCEPTed by
codex (gpt-5.5 xhigh — 4 hard constraints + terminology edits, all
incorporated: not-a-binding-kind §3.1; no CVAR→CVAR deps §3.5; CascadePolicy
anchor §4; compilation-relation framing §3.8; "structural constructors"
naming) and by gemini (workspace-impact concurrence: schema stability,
JS parity, spine coverage-fold fit, FE provenance rendering).
