# RFC 0002 — Composite Knobs: a sealed control-flow algebra and a named pattern catalog

| | |
|---|---|
| **Status** | **DRAFT v6** — under cross-model review; owner acceptance pending |
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
- the `Loop → K-chain` bounded-unroll **semantic compilation relation**
  (`signal_accept` loops only; §3.8);
- a `composites:` surface block as a conservative grammar extension (§3.9);
- subsumption of `policies.strategy: cascade` by exact expansion mapping (§4).

**Explicitly deferred** (out of scope for TVL 1.2 and this increment):

- any wire/schema crossing: composites do not ride the typed session wire,
  TraigentSchema is untouched, backend/FE see no new fields (contract
  decision v1; a content-free composite summary is a recorded revisit
  trigger);
- CVAR→CVAR dependencies (`depends_on` still names TVARs only — the RFC 0001
  deferral stands; composite structure compiles to leaf-TVAR coverage
  obligations, §3.5). **Revisit trigger:** because this deferral leaves
  nested-certificate freshness per-member and NOT cross-level (an outer
  certificate is not bound to inner CVAR values — §3.6 scope, §6
  assumption 8), the CVAR→CVAR mechanism is the work item that would let an
  inner recalibration stale an outer certificate; revisit when cross-level
  value-dependency freshness is required;
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
                threshold : Ident,               (* MUST resolve to a CVAR of TVL
                                                    type int or float (kind- AND
                                                    type-checked; §3.2 item 6) *)
                signal? : SignalUse ⟩            (* REQUIRED iff kind=signal_below
                                                    (`missing_gate_signal`) *)

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
                                                    MUST resolve to a CVAR of TVL
                                                    type int or float *)
                signal? : SignalUse,             (* REQUIRED iff kind=signal_accept
                                                    (`missing_stop_signal`);
                                                    inputs MUST ⊆ state_keys *)
                predicate? : Ident ⟩             (* REQUIRED iff kind=external_accept:
                                                    OPAQUE runtime predicate id,
                                                    StageRef-style — outside P8 *)

SignalUse ::= ⟨ signal : Ident,       (* a NAMED signal reference into the SAME
                                         signal namespace RFC 0001's module-facing
                                         calibration.signal uses (an Ident,
                                         operationally resolved by the runtime's
                                         signal registry — NOT a module-namespace
                                         declaration, and NOT a calibration SOURCE:
                                         sources identify evidence pools; signals
                                         identify the scoring FUNCTION. The full
                                         closed SignalSpec shape enters the formal
                                         model only through its canonical hash
                                         H_c(σ), exactly as in RFC 0001 §3.5 —
                                         one signal model across the language) *)
                inputs : Ident* ⟩     (* the declared input keys the signal reads:
                                         for stops, MUST ⊆ the loop's state_keys
                                         (statically checked); for pre-gates,
                                         opaque input-feature identifiers
                                         (environment.bindings precedent).
                                         Malformed SignalUse objects (missing
                                         signal, unknown keys, non-list inputs)
                                         reject: invalid_signal_use *)
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
5. **Gate kind / placement / arm typing** (strict placement symmetry).
   The two gate kinds are placement-exclusive and one carries an arm-typing
   obligation:
   - `margin_below` is **POST-only** — it consumes the just-executed arm's
     vote statistics. Its gated arm (the arm `i` whose margin gate `g_i`
     reads in a post-cascade) MUST be **margin-bearing**: either a `stage`
     arm (RFC 0001 vote semantics produce its vote statistics) or an
     `ensemble` arm whose `aggregate.kind = majority_vote` (the committee's
     vote statistics). Gating any other arm kind — a `loop` arm, a nested
     **pre**-cascade composite, a `judge_max` ensemble (it yields a score,
     not a vote margin), or a nested **post**-cascade composite — with
     `margin_below` rejects statically (`gate_arm_incompatible`).
   - `signal_below` is **PRE-only** — it scores the input before any arm
     runs and routes (§ execution semantics). It requires a declared
     `signal` field; a `signal_below` gate missing its `signal` rejects
     (`missing_gate_signal`).
   - A `margin_below` gate under `placement: pre`, or a `signal_below` gate
     under `placement: post`, rejects (`gate_kind_placement_mismatch` —
     covers BOTH directions of kind/placement misuse, subsuming the former
     pre-with-margin case).

   *Future extension (deferred):* post-cascade gates keyed on an output
   signal (a `signal_below`-style post gate scoring the executed arm's
   output rather than its vote margin) are out of scope for TVL 1.2 — the
   v1 post gate is `margin_below` only.
6. Gate/accept/stop thresholds resolve to CVARs (kind-checked, reusing
   RFC 0001's gate rule — `missing_ref` family); `stage(·)` duplicates
   within one composite are rejected (`duplicate_stage`).
7. Ensemble cardinality: present iff `|arms| = 1`
   (`cardinality_arity_mismatch`); must reference a TVAR or CVAR whose
   declared TVL type is `int` (`invalid_cardinality_type`); resolution-time
   values `k < 1` are rejection **R9** (`invalid_cardinality_value`).
   **Acceptance-algebra extension (TVL 1.2):** RFC 0001 §3.4's resolution
   acceptance extends to

   ```
   Accept₁.₂ ⟺ ¬(R1 ∨ … ∨ R8 ∨ R9) ∧ calibrators ≠ ⊥
   ```

   with P3/P4 (the two directions of the acceptance biconditional) carrying
   over verbatim with R9 in the disjunction. This is conservative: a TVL 1.1
   module declares no composites, so R9 is unreachable and `Accept₁.₂`
   coincides with RFC 0001's `Accept` on all 1.1 modules.
8. Loop: `stop.signal.inputs`, when present, MUST be a subset of the
   declared `state_keys` (`stop_signal_outside_state`); `max_iters ≥ 1`
   (`invalid_max_iters`).
9. **`tuned_params` entries resolve to TVARs only**: every entry of a
   stage arm's `tuned_params` MUST resolve (exact match, RFC 0001 §3.7) to
   a declared TVAR; an entry naming a CVAR, policy, composite, or nothing
   is rejected (`invalid_tuned_param`). Together with §3.5 this makes C6
   hold by construction: `required_parents` is a union of validated
   TVAR-only sets.
10. **Numeric thresholds**: every gate/accept/stop `threshold` CVAR must
   have declared TVL type `int` or `float` (`invalid_threshold_type`) —
   the execution comparisons (`margin < θ`, `σ ≥ θ`, `stat ≥ θ`) are over
   finite numbers; a non-finite resolved value fails the item's evaluation
   per the existing exception rules (never a silent comparison).
11. **Signal/threshold calibration binding** (cross-model round 4;
   **COMPOSITE-SCOPED**, cross-model fresh pass): every **composite-bound**
   thresholded construct determines a signal id —

   ```
   sig(signal_below g)        = g.signal.signal        (explicit SignalUse)
   sig(signal_accept stop)    = stop.signal.signal     (explicit SignalUse)
   sig(margin_below g)        = vote_margin            (canonical stat id)
   sig(stat_at_least a)       = a.stat                 (vote_margin │ vote_agreement)
   ```

   where the canonical vote-statistic ids live in the SAME registry
   namespace as named signals. **The lint fires at the composite USE SITE**:
   it is the `composites:` construct that references `θ` (as a gate, accept,
   or stop threshold) which obliges `θ` to declare
   `calibration.signal = sig(construct)`. It NEVER fires on a `cvars` or
   `policies` block in isolation — a CVAR whose `calibration.signal` is
   absent or differs is well-formed on its own (RFC 0001 leaves
   `calibration.signal` OPTIONAL), and a legacy `policies:` cascade keeps
   RFC 0001 semantics untouched. Only when a composite USES `θ` as a
   threshold does the binding become an obligation of that composite: a
   missing `calibration.signal` on a composite-referenced `θ` rejects
   (`missing_calibration_signal`); a differing one rejects
   (`signal_mismatch`). Rationale: certificate freshness binds `H_c(σ)` for
   the signal used DURING CALIBRATION — a threshold calibrated against
   signal A gating signal B would be **vacuously fresh**. This rule is
   static (both sides are declared identifiers) and is distinct from
   `missing_composite_parent`: parent coverage binds tuned-TVAR freshness;
   this rule binds the measured signal semantics of the threshold itself.
   Because the obligation lives on the composite use site, it is one of the
   two intended composite-only ratchets over RFC 0001 (the other being the
   empty-`tuned_params` parent-coverage ratchet, §4); a TVL 1.1 module
   declares no composites, so the lint never fires on it (P1 preserved, §4).

   **Use-site signal inputs are freshness-bound** (cross-model fresh pass):
   a `SignalUse.inputs` list changes the runtime scoring semantics of the
   signal (it selects which keys/features the scoring function reads), so a
   recalibration that held inputs fixed must be invalidated when the
   composite changes them. TVL 1.2 adds a NEW optional freshness-context
   **extension** key, `signal_inputs`, to the RFC 0001 §3.5 `ctx_ext`
   registry (conservative: an optional extension key; `ctx_core` is
   untouched, so all TVL 1.1 freshness behavior is unchanged). The rule,
   composite-use-site-scoped exactly like the signal-id binding above: when
   a composite-bound threshold's governing `SignalUse` has `inputs ≠ []`,
   the threshold CVAR `θ`'s
   `promotion_policy.require_calibration.hash_covered_context` MUST include
   `signal_inputs`, AND the value covered under `signal_inputs` MUST equal
   the use-site ordered input list; either failure rejects
   (`unbound_signal_inputs`). This is static — both the use-site `inputs`
   list and the covered context value are declared identifiers. When
   `inputs = []` the signal reads no use-site-selected keys and no coverage
   of `signal_inputs` is required. Isolated `cvars`/`policies` are
   unaffected (the obligation is the composite's, not the CVAR's).

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
  route(x) = arm_j  where  j = min({ i < m : σ_i(x) ≥ θ_i } ∪ {m})
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

### 3.2.1 The result algebra (closed, total, deterministic)

The per-construct sentences above each handle three outcomes — a produced
output, an honest non-acceptance, and an evaluation failure. This subsection
names that codomain once and gives the propagation rules through nesting, so
the per-construct sentences are instances of one algebra rather than ad-hoc
prose. Every arm and every composite evaluates to:

```
ArmResult ::= output(o, vote_stats?)    (* a produced output; vote_stats present
                                           iff the producer is margin-bearing —
                                           a stage or a majority_vote ensemble *)
            | no_accept                 (* ran, but no result met the construct's
                                           acceptance condition — an HONEST
                                           no-output outcome, NOT an error *)
            | error                     (* evaluation failed — exception, judge
                                           contract violation with no survivor,
                                           non-finite threshold comparison, etc. *)
```

The three kinds are disjoint and exhaustive: every evaluation lands in exactly
one. Propagation is **total and deterministic** — defined for every kind in
every construct:

- **`error` is absorbing.** An `error` from any arm/body/gate/judge/stop fails
  the enclosing item's evaluation in every construct, propagating outward to the
  root (where, under strict modes, it feeds the RFC 0001 §3.6 fail-closed law).
  This unifies the per-construct exception sentences above (post-cascade stage
  exception, pre-cascade signal exception, all-judge-excluded, loop body/stop
  exception, non-finite threshold) — those sentences are retained for locality
  but are each an instance of this single rule.
- **`no_accept` propagation** (per construct):
  - *post-cascade*: a `no_accept` from arm `i` escalates to arm `i+1` when
    `i < m`; if the last arm (`i = m`) yields `no_accept`, the cascade yields
    `no_accept`.
  - *pre-cascade (dispatch)*: the routed arm's result is the cascade's result;
    if the single routed arm yields `no_accept`, the cascade yields `no_accept`
    (routing selects the arm; it does not re-route on non-acceptance).
  - *loop*: a `no_accept` body result completes the iteration unaccepted and the
    loop **continues** to the next iteration; a loop that reaches `max_iters`
    without acceptance (no `signal_accept` fired), or whose final body result is
    `no_accept` (the `exhausted` case), yields `no_accept`.
  - *ensemble (committee `majority_vote`)*: a committee arm yielding `no_accept`
    is a candidate **excluded** from the vote; if ALL candidates are excluded by
    `no_accept`, the ensemble yields `no_accept` — DISTINCT from the
    all-excluded-**by-error** case (judge contract violations), which is an
    `error` and FAILS.
  - *ensemble (aggregate accept)*: when an `accept` decl is present, an
    aggregate that runs but fails `stat ≥ θ` yields `no_accept`.
- **`output` propagation.** An arm/body producing `output(o, vote_stats?)`
  contributes `o` (and its `vote_stats` where margin-bearing) as the construct's
  selected output per the construct's selection rule (escalation stop, route,
  vote/judge winner, accepted loop state).

**Root-level `no_accept`.** A `no_accept` that reaches the composite root is an
honest no-output evaluation. Under strict modes it feeds the RFC 0001 §3.6
fail-closed law exactly as the other no-certified-selection verdicts do (no
winner-by-objective fallback). Under non-strict modes it surfaces as an honest
no-output evaluation result; how operational scoring treats a no-output item
(skip, penalty, abstain) is **runtime-defined** and outside this RFC.

**Vote abstention is not a result kind.** Abstention stays INTERNAL to voting:
an empty/abstain-only vote yields `margin = 0` (RFC 0001's rule, carried over),
which the gate/accept inequality then consumes — it never escapes the voting
step as an `ArmResult`. The only result kinds are `output`, `no_accept`, and
`error`.

### 3.3 Calibratable surface

Each constructor *defines* which members admit calibration and with what
target-property shape — this is the machine-facing payoff of sealing:

| Constructor | Calibratable members | Target-property shape |
|---|---|---|
| `cascade` (post) | each gate threshold `θ_i` | conditional property of the ACCEPTANCE REGION the gate induces (e.g. `P(arm_i correct │ margin ≥ θ_i) ≥ p`) — exactly RFC 0001 §3.5's per-CVAR scope |
| `cascade` (pre) | each routing threshold `θ_i` | conditional property of the ROUTE the signal induces (e.g. `P(arm_i adequate │ σ_i ≥ θ_i) ≥ p`) |
| `ensemble` | `accept.threshold`; `cardinality` when bound Calibrated | acceptance: `P(aggregate correct │ stat ≥ θ) ≥ p`; cardinality: cost-bounded sufficiency |
| `loop` | `stop.threshold` (signal_accept) | stop adequacy: `P(accepted state meets target │ σ ≥ θ) ≥ p` |

The §3.2 item-11 binding rule makes these target-property shapes
well-posed: the certificate's `H_c(σ)` covers the very signal the gate
evaluates at runtime, never a different one.

The **Claim scope** paragraph added to RFC 0001 §3.5 (the 2026-06-06
post-acceptance owner wording-audit clarification, recorded as the
`post-acceptance` row of RFC 0001's §10 review log; no semantic rule changed)
applies verbatim here: each certificate is a per-variable, procedural claim —
the declared calibration procedure ran over the declared evidence pool under
the hashed freshness context, and, where the `TargetProperty` carries a
statistical bound, that bound's subject is the conditional, component-level
property the variable controls — valid only under the documented assumptions.
A "certified selection" is the **conjunction** of the §3.6 promotion win on
observed metrics AND per-CVAR certificate coverage; neither subsumes the
other. **A composite's end-to-end metrics remain observations** under the
promotion judgment; nothing in this RFC creates a config-level guarantee, and
user-facing copy MUST NOT present a composite as one.

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
                          ∪ ({cardinality(x)} ∩ N_T)    (* iff x is an Ensemble in
                                                           sampling form whose
                                                           cardinality is bound Tuned;
                                                           ∅ otherwise — folds in
                                                           recursively through nesting *)
```

The `({cardinality} ∩ N_T)` term makes a composite's leaf set include its
ensemble's tuned sample count: a sampling-form ensemble whose `cardinality`
is a TVAR is parameterized by that TVAR exactly as a stage is parameterized
by its `tuned_params`, so swapping `k` must read stale through the same
parent-coverage cascade. The intersection with `N_T` keeps the codomain
TVAR-only (C6): a Calibrated or absent cardinality contributes nothing to
`leafT` (it is instead a member of `Cal`, §3.6). Because `leafT(composite(x))`
recurses over `arms/body/judge(x)`, nested ensembles' tuned cardinalities
fold up to every enclosing threshold's obligation.

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
                                          ∪ ({cardinality} ∩ N_T)   (* this ensemble's
                                                                       own k; nested arms'
                                                                       k flow in via leafT *)
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

**Scope of the fold (honest, per-member).** The fold is exact **per-member**
coverage: it guarantees that *each member CVAR* carries its own valid, fresh
certificate (its own §3.5 freshness context, including its own `t|π` parent
values). It does NOT establish a cross-level value-dependency: an OUTER
certificate is not bound to the *values* of INNER CVARs. Concretely, a nested
composite's inner threshold may be re-calibrated to a new value while the
outer construct's certificate stays fresh — because RFC 0001's freshness core
hashes tuned parents (`t|π`), not the resolved values of sibling/child CVARs,
and CVAR→CVAR dependencies remain deferred (§2). This limitation is named as
§6 assumption 8, with a recommended conservative practice (re-issue outer
certificates when any member of the subtree's `Cal` set is re-calibrated).

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

**Surface vs. expansion-output.** The full closed `Provenance` object above
is **expansion-output metadata produced by `expand` (SDK-internal)** — it is
NEVER surface syntax. The only provenance the `composites:` surface accepts
is the flat `pattern: <name>` **sugar key**, which maps to `Provenance.pattern`
on the emitted root node; the surface author never writes
`pattern_version`/`param_hash`/`node_path` (those are stamped by the
expander). The surface accepts ONLY the sugar key.

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
| `self_debug` | `Loop(body=stage(a), state_keys=[attempt, critique], stop=external_accept(tests), max_iters=K)` | "2-step knob" at K=1; `external_accept` stop ⇒ **NO unroll** (§3.8) |
| `self_refine` | `Loop(body=stage(a), state_keys=[draft], stop=signal_accept(σ, θ), max_iters=K)` | calibrated `signal_accept` stop ⇒ unroll-eligible (§3.8) |

The catalog is curated in-repo; growth follows the admission contract, never
ad-hoc (the documented failure mode of open chain taxonomies).

### 3.8 Loop → K-chain: a semantic compilation (not a surface map)

`Unroll` is a **semantic compilation into an internal K-chain execution
form** (an SDK intermediate representation), NOT a syntactic rewrite into the
surface algebra (cross-model fresh pass). It is deliberately NOT a map into a
surface `Cascade_post`: the v1 gate registry has only `margin_below` and
`signal_below`, and **neither is a state-predicate gate** — there is no
surface gate kind whose decision is `¬stop = σ(state) < θ` over the loop's
threaded state. Writing `Unroll` as a surface `Cascade_post` with
`¬stop` gates would therefore require a gate kind that does not exist; the
compilation target is instead the internal K-chain, whose escalation
predicate the SDK IR carries directly.

The unroll offer exists **only for `signal_accept` loops**. For such a loop
the chain of length `K` is:

```
KChain(Loop(b, S, signal_accept(σ, θ), K))
   = ⟨ stages = [b₍₁₎ .. b₍K₎],
       escalate after stage i  ⟺  ¬stop₍ᵢ₎  =  σ(state₍ᵢ₎) < θ ⟩
```

where `b₍ᵢ₎` is the body specialized to iteration `i`'s threaded state over
the declared `state_keys`, and the chain escalates to stage `i+1` exactly
when the `signal_accept` stop has NOT fired (`σ(state₍ᵢ₎) < θ`, the
acceptance-direction complement). `external_accept` loops (opaque runtime
predicate — no declared state predicate to chain) and `exhausted` loops (no
acceptance predicate at all) offer **no unroll**.

This is a **compilation relation, not semantic equality** (design review,
codex): it is meaning-preserving **only under all of**:

1. the body's state flows exclusively through the declared `state_keys`
   (`state_keys = []` ⟺ pure body) — no ambient mutation;
2. the stop rule is a deterministic function of the declared state
   (structurally enforced for `signal_accept` by `stop_signal_outside_state`
   — the only stop kind that offers unroll, so condition 2 is structural
   here, not contract-asserted);
3. iterations are bounded by `max_iters` (always true in this algebra —
   `max_iters` is required);
4. telemetry and side effects are observationally accounted:
   `iterations_used` maps to "index of the selected chain stage",
   `stop_reason` maps to the final escalation decision, and per-iteration
   effects are declared effects of the corresponding chain stage.

Implementations MAY offer the unrolled compilation (e.g. `unroll=K` on
`signal_accept` loop patterns). Verification is split by mechanism (claim
C5): the model checker compares the **execution traces** of the `Loop` and of
its `KChain` under conditions 1–3 at small scopes (output/selection
preservation); the telemetry/effect accounting of condition 4 is verified by
the golden expansion fixtures and SDK property tests for every pattern that
offers `unroll`. Outside the conditions, and for non-`signal_accept` loops,
no equivalence is claimed.

### 3.9 Surface syntax (draft normative for the validators packet)

**The arm surface form** — ONE shape, used EVERYWHERE an `Arm` appears
(cascade `arms[]`, loop `body`, ensemble `arms[]` and `judge`):

```
ArmSurface ::= Ident                                      (* bare = stage, tuned_params [] *)
             | { stage: Ident, tuned_params?: [Ident*] }  (* explicit stage form *)
             | { composite: Ident }                       (* tagged nesting *)
```

Unknown keys in the object forms reject (`invalid_arm_shape`); absent
`tuned_params` defaults to `[]`. There is no separate per-composite
`arm_params` map — parentage is declared ON the arm, so body/judge/nested
arms are expressed identically.

**The signal surface form** (everywhere a `SignalUse` appears —
`signal_below` gates and `signal_accept` stops):

```
SignalSurface ::= { signal: Ident, inputs?: [Ident*] }   (* inputs default [] *)
```

`signal` names a registry signal exactly as `calibration.signal` does
(operationally resolved; one signal model across the language); malformed
objects reject (`invalid_signal_use`).

```yaml
composites:
  - name: answerer
    kind: cascade            # cascade | ensemble | loop (closed)
    placement: post          # cascade only; default post
    arms:
      - { stage: cheap_stage, tuned_params: [cheap_model, temperature] }
      - { stage: strong_stage, tuned_params: [strong_model] }
    gates:
      - kind: margin_below
        threshold: router.margin_threshold     # CVAR of type float
    pattern: binary_cascade  # the ONLY surface provenance key (sugar → Provenance.pattern, §3.7)

  - name: coder
    kind: loop
    body: { composite: answerer }              # tagged nesting
    state_keys: [attempt, critique]
    stop: { kind: external_accept, predicate: run_unit_tests }
    max_iters: 3
    pattern: self_debug
```

The surface `pattern:` field is a flat **sugar key** mapping to
`Provenance.pattern` (§3.7); the full closed `Provenance` object is
expansion-output metadata stamped by the expander (SDK-internal) and is never
surface syntax — the surface accepts ONLY the sugar key, never
`pattern_version`/`param_hash`/`node_path`.

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
fixture in the validators packet). The list and the well-formedness /
execution rules above are in **1:1 correspondence** — every code below is
emitted by exactly the cited rule, and every rule that rejects cites exactly
one of these codes (or the reused RFC 0001 `missing_ref` family):

| Code | Emitted by |
|---|---|
| `unknown_composite_kind` | item 1 — `kind` outside the closed registry |
| `composite_binds_value` | §3.1 — a value bound on a composite |
| `composite_shadows_name` | §3.1 — `N_X` name shadows another class |
| `duplicate_composite` | §3.1 — duplicate name within `N_X` |
| `empty_arms` | item 2 — `arms` empty for any constructor |
| `ambiguous_arm` | item 3 — bare arm id collides with a composite name |
| `missing_composite_ref` | item 3 — `composite(x)` resolves to no `N_X` member |
| `composite_cycle` | item 4 — the `N_X` reference graph is cyclic |
| `gate_arm_incompatible` | item 5 — `margin_below` gating a non-margin-bearing arm |
| `gate_kind_placement_mismatch` | item 5 — `margin_below` in `pre`, or `signal_below` in `post` (both directions; subsumes the former `pre_gate_requires_signal`) |
| `missing_gate_signal` | item 5 / `GateDecl` — `signal_below` gate missing its `signal` |
| `duplicate_stage` (extended scope) | item 6 — duplicate `stage(·)` within one composite |
| `cardinality_arity_mismatch` | item 7 — `cardinality` present iff `|arms| = 1` violated |
| `invalid_cardinality_type` | item 7 — `cardinality` ref not int-typed |
| `invalid_cardinality_value` (R9) | item 7 — resolution-time `k < 1` (extends the §3.4 acceptance algebra as `Accept₁.₂`) |
| `stop_signal_outside_state` | item 8 / `StopDecl` — `stop.signal.inputs ⊄ state_keys` |
| `missing_stop_signal` | `StopDecl` — `signal_accept` stop missing its `signal` |
| `missing_stop_threshold` | `StopDecl` — `signal_accept` stop missing its `threshold` |
| `missing_stop_predicate` | `StopDecl` — `external_accept` stop missing its `predicate` |
| `unknown_stop_kind` | `StopDecl` — `stop.kind` outside the closed registry |
| `invalid_max_iters` | item 8 — `max_iters < 1` |
| `missing_judge` | `AggregateDecl` — `judge_max` aggregate missing its `judge` |
| `unknown_aggregate_kind` | `AggregateDecl` — `aggregate.kind` outside the closed registry |
| `invalid_tuned_param` | item 9 — a `tuned_params` entry not resolving to a TVAR |
| `invalid_threshold_type` | item 10 — a gate/accept/stop threshold CVAR not int/float |
| `missing_calibration_signal` | item 11 — composite-referenced `θ` missing `calibration.signal` |
| `signal_mismatch` | item 11 — composite-referenced `θ`'s `calibration.signal ≠ sig(construct)` |
| `unbound_signal_inputs` | item 11 — use-site `SignalUse.inputs ≠ []` not covered by `signal_inputs`, or covered value ≠ the use-site list |
| `missing_composite_parent` | §3.5 — `required_parents(θ) ⊄ depends_on(θ)` |
| `invalid_arm_shape` | §3.9 — unknown keys in an `ArmSurface` object form |
| `invalid_signal_use` | §3.2 / §3.9 — malformed `SignalUse` object (missing `signal`, unknown keys, non-list `inputs`) |

Plus the RFC 0001 `missing_ref` family, reused unchanged for every
CVAR/threshold namespace reference (gate/accept/stop thresholds, item 6), and
rejection **R9** (`invalid_cardinality_value`) extending the §3.4 acceptance
algebra as `Accept₁.₂` (§3.2 item 7). The former `pre_gate_requires_signal`
code is RETIRED into `gate_kind_placement_mismatch`, which now covers both
directions of gate-kind/placement misuse (cross-model fresh pass).

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

**Subsumption is exact on EXECUTION SEMANTICS, with two intended composite
ratchets on the lint surface** (cross-model fresh pass — the `≡` above is the
execution-semantics identity, not a lint identity). The mapping is exact on
StageRef opacity, the gate→CVAR rule, and execution semantics, which are
unchanged (§3.2 incorporates RFC 0001 §3.8 by reference). The composite form
ADDITIONALLY enforces two static lints that the RFC 0001 `policies:` form does
NOT — both deliberate, explicit ratchets, fired only at the composite use
site:

- **`stages` → empty `tuned_params`** (§3.5): the policy form never declared
  parentage, so the obligation lint is vacuous on migrated forms until authors
  declare per-arm `tuned_params`.
- **signal/threshold binding** (§3.2 item 11): a gate threshold CVAR used by a
  composite must declare `calibration.signal = sig(construct)` (and, when its
  `SignalUse.inputs ≠ []`, cover `signal_inputs`). RFC 0001 leaves
  `calibration.signal` OPTIONAL, so a legacy `policies:` cascade is unaffected;
  only the composite use site adds this obligation.

`parameters?` and `scope?` carry over verbatim with identical semantics and
the identical outside-P8 categorization.

**P1 is preserved.** Because a TVL 1.1 module declares no `composites:` block,
neither ratchet can fire on it — both lints are use-site obligations of a
`composites:` construct, of which a 1.1 module has none. A valid TVL 1.1
cascade `policies:` block whose threshold CVAR omits `calibration.signal` (or
covers no `signal_inputs`) therefore remains valid under TVL 1.2 with RFC 0001
semantics untouched; the ratchets are an opt-in cost of MOVING to the composite
form, not a retroactive invalidation. `policies` with `strategy: cascade`
remains VALID in TVL 1.2 (no deprecation this increment); the
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
| **C3** Coverage-fold soundness (PER-MEMBER) | `Cal` over all roots collects EXACTLY the calibratable members (the CVARs) of the whole expansion (no over-, no under-collection, judge and nested levels included); strict selection requires a valid fresh certificate for EACH such member and fails closed on any gap. **Scope:** this is exact PER-MEMBER coverage — each member CVAR's own freshness — and is explicitly NOT a cross-level value-dependency guarantee: an outer certificate is not bound to inner CVAR values (a nested composite's inner threshold may recalibrate while the outer certificate stays fresh; §6 assumption 8, riding the §2 CVAR→CVAR deferral) | model checking (fold vs. ground-truth member walk + a MUST-BE-SAT uncertified-gate violation); red-first SDK tests |
| **C4** Cost compositionality | the cost forms close over nesting: substituting an arm's cost form yields the composite's, for all five forms (§3.4) | model checking at small scopes (structural induction of FORM closure only); operational estimate quality is OUT OF SCOPE (§6 assumption 3); cross-implementation compatibility of `c(agg)` and the cost forms pinned by SHARED golden cost fixtures (the cross-SDK fixture convention) |
| **C5** Loop→K-chain compilation (`signal_accept` only) | for `signal_accept` loops, under §3.8 conditions 1–3, `Unroll` into the internal K-chain preserves the selected output / execution trace at small scopes (model-checked, trace comparison Loop vs. K-chain); condition 4's telemetry accounting holds for every catalog pattern offering `unroll` (golden fixtures + SDK property tests); `external_accept`/`exhausted` loops offer no unroll and claim nothing | split by mechanism as stated |
| **C6** Dependency-compilation soundness (TVAR-ONLY obligations) | `required_parents` obligations land in `N_T` only and are checkable statically; no rule of this RFC can emit or require a non-TVAR `depends_on` entry; `missing_ref` remains the single entry-validity authority. **Scope:** the obligations bind tuned-TVAR freshness only; they do NOT establish CVAR→CVAR (cross-level value-dependency) freshness, which stays deferred (§2; §6 assumption 8) | model checking (codomain check + MUST-BE-SAT violation transition); `missing_composite_parent` lint tests |

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
8. **Nested-certificate freshness is per-member, not cross-level**
   (cross-model fresh pass) — the §3.6 coverage fold and the §3.5
   parent-coverage obligations bind *each member CVAR's own* freshness; they
   do NOT make an OUTER certificate depend on the *values* of INNER CVARs.
   An inner threshold can be re-calibrated to a new value while an outer
   construct's certificate remains fresh, because RFC 0001's freshness core
   hashes tuned parents (`t|π`), not sibling/child CVAR values, and
   **CVAR→CVAR dependencies remain deferred** (§2). This is the direct
   consequence of that deferral; closing it is the work of the deferred
   CVAR→CVAR dependency mechanism. *Recommended conservative practice
   (non-normative):* implementations **SHOULD** re-issue an outer construct's
   certificate whenever any member of that subtree's `Cal` set (§3.6) is
   re-calibrated, so that an outer "fresh" verdict never outlives an inner
   recalibration in practice.

## 7. Field categorization (P8 alignment)

Composites introduce **no content-typed fields**: kinds, placements, arity,
identifiers (names, StageRefs, predicate ids, state keys, signal ids from
the `calibration.signal` namespace, opaque input-feature ids), one required
integer (`max_iters`), and namespace references.
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
   policy form and its composite form have **identical execution semantics**
   and lint identically on the shared examples **except** for the two intended
   composite-only ratchets — the empty-`tuned_params` parent-coverage
   obligation (§3.5) and the signal/threshold binding (§3.2 item 11, incl.
   `signal_inputs` coverage) — which fire only on the composite form, never on
   the legacy `policies:` form), with explicit degenerate fixtures: `m=1`
   cascade, `k=1` sampling ensemble, committee ensemble, `max_iters=1` loop,
   empty-arms rejection, tagged-nesting under an ensemble judge, an
   `ambiguous_arm` rejection, and a `gate_arm_incompatible` /
   `gate_kind_placement_mismatch` rejection pair.
4. Owner acceptance recorded in this header and §10 (human-only gate).
5. No semantic change to any RFC 0001 construct: the RFC 0001 conformance
   fixtures pass unchanged.

## 10. Review log

| Round | Reviewer | Verdict | Disposition |
|---|---|---|---|
| 1 | codex (gpt-5.5, xhigh, read-only) — 2026-06-06 | **REJECT** — 10 blocking, 5 non-blocking | All addressed in Draft v2: (1) arm resolution made tag-driven (`stage`/`composite` tags; bare = stage always; `ambiguous_arm` rejection); (2) pre-cascade made total (first-match-wins routing with fallback arm, per-gate signals + per-gate cost, absent-signal routes onward, `pre_gate_requires_signal`); (3) ensemble cardinality: required iff single-arm, int-typed, R9 rejection for k<1, both cost forms; (4) judge output contract (finite numeric score, exclusion rules, all-excluded fails, deterministic tie-break); (5) loop state formalized (`state_keys` + `stop_signal_outside_state`; pure ⟺ empty); (6) dependency compilation rebuilt as DECLARED parentage (`tuned_params` on stage arms) + static coverage obligations (`missing_composite_parent`), `missing_ref` stays single authority, judge/signal parents included; (7) root-consumption rule (all N_X roots, conservative fail-closed; selective consumption deferred); (8) subsumption made exact (scope?/parameters? carried onto Composite verbatim; empty tuned_params on migrated stages stated as intended ratchet); (9) Provenance closed shape (param_hash only, canary in admission contract); (10) C5 verification split by mechanism incl. condition 4. Non-blocking: full error-code surface §3.11; SignalSourceRef clarified as the RFC 0001 calibration-source registry (no new declaration surface); degenerate fixtures added to §9; AcceptDecl separated from GateDecl with opposite inequality; P6 note absorbed. |

| 2 | codex (gpt-5.5, xhigh, read-only) — 2026-06-06 | **REJECT** — 5 blocking (all on the NEW round-1 machinery); round-1 dispositions confirmed closed | All addressed in Draft v3: (1) R9 integrated into the acceptance algebra — explicit `Accept₁.₂ ⟺ ¬(R1∨…∨R9) ∧ calibrators ≠ ⊥` with P3/P4 carrying over and a conservativity note (R9 unreachable on 1.1 modules); (2) `tuned_params` entries now have a static TVAR-only resolution rule (`invalid_tuned_param`, well-formedness item 9) making C6 hold by construction; (3) `arm_params` map REPLACED by a single ArmSurface form declared ON the arm (bare Ident │ {stage, tuned_params?} │ {composite}) used identically for cascade arms, loop body, ensemble arms and judge — `invalid_arm_shape` for unknown keys; (4) `SignalSourceRef` (a source id) replaced by `SignalUse ⟨spec: SignalSpec, inputs⟩` preserving RFC 0001's source/signal split — the spec is the §3.5 closed signal shape hashed H_c(σ); stop inputs MUST ⊆ state_keys making `stop_signal_outside_state` precisely checkable; (5) numeric threshold type rule (`invalid_threshold_type`: thresholds are int/float CVARs; non-finite resolved values fail evaluation). |

| 3 | codex (gpt-5.5, xhigh, read-only) — 2026-06-06 | **REJECT** — 3 findings (1 model choice + 2 wording residue); rounds 1–2 dispositions confirmed closed (incl. judge-arm coverage via ArmSurface and §3.11 completeness) | All addressed in Draft v4: (1) the signal model is CHOSEN explicitly — `SignalUse.signal` is a named Ident into the SAME registry namespace as RFC 0001's module-facing `calibration.signal` (one signal model across the language; the closed SignalSpec shape enters only through H_c(σ)); SignalSurface grammar added to §3.9 and `invalid_signal_use` to §3.11; (2) stale `arm_params` wording in §4 corrected to per-arm `tuned_params`; (3) §7 terminology fixed (signal ids + opaque input-feature ids; sources reserved for evidence pools). |

| 4 | codex (gpt-5.5, xhigh, read-only) — 2026-06-06 | **REJECT** — 1 blocking (round-3 deltas confirmed closed): the signal/threshold calibration binding was not normative | Addressed in Draft v5: §3.2 item 11 — every thresholded construct determines a signal id (explicit `SignalUse.signal` for `signal_below`/`signal_accept`; canonical stat ids `vote_margin`/`vote_agreement` for `margin_below`/`stat_at_least`); `θ.calibration.signal` MUST equal it; static lints `signal_mismatch` + `missing_calibration_signal`; rationale recorded (a threshold calibrated against signal A gating signal B is vacuously fresh); §3.3 notes the rule makes the target-property shapes well-posed. |

| 5 | codex (gpt-5.5, xhigh, read-only, FRESH unanchored) — 2026-06-06 | **REJECT** — 8 blocking + 4 non-blocking | All addressed in Draft v6. Blocking: (FB1) §3.2 item-11 signal binding broke P1 (RFC 0001 leaves `calibration.signal` OPTIONAL) → rule re-scoped to COMPOSITES ONLY, fires at the composite USE SITE, never on `cvars`/`policies`; §4 subsumption narrowed to exact-on-execution-semantics + two intended composite-only ratchets (empty-`tuned_params`, signal binding); §4 P1-preserved sentence added (1.1 modules declare no composites); §9 criterion 3 "lint identically" carved out for the two ratchets. (FB2) use-site `SignalUse.inputs` not freshness-bound → `signal_inputs` added to the RFC 0001 §3.5 `ctx_ext` extension registry (conservative); item-11 rule requires `hash_covered_context ⊇ {signal_inputs}` AND covered value = use-site list when `inputs ≠ []`, else `unbound_signal_inputs`. (FB3) nested-certificate freshness honestly scoped → C3/C6 reworded to per-member coverage / TVAR-only obligations, explicitly NOT cross-level value-dependency freshness; §6 assumption 8 added (riding the §2 CVAR→CVAR deferral) with non-normative SHOULD to re-issue outer certificates on inner recalibration; §2 deferral bullet gains a revisit trigger; §3.6 fold scope note added. (FB4) `leafT` extended so a sampling ensemble's tuned `cardinality` (`{cardinality} ∩ N_T`) is in its leaf set, recursively through nesting. (FB5) post-cascade gate typing with strict placement symmetry — `margin_below` POST-only + gated arm must be margin-bearing (stage / `majority_vote` ensemble) else `gate_arm_incompatible`; `signal_below` PRE-only; `gate_kind_placement_mismatch` covers both misuse directions (retiring `pre_gate_requires_signal`); `missing_gate_signal` for signal-less `signal_below`; future output-signal post-gate noted deferred. (FB6) §3.2.1 closed result algebra `ArmResult ::= output(o, vote_stats?) | no_accept | error` with total/deterministic propagation rules unifying the per-construct exception/no-accept sentences; root no_accept → §3.6 fail-closed under strict / honest no-output (runtime-defined scoring) under non-strict; vote abstention stays internal. (FB7) §3.8 + C5 rewritten — `Unroll` is a SEMANTIC compilation into an internal K-chain IR (no surface state-predicate gate exists), `signal_accept` loops only; `external_accept`/`exhausted` offer no unroll; catalog table made honest (`self_debug` external_accept ⇒ no unroll). (FB8) §3.7/§3.9 — surface `pattern:` is sugar → `Provenance.pattern`; the full closed `Provenance` object is expansion-output (SDK-internal), never surface syntax. Non-blocking: (NB9) §3.3 cross-ref now cites the RFC 0001 §3.5 *Claim scope* paragraph accurately (2026-06-06 post-acceptance owner wording-audit clarification, §10 `post-acceptance` row); (NB10) pre-cascade route fixed to `j = min({ i < m : σ_i(x) ≥ θ_i } ∪ {m})`; (NB11) §3.11 restated as a 1:1 code↔rule table incl. `missing_gate_signal`, `missing_stop_signal`, `unbound_signal_inputs`, `gate_arm_incompatible`, `gate_kind_placement_mismatch`; (NB12) C4 verification narrowed — structural induction validates FORM closure only, operational estimate quality out of scope (assumption 3), cross-impl `c(agg)`/cost forms pinned by SHARED golden cost fixtures. |

Design pre-review (before Draft v1): Option E architecture ACCEPTed by
codex (gpt-5.5 xhigh — 4 hard constraints + terminology edits, all
incorporated: not-a-binding-kind §3.1; no CVAR→CVAR deps §3.5; CascadePolicy
anchor §4; compilation-relation framing §3.8; "structural constructors"
naming) and by gemini (workspace-impact concurrence: schema stability,
JS parity, spine coverage-fold fit, FE provenance rendering).
