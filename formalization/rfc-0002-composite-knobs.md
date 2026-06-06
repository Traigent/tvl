# RFC 0002 — Composite Knobs: a sealed control-flow algebra and a named pattern catalog

| | |
|---|---|
| **Status** | **DRAFT v1** — under cross-model review; owner acceptance pending |
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
- dependency compilation onto leaf TVARs (§3.5);
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
  deferral stands; composite edges COMPILE DOWN to leaf TVARs, §3.5);
- in-loop CVAR re-fitting and CVAR optimizers (RFC 0001 deferrals stand);
- learned routers / dispatch functions as calibrators (would extend the
  calibrator registry, not this algebra);
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
surfaced as `composite_shadows_name`). `N_X` never enters `Γ`,
`Config(Δ, E_τ)`, `F^str`, or the optimizer projection `Σ` (§3.2 of RFC 0001
is unchanged): the optimizer sees member TVARs individually; the composite is
invisible to search exactly as cvars are (Property P2/P5 preserved).

### 3.2 The sealed algebra

```
Composite ::= ⟨ name : Ident,
                kind : CompositeKind,            (* CLOSED registry *)
                body : Cascade | Ensemble | Loop,(* discriminated by kind *)
                pattern? : Ident ⟩               (* provenance annotation, §3.7 *)

CompositeKind ::= cascade | ensemble | loop      (* SEALED: a fourth kind is a
                                                    new RFC, not a registry entry *)

Arm       ::= StageRef | CompositeName           (* nesting: an arm may be another
                                                    declared composite *)

Cascade   ::= ⟨ arms : Arm+,                     (* |arms| = m ≥ 1 *)
                gates : GateDecl*,               (* |gates| = m − 1 *)
                placement : pre | post ⟩         (* DEFAULT post *)

Ensemble  ::= ⟨ arms : Arm+,                     (* |arms| ≥ 1 *)
                cardinality? : Ident,            (* namespace ref → TVAR or CVAR:
                                                    the per-arm sample count k *)
                aggregate : AggregateDecl ⟩

Loop      ::= ⟨ body : Arm,
                stop : StopDecl,
                max_iters : ℕ≥1 ⟩                (* REQUIRED bound — totality *)

GateDecl  ::= ⟨ kind : margin_below | signal_below,   (* v1 registry *)
                threshold : Ident,               (* MUST resolve to a CVAR
                                                    (kind-checked), as RFC 0001 §3.8 *)
                signal? : Ident ⟩                (* REQUIRED iff kind=signal_below:
                                                    resolves to a declared SignalSpec *)

AggregateDecl ::= ⟨ kind : majority_vote | judge_max,  (* v1 registry *)
                    judge? : StageRef,           (* REQUIRED iff kind=judge_max *)
                    accept? : GateDecl ⟩         (* optional acceptance gate over
                                                    the aggregate's vote statistics *)

StopDecl  ::= ⟨ kind : signal_accept | external_accept | exhausted,
                threshold? : Ident,              (* REQUIRED iff kind=signal_accept:
                                                    MUST resolve to a CVAR *)
                signal? : Ident,                 (* REQUIRED iff kind=signal_accept *)
                predicate? : Ident ⟩             (* REQUIRED iff kind=external_accept:
                                                    OPAQUE runtime predicate id,
                                                    StageRef-style (§3.8 of RFC 0001) *)
```

**Well-formedness (statically checked):**

1. `kind` ∈ the closed registry; anything else rejects
   (`unknown_composite_kind`).
2. Gate/arm arity: `|gates| = |arms| − 1` for cascades (degenerate `m = 1`
   cascade has no gates and always returns its arm — RFC 0001's rule carries
   over).
3. Every `Arm` that is a `CompositeName` must resolve to a declared composite
   (exact match, RFC 0001 §3.7 namespace rules); the resulting **reference
   graph over `N_X` must be acyclic** (`composite_cycle`). Composition depth
   is finite by construction: nesting is the ONLY composition mechanism, and
   DAG-shaped configurations are the **closure of nesting** — there is no
   fourth "DAG kind".
4. Gate/stop thresholds resolve to CVARs (kind-checked, reusing RFC 0001's
   gate rule); signals resolve to declared SignalSpecs (§3.5 of RFC 0001).
5. `StageRef` remains an opaque operational identifier (RFC 0001 §3.8,
   review finding 6) — not a namespace reference; duplicates within one
   composite are rejected (`duplicate_stage`).
6. Discriminator totality: exactly the body fields of the declared kind are
   present; unknown or cross-kind fields reject (closed shapes, exact
   diagnostics — the RFC 0001 grammar discipline).

**Execution semantics.**

- `placement: post` cascade is EXACTLY RFC 0001 §3.8 cascade execution
  (normative text incorporated by reference): run arm `i`, vote over `k_i`
  samples, escalate iff `margin < θ_i`; totality/determinism/error rules
  unchanged, including fail-closed propagation of stage exceptions under
  strict modes.
- `placement: pre` cascade (dispatch): the gate's `signal` is evaluated on
  the INPUT before any arm runs; `route to arm_{i+1} ⟺ signal(x) < θ_i`
  applied left to right; exactly one arm executes. Cost consequences in §3.4.
  Empty/abstaining signal evaluation escalates (the RFC 0001 `margin = 0`
  rule generalizes: an absent signal value compares below any `θ > 0`).
- `ensemble`: run each arm (or one arm `k` times when `cardinality` is
  declared and `|arms| = 1`); aggregate by the declared kind
  (`majority_vote` over caller-defined equivalence keys with the RFC 0001
  tie/abstain rules; `judge_max` runs the judge stage over candidate outputs
  and selects the maximum-scored candidate deterministically, ties broken by
  the RFC 0001 total order). An `accept` gate, when present, evaluates over
  the aggregate's content-free vote statistics; failing it is an honest
  no-accept outcome that propagates to the consumer (under strict modes it
  feeds the fail-closed law).
- `loop`: execute `body`; evaluate `stop` over the declared loop state;
  repeat up to `max_iters`. State is explicitly threaded: iteration `i+1`
  sees a declared accumulator (operationally defined by the runtime, like
  stage bindings), never ambient hidden state. `exhausted` means "always run
  `max_iters` iterations"; `signal_accept` stops when
  `signal(state) ≥ θ` (acceptance, not escalation — the inequality direction
  is deliberate and lint-pinned); `external_accept` delegates to an opaque
  runtime predicate (outside the P8 surface, like `parameters`).

### 3.3 Calibratable surface

Each constructor *defines* which members admit calibration and with what
target-property shape — this is the machine-facing payoff of sealing:

| Constructor | Calibratable members | Target-property shape |
|---|---|---|
| `cascade` (post) | each gate threshold `θ_i` | conditional property of the ACCEPTANCE REGION the gate induces (e.g. `P(arm_i correct │ margin ≥ θ_i) ≥ p`) — exactly RFC 0001 §3.5's per-CVAR scope |
| `cascade` (pre) | each routing threshold `θ_i` | conditional property of the ROUTE the signal induces (e.g. `P(arm_i adequate │ signal < θ_i) ≥ p`) |
| `ensemble` | `accept.threshold`; `cardinality` when bound Calibrated | acceptance: `P(aggregate correct │ vote stat ≥ θ) ≥ p`; cardinality: cost-bounded sufficiency |
| `loop` | `stop.threshold` (signal_accept) | stop adequacy: `P(accepted state meets target │ signal ≥ θ) ≥ p` |

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
cost(StageRef s)                       = c(s)                       (runtime-supplied)
cost(Cascade_post(a₁..a_m, θ₁..θ_{m−1})) = cost(a₁) + Σ_{i=1}^{m−1} P(esc₁..esc_i) · cost(a_{i+1})
cost(Cascade_pre (a₁..a_m, θ₁..θ_{m−1})) = c(signal) + Σ_i P(route = i) · cost(a_i)
cost(Ensemble(a, k, agg))               = k · cost(a) + c(agg)      (single-arm form;
                                           multi-arm: Σ_j cost(a_j) + c(agg))
cost(Loop(b, stop, K))                  = E[iters] · cost(b),  E[iters] ≤ K
```

Escalation/route/stop probabilities are *operational estimates* (observed
telemetry or calibration-split estimates) — the cost model is a structured
estimator, not a guarantee (§3.3 claim scope applies). **Compositionality
(claim C4)**: `cost(X)` for a nested composite arm is the arm's own cost
form — the equations close over the algebra. This is what makes
frontier/constrained search over composites structurally informed instead of
black-box.

### 3.5 Dependency compilation (leaf TVARs only)

RFC 0001 defers CVAR→CVAR dependencies; this RFC **keeps that deferral** and
defines how composite structure compiles onto the existing mechanism:

```
leafT : Arm → ℘(N_T)
leafT(StageRef s)     = T(s)            (* the tuned variables parameterizing the
                                           stage, per the module's declarations *)
leafT(CompositeName x) = ⋃_{a ∈ arms/body(x)} leafT(a)

Compile_π(gate θ_i in Cascade(arms..)) :
    π(θ_i) ⊇ leafT(a₁) ∪ … ∪ leafT(a_i)     (post: everything the gate observes)
    π(θ_i) ⊇ ∅ ∪ signal's tuned parents      (pre: the signal's parameterization)
Compile_π(accept θ in Ensemble(arms, k)) :
    π(θ) ⊇ ⋃_j leafT(a_j) ∪ {k if k ∈ N_T}
Compile_π(stop θ in Loop(body))         :
    π(θ) ⊇ leafT(body)
```

The compiled `depends_on` sets contain **TVARs only** (claim C6); the
RFC 0001 `missing_ref` lint remains the single authority. The payoff is that
the freshness cascade becomes structural: swap an arm's model and every gate
observing that arm reads stale through the existing
`tuned_parent_values` core — by construction, not convention.

### 3.6 Certificate coverage fold (extends RFC 0001 §3.6)

```
Cal : Composite → ℘(N_C)
Cal(Cascade(arms, gates, _)) = ⋃ Cal(arms) ∪ { g.threshold : g ∈ gates }
Cal(Ensemble(arms, k, agg))  = ⋃ Cal(arms) ∪ { agg.accept.threshold if present }
                               ∪ { k if k ∈ N_C }
Cal(Loop(body, stop, _))     = Cal(body) ∪ { stop.threshold if kind=signal_accept }
Cal(StageRef)                = ∅
```

Under `strict(M, c)` (RFC 0001 §3.6, unchanged), `CalibrationPass(c, M)`
extends to require a valid, fresh certificate for **every** CVAR in
`Cal(root)` for every composite the configuration consumes. The fold is
**fail-closed** (claim C3): any uncertified or stale member ⇒ no certified
selection — never a partial pass, never a silent skip of a nested level.

### 3.7 The pattern catalog contract

```
Pattern ::= ⟨ name : Ident,
              params : ParamSchema,
              expand : params → Composite ⟩    (* DETERMINISTIC, TOTAL on
                                                  validated params *)
```

A pattern is a **macro**: `expand` emits algebra nodes, every one stamped
with `pattern = name` (the provenance annotation of §3.2). Provenance is a
content-free identifier: it rides operational metadata (and any future wire
summary) as an annotation, never as schema vocabulary — adding a pattern is
an SDK release, not a language or schema change.

**Admission contract** — a pattern enters the catalog only with ALL of:

1. an expansion into the sealed algebra (no pattern-private node kinds);
2. provenance/source-map metadata on every emitted node;
3. a calibration recipe for every CVAR the expansion introduces (which
   signal, which split, which target-property shape from §3.3);
4. standard telemetry names (§3.10);
5. a byte-stable **golden expansion test** (known-answer fixture);
6. demonstrated fail-closed behavior under the §3.6 fold (a red-first test
   in the consuming SDK).

**Catalog v1:**

| Pattern | Expansion (sketch) | Notes |
|---|---|---|
| `binary_cascade` | `Cascade(arms=[base, expert], gates=[margin_below θ], post)` | the RFC 0001 cascade policy's exact shape; migration target (§4) |
| `n_cascade` | `Cascade(arms=[a₁..a_m], gates=[θ₁..θ_{m−1}], post)` | ordered escalation |
| `self_consistency` | `Ensemble(arms=[a], cardinality=k, majority_vote, accept: margin_below θ?)` | k tuned or calibrated |
| `best_of_n` | `Ensemble(arms=[a], cardinality=k, judge_max(judge))` | judge is a StageRef |
| `self_debug` | `Loop(body=a, stop=external_accept(tests), max_iters=K)` | "2-step knob" at K=1 |
| `self_refine` | `Loop(body=a, stop=signal_accept(σ, θ), max_iters=K)` | calibrated stop |

The catalog is curated in-repo; growth follows the admission contract, never
ad-hoc (the documented failure mode of open chain taxonomies).

### 3.8 Loop → NCascade: a compilation relation

For a bounded loop, define the unrolling
`Unroll(Loop(b, stop, K)) = Cascade_post(arms=[b₍₁₎..b₍K₎], gates=[¬stop₍₁₎..¬stop₍K−1₎])`
where `b₍ᵢ₎` is the body specialized to iteration `i`'s threaded state and
each gate escalates exactly when the stop rule does NOT accept.

This is a **compilation relation, not semantic equality** (design review,
codex): it is meaning-preserving **only under all of**:

1. the body is pure, or its state is explicitly threaded through the
   declared accumulator (no ambient mutation);
2. the stop rule is a deterministic function of the declared state;
3. iterations are bounded by `max_iters` (always true in this algebra —
   `max_iters` is required);
4. telemetry/side effects are observationally accounted: `iterations_used`
   maps to "index of the selected arm", and per-iteration effects are
   declared effects of the corresponding arm.

Implementations MAY offer the unrolled compilation (e.g. `unroll=K` on loop
patterns); claim C5 model-checks the relation under conditions 1–3 at small
scopes. Outside the conditions no equivalence is claimed.

### 3.9 Surface syntax (draft normative for the validators packet)

```yaml
composites:
  - name: answerer
    kind: cascade            # cascade | ensemble | loop (closed)
    placement: post          # cascade only; default post
    arms: [cheap_stage, strong_stage]          # StageRef | composite name
    gates:
      - kind: margin_below
        threshold: router.margin_threshold     # MUST resolve to a CVAR
    pattern: binary_cascade  # optional provenance annotation

  - name: coder
    kind: loop
    body: draft_stage
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
enums only — nothing content-typed; P8 discipline):

- cascade: `escalation_rate`, `stage_selected` (index), per-gate
  `gate_margin_pass_rate`;
- ensemble: `vote_agreement`, `vote_margin`, `candidates_evaluated`;
- loop: `iterations_used`, `stop_reason` (enum over StopDecl kinds ∪
  `exhausted`).

## 4. Compatibility and migration (P1 argument)

**Conservative extension.** The `composites:` block is additive: every valid
TVL 1.1 module parses identically with the same meaning (no existing block's
grammar changes; the namespace rule extends by adding `N_X` to the same
collision discipline). The shipped canonical examples remain green unchanged.

**Cascade-policy subsumption.** The RFC 0001 policy form maps exactly:

```
PolicyDecl⟨name, "policy", "cascade", stages = s₁..s_m, gates = g₁..g_{m−1}⟩
  ≡ Composite⟨name, cascade, arms = s₁..s_m, gates = g₁..g_{m−1}, placement = post⟩
```

field for field — same StageRef opacity, same gate→CVAR rule, same execution
semantics (§3.2 incorporates RFC 0001 §3.8 by reference). `policies` with
`strategy: cascade` remains VALID in TVL 1.2 (no deprecation this
increment); the `binary_cascade`/`n_cascade` patterns are its forward form,
and a future increment may add a migration lint. The SDK's shipped
`CascadePolicy` is the execution target for cascade composites; the binary
`Router` (unmerged) is a future *pattern/adapter* over it, and nothing in
this RFC assumes its API.

## 5. Property claims (Phase 2)

| Claim | Statement | Verification plan |
|---|---|---|
| **C1** Constructor disjointness | every composite node has exactly one kind from the closed registry; cross-kind/unknown fields reject | model checking (kind partition); lints with exact diagnostics |
| **C2** Nesting well-formedness | the `N_X` reference graph is acyclic; expansion terminates; depth finite | model checking (acyclicity + a MUST-BE-SAT cyclic counterexample); `composite_cycle` lint |
| **C3** Coverage-fold soundness | `Cal(root)` collects EXACTLY the calibratable members of the whole expansion (no over-, no under-collection); strict selection fails closed on any gap | model checking (fold vs. ground-truth member walk + a MUST-BE-SAT uncertified-gate violation); red-first SDK tests |
| **C4** Cost compositionality | the cost forms close over nesting: substituting an arm's cost form yields the composite's | model checking at small scopes (structural induction skeleton); SDK property tests |
| **C5** Loop→NCascade compilation | under §3.8 conditions 1–3, `Unroll` preserves selected output and accounted telemetry at small scopes | model checking (bounded K ≤ 4); golden fixtures for `unroll=K` patterns |
| **C6** Dependency-compilation soundness | every `Compile_π` edge lands in `N_T`; no CVAR→CVAR edge is ever emitted | model checking (codomain check + MUST-BE-SAT violation transition); reuse of the RFC 0001 `missing_ref` lint as the single authority |

Model-checking discipline: every UNSAT assertion is paired with a
deliberately-broken transition that MUST be SAT (vacuity teeth — program
convention).

## 6. Documented assumptions

The claims above hold under, and only under:

1. **RFC 0001's assumption set** (§5 there) for everything
   certificate/freshness related — split independence, dataset-hash
   stability, canonical hashing, exchangeability for statistical targets.
2. **Stage cost stability** — `c(StageRef)` is a runtime-supplied estimate;
   cost-model outputs are estimators, never guarantees.
3. **Probability estimates are operational** — escalation/route/stop
   probabilities come from observed telemetry or calibration splits;
   distribution shift degrades the estimate and is surfaced through the same
   freshness context keys as RFC 0001 (no new drift detection is introduced).
4. **Loop state discipline** — the §3.8 conditions are the implementation's
   responsibility to uphold; the algebra makes them checkable, not
   automatic.
5. **Pattern determinism** — `expand` is a pure function of validated
   params; catalog entries violating this are rejected at admission.

## 7. Field categorization (P8 alignment)

Composites introduce **no content-typed fields**: kinds, placements, arity,
identifiers (names, StageRefs, predicate ids), one required integer
(`max_iters`), and namespace references. `pattern` is a content-free
identifier. Telemetry (§3.10) is counts/rates/enums. The opaque escape
hatches (`StageRef`, `external_accept.predicate`) follow RFC 0001's
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
   examples).
4. Owner acceptance recorded in this header and §10 (human-only gate).
5. No semantic change to any RFC 0001 construct: the RFC 0001 conformance
   fixtures pass unchanged.

## 10. Review log

| Round | Reviewer | Verdict | Disposition |
|---|---|---|---|
| — | (pending: anchored codex rounds, fresh pass, owner gate) | — | — |

Design pre-review (before this draft): Option E architecture ACCEPTed by
codex (gpt-5.5 xhigh — 4 hard constraints + terminology edits, all
incorporated: not-a-binding-kind §3.1; no CVAR→CVAR deps §3.5; CascadePolicy
anchor §4; compilation-relation framing §3.8; "structural constructors"
naming) and by gemini (workspace-impact concurrence: schema stability,
JS parity, spine coverage-fold fit, FE provenance rendering).
