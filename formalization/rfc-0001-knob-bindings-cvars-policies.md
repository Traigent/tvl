# RFC 0001 — Knob Bindings: Calibrated Variables (`cvars`) and `policies`

| | |
|---|---|
| **Status** | **ACCEPTED** — owner acceptance recorded 2026-06-05 (nimrod, interactive) after cross-model ACCEPT ×2 (anchored round 4 + fresh-pass confirmation); see §10 |
| **Target language version** | TVL 1.1 (conservative extension of 1.0) |
| **Tracking** | `FR-TVL-CVARS-POLICIES-V1` · ChangeSession `cs_607ce2f4f8833804` |
| **Phases covered** | Phase 0 (scope freeze) · Phase 1 (formal semantics) · Phase 2 (property claims) |
| **Downstream gate** | Acceptance of this RFC + green Phase 3/4 validators unblock all SDK implementation |

## 1. Motivation

TVL 1.0 models exactly one binding for a declared variable: **tuned** — every `tvars`
entry is optimizer-visible and searched. Real governed tuning needs two more bindings
that today live outside the language, untyped and ungoverned:

1. **Fixed values** — runtime-supplied constants that are part of the resolved
   configuration but never searched.
2. **Calibrated values** — quantities whose optimal value is a *data-dependent
   function of the tuned variables*, fit from calibration evidence rather than
   searched (the canonical instance: a router's escalation threshold, which must be
   re-fit whenever the cheap/strong models, sample count `k`, comparator, dataset, or
   budget target change). Today these are fit ad hoc, with no validity object, no
   staleness detection, and no governance.

This RFC introduces the **one-Knob model**: every configuration variable is a *knob*
with exactly one typed binding — **Tuned | Fixed | Calibrated** — and extends TVL with:

- a `cvars` block declaring **calibrated variables** (CVARs): parsed and governed,
  **excluded from structural SAT and from the optimizer search space**;
- a `policies` block declaring named operational policies (first concrete strategy:
  `cascade`), aligned with the effectuation knob-kind `policy`;
- `promotion_policy.require_calibration` — a strict evidence mode whose certificate
  freshness is validated against a **hash-covered calibration context**;
- formal **namespace/scope rules** replacing the current ambiguity where dotted names
  are simultaneously "nested" in grammar prose and flat strings in every
  implementation.

The bilevel-programming literature gives this the standard reading: tuned variables
are **outer variables**, calibrated variables are **inner variables**, and the
calibrator is the (memoized) **response function** (Franceschi et al., ICML 2018).
No mainstream HPO framework models inner variables natively; TVL 1.1 makes them a
first-class governed construct.

## 2. Scope freeze (Phase 0)

**Minimum formal surface** (in scope):

| Concept | One-line definition |
|---|---|
| Tuned variable (TVAR) | Optimizer-visible declaration with a searchable domain (`tvars`, unchanged) |
| Fixed value | Runtime-supplied constant at resolution; never searched; never declared in the module |
| Calibrated variable (CVAR) | Value produced by a calibrator from calibration evidence; never searched; certificate-backed |
| Policy / CascadePolicy | Named declarative operational policy; `cascade` = staged escalate-or-stop execution |
| Namespace / node scope | Identity, resolution, and collision rules for declared names |
| Ref / dependency | A CVAR's declared dependence on tuned parents — a freshness relation, **not** a constraint |
| Certificate / freshness | Validity object binding a calibrated value to the hash of its calibration context |
| Strict promotion mode | Evidence modes under which promotion fails closed |

**Explicitly deferred** (out of scope for TVL 1.1 and the whole program increment):

- in-loop CVAR fitting (re-calibration inside the optimization loop);
- a CVAR optimizer (searching over calibration strategies);
- generic policy algebra (composition, conditionals over policies);
- CVAR→CVAR dependencies (`depends_on` may name TVARs only in v1);
- CVAR substitution-as-constant into structural constraints;
- relative/implicitly-prefixed name resolution (v1 resolution is exact-match only);
- workflow-ownership *semantics* for `scope` (v1 is metadata + one consistency lint);
- FE/BE product views of cvars/policies/certificates.

## 3. Formal model (Phase 1)

Notation follows `formalization/tvl-formal-semantics.md` (§2.1): Γ is the typing
context, `E_τ` the environment snapshot, `Config(Δ, E_τ)` the configuration space,
`F^str` structural feasibility, layers per §1.5.4.

### 3.1 Binding partition

Let `N` be the set of variable names participating in a resolution. TVL 1.1
partitions `N`:

```
N = N_T ⊎ N_F ⊎ N_C          (Tuned ⊎ Fixed ⊎ Calibrated; pairwise disjoint)
```

- `N_T` = names declared in `tvars` (unchanged from TVL 1.0).
- `N_C` = names declared in `cvars`.
- `N_F` = `dom(f)` for the **runtime-supplied fixed assignment** `f` provided by the
  consuming runtime at resolution time. TVL 1.1 deliberately has **no `fixed:`
  module block** and **no change to configuration documents**: the existing
  configuration schema's `assignments` remain *candidate TVAR assignments* exactly
  as in 1.0 (`tvl-configuration.schema.json` is untouched). `N_F` exists only in the
  resolution semantics; the static module never names it.

Disjointness of `N_T ⊎ N_C` is syntactic and statically checkable
(`binding_partition_collision`, also surfaced as `cvar_shadows_tvar`). Disjointness
of `N_F` from the declared names is checked **at resolution time**: a runtime fixed
assignment whose domain intersects `N_T ∪ N_C` is rejection **R3**
(`duplicate_provider`, §3.4).

**`Range.default` is unchanged**: a TVAR's `default` remains a *default candidate
value* within its searched domain. It is NOT a Fixed binding.

### 3.2 TVAR projection (optimizer visibility)

The optimizer-visible search space is exactly the tuned projection:

```
Σ = ∏_{n ∈ N_T} 𝒟⟦domain(n)⟧(E_τ)
```

Every optimizer suggestion `t` satisfies `dom(t) = N_T`. CVARs, fixed values, policy
internals, and certificates are **invisible** to the optimizer (Property P2). The
typing context for structural constraints is unchanged: **Γ ranges over `N_T`
only** — `cvars` do not enter Γ, `Config(Δ, E_τ)`, or `F^str` (Property P5; §3.8 has
the lint that makes violations precise).

### 3.3 CVAR declarations

Abstract syntax (extends §2 of the formal semantics):

```
CVarDecl ::= ⟨ name : Ident,
               type : Type,                      (* same Type grammar as TVarDecl *)
               domain? : ValidityDomain,         (* OPTIONAL, see below *)
               calibration : CalibrationSpec,
               governance? : ⟨ require_calibration : Bool ⟩,
               scope? : Scope ⟩

CalibrationSpec ::= ⟨ source : Ident,            (* evidence source id, REQUIRED *)
                      signal? : Ident,           (* signal spec id *)
                      calibrator? : Ident,       (* calibrator id *)
                      depends_on? : Ident* ⟩     (* tuned parents π ⊆ N_T; may be empty *)

Scope ::= ⟨ node? : Ident, agent? : Ident, workflow? : Ident ⟩
```

**Validity domains are not search domains.** A CVAR's optional `domain` is a
membership predicate applied to the *calibrated output* at resolution time. Unlike
TVAR search domains, a float-range validity domain denotes the **closed real
interval** `[lo, hi]` and **does not require `resolution`** — there is nothing to
enumerate. This is an intentional, explicit deviation from the TVAR float-domain
rule (which exists to keep search spaces finite); validity domains never feed the
SAT encoding, the optimizer, or `𝒟⟦·⟧` enumeration.

`depends_on` declares the parent set `π(n) ⊆ N_T`. Each entry MUST resolve (exact
match, §3.7) to a declared TVAR; an entry naming a CVAR or policy is an error in v1.
Consequently the v1 dependency graph is **bipartite (CVAR → TVAR) and cycles are
unreachable by construction**; rejection R1 below is retained as a normative
forward-compatibility guard for the deferred CVAR→CVAR extension, and the Phase 3
model checker proves *unreachability* of R1 in v1 rather than exhibiting it.

**Dependencies are a freshness/validity relation, not search-space constraints**:
`depends_on` never generates SAT clauses and never restricts `Σ`. Its only semantic
effect is through the freshness context (§3.5).

### 3.4 CVAR resolution

A CVAR `n` denotes a **calibrator** (the inner/response function):

```
𝒦_n : (assignments to π(n)) × 𝓔_cal  →  Val_{τ(n)} ∪ {⊥}
```

where `𝓔_cal` is evidence drawn from the **calibration split** and `⊥` means
*no decision*. TVL specifies the *contract* of `𝒦_n` (inputs, freshness,
abstention); the calibrator implementation is operational (§1.5.2), identified by
`calibration.calibrator` / `calibration.source`.

Given an optimizer suggestion `t ∈ Σ` and a runtime fixed assignment `f`, the
**resolved configuration** is:

```
c  =  t  ∪  f  ∪  { n ↦ v_n : n ∈ N_C }
```

computed in deterministic topological order over the dependency graph. Define the
rejection conditions:

| # | Rejection | Meaning |
|---|---|---|
| R1 | `cycle` | the dependency graph is not a DAG *(unreachable in v1 by construction; normative for the deferred CVAR→CVAR extension)* |
| R2 | `missing_ref` | a `depends_on` entry resolves to no TVAR declaration |
| R3 | `duplicate_provider` | two sources provide the same output name — including `dom(f) ∩ (N_T ∪ N_C) ≠ ∅` |
| R4 | `phase_mismatch` | a value is consumed before the phase that produces it |
| R5 | `infeasible_value` | a fixed or calibrated value violates its declared validity domain or type |
| R6 | `stale_certificate` | certificate validity check fails (§3.5) for a CVAR that requires one |
| R7 | `evidence_leakage` | calibration evidence intersects the evaluation split (`𝓔_cal ∩ 𝓔_eval ≠ ∅`) |
| R8 | `insufficient_evidence` | evidence below the declared floor (for a chance-style target at level ε: `n_cal < ⌈1/ε⌉ − 1`) |

**Resolution acceptance is exactly the complement of rejection plus calibrator
success** (this single definition makes soundness and completeness two directions of
one biconditional — cross-model review round 1, finding 1):

```
Accept(t, f, M, 𝓔_cal) ⟺ ¬(R1 ∨ R2 ∨ R3 ∨ R4 ∨ R5 ∨ R6 ∨ R7 ∨ R8)
                          ∧ ∀ n ∈ N_C : 𝒦_n(t|π(n), 𝓔_cal) ≠ ⊥
```

- **Soundness (P3)**: `Accept ⟹` every conjunct on the right (by definition).
- **Completeness (P4)**: if no rejection condition holds and every calibrator
  returns a value, the resolver MUST produce the resolved configuration — no
  spurious rejection, no additional implicit conditions.
- A calibrator returning `⊥` with no rejection condition holding is reported as
  `no_decision` (distinct from R6/R8; it feeds §3.6).

### 3.5 Certificates and freshness

A **certificate** binds a *specific calibrated value of a specific CVAR* to the
exact context it was fit under (cross-model review round 1, finding 2 — the subject
is mandatory):

```
Certificate ::= ⟨ subject : ⟨ cvar : Ident,
                              type : Type,
                              value_hash : Hash ⟩,     (* H_c(canonical value) *)
                  target : TargetProperty,
                  issued_hash : Hash,                  (* H_c(ctx) at issue time *)
                  decision : CERTIFIED | NO_DECISION | BEST_EFFORT_UNCERTIFIED,
                  evidence : ⟨ n : ℕ, pool_hash : Hash ⟩ ⟩
```

There is **no open `payload` field** in the v1 certificate: every field is one of
the closed shapes above (identifiers, types, hashes, counts, enum) — this is what
makes Property P8 checkable at the schema level. Implementations needing more
context attach it *outside* the certificate object.

The decision vocabulary is shared with the per-config guarantee certificates already
in TraigentSchema (`guarantee_certificate_schema.json`): **one certificate ontology,
two scopes** — per-config selection there, per-CVAR value here.

**Freshness context.** The context has a **mandatory core** — always hashed,
non-negotiable — and **optional extensions** (cross-model review round 1,
finding 3 — the module can never opt out of the core):

```
ctx_core = ( ctx_schema_version,        — version of this context schema AND the
                                          canonicalization profile (currently 1)
             cvar_name,
             t|π                        — tuned parent values (sorted by name),
             calibration_source_id,
             H_c(σ)                     — signal spec hash (id, version, score fn +
                                          version, comparator + version),
             calibrator_id, calibrator_version,
             H_c(calibrator_params),    — calibrator hyperparameters, canonicalized
             H_c(dataset), evidence_n,
             calibration_split, eval_split,
             target )

ctx_ext  ⊆ { stage_versions, model_versions, budget_assumptions, cost_assumptions }
```

**Validity** — every certificate field participates; the audit copies (`target`,
`evidence`) must agree with the live context so a certificate cannot *display*
one context while *hashing* another (cross-model review round 2, new finding 1):

```
valid(cert, n, v, ctx_now) ⟺ ctx_now.cvar_name = n
                            ∧ cert.subject.cvar = n
                            ∧ cert.subject.type = τ(n)
                            ∧ cert.subject.value_hash = H_c(v)
                            ∧ cert.target = ctx_now.target
                            ∧ cert.evidence.n = ctx_now.evidence_n
                            ∧ cert.evidence.pool_hash = ctx_now.dataset_hash
                            ∧ cert.issued_hash = H_c(ctx_now)
                            ∧ cert.decision = CERTIFIED
```

The first conjunct (`ctx_now.cvar_name = n`, cross-model review round 3) closes
the forged-subject hole: a certificate issued against CVAR B's context cannot
validate CVAR A by forging `subject.cvar = A`, because the live context
presented for A must itself name A — and then `issued_hash` (which covers
`cvar_name`) cannot match.

**Signal observations** (the other persisted-signal shape, referenced by P8) are
likewise closed:

```
SignalObservation ::= ⟨ signal : Ident, value : FiniteFloat, n : ℕ, split : Ident ⟩
```

— no metadata map, no content-typed field.

Because `t|π` is in the mandatory core, **certificates are parent-specific by
construction**: a new suggested value for any parent makes the certificate stale via
hash mismatch — and no module configuration can opt out of that.

`promotion_policy.require_calibration` declares which *extension* keys are
additionally covered; the core is implicit and immutable:

```yaml
promotion_policy:
  require_calibration:
    enabled: true
    hash_covered_context:        # OPTIONAL extension keys ONLY; the core is always hashed
      [stage_versions, model_versions, budget_assumptions, cost_assumptions]
```

A key outside the extension enum is an error (`invalid_calibration_context`); an
explicitly empty list is valid (core-only). The `empty_calibration_context` lint
from earlier drafts is retired — it is the *core* that may never be empty, and the
core is not module-configurable.

**Stale-certificate behavior**: an invalid or absent certificate (for a CVAR that
requires one) makes R6 fire. Under a strict evidence mode (§3.6) this MUST NOT
degrade to any default, cached, or "best-effort" value. Outside strict modes, a
declared `fallback` fixed value MAY be used; using it is observable (recorded in the
resolution output), never silent.

**Hash canonicalization `H_c`** (cross-model review round 1, finding 4): `H_c(x)` =
SHA-256 over the **RFC 8785 (JSON Canonicalization Scheme)** serialization of `x`,
with these TVL-specific restrictions on the value space:

1. Numbers MUST be finite — NaN and ±Infinity are rejected upstream (schema/R5),
   never hashed.
2. Numeric serialization follows JCS/ECMAScript shortest-round-trip rules (JCS
   already fixes `1` vs `1.0`, exponent form, and `-0` → `0`).
3. Strings are Unicode-NFC-normalized **before** JCS serialization.
4. Objects with duplicate keys are rejected at parse time (loaders MUST error, not
   last-wins).
5. `ctx_schema_version` is part of `ctx_core`, so any future change to the
   canonicalization profile or context schema is automatically staleness-inducing.

Two conformant implementations hashing the same context MUST produce the same hash;
this is an executable conformance obligation (Phase 4 fixture with known-answer
hashes).

### 3.6 Strict promotion fail-closed semantics

A module-with-resolution is in a **strict evidence mode** iff any of the following
holds (cross-model review round 1, finding 5 — per-CVAR governance included):

```
strict(M, c) ⟺ promotion_policy.require_calibration.enabled
             ∨ promotion_policy.chance_constraints ≠ ∅
             ∨ guaranteed-selection target               (operational profile)
             ∨ ∃ n ∈ N_C consumed by c :
                   cvars[n].governance.require_calibration = true
             ∨ ∃ n ∈ N_C consumed by c with a certificate-backed TargetProperty
```

Under `strict(M, c)`, the promotion judgment of §9 (formal semantics) is extended:

```
Promote(c_cand, c_inc, M) ⟹ CalibrationPass(c_cand, M)
```

where `CalibrationPass` requires every governed CVAR consumed by `c_cand` to carry a
certificate valid per §3.5. **Gate exception** is defined as: any exception raised
during the evaluation of `CalibrationPass`, `ChancePass`, `BandPass`, or the
dominance computation. The fail-closed law (Property P7):

> Under `strict(M, c)`, the verdicts *insufficient evidence* (R8), *gate exception*,
> *stale certificate* (R6), and *no_decision* (calibrator ⊥ or gate `no_decision`)
> each yield **no promotion** and **no winner-by-objective fallback**. The promotion
> outcome is the explicit no-certified-selection result, never the highest-scoring
> trial.

This sits at **Layer 2 (behavioral acceptability)** of §1.5.4 — `require_calibration`
is an acceptability filter exactly like `chance_constraints`: it determines *if* a
candidate is admissible, not *how* it compares (the ≻_ε dominance relation is
untouched).

### 3.7 Namespaces and node scope

TVL 1.0 status quo: `Ident` permits dots (`retriever.k`); the grammar prose calls
dotted names "nested structures," yet the reference validator, the SAT encoder, and
both SDK loaders treat names as **flat opaque strings**. TVL 1.1 resolves the
ambiguity in favor of the implementations, then adds the minimum scope structure:

1. **Identity is the full dotted string.** `retriever.k` is one name. Segments have
   no intrinsic semantics. (Status quo, now normative — P1-preserving.)
2. **Lexical rule** (single normative identifier grammar, aligned across EBNF,
   schema `pattern`, parser, and lints in Phase 4 — cross-model review round 1,
   finding 12): `Ident ::= Seg ('.' Seg)*` with `Seg ::= [A-Za-z_][A-Za-z0-9_]*` —
   ASCII, case-sensitive, no empty segments, no leading/trailing dots.
3. **One shared declaration namespace.** `tvars`, `cvars`, and `policies` names live
   in a single namespace. Exact-string duplicates anywhere in it are errors
   (`duplicate_tvar` / `duplicate_cvar` / `cvar_shadows_tvar` / `duplicate_policy` /
   `policy_name_conflict`).
4. **Resolution is exact-match only.** Every namespace reference — in v1 that is
   exactly `calibration.depends_on` and `gates[].threshold` (§3.8) — resolves by
   exact string equality to exactly one declaration of the *required kind*, or it is
   an error (`missing_ref`, kind-checked). No relative resolution, no implicit
   prefixing, no fallback search (Property P6 — no silent shadowing). Policy
   `stages` are NOT namespace references (§3.8).
5. **Prefix collisions are diagnosed conservatively** (cross-model review round 1,
   finding 8): declaring both `retriever` and `retriever.k` triggers
   `namespace_prefix_collision` as a **warning** on any module that is valid TVL 1.0
   (validity is never affected — P1 holds for *all* 1.0 modules, not just the
   corpus), and as an **error** only in modules that use TVL 1.1 constructs
   (`cvars`, `policies`, `require_calibration`, `scope`) — new-surface opt-in.
6. **Ownership scope is metadata.** The optional `scope` object
   (`scope: { node?, agent?, workflow? }`, §3.3) on any declaration records
   node/agent/workflow ownership. v1 semantics: informational (§1.5.3 metadata
   layer) with one consistency lint — if both `scope.node` and a dotted name prefix
   are present and disagree, warn (`scope_prefix_mismatch`). Workflow-ownership
   *semantics* are deferred.

### 3.8 Policies and cascade execution

```
PolicyDecl ::= ⟨ name : Ident,
                 kind : "policy",                (* fixed literal; aligns with the
                                                    effectuation knob-kind POLICY *)
                 strategy : Ident,               (* v1 registry: "cascade" *)
                 stages : StageRef*,             (* REQUIRED for cascade, |stages| ≥ 1 *)
                 gates? : GateDecl*,             (* |gates| = |stages| − 1 *)
                 parameters? : Map,              (* opaque; OUTSIDE the P8 guarantee *)
                 scope? : Scope ⟩

StageRef ::= Ident      (* OPAQUE operational stage identifier — like
                           environment.bindings (§1.5.3): resolved by the runtime,
                           NOT a module-namespace reference. Duplicates within one
                           policy are an error (duplicate_stage). *)

GateDecl ::= ⟨ kind : "margin_below",            (* v1 registry *)
               threshold : Ident ⟩               (* namespace ref, MUST resolve to a
                                                    CVAR (kind-checked) *)
```

Policies are **operational** (§1.5.2): they select/parameterize runtime behavior and
never enter Γ, `F^str`, or the dominance relation. `parameters` is an opaque
operational map and is explicitly **outside** the P8 privacy guarantee (it is module
configuration, not a persisted signal); persisted signals and certificates are the
closed shapes of §3.5.

**Stage references are deliberately not namespace references** (cross-model review
round 1, finding 6): a stage names a runtime execution unit (model + prompt +
sampling configuration), which is not a declarable TVL variable. They follow the
existing precedent of `environment.bindings` — implementation-defined deployment
identifiers. The lint surface is accordingly `duplicate_stage` (within a policy) and
the gate-count invariant, not unresolved-name errors.

**Cascade execution semantics** (normative for `strategy: cascade`):

- `stages` is REQUIRED with `|stages| = m ≥ 1`; `gates` MUST satisfy
  `|gates| = m − 1` (so `m = 1` ⟺ `gates` absent/empty — the degenerate cascade
  that always returns its only stage's output).
- Each gate's `threshold` resolves to a CVAR `θ_i` (the declared gate→CVAR binding —
  cross-model review round 1, findings 6/11).
- For input `x`:

```
𝒞(x) = output of stage s_j   where   j = min{ i : i = m ∨ g_i(vote_i(x)) = stop }
```

- Each stage runs `k_i ≥ 1` samples (`k_i` is a per-stage **cardinality** tuned
  variable, not part of the policy), votes over caller-defined equivalence keys, and
  exposes content-free vote statistics. The v1 gate predicate is
  `escalate ⟺ margin < θ_i`.
- **Totality and determinism** (cross-model review round 1, finding 11):
  - *Empty/abstain-only vote* (no valid keys): `margin = 0`, hence the gate
    escalates for any `θ_i > 0`; `θ_i = 0` means "never escalate" by the strict
    inequality.
  - *Ties*: the representative is the first winning key in a deterministic total
    order (lexicographic over serialized keys); `margin` is unaffected by the tie.
  - *Stochastic sampling*: the determinism claim is conditional —
    **given the per-stage sample multisets**, gate decisions and stage selection are
    a deterministic function of (votes, θ). Sampling randomness is operational
    (seeded by the runtime); TVL does not legislate RNGs.
  - *Stage or gate exception*: the item's cascade evaluation FAILS (propagates as an
    evaluation error); it MUST NOT silently degrade to any stage's output. Under
    strict modes the failure feeds the fail-closed law (§3.6).

**Disambiguation** (three things named "policy", kept distinct):

| Construct | What it is |
|---|---|
| `policies` (this RFC) | NEW top-level block of named operational policy declarations |
| `promotion_policy` | Existing promotion gate parameters (§9) — unchanged |
| `spec/policies/*.yml` | Existing repo convention: standalone *promotion-policy files* for `--policy` in the CI gate — unchanged, unrelated |

### 3.9 Surface syntax (draft normative for the validators packet)

```yaml
tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4o-mini", "gpt-4o"]
  - name: retriever.k
    type: int
    domain: { range: [0, 20] }

cvars:
  - name: router.margin_threshold
    type: float
    domain: { range: [0.0, 1.0] }          # validity domain: closed interval,
                                           # no resolution required (§3.3)
    calibration:
      source: margin_eval_pool             # required
      signal: vote_margin_v1
      calibrator: budget_threshold_v1
      depends_on: [model, retriever.k]     # tuned parents (namespace refs)
    governance:
      require_calibration: true
    scope: { node: router }

policies:
  - name: cheap_strong_cascade
    kind: policy
    strategy: cascade
    stages: [cheap, strong]                # opaque runtime stage ids (NOT namespace refs)
    gates:
      - kind: margin_below
        threshold: router.margin_threshold # namespace ref -> CVAR (kind-checked)
```

EBNF additions (following the repo's existing EBNF conventions; optional lists may
be present-and-empty — cross-model review round 1, finding 13):

```ebnf
module     = header, environment, evaluation_set, tvars, [ cvars ], constraints,
             objectives, promotion_policy, [ policies ], [ exploration ] ;

(* scope is expressible with any single field or combination, no leading comma *)
scope_spec  = "scope", ":", "{", [ scope_field, { ",", scope_field } ], "}" ;
scope_field = ( "node" | "agent" | "workflow" ), ":", ident ;

(* AMENDED 1.0 production: tvar_decl gains the optional scope (the one
   existing-production change; additive and optional) *)
tvar_decl   = "{", "name", ":", ident, ",", "type", ":", type,
              ",", "domain", ":", domain_spec, [ ",", scope_spec ], "}" ;

(* AMENDED 1.0 production: promotion_policy gains require_calibration *)
require_calibration_spec = "require_calibration", ":", "{",
              "enabled", ":", boolean,
              [ ",", "hash_covered_context", ":", "[",
                [ ctx_ext_key, { ",", ctx_ext_key } ], "]" ], "}" ;
ctx_ext_key = "stage_versions" | "model_versions"
            | "budget_assumptions" | "cost_assumptions" ;

cvars      = "cvars", ":", "[", [ cvar_decl, { ",", cvar_decl } ], "]" ;
cvar_decl  = "{", "name", ":", ident, ",", "type", ":", type,
             [ ",", "domain", ":", domain_spec ],
             ",", "calibration", ":", calibration_spec,
             [ ",", "governance", ":", governance_spec ],
             [ ",", scope_spec ], "}" ;
calibration_spec = "{", "source", ":", ident, [ ",", "signal", ":", ident ],
             [ ",", "calibrator", ":", ident ],
             [ ",", "depends_on", ":", "[", [ ident, { ",", ident } ], "]" ], "}" ;
governance_spec  = "{", "require_calibration", ":", boolean, "}" ;

policies    = "policies", ":", "[", [ policy_decl, { ",", policy_decl } ], "]" ;
policy_decl = "{", "name", ":", ident, ",", "kind", ":", "policy",
              ",", "strategy", ":", ident,
              ",", "stages", ":", "[", ident, { ",", ident }, "]",
              [ ",", "gates", ":", "[", [ gate_decl, { ",", gate_decl } ], "]" ],
              [ ",", "parameters", ":", object ],
              [ ",", scope_spec ], "}" ;
gate_decl   = "{", "kind", ":", "margin_below", ",", "threshold", ":", ident, "}" ;
```

JSON-schema shape: `cvars`/`policies` added to `properties` (NOT `required`) of the
module schema; `$defs.CVarDecl` / `$defs.PolicyDecl` / `$defs.GateDecl` /
`$defs.Scope` mirroring the above; **`$defs.Scope` is also added as an optional
property of the existing `TVarDecl`** (the one 1.0-shape modification — additive and
optional, so every existing document remains valid — cross-model review round 1,
finding 9); `promotion_policy.require_calibration` per §3.5 (extension-keys enum
only); the shared `Ident` lexical `pattern` of §3.7(2) applied to all `name` fields
of the new $defs.

## 4. Property claims (Phase 2)

Each property is a named obligation stated as a checkable predicate; Phase 3
model-checks it on finite instances (producing counterexample fixtures where the
*negation* is satisfiable in a buggy variant), and Phase 4 carries the executable
form. SDK-level obligations (marked →SDK) are tracked by the SDK features, not by
TVL validators (cross-model review round 1, finding 15).

| ID | Property | Claim (checkable form) | Verification obligation |
|---|---|---|---|
| **P1** | Conservative extension | For every module M valid under TVL 1.0: M is valid under 1.1, and Γ, `F^str` satisfiability, ≻_ε, and acceptability are unchanged. New 1.1 diagnostics on 1.0-valid modules are warnings only (§3.7(5)) | Phase 3: equivalence over the canonical corpus + the prefix-collision warning case; Phase 4: full existing example + conformance suite green unchanged |
| **P2** | Optimizer soundness | The optimizer-visible space is exactly `Σ = ∏_{N_T}`; no CVAR, fixed value, or policy internal appears in any suggestion | Phase 3: projection model; →SDK suggestion-domain tests |
| **P3** | Resolver soundness | `Accept ⟹ ¬(R1 ∨ … ∨ R8) ∧ all calibrators ≠ ⊥` — by the §3.4 definition, with each R_i independently exhibitable (except R1, proven unreachable in v1) | Phase 3: per-R_i reachability fixtures (R1: unreachability proof); →SDK typed-rejection unit tests |
| **P4** | Resolver completeness | `¬(R1 ∨ … ∨ R8) ∧ all calibrators ≠ ⊥ ⟹ Accept` — exact converse of P3 by construction | Phase 3: completeness side of the resolver model (no implicit rejection) |
| **P5** | SAT preservation | For any module M and its cvar/policy-stripped projection M⁻: `compile_constraints(M)` and `compile_constraints(M⁻)` produce identical variable sets (= `N_T`) and identical clause sets; satisfiability coincides | Phase 3: encoding-equality model; Phase 4: lock test asserting solver domain keys = tvar names on modules with cvars |
| **P6** | Namespace uniqueness | Each namespace reference (`depends_on`, `gates[].threshold`) resolves to exactly one declaration of the required kind or errs; duplicate names across tvars ∪ cvars ∪ policies err; prefix collisions diagnosed per §3.7(5) | Phase 3: shadowing/collision/kind-mismatch model; Phase 4: lints `cvar_shadows_tvar`, `policy_name_conflict`, `namespace_prefix_collision`, `missing_ref`, `duplicate_stage` |
| **P7** | Fail-closed strictness | Under `strict(M, c)`: each of {R6, R8, calibrator ⊥, gate exception (§3.6), gate no_decision} ⟹ no promotion ∧ no winner-by-objective fallback | Phase 3: promotion-verdict reachability model (all five verdicts reachable, none promotes); →SDK spy tests on the four leak sites |
| **P8** | Privacy | The certificate and `SignalObservation` shapes (both defined in §3.5) are closed: every field is an identifier, type, hash, finite number, count, split label, or enum — no raw-content-typed field exists to leak. `policies[].parameters` is explicitly outside the guarantee | Phase 4: schema-level closed-shape check over the §3.5 shapes; →SDK canary test in observation emission |

## 5. Documented assumptions

The guarantees above hold under, and only under:

1. **Split independence** — the calibration split and evaluation split are disjoint
   and the resolver enforces R7.
2. **Dataset hash stability** — `H_c(dataset)` identifies the evidence pool; a
   mutated pool ⇒ new hash ⇒ stale certificates (never silent reuse).
3. **Canonical signal-spec hash** — `H_c(σ)` covers the signal id, version, score
   function + version, comparator + version.
4. **Version and parameter coverage** — calibrator id/version/hyperparameters and
   the context schema version are in `ctx_core`; stage/model versions are extension
   keys. An input outside `ctx_core ∪ ctx_ext` is by definition outside the
   freshness guarantee.
5. **Registry snapshot-resolution** — registry-backed domains are resolved to
   explicit values *before* certificate hashing (consistent with §1.4 of the formal
   semantics).
6. **Deterministic canonicalization** — RFC 8785 + the §3.5 restrictions, identical
   across implementations (known-answer conformance fixtures).
7. **Exchangeability for statistical targets** — where a `TargetProperty` carries a
   statistical guarantee, calibration and deployment data are exchangeable;
   distribution shift voids the guarantee and is surfaced only through context keys
   (dataset hash, splits) — runtime drift detection is deferred.

## 6. Field categorization update (extends §1.5 of the formal semantics)

New category **§1.5.5 Governed-but-not-searched fields**:

| Field | Layer | Role |
|---|---|---|
| `cvars[].name/type/domain` | Governed (NEW) | Declared, typed, validated — absent from Γ, `Config(Δ, E_τ)`, and `F^str` |
| `cvars[].calibration.*` | Operational | Calibrator/evidence identification; freshness inputs |
| `cvars[].governance.require_calibration` | Acceptability (Layer 2) | Per-CVAR strict-mode opt-in (in `strict(M, c)`) |
| `policies[].*` | Operational | Like `exploration.*` — affects how, not what |
| `promotion_policy.require_calibration` | Acceptability (Layer 2) | Same layer as `chance_constraints` |
| `scope` (any decl) | Metadata | Ownership annotation |

Theorem 8.1 (SAT soundness) and the §9 promotion theorems are **unaffected** by
construction (P1/P5): the new fields never enter the encodings those theorems
govern. `Promote` gains the `CalibrationPass` conjunct only under `strict(M, c)`
(§3.6), at the acceptability layer where `ChancePass` already sits.

## 7. Compatibility argument (P1 sketch)

1. Both new blocks are *optional* additions to `properties` of an
   `additionalProperties: false` schema — absent blocks ⇒ identical schema
   acceptance. The only 1.0-shape change is the optional `scope` property on
   `TVarDecl` — additive, so all existing documents remain valid.
2. Configuration documents (`tvl-configuration.schema.json`) are **untouched**;
   their `assignments` remain candidate TVAR assignments (N_F is a resolution-time
   concept, §3.1 — cross-model review round 1, finding 7).
3. The lint pipeline appends new checks; no existing diagnostic changes meaning. All
   new diagnostics on 1.0-valid modules are warnings (§3.7(5)).
4. The SAT encoder reads only `tvars` (verified: `python/tvl/constraints.py`
   `compile_constraints` → `extract_domains(module.get("tvars", …))`); `cvars` never
   reach it (P5 is the executable lock).
5. The promotion gate adds a conjunct only when a 1.1 construct is declared. (Note:
   `chance_constraints` already make modules strict in the SDK's runtime — the
   *language* semantics of chance-constraint acceptability are unchanged here; the
   SDK-side fail-closed repair of its fallback bugs is tracked separately by
   FR-SDK-FAIL-CLOSED-PROMOTION-V1.)

The executable form of this argument is the Phase 4 requirement that the entire
existing example/conformance corpus passes unchanged.

## 8. Prior art (informative)

- **Bilevel HPO** — Franceschi et al., ICML 2018 (outer/inner variables; response
  function). CVARs = inner variables; the resolver memoizes the response function
  keyed by the freshness hash.
- **Calibration-split discipline** — Cawley & Talbot, JMLR 2010; scikit-learn
  `TunedThresholdClassifierCV` ("never tune the threshold on training data") — the
  basis of R7.
- **Certified calibration** — Learn-then-Test (Angelopoulos et al.; empty accepted
  set = abstention ⇒ fail-closed `NO_DECISION` is literature-sanctioned), RCPS
  (UCB scan over a monotone 1-D threshold family), Pareto Testing (fixed-sequence
  multiplicity control), Trust-or-Escalate (ICLR 2025: LTT-certified LLM cascade
  thresholds — direct prior art for certified gates). The `n ≥ ⌈1/ε⌉ − 1` floor
  (R8) is the split-conformal minimum-calibration-size bound.
- **Canonical hashing** — RFC 8785 (JSON Canonicalization Scheme).
- Uncertified practice (RouteLLM `calibrate_threshold`, FrugalGPT, AutoMix) fits
  the same thresholds with no validity object — the gap this RFC closes.

## 9. Acceptance criteria for this RFC

1. Cross-model review recorded on `FR-TVL-CVARS-POLICIES-V1` with verdict
   ACCEPT/ACCEPT-WITH-FIXES (round 1: REJECT — see §10; round 2 pending).
2. Owner acceptance recorded in the spine (human-only gate).
3. Phase 3 model-check cases enumerate at least: binding-partition collision,
   namespace shadowing + prefix collision (incl. the legacy-warning case),
   dependency-graph R1 unreachability (v1), R2–R8 reachability, certificate
   subject/value binding, stale-certificate on parent change, SAT
   encoding-equality, strict-mode verdict reachability (all five P7 verdicts),
   cascade totality (m=1, empty vote, tie) — each with a committed fixture.
4. Only after 1–3 and green Phase 4 validators may any SDK implementation begin.

## 10. Review log

| Round | Reviewer | Verdict | Disposition |
|---|---|---|---|
| 1 | codex (gpt-5.5, xhigh, read-only) — 2026-06-04 | **REJECT** — 12 blocking, 3 non-blocking | All 15 addressed in Draft v2 (below) |
| 2 | codex (gpt-5.5, xhigh, read-only) — 2026-06-04 | **REJECT** — 11/15 resolved, 4 partial; 2 new blocking, 1 non-blocking | Addressed in Draft v3: (a) `valid(…)` now checks the full subject (incl. `type = τ(n)`) AND the audit copies `target`/`evidence{n, pool_hash}` against the live context — a certificate cannot display one context while hashing another; (b) `scope_spec` rewritten with a proper field alternation (agent-only/workflow-only expressible) and `tvar_decl` explicitly amended to carry it; (c) `require_calibration_spec` EBNF production added (the promotion_policy extension is no longer prose-only); (d) `SignalObservation` closed shape defined in §3.5 and referenced by P8. The round-2 verification also confirmed: gates[].threshold consistent with §3.7(4); m=1/no-gates consistent; the §3.9 YAML example validates against the draft shapes. |
| 3 | codex (gpt-5.5, xhigh, read-only) — 2026-06-04 | **REJECT** — 7/8 v3 deltas confirmed resolved; ONE remaining blocker | Addressed in Draft v4: `valid(…)` gains the first conjunct `ctx_now.cvar_name = n`, closing the forged-subject hole (a certificate issued against CVAR B's hashed context can no longer validate CVAR A via a forged `subject.cvar`). Model + test added in the model-checking packet. |
| 4 | codex (gpt-5.5, xhigh, read-only) — 2026-06-05 | **ACCEPT** | Final confirmation: `valid()`'s `ctx_now.cvar_name = n` conjunct verified correct and coherent with issuance/ctx_core/parent-specificity; §10 log accurate. No remaining findings. |

Round-1 finding dispositions:

1. P4 not the converse of R1–R8 → §3.4 now defines `Accept ⟺ ¬(R1∨…∨R8) ∧
   calibrators ≠ ⊥`; P3/P4 are the two directions of one biconditional; R1 marked
   unreachable-in-v1 with an unreachability proof obligation.
2. Certificate didn't bind the value → mandatory `subject{cvar, type, value_hash}`;
   validity checks the subject (§3.5).
3. Freshness subset undercut parent-specificity → mandatory `ctx_core` (incl.
   `tuned_parent_values`, source id, calibrator id/version/params hash, evidence
   n + pool hash, context schema version); `hash_covered_context` selects
   extensions only (§3.5).
4. Canonicalization underspecified → RFC 8785 + finite-number/NFC/duplicate-key
   rules + versioned context schema (§3.5).
5. Per-CVAR governance missing from strict(M) → `strict(M, c)` includes consumed
   CVARs with `governance.require_calibration` (§3.6).
6. Policy stages untyped / RFC's own YAML invalid → stages redefined as opaque
   operational ids (`environment.bindings` precedent); gate→CVAR binding made
   declarative via `gates[].threshold` namespace refs (§3.8).
7. Fixed partition vs configuration schema → N_F is runtime-supplied only;
   configuration documents untouched; collision checked at resolution as R3 (§3.1).
8. P1 overclaim via prefix-collision error → warning on ALL 1.0-valid modules;
   error only with 1.1 constructs (§3.7(5)).
9. `scope` absent from syntax → `scope_spec` EBNF + `$defs.Scope` + optional on
   `TVarDecl` (§3.9).
10. CVAR float domain vs resolution rule → validity domains are closed intervals,
    no resolution required; explicit deviation note (§3.3).
11. Cascade not total → `stages` required (m ≥ 1), m=1 defined, gate→θ binding
    declared, empty-vote/tie/exception semantics specified (§3.8).
12. (NB) Lexical inconsistency → single normative `Ident` grammar (§3.7(2)),
    Phase 4 alignment obligation.
13. (NB) EBNF/abstract-syntax mismatch → empty-list forms made explicit; literal
    style aligned (§3.9).
14. P8 uncheckable → certificate `payload` removed (closed shapes only);
    `parameters` explicitly outside the guarantee (§3.5, §3.8, P8).
15. (NB) Properties not finite predicates → P-table restated as checkable
    predicates; →SDK obligations marked; "gate exception" defined (§3.6, §4).
