# RFC 0001 — Knob Bindings: Calibrated Variables (`cvars`) and `policies`

| | |
|---|---|
| **Status** | Draft — awaiting cross-model review and owner acceptance |
| **Target language version** | TVL 1.1 (conservative extension of 1.0) |
| **Tracking** | `FR-TVL-CVARS-POLICIES-V1` · ChangeSession `cs_607ce2f4f8833804` |
| **Phases covered** | Phase 0 (scope freeze) · Phase 1 (formal semantics) · Phase 2 (property claims) |
| **Downstream gate** | Acceptance of this RFC + green Phase 3/4 validators unblock all SDK implementation |

## 1. Motivation

TVL 1.0 models exactly one binding for a declared variable: **tuned** — every `tvars`
entry is optimizer-visible and searched. Real governed tuning needs two more bindings
that today live outside the language, untyped and ungoverned:

1. **Fixed values** — supplied constants that are part of the resolved configuration
   but never searched. Today these ride along in implementation-defined config dicts.
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
| Fixed value | Constant supplied at resolution; never searched |
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
- CVAR substitution-as-constant into structural constraints (the only planned
  extension of constraint scope, deferred);
- relative/implicitly-prefixed name resolution (v1 resolution is exact-match only);
- FE/BE product views of cvars/policies/certificates.

## 3. Formal model (Phase 1)

Notation follows `formalization/tvl-formal-semantics.md` (§2.1): Γ is the typing
context, `E_τ` the environment snapshot, `Config(Δ, E_τ)` the configuration space,
`F^str` structural feasibility, layers per §1.5.4.

### 3.1 Binding partition

Let `N` be the set of declared variable names in a module. TVL 1.1 partitions `N`:

```
N = N_T ⊎ N_F ⊎ N_C          (Tuned ⊎ Fixed ⊎ Calibrated; pairwise disjoint)
```

- `N_T` = names declared in `tvars` (unchanged from TVL 1.0).
- `N_C` = names declared in `cvars`.
- `N_F` = names bound to constants at resolution time. TVL 1.1 does **not** add a
  `fixed:` block: fixed values remain resolution inputs (configuration documents,
  `spec/configurations/*.config.yml`), but the partition makes their role explicit —
  a fixed name MUST NOT collide with `N_T ∪ N_C`.

Membership is syntactic and statically checkable. A name appearing in more than one
partition is an error (`binding_partition_collision`).

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
only** — `cvars` do not enter Γ, `Config(Δ, E_τ)`, or `F^str` (Property P5; see
§3.8 for the lint that makes violations precise).

### 3.3 CVAR declarations

Abstract syntax (extends §2 of the formal semantics):

```
CVarDecl ::= ⟨ name : Ident,
               type : Type,                      (* same Type grammar as TVarDecl *)
               domain? : DomainSpec,             (* OPTIONAL validity domain *)
               calibration : CalibrationSpec,
               governance? : ⟨ require_calibration : Bool ⟩ ⟩

CalibrationSpec ::= ⟨ source : Ident,            (* evidence source id, REQUIRED *)
                      signal? : Ident,           (* signal spec id *)
                      calibrator? : Ident,       (* calibrator id *)
                      depends_on? : Ident* ⟩     (* tuned parents π ⊆ N_T *)
```

Semantics of the optional `domain`: it is a **validity domain** — a set membership
check applied to the *calibrated output* at resolution time — not a search domain.
It never feeds the SAT encoding or the optimizer.

`depends_on` declares the parent set `π(n) ⊆ N_T`. Each entry MUST resolve (exact
match, §3.7) to a declared TVAR. `depends_on` entries naming a CVAR are an error in
v1 (CVAR→CVAR dependencies are deferred with in-loop fitting; the resolver model
below still specifies DAG semantics so the extension is non-breaking).

**Dependencies are a freshness/validity relation, not search-space constraints**:
`depends_on` never generates SAT clauses and never restricts `Σ`. Its only semantic
effect is through the freshness context (§3.5).

### 3.4 CVAR resolution

A CVAR `n` denotes a **calibrator** (the inner/response function):

```
𝒦_n : (assignments to π(n)) × 𝓔_cal  →  Val_{τ(n)} ∪ {⊥}
```

where `𝓔_cal` is evidence drawn from the **calibration split** and `⊥` means
*no decision* (insufficient or invalid evidence). TVL specifies the *contract* of
`𝒦_n` (inputs, freshness, abstention); the calibrator implementation is operational
(§1.5.2 layer), identified by `calibration.calibrator`/`source` ids.

Given an optimizer suggestion `t ∈ Σ` and fixed assignment `f` over `N_F`, the
**resolved configuration** is:

```
c  =  t  ∪  f  ∪  { n ↦ v_n : n ∈ N_C }
```

computed in **deterministic topological order** over the dependency DAG, where each
`v_n` is the certificate-backed calibrated value for context (§3.5). Resolution is
**undefined** (MUST be rejected, with the stated reason) when any of the following
holds:

| # | Rejection | Meaning |
|---|---|---|
| R1 | `cycle` | the dependency graph is not a DAG |
| R2 | `missing_ref` | a `depends_on` or policy `stages` entry resolves to no declaration |
| R3 | `duplicate_provider` | two declarations provide the same output name (binding-partition collision) |
| R4 | `phase_mismatch` | a value is consumed before the phase that produces it |
| R5 | `infeasible_value` | a fixed/calibrated value violates its declared (validity) domain |
| R6 | `stale_certificate` | certificate freshness check fails (§3.5) |
| R7 | `evidence_leakage` | calibration evidence intersects the evaluation split (`𝓔_cal ∩ 𝓔_eval ≠ ∅`) |
| R8 | `insufficient_evidence` | evidence below the declared floor (e.g. `n < ⌈1/ε⌉ − 1` for a chance-style target at level ε) |

Resolution is **complete** in the converse direction: if all refs resolve, the graph
is acyclic, values are in domain, and required certificates are fresh, the resolver
MUST produce a resolved configuration (Property P4 — no spurious rejection).

### 3.5 Certificates and freshness

A **certificate** binds a calibrated value to the exact context it was fit under:

```
Certificate ::= ⟨ target : TargetProperty,
                  issued_hash : Hash,            (* H(ctx) at issue time *)
                  decision : CERTIFIED | NO_DECISION | BEST_EFFORT_UNCERTIFIED,
                  payload? : Map ⟩
```

The decision vocabulary is shared with the per-config guarantee certificates already
in TraigentSchema (`guarantee_certificate_schema.json`): **one certificate ontology,
two scopes** — per-config selection there, per-CVAR value here.

The **freshness context** `ctx` is the tuple of hash-covered inputs:

```
ctx = ( t|π            — tuned parent values,
        H(σ)           — signal spec hash (incl. score-function + comparator versions),
        stage_versions, model_versions,
        H(dataset), calibration_split, eval_split,
        target,        — the TargetProperty
        budget_assumptions, cost_assumptions,
        calibrator_version )
```

**Validity**: a certificate is valid for the current context iff

```
valid(cert, ctx_now) ⟺ cert.issued_hash = H(ctx_now) ∧ cert.decision = CERTIFIED
```

Because `t|π` is hashed, **certificates are parent-specific**: when the optimizer
suggests a new value for any parent in `π(n)`, the certificate for the old context is
stale by construction — detected by hash mismatch, never by convention.

**Stale-certificate behavior**: a stale or absent certificate makes resolution
rejection R6 fire. Under a strict evidence mode (§3.6) this MUST NOT degrade to any
default, cached, or "best-effort" value. Outside strict modes, a declared
`fallback` Fixed value MAY be used; using it is observable (it must be recorded in
the resolution output), never silent.

**Hash canonicalization** MUST be deterministic: canonical JSON (sorted keys, UTF-8,
no insignificant whitespace) → SHA-256. Two implementations hashing the same context
MUST produce the same hash (this is an executable conformance obligation).

`promotion_policy.require_calibration` declares which context keys are covered:

```yaml
promotion_policy:
  require_calibration:
    enabled: true
    hash_covered_context:        # enum-validated; subset of the keys above
      [tuned_parent_values, signal_spec_hash, stage_versions, model_versions,
       comparator_version, score_function_version, dataset_hash,
       calibration_split, eval_split, target, budget_assumptions,
       cost_assumptions, calibrator_version]
```

An empty `hash_covered_context` is an error (`empty_calibration_context`); a key
outside the enum is an error (`invalid_calibration_context`).

### 3.6 Strict promotion fail-closed semantics

A module is in a **strict evidence mode** iff any of the following is declared:

```
strict(M) ⟺ require_calibration.enabled
           ∨ promotion_policy.chance_constraints ≠ ∅
           ∨ guaranteed-selection target          (operational profile)
           ∨ certificate-backed TargetProperty on any CVAR
```

Under `strict(M)`, the promotion judgment of §9 (formal semantics) is extended:

```
Promote(c_cand, c_inc, M) ⟹ CalibrationPass(c_cand, M)
```

where `CalibrationPass` requires every governed CVAR consumed by `c_cand` to carry a
valid certificate for the current context. The fail-closed law (Property P7):

> Under `strict(M)`, the verdicts *insufficient evidence*, *gate exception*,
> *stale certificate*, and *no_decision* each yield **no promotion** and **no
> winner-by-objective fallback**. The promotion outcome is the explicit
> no-certified-selection result, never the highest-scoring trial.

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
   no intrinsic semantics. (This is the status quo, now normative — P1-preserving.)
2. **One shared namespace.** `tvars`, `cvars`, and `policies` names live in a single
   namespace. Exact-string duplicates anywhere in it are errors
   (`duplicate_tvar` / `duplicate_cvar` / `cvar_shadows_tvar` /
   `duplicate_policy` / `policy_name_conflict`).
3. **Resolution is exact-match only.** Every reference (`depends_on`, policy
   `stages`) resolves by exact string equality against the shared namespace, to
   exactly one declaration, or it is an error (`missing_ref`). No relative
   resolution, no implicit prefixing, no fallback search (Property P6 — no silent
   shadowing).
4. **Prefix collisions are diagnosed.** Declaring both `retriever` and `retriever.k`
   makes attribute-style access ambiguous in downstream consumers. v1 adds the lint
   `namespace_prefix_collision` (a declared name that is a strict dotted prefix of
   another declared name). Severity: error for new modules — demoted to warning if
   the Phase 4 conformance sweep finds any existing canonical example relying on it
   (conservative-extension escape hatch; the sweep result is recorded in the
   validators packet).
5. **Ownership scope is metadata.** An optional `scope` object
   (`scope: { node?: Ident, agent?: Ident, workflow?: Ident }`) on any declaration
   records node/agent/workflow ownership. v1 semantics: informational (§1.5.3
   metadata layer) with one consistency lint — if both `scope.node` and a dotted
   name prefix are present and disagree, warn (`scope_prefix_mismatch`). Workflow
   ownership *semantics* (visibility, cross-node refs) are deferred.

### 3.8 Policies and cascade execution

```
PolicyDecl ::= ⟨ name : Ident,
                 kind : "policy",               (* fixed literal; aligns with the
                                                   effectuation knob-kind POLICY *)
                 strategy : Ident,              (* v1 registry: "cascade" *)
                 stages? : Ident*,              (* refs into the shared namespace *)
                 parameters? : Map ⟩            (* opaque in v1 *)
```

Policies are **operational** (§1.5.2): they select/parameterize runtime behavior and
never enter Γ, `F^str`, or the dominance relation.

**Cascade execution semantics** (normative for `strategy: cascade`): a cascade of
arity `m` is `(S, G)` with stages `S = ⟨s_1 … s_m⟩` and gates `G = ⟨g_1 … g_{m−1}⟩`
(invariant `|G| = |S| − 1`). For input `x`:

```
𝒞(x) = output of stage s_j   where   j = min{ i : i = m ∨ g_i(vote_i(x)) = stop }
```

Each stage runs `k_i ≥ 1` samples (`k_i` is a per-stage **cardinality** tuned
variable, not part of the policy), votes over caller-defined equivalence keys, and
exposes content-free vote statistics; the v1 gate predicate is
`escalate ⟺ margin < θ_i` where each `θ_i` is a **CVAR**. Gate evaluation is
deterministic: identical inputs and identical calibrated `θ` produce the identical
stage index. The binary router (`m = 2`) is the compatibility instance; arity
generalizes by `|S|`, never by a separate router family.

**Disambiguation** (three things named "policy", kept distinct):

| Construct | What it is |
|---|---|
| `policies` (this RFC) | NEW top-level block of named operational policy declarations |
| `promotion_policy` | Existing promotion gate parameters (§9) — unchanged |
| `spec/policies/*.yml` | Existing repo convention: standalone *promotion-policy files* for `--policy` in the CI gate — unchanged, unrelated to the new block |

### 3.9 Surface syntax (draft normative for the validators packet)

```yaml
cvars:
  - name: router.margin_threshold
    type: float
    domain: { range: [0.0, 1.0] }          # validity domain (optional)
    calibration:
      source: margin_eval_pool             # required
      signal: vote_margin_v1
      calibrator: budget_threshold_v1
      depends_on: [model, retriever.k]     # tuned parents
    governance:
      require_calibration: true

policies:
  - name: cheap_strong_cascade
    kind: policy
    strategy: cascade
    stages: [cheap_stage, strong_stage]
    parameters: {}
```

EBNF additions (module rule gains two optional blocks; declarations mirror
`tvar_decl`'s list-with-name shape so existing duplicate/diagnostic machinery
applies):

```ebnf
module     = header, environment, evaluation_set, tvars, [ cvars ], constraints,
             objectives, promotion_policy, [ policies ], [ exploration ] ;

cvars      = "cvars", ":", "[", cvar_decl, { ",", cvar_decl }, "]" ;
cvar_decl  = "{", "name", ":", ident, ",", "type", ":", type,
             [ ",", "domain", ":", domain_spec ],
             ",", "calibration", ":", calibration_spec,
             [ ",", "governance", ":", governance_spec ], "}" ;
calibration_spec = "{", "source", ":", ident, [ ",", "signal", ":", ident ],
             [ ",", "calibrator", ":", ident ],
             [ ",", "depends_on", ":", "[", ident, { ",", ident }, "]" ], "}" ;
governance_spec  = "{", "require_calibration", ":", boolean, "}" ;

policies    = "policies", ":", "[", policy_decl, { ",", policy_decl }, "]" ;
policy_decl = "{", "name", ":", ident, ",", "kind", ":", '"policy"',
              ",", "strategy", ":", ident,
              [ ",", "stages", ":", "[", ident, { ",", ident }, "]" ],
              [ ",", "parameters", ":", object ], "}" ;
```

JSON-schema shape: `cvars`/`policies` added to `properties` (NOT `required`) of the
module schema (which is `additionalProperties: false`), with `$defs.CVarDecl` /
`$defs.PolicyDecl` mirroring the above, and
`promotion_policy.require_calibration` as in §3.5.

## 4. Property claims (Phase 2)

Each property is a named obligation; Phase 3 model-checks it on finite instances
(producing counterexample fixtures where the *negation* is satisfiable in a buggy
variant), and Phase 4 carries the executable form.

| ID | Property | Claim | Verification obligation |
|---|---|---|---|
| **P1** | Conservative extension | Every valid TVL 1.0 module remains valid under 1.1 with identical semantics (Γ, `F^str`, ≻_ε, acceptability all unchanged when `cvars`/`policies`/`require_calibration` are absent) | Phase 3: equivalence over the canonical example corpus; Phase 4: full existing example suite green unchanged |
| **P2** | Optimizer soundness | The optimizer-visible space is exactly `Σ = ∏_{N_T}`; no CVAR, fixed value, or policy internal is ever suggested | Phase 3: projection model; Phase 6: SDK suggestion-domain tests |
| **P3** | Resolver soundness | If resolution accepts, then: all refs resolve, the dependency graph is acyclic, all values are in their (validity) domains, all required certificates are fresh, and `𝓔_cal ∩ 𝓔_eval = ∅` | Phase 3: R1–R8 reachability model; Phase 6: typed-rejection unit tests |
| **P4** | Resolver completeness | If refs resolve ∧ acyclic ∧ in-domain ∧ required certs fresh ∧ evidence floor met, resolution produces a resolved configuration (no spurious rejection) | Phase 3: completeness side of the resolver model |
| **P5** | SAT preservation | Adding `cvars`/`policies` to a module changes neither the structural constraint encoding nor its satisfiability: solver variables = `N_T` exactly | Phase 3: model with/without cvars compares encodings; Phase 4: lock test asserting solver domain keys = tvar names |
| **P6** | Namespace uniqueness | Every reference resolves to exactly one declaration in the shared namespace or fails; no silent shadowing; prefix collisions are diagnosed | Phase 3: shadowing/collision model; Phase 4: lints `cvar_shadows_tvar`, `policy_name_conflict`, `namespace_prefix_collision`, `missing_ref` |
| **P7** | Fail-closed strictness | Under `strict(M)`: missing/stale certificate, no_decision, gate exception, and insufficient evidence each produce no promotion and no winner-by-objective fallback | Phase 3: promotion-verdict reachability model; Phase 6: spy tests on the four SDK leak sites |
| **P8** | Privacy | Persisted calibration signals are content-free (ids, counts, margins, hashes); certificate validity checking requires no raw model outputs | Phase 4: schema-level check (certificate/signal fields carry no content-typed fields); Phase 6: canary test in observation emission |

## 5. Documented assumptions

The guarantees above hold under, and only under:

1. **Split independence** — the calibration split and evaluation split are disjoint
   and the resolver enforces R7 (no eval evidence flows into calibration before
   scoring).
2. **Dataset hash stability** — `H(dataset)` identifies the evidence pool;
   a mutated pool ⇒ new hash ⇒ stale certificates (never silent reuse).
3. **Canonical signal-spec hash** — `H(σ)` covers the signal id, version, score
   function + version, comparator + version.
4. **Version coverage** — stage, model, and calibrator versions are included in
   `ctx`; an uncovered version change is *by definition* outside the freshness
   guarantee (hence the enum guard on `hash_covered_context`).
5. **Registry snapshot-resolution** — registry-backed domains are resolved to
   explicit values *before* certificate hashing (consistent with the formal
   semantics' exclusion of live registry interaction, §1.4).
6. **Deterministic hash canonicalization** — canonical JSON + SHA-256, identical
   across implementations.
7. **Exchangeability for statistical targets** — where a `TargetProperty` carries a
   statistical guarantee (chance-style), calibration and deployment data are
   exchangeable; distribution shift voids the guarantee and is surfaced only through
   context keys (dataset hash, splits) — runtime drift detection is deferred.

## 6. Field categorization update (extends §1.5 of the formal semantics)

New category **§1.5.5 Governed-but-not-searched fields**:

| Field | Layer | Role |
|---|---|---|
| `cvars[].name/type/domain` | Governed (NEW) | Declared, typed, validated — absent from Γ, `Config(Δ, E_τ)`, and `F^str` |
| `cvars[].calibration.*` | Operational | Calibrator/evidence identification; freshness inputs |
| `cvars[].governance.require_calibration` | Acceptability (Layer 2) | Per-CVAR strict-mode opt-in |
| `policies[].*` | Operational | Like `exploration.*` — affects how, not what |
| `promotion_policy.require_calibration` | Acceptability (Layer 2) | Same layer as `chance_constraints` |
| `scope` (any decl) | Metadata | Ownership annotation |

Theorem 8.1 (SAT soundness) and the §9 promotion theorems are **unaffected** by
construction (P1/P5): the new fields never enter the encodings those theorems govern.
`Promote` gains the `CalibrationPass` conjunct only under `strict(M)` (§3.6), at the
acceptability layer where `ChancePass` already sits.

## 7. Compatibility argument (P1 sketch)

1. Both new blocks are *optional* additions to `properties` of an
   `additionalProperties: false` schema — absent blocks ⇒ identical schema
   acceptance.
2. The lint pipeline appends new checks; no existing diagnostic changes meaning.
3. The SAT encoder reads only `tvars` (verified: `python/tvl/constraints.py`
   `compile_constraints` → `extract_domains(module.get("tvars", …))`); `cvars` never
   reach it.
4. The promotion gate adds a conjunct only when a 1.1 construct
   (`require_calibration`) is declared. (Note: `chance_constraints` already make
   modules strict in the SDK's runtime — the *language* semantics of
   chance-constraint acceptability are unchanged here; the SDK-side fail-closed
   repair of its fallback bugs is tracked separately by
   FR-SDK-FAIL-CLOSED-PROMOTION-V1.)
5. Namespace rule §3.7(1) codifies current implementation behavior; rule §3.7(4)
   carries the conservative-extension escape hatch.

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
- Uncertified practice (RouteLLM `calibrate_threshold`, FrugalGPT, AutoMix) fits
  the same thresholds with no validity object — the gap this RFC closes.

## 9. Acceptance criteria for this RFC

1. Cross-model review (independent assistant) recorded on
   `FR-TVL-CVARS-POLICIES-V1`.
2. Owner acceptance recorded in the spine (human-only gate).
3. Phase 3 model-check cases enumerate at least: binding-partition collision,
   namespace shadowing + prefix collision, dependency cycle, stale-certificate on
   parent change, SAT exclusion, strict-mode no-decision reachability, cascade
   arity/gate determinism, legacy-corpus equivalence — each with a committed
   fixture.
4. Only after 1–3 and green Phase 4 validators may any SDK implementation begin.
