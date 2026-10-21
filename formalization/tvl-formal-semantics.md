# TVL Formal Semantics

**Version 1.0 — Formal Foundations**

**Authors**: Traigent Research
**Date**: January 2026
**Status**: Draft semantic reference. Sections 2–6 and 9 define the intended core semantics; Sections 7–8 are informative formal foundations and a reference encoding; Section 10 states conformance requirements.

---

## Abstract

This document defines the mathematical meaning of the Tuned Variables Language (TVL), a requirements specification language for AI agents. A TVL module describes an admissible agent design space, the desired properties of candidates in that space, and the evidence conditions for acceptance or promotion. We define the abstract syntax, semantic domains, type system, denotational semantics, feasibility predicates, and promotion relation. The document also gives an informative SMT encoding and explicitly bounds the claims supported by the current formalization.

---

## 1. Introduction

### 1.1 Specification Languages vs. Programming Languages

TVL is a **domain-specific requirements language** for AI agents. Unlike a programming language or build recipe, it does not describe the steps for constructing one agent. It defines a set of allowed agent configurations and the properties and evidence that make a candidate acceptable.

| Property | Programming Language | Specification Language (TVL) |
|----------|---------------------|------------------------------|
| Primary purpose | Describe computation | Describe admissible agents and required properties |
| Execution model | Operational | Declarative (validated/checked) |
| Expressiveness | Typically Turing-complete | Intentionally restricted |
| Key property | Termination | Decidability |

### 1.2 Formal Requirements

For TVL to serve as a trustworthy specification language, we must establish:

1. **Well-defined syntax**: Unambiguous grammar with formal AST
2. **Well-defined semantics**: Mathematical meaning for every construct
3. **Type soundness**: Well-typed modules don't produce runtime type errors
4. **Decidability**: All validation questions are decidable
5. **Soundness within scope**: If a conforming check accepts an input, the corresponding formal judgment holds under its stated preconditions
6. **Completeness within scope**: If a judgment holds in the defined subset, a conforming decision procedure can establish it

### 1.3 Document Structure

- **§2**: Abstract Syntax — formal AST definitions
- **§3**: Semantic Domains — mathematical structures for meanings
- **§4**: Type System — typing rules and judgments
- **§5**: Denotational Semantics — meaning functions
- **§6**: Feasibility Predicates — structural and operational constraints
- **§7**: Informative Metatheory — soundness, completeness, and decidability results under stated assumptions
- **§8**: Informative SMT Encoding — one reference compilation to solver format
- **§9**: Promotion Semantics — acceptability, dominance, and promotion correctness
- **§10**: Conformance Requirements — behavior required of implementations
- **§11**: Future Work — proposed extensions, not current requirements
- **§12**: Runtime Semantics (TVL 1.3) — requirements, monitors, obligations, and governed responses

Sections 2–6 and 9 specify **what** core TVL constructs mean; §12 specifies the optional TVL 1.3 runtime extension. Section 7 explains properties of that core and Section 8 describes one way a validator may implement structural checks; neither requires an implementation to expose its algorithms. Search algorithms, optimizer architecture, optimizer sample allocation, and candidate scheduling are outside this formal language contract. Monitor sampling and decision schedules are part of the §12 evidence contract.

### 1.4 Scope of Formal Guarantees

The formal semantics and soundness proofs in this document apply to the **core TVL subset**. The following constructs are **outside the formally verified subset**:

| Construct | Reason | Status |
|-----------|--------|--------|
| Registry domains (`domain: { registry: ... }`) | External state interaction | Future work |
| Filter expressions in registry refs | Filter language not formalized | Future work |
| Callable types (`type: callable[Protocol]`) | Protocol typing not defined | Future work |
| `cvars`/`policies` (RFC 0001, landed 2026-06-05) | Post-dates the Lean proof tree; no formalization exists | Not yet formalized |
| `composites` (RFC 0002, landed 2026-06-06) | Post-dates the Lean proof tree; no formalization exists | Not yet formalized |

**Implications**:

1. **Modules using excluded constructs**: The soundness theorems (Theorem 8.1, etc.) do not apply. Validation may pass, but formal correctness guarantees are not provided.

2. **Warnings**: Conformant validators SHOULD emit warnings when excluded constructs are used:
   - `W6001: unverifiable_registry_domain` — "Module uses registry domain; formal soundness guarantees do not apply"
   - `W6002: unverifiable_callable_type` — "Module uses callable type; type safety is not formally verified"
   - cvars/policies/composites (RFC 0001/0002) have **no lint warning implemented yet** (tracked as
     follow-up work): `lint_module`'s existing conservative-extension guarantee
     (`tests/model_checking/test_legacy_corpus.py`) locks identical diagnostics whether or not a
     legacy module has `cvars`/`policies` injected, so adding a warning here needs that guarantee
     re-scoped first — see the coverage note below instead for the disclosure in the meantime.

3. **Workaround**: For formal guarantees, resolve registry domains to explicit enum domains before validation, replace callable types with enum types listing known implementations, and restrict the module to the pre-RFC-0001/0002 subset (no `cvars`, `policies`, or `composites` blocks).

**Rationale**: Registry domains require interaction with external state (registries), which introduces semantic complexity beyond the scope of this static specification. Callable types require a protocol typing system that would significantly expand the formalization. These features are valuable for practical use but are excluded from the formally verified core to keep the proofs tractable.

**cvars/policies/composites are a different case from the three constructs above**: they are not deliberately scoped out of a tractable core — the Lean proof tree (`proofs/`) simply predates RFC 0001 and RFC 0002 and has never been extended to cover them. `proofs/TVL/Types.lean`'s `Atom`/`Formula` inductives model only `eq/neq/geq/leq/mem` atoms and `and/or/not/impl` connectives; nothing in `proofs/TVL/*.lean` mentions `composite`, `cvar`, or `policy`. Closing this gap is future work, not a permanent exclusion; see `proofs/PROOF_SUMMARY.md`'s coverage note.

**Runtime extension scope (TVL 1.3, accepted 2026-10-21)**. Section 12 defines a separate runtime typing context, the meaning of runtime declarations on complete unit histories, the contract every verdict, episode, obligation state and response effect must satisfy, and conditional theorem statements about the language and about exact binomial tests. These are claimed obligations for mechanization, not a report of completed Lean proofs or deployed enforcement. Verdicts are produced by evaluator profiles outside TVL; their decision procedures, and the proofs that they meet the contract, are not part of this document. Statistical claims apply only to `clopper_pearson_rational_v2` under the stated sampling and latent-count model. The hosted platform's floating-point `clopper_pearson_exact_v1` is a distinct computation, with no theorem. Checker claims are relative to the declared checker's labels; agent-scoped evidence does not establish per-configuration behavior without verified configuration attribution. No episode false-closure bound, sampled prevention guarantee, repair efficacy, or universal agent guarantee follows.

### 1.5 Field Categorization and Semantic Layers

TVL module fields fall into three categories based on their role in the formal semantics:

#### 1.5.1 Semantic Fields (Under Formal Semantics)

These fields have precise mathematical meaning and are subject to the theorems in this document:

| Category | Field | Semantic Role |
|----------|-------|---------------|
| **Type System** | `tvars[].name` | Identifier in typing context Γ |
| **Type System** | `tvars[].type` | Type τ in judgment Γ ⊢ x : τ |
| **Type System** | `tvars[].domain` | Domain D in 𝒟⟦d⟧(E_τ) |
| **Static Validity** | `constraints.structural` | Formula φ in F^str(c, Φ^str) |
| **Static Validity** | `constraints.derived` | Environment-scoped operational preconditions evaluated on E_τ |
| **Promotion** | `objectives[].name` | Component index in objective vector y |
| **Operational Metadata** | `objectives[].metric_ref` | Declarative identifier for the evaluator metric contract |
| **Promotion** | `objectives[].direction` | Direction sign σ(·) |
| **Promotion** | `objectives[].band` | TOST equivalence band [L, U] |
| **Promotion** | `promotion_policy.dominance` | Dominance relation ≻_ε |
| **Promotion** | `promotion_policy.min_effect` | Epsilon map ε : Objective → ℝ⁺ |
| **Promotion** | `promotion_policy.alpha` | Significance level α |
| **Promotion** | `promotion_policy.adjust` | Multiple-testing adjustment |
| **Acceptability** | `promotion_policy.chance_constraints` | Behavioral acceptability filter |

#### 1.5.2 Operational Fields (Affect Tooling, Not Semantics)

These fields control tooling behavior but do not affect the mathematical meaning of constraints or promotions:

| Field | Purpose |
|-------|---------|
| `exploration.strategy` | Algorithm selection for optimization |
| `exploration.budgets` | Resource limits (trials, time, cost) |
| `exploration.parallelism` | Execution concurrency |
| `exploration.convergence` | Early stopping heuristics |
| `exploration.initial_sampling` | Search initialization |
| `promotion_policy.tie_breakers` | Deterministic ordering for equal configs |

#### 1.5.3 Metadata Fields (Informational Only)

These fields are for identification and reproducibility, with no semantic content:

| Field | Purpose |
|-------|---------|
| `tvl.module` | Namespace identifier |
| `tvl.validation` | Tooling flags (skip checks) |
| `tvl_version` | Language version for compatibility |
| `environment.snapshot_id` | Timestamp labeling E_τ |
| `environment.bindings` | Implementation-defined deployment identifiers |
| `environment.components` | Deprecated alias for `environment.bindings` |
| `evaluation_set.dataset` | Evidence-binding identifier for the evaluated task set |
| `evaluation_set.seed` | Evidence-binding seed for repeatable evaluation |

#### 1.5.4 Semantic Layer Architecture

The semantic fields operate at three distinct layers:

**Layer 1: Static Validity (Pre-Evaluation)**

Determines which configurations are *structurally valid* before any evaluation:

```
Valid(c, M) ⟺ c ∈ Config(Δ, E_τ) ∧ F^str(c, Φ^str) ∧ F^op(E_τ, Φ^der)
```

- **Structural constraints** (`constraints.structural`): Boolean formulas over TVARs
- **Operational preconditions** (`constraints.derived`): Linear predicates over environment

These are checked *statically* — no evaluation of the configuration is required.

**Layer 2: Behavioral Acceptability (Post-Evaluation)**

Determines which evaluated configurations meet *hard behavioral requirements*:

```
Acceptable(c, Y_c, M) ⟺ ChancePass(c, Y_c, M) ∧ BandPass(c, Y_c, M)
```

Where:
- `Y_c` is the evaluation result (observed objective values, chance outcomes)
- `ChancePass` checks that all chance constraints are satisfied
- `BandPass` checks that all banded objectives fall within their equivalence bands

These require *evaluation* — the configuration must be run to observe outcomes.

**Layer 3: Dominance Relation (Comparative)**

Determines whether an acceptable candidate should *replace* the incumbent:

```
Promote(c_cand, c_inc, M) ⟺
    Valid(c_cand, M) ∧
    Acceptable(c_cand, Y_cand, M) ∧
    c_cand ≻_ε c_inc  (statistically, per §9)
```

Only the dominance relation (`min_effect`, `alpha`, `adjust`) is comparative. Chance constraints and band objectives are *acceptability filters*, not factors in the dominance comparison.

**Key Distinction**: Chance constraints determine *if* a configuration is acceptable, not *how* it compares to alternatives. A candidate failing a chance constraint is rejected regardless of how well it performs on objectives.

**Not Covered by Formal Semantics:**

| Field Category | Examples | Reason |
|----------------|----------|--------|
| Exploration settings | `exploration.*` | Operational (algorithm choice, not meaning) |
| Evaluation context | `evaluation_set.*` | Binds evidence and claims; evaluation execution is outside the static semantics |
| Tie-breaking | `promotion_policy.tie_breakers` | Heuristic (not part of dominance relation) |
| Module metadata | `tvl.module`, `tvl_version` | Informational (no semantic content) |

These fields affect *how* optimization is performed, not *what* constitutes a valid or acceptable configuration.

#### 1.5.5 Governed-but-not-searched fields (TVL 1.1)

> **Status**: accepted (2026-06-05) in [RFC 0001](rfc-0001-knob-bindings-cvars-policies.md)
> (Knob bindings: calibrated variables and policies). The RFC holds the normative
> semantics; this subsection places the category in the layering.

TVL 1.1 introduces a fourth field category: declarations that are **parsed, typed,
and governed but absent from the search semantics** — they never enter Γ,
`Config(Δ, E_τ)`, or `F^str`, so Theorem 8.1 (SAT soundness) and the §9 promotion
theorems are preserved by construction: the existing results still hold for the
core language. The new constructs themselves are not yet covered by the mechanized
proofs (§1.4).

| Field | Layer | Role |
|-------|-------|------|
| `cvars[].name/type/domain` | Governed (new) | Calibrated variables: optimizer-invisible, certificate-backed values resolved per configuration |
| `cvars[].calibration.*` | Operational (§1.5.2) | Calibrator/evidence identification; freshness-context inputs |
| `cvars[].governance.require_calibration` | Acceptability (Layer 2, §1.5.4) | Per-CVAR strict-mode opt-in (a `strict(M, c)` disjunct) |
| `policies[].*` | Operational (§1.5.2) | Named operational policies (e.g. cascade) — like `exploration.*` |
| `promotion_policy.require_calibration` | Acceptability (Layer 2, §1.5.4) | Strict evidence mode; certificate-freshness filter alongside `chance_constraints` |
| `scope` (any declaration) | Metadata (§1.5.3) | Node/agent/workflow ownership annotation |

Calibrated variables enter the formal semantics only when explicitly substituted as
constants into structural constraints — an extension deferred by RFC 0001.

---

## 2. Abstract Syntax

We define TVL's abstract syntax tree (AST) using algebraic data types. This separates the language's structure from its concrete (textual) representation.

### 2.1 Notation

We use the following notational conventions:

- `x ∈ X` denotes membership
- `X → Y` denotes total functions from X to Y
- `X ⇀ Y` denotes partial functions
- `𝒫(X)` denotes the powerset of X
- `X*` denotes finite sequences over X
- `⟦·⟧` denotes semantic (denotation) functions
- `⊢` denotes derivability in a judgment
- `⊥` denotes undefined/bottom (used for constructs outside the verified subset)

### 2.2 Identifiers and Literals

```
Ident    ::= [a-zA-Z_][a-zA-Z0-9_.]*     (* Identifiers *)
IntLit   ::= ℤ                           (* Integer literals *)
FloatLit ::= ℚ                           (* Rational literals, representing floats *)
StrLit   ::= String                      (* String literals *)
BoolLit  ::= true | false                (* Boolean literals *)

Literal  ::= IntLit | FloatLit | StrLit | BoolLit

Number   ::= IntLit | FloatLit           (* Numeric literals *)
```

### 2.3 Types

TVL supports a closed set of types:

```
BaseType     ::= bool | int | float | str

CompoundType ::= enum[ElemType]
               | tuple[Type+]
               | callable[ProtoId]

ElemType     ::= str | int | float

Type         ::= BaseType | CompoundType

ProtoId      ::= Ident                   (* Protocol identifier *)
```

**Definition 2.1 (Type Universe)**.
The set of all valid TVL types is:
```
𝒯 = {bool, int, float, str}
    ∪ {enum[τ] | τ ∈ {str, int, float}}
    ∪ {tuple[τ₁,...,τₙ] | n ≥ 1, τᵢ ∈ 𝒯}
    ∪ {callable[P] | P ∈ Ident}
```

**Note**: While `str` is a base type, there is no `str`-typed TVAR domain in the core language. String values appear only within `enum[str]` domains. The `str` type exists to give string literals a proper type in the type system, enabling well-typed equality comparisons like `model = "gpt-4"` where `model : enum[str]`.

### 2.4 Domain Specifications

```
DomainSpec ::= EnumDomain
             | RangeDomain
             | SetDomain
             | RegistryDomain
             | TupleDomain

EnumDomain    ::= [Literal+]                          (* Explicit enumeration *)
RangeDomain   ::= {range: [Number, Number], resolution: Number}
SetDomain     ::= {set: [Literal+]}                   (* Wrapped enumeration *)
RegistryDomain::= {registry: Ident, filter?: String, version?: String}
TupleDomain   ::= {components: [DomainSpec+]}         (* Product domain *)
TupleLit      ::= (Literal, ..., Literal)             (* Tuple literal *)
```

**Well-formedness for RangeDomain**: A range domain `{range: [a, b], resolution: r}` is well-formed iff:
- `r > 0` (positive resolution)
- `a ≤ b` (non-empty range)
- For float ranges: `resolution` MUST be specified (required field)
- For int ranges: `resolution` defaults to `1` if omitted

### 2.5 TVAR Declarations

```
TVarDecl ::= {
  name: Ident,
  type: Type,
  domain: DomainSpec
}

TVarDeclContext ::= TVarDecl*            (* Written as Δ for declarations *)
```

**Notation**: We use `Δ` for TVAR declaration contexts (lists of declarations) and `Γ` for typing contexts (maps from identifiers to types). Given `Δ`, we derive `Γ` by: `Γ(t.name) = t.type` for each `t ∈ Δ`.

### 2.6 Constraint Syntax

#### Structural Constraints (Boolean formulas over TVARs)

```
Atom ::= ScalarAtom | TupleAtom

ScalarAtom ::= EqAtom | CmpAtom | IntervalAtom | TVarEqAtom | MemAtom

EqAtom       ::= Ident = Literal | Ident ≠ Literal
CmpAtom      ::= Ident ≥ Number | Ident ≤ Number | Ident > Number | Ident < Number
IntervalAtom ::= Number ≤ Ident ≤ Number
TVarEqAtom   ::= Ident = Ident | Ident ≠ Ident
MemAtom      ::= Ident ∈ {Literal+}

TupleAtom ::= TupleEqAtom | TupleMemAtom | TupleVarEqAtom

TupleEqAtom     ::= Ident = TupleLit              (* t = (v₁,...,vₙ) *)
TupleMemAtom    ::= Ident ∈ {TupleLit+}           (* t ∈ {(1,2), (3,4)} *)
TupleVarEqAtom  ::= Ident = Ident                 (* t = u for tuple TVARs *)

Formula ::= Atom
          | Formula ∧ Formula           (* Conjunction *)
          | Formula ∨ Formula           (* Disjunction *)
          | ¬ Formula                   (* Negation *)
          | Formula ⇒ Formula           (* Implication: sugar for ¬A ∨ B *)

StructClause ::= {expr: Formula}
               | {when: Formula, then: Formula}

StructConstraints ::= StructClause*
```

#### Derived Constraints (Linear arithmetic over environment)

```
EnvIdent ::= Ident                       (* Environment variable identifier *)

AffineTerm ::= Number | Number · EnvIdent | EnvIdent

LinExpr ::= AffineTerm (+ AffineTerm | - AffineTerm)*

DerivedAtom ::= LinExpr ≤ Number
              | LinExpr ≥ Number
              | LinExpr = Number

DerivedClause ::= {require: DerivedAtom}

DerivedConstraints ::= DerivedClause*
```

### 2.7 Objectives

```
Direction ::= maximize | minimize

StdObjective ::= {
  name: Ident,
  direction: Direction
}

BandTarget ::= [Number, Number]                    (* Interval form *)
             | {center: Number, tol: Number}       (* Center-tolerance form *)

BandObjective ::= {
  name: Ident,
  band: {
    target: BandTarget,
    test: TOST,
    alpha: Number
  }
}

Objective ::= StdObjective | BandObjective

Objectives ::= Objective+
```

### 2.8 Promotion Policy

```
TieBreaker ::= min | max | min_abs_deviation | custom

AdjustMethod ::= none | bonferroni | holm | BH

ChanceConstraint ::= {
  name: Ident,
  threshold: Number,
  confidence: Number
}

PromotionPolicy ::= {
  dominance: epsilon_pareto,
  alpha?: Number,                        (* Default: 0.05 *)
  min_effect?: Ident → Number,           (* ε values per objective *)
  adjust?: AdjustMethod,                 (* Default: holm *)
  chance_constraints?: ChanceConstraint*,
  tie_breakers?: Ident → TieBreaker
}
```

### 2.9 Module Structure

```
Environment ::= {
  snapshot_id: Timestamp,
  components?: Ident → Value
}

EvaluationSet ::= {
  dataset: String,
  seed?: Integer
}

Module ::= {
  tvl: {module: Ident, validation?: ValidationOpts},
  tvl_version?: String,
  environment: Environment,
  evaluation_set: EvaluationSet,
  tvars: TVarDeclContext,
  constraints?: {
    structural?: StructConstraints,
    derived?: DerivedConstraints
  },
  objectives: Objectives,
  promotion_policy: PromotionPolicy,
  exploration?: Exploration
}
```

---

## 3. Semantic Domains

We define the mathematical structures that give meaning to TVL constructs.

### 3.1 Value Domains

**Definition 3.1 (Base Value Domains)**.
```
𝔹 = {true, false}                        (* Booleans *)
ℤ                                         (* Integers *)
ℚ                                         (* Rationals, representing floats *)
𝕊                                         (* Strings *)
```

**Definition 3.2 (Type Interpretation)**.
The interpretation function `⦃·⦄ : Type → 𝒫(Value)` maps types to their value sets:

```
⦃bool⦄         = 𝔹
⦃int⦄          = ℤ
⦃float⦄        = ℚ
⦃str⦄          = 𝕊
⦃enum[str]⦄    = 𝕊
⦃enum[int]⦄    = ℤ
⦃enum[float]⦄  = ℚ
⦃tuple[τ₁,...,τₙ]⦄ = ⦃τ₁⦄ × ... × ⦃τₙ⦄
⦃callable[P]⦄  = ⊥                           (* Outside verified subset; see §1.4 *)
```

**Note**: The interpretation of `callable[P]` types is left undefined in this document. Callable types are excluded from the formally verified subset (§1.4) because "implements protocol P" requires a protocol typing system beyond the scope of this specification. For practical use, treat callable-typed TVARs as opaque identifiers validated at runtime.

### 3.2 Environment Domain

**Definition 3.3 (Environment Typing Context)**.
An environment typing context `Γ_env` maps environment identifiers to numeric types:
```
Γ_env : EnvIdent → {int, float}
```

**Definition 3.4 (Environment)**.
An environment `E` is a partial function from identifiers to values:
```
E : Ident ⇀ Value
```

The environment is indexed by a timestamp τ, written `E_τ`, representing a snapshot of external state (model catalogs, price lists, quotas, etc.).

**Definition 3.5 (Well-formed Environment)**.
Environment `E_τ` is well-formed with respect to typing context `Γ_env` iff:
```
∀x ∈ dom(Γ_env): x ∈ dom(E_τ) ∧ E_τ(x) ∈ ⦃Γ_env(x)⦄
```

### 3.3 Domain Interpretation

**Definition 3.6 (Domain Interpretation)**.
Given environment `E_τ`, the domain interpretation function maps domain specs to finite sets of values:

```
𝒟⟦·⟧ : DomainSpec × Environment → 𝒫_fin(Value)

𝒟⟦[v₁,...,vₙ]⟧(E_τ)              = {v₁,...,vₙ}
𝒟⟦{range:[a,b], resolution:r}⟧(E_τ) = {a + i·r | i ∈ {0,...,N}}
    where N = ⌊(b-a)/r⌋
𝒟⟦{set:[v₁,...,vₙ]}⟧(E_τ)        = {v₁,...,vₙ}
𝒟⟦{registry:R, filter:f}⟧(E_τ)   = ⊥   (* Outside verified subset *)
𝒟⟦{components:[d₁,...,dₙ]}⟧(E_τ) = 𝒟⟦d₁⟧(E_τ) × ... × 𝒟⟦dₙ⟧(E_τ)
```

**Note on Registry Domains**: Registry domain interpretation is undefined (`⊥`) in this specification because it requires external state interaction. Modules using registry domains fall outside the formally verified subset (§1.4). To obtain formal guarantees, resolve registry domains to explicit enum domains before validation.

**Lemma 3.1 (Range Domain Finiteness)**.
For any well-formed range domain `{range:[a,b], resolution:r}` with `r > 0` and `a ≤ b`:
```
|𝒟⟦{range:[a,b], resolution:r}⟧| = ⌊(b-a)/r⌋ + 1 < ∞
```

*Proof*: Immediate from the definition; the index set `{0,...,N}` is finite. □

### 3.4 Configuration Space

**Definition 3.7 (Configuration)**.
Given TVAR declaration context `Δ = [t₁,...,tₙ]` and environment `E_τ`, a **configuration** is a total assignment:
```
c : {t.name | t ∈ Δ} → Value

such that ∀t ∈ Δ: c(t.name) ∈ 𝒟⟦t.domain⟧(E_τ)
```

**Definition 3.8 (Configuration Space)**.
The configuration space is the Cartesian product of all TVAR domains:
```
Config(Δ, E_τ) = ∏_{t ∈ Δ} 𝒟⟦t.domain⟧(E_τ)
```

### 3.5 Objective Space

**Definition 3.9 (Objective Vector)**.
For objectives `O = [o₁,...,oₖ]`, an objective vector is:
```
y ∈ ℝᵏ

where y[i] is the observed (point estimate) value for objective oᵢ
```

This is the **theoretical** objective vector used for defining dominance relations. For statistical testing, we require additional uncertainty information; see Definition 9.7 (Evaluation Result).

**Definition 3.10 (Direction Sign)**.
```
σ(maximize) = +1
σ(minimize) = -1
```

Normalized comparison: objective `i` improves when `σ(oᵢ.direction) · y[i]` increases.

**Definition 3.11 (Banded Objective Predicate)**.
An objective `o` is **banded** iff `o.band ≠ ⊥` (i.e., it has a defined band specification). We write:
```
Banded(o) ⟺ o.band is defined

BandedObjectives(M) = {o ∈ M.objectives | Banded(o)}
StandardObjectives(M) = {o ∈ M.objectives | ¬Banded(o)}
```

---

## 4. Type System

TVL uses a simple type system to ensure constraints are well-formed.

### 4.1 Typing Context

**Definition 4.1 (Typing Context)**.
A typing context `Γ` maps TVAR names to their declared types:
```
Γ : Ident → Type
```

Given declaration context `Δ`, we derive `Γ` by: `Γ(t.name) = t.type` for each `t ∈ Δ`.

### 4.2 Type Judgments

We define typing judgments of the form:
```
Γ ⊢ e : τ      (* Expression e has type τ under context Γ *)
Γ ⊢ φ : prop   (* Formula φ is well-typed under context Γ *)
```

### 4.3 Literal Typing Rules

```
─────────────────── (T-Int)
Γ ⊢ n : int         where n ∈ ℤ

─────────────────── (T-Float)
Γ ⊢ r : float       where r ∈ ℚ

─────────────────── (T-Bool)
Γ ⊢ b : bool        where b ∈ {true, false}

─────────────────── (T-Str)
Γ ⊢ s : str         where s ∈ 𝕊
```

### 4.4 TVAR Reference Typing

```
Γ(x) = τ
─────────────────── (T-Var)
Γ ⊢ x : τ
```

### 4.5 Element Type Extraction

**Definition 4.2 (Element Type)**.
The element type function extracts the underlying element type for comparison purposes:
```
elem(bool)        = bool
elem(int)         = int
elem(float)       = float
elem(str)         = str
elem(enum[τ])     = τ
elem(tuple[...])  = tuple[...]     (* Tuples have no element extraction *)
elem(callable[P]) = callable[P]
```

**Rationale**: A TVAR declared `enum[str]` has type `enum[str]`, but comparisons are against string literals with type `str`. The `elem()` function bridges this gap, allowing `model = "gpt-4"` to type-check when `model : enum[str]`.

### 4.6 Scalar Atom Typing Rules

```
Γ ⊢ x : τ    Γ ⊢ v : elem(τ)
──────────────────────────── (T-Eq)
Γ ⊢ (x = v) : prop

Γ ⊢ x : τ    Γ ⊢ v : elem(τ)
──────────────────────────── (T-Neq)
Γ ⊢ (x ≠ v) : prop

Γ ⊢ x : τ    elem(τ) ∈ {int, float}    Γ ⊢ n : elem(τ)
────────────────────────────────────────────────────── (T-Cmp)
Γ ⊢ (x ≥ n) : prop
(similarly for ≤, >, <)

Γ ⊢ x : τ    elem(τ) ∈ {int, float}    a ≤ b
────────────────────────────────────────────── (T-Interval)
Γ ⊢ (a ≤ x ≤ b) : prop

Γ ⊢ x : τ    Γ ⊢ y : τ'    elem(τ) = elem(τ')
───────────────────────────────────────────── (T-TVarEq)
Γ ⊢ (x = y) : prop

Γ ⊢ x : τ    ∀v ∈ S: Γ ⊢ v : elem(τ)
────────────────────────────────────── (T-Mem)
Γ ⊢ (x ∈ S) : prop
```

### 4.7 Tuple Atom Typing Rules

```
Γ ⊢ t : tuple[τ₁,...,τₙ]    ∀i: Γ ⊢ vᵢ : elem(τᵢ)
──────────────────────────────────────────────── (T-TupleEq)
Γ ⊢ (t = (v₁,...,vₙ)) : prop

Γ ⊢ t : tuple[τ₁,...,τₙ]    ∀(v₁,...,vₙ) ∈ S: ∀i: Γ ⊢ vᵢ : elem(τᵢ)
────────────────────────────────────────────────────────────────── (T-TupleMem)
Γ ⊢ (t ∈ S) : prop

Γ ⊢ t : tuple[τ₁,...,τₙ]    Γ ⊢ u : tuple[τ₁,...,τₙ]
───────────────────────────────────────────────────── (T-TupleVarEq)
Γ ⊢ (t = u) : prop
```

**Note**: Tuple comparison requires component-wise type matching. A tuple of n components can only be compared against another tuple of the same arity with matching component types.

### 4.8 Formula Typing Rules

```
Γ ⊢ φ : prop    Γ ⊢ ψ : prop
─────────────────────────────── (T-And)
Γ ⊢ (φ ∧ ψ) : prop

Γ ⊢ φ : prop    Γ ⊢ ψ : prop
─────────────────────────────── (T-Or)
Γ ⊢ (φ ∨ ψ) : prop

Γ ⊢ φ : prop
─────────────────── (T-Not)
Γ ⊢ (¬φ) : prop

Γ ⊢ φ : prop    Γ ⊢ ψ : prop
─────────────────────────────── (T-Impl)
Γ ⊢ (φ ⇒ ψ) : prop
```

### 4.9 Derived Constraint Typing

**Definition 4.3 (Derived Expression Typing)**.
Given environment typing context `Γ_env`:

```
Γ_env(x) = τ    τ ∈ {int, float}
───────────────────────────────── (T-EnvVar)
Γ_env ⊢ x : τ

─────────────────── (T-NumConst)
Γ_env ⊢ n : num     where n ∈ ℚ

Γ_env ⊢ n : num    Γ_env ⊢ x : τ
────────────────────────────────── (T-Scale)
Γ_env ⊢ n · x : float

Γ_env ⊢ e₁ : τ₁    Γ_env ⊢ e₂ : τ₂
────────────────────────────────── (T-Add)
Γ_env ⊢ e₁ + e₂ : num

Γ_env ⊢ e : num
────────────────────── (T-DerivedCmp)
Γ_env ⊢ (e ≤ n) : prop
(similarly for ≥, =)
```

**Definition 4.4 (Well-formed Derived Constraint)**.
A derived constraint `ψ` is well-formed under `Γ_env` iff `Γ_env ⊢ ψ : prop` is derivable and `ψ` contains no TVAR references (only environment identifiers).

### 4.10 Type Soundness

**Theorem 4.1 (Denotation Totality)**.
If `Γ ⊢ φ : prop` and `c` is a configuration respecting `Γ` (i.e., `∀x ∈ dom(Γ): c(x) ∈ ⦃Γ(x)⦄`), then `⟦φ⟧(c) ∈ 𝔹` (the denotation is defined and boolean).

*Proof*: By structural induction on the derivation of `Γ ⊢ φ : prop`.

**Base cases (atoms)**:
- (T-Eq): By premises, `c(x) ∈ ⦃τ⦄` and `v ∈ ⦃elem(τ)⦄`. Since `⦃enum[τ]⦄ ⊆ ⦃τ⦄` and equality is decidable on all value domains, `⟦x = v⟧(c) ∈ 𝔹`.
- (T-Cmp): By premises, `c(x)` and `n` are both numeric. Comparison is total on numeric types, so `⟦x ≥ n⟧(c) ∈ 𝔹`.
- Other atoms: Analogous reasoning.

**Inductive cases (connectives)**:
- (T-And): By IH, `⟦φ⟧(c), ⟦ψ⟧(c) ∈ 𝔹`. Conjunction is total on 𝔹, so `⟦φ ∧ ψ⟧(c) ∈ 𝔹`.
- (T-Or), (T-Not), (T-Impl): Similar. □

---

## 5. Denotational Semantics

We define meaning functions that map syntactic constructs to their mathematical interpretations.

### 5.1 Scalar Atom Semantics

**Definition 5.1 (Scalar Atom Interpretation)**.
Given configuration `c`, the atom interpretation `⟦·⟧ : Atom × Config → 𝔹`:

```
⟦x = v⟧(c)       = true  iff  c(x) = v
⟦x ≠ v⟧(c)       = true  iff  c(x) ≠ v
⟦x ≥ n⟧(c)       = true  iff  c(x) ≥ n
⟦x ≤ n⟧(c)       = true  iff  c(x) ≤ n
⟦x > n⟧(c)       = true  iff  c(x) > n
⟦x < n⟧(c)       = true  iff  c(x) < n
⟦a ≤ x ≤ b⟧(c)   = true  iff  a ≤ c(x) ≤ b
⟦x = y⟧(c)       = true  iff  c(x) = c(y)      (* TVAR equality *)
⟦x ≠ y⟧(c)       = true  iff  c(x) ≠ c(y)
⟦x ∈ S⟧(c)       = true  iff  c(x) ∈ S
```

### 5.2 Tuple Atom Semantics

**Definition 5.2 (Tuple Atom Interpretation)**.
Tuple atoms are interpreted by expansion to conjunctions/disjunctions of component comparisons:

```
⟦t = (v₁,...,vₙ)⟧(c) = ⟦t.1 = v₁⟧(c) ∧ ... ∧ ⟦t.n = vₙ⟧(c)
                      = true iff ∀i: c(t)[i] = vᵢ

⟦t ∈ S⟧(c)           = ⋁_{s ∈ S} ⟦t = s⟧(c)
                      = true iff ∃s ∈ S: c(t) = s

⟦t = u⟧(c)           = true iff c(t) = c(u)
                      (component-wise equality for tuples)
```

Where `c(t)[i]` denotes the i-th component of the tuple value assigned to TVAR `t`.

**Rationale**: Defining tuple semantics via expansion keeps the core semantics small and aligns with the SMT flattening strategy (§8.2).

### 5.3 Formula Semantics

**Definition 5.3 (Formula Interpretation)**.
The formula interpretation `⟦·⟧ : Formula × Config → 𝔹`:

```
⟦A⟧(c)           = (atom interpretation of A)
⟦φ ∧ ψ⟧(c)       = ⟦φ⟧(c) ∧ ⟦ψ⟧(c)
⟦φ ∨ ψ⟧(c)       = ⟦φ⟧(c) ∨ ⟦ψ⟧(c)
⟦¬φ⟧(c)          = ¬⟦φ⟧(c)
⟦φ ⇒ ψ⟧(c)       = ¬⟦φ⟧(c) ∨ ⟦ψ⟧(c)
```

### 5.4 Constraint Clause Semantics

**Definition 5.4 (Structural Clause Interpretation)**.

```
⟦{expr: φ}⟧(c)           = ⟦φ⟧(c)
⟦{when: φ, then: ψ}⟧(c)  = ⟦φ ⇒ ψ⟧(c) = ¬⟦φ⟧(c) ∨ ⟦ψ⟧(c)
```

**Definition 5.5 (Constraint Set Satisfaction)**.
Configuration `c` satisfies constraint set `Φ` iff:
```
c ⊨ Φ  ⟺  ∀φ ∈ Φ: ⟦φ⟧(c) = true
```

### 5.5 Derived Constraint Semantics

**Definition 5.6 (Linear Expression Interpretation)**.
Given well-formed environment `E_τ` with respect to `Γ_env`:

```
⟦n⟧(E_τ)         = n                      (* Numeric constant *)
⟦k · x⟧(E_τ)     = k · E_τ(x)             (* Scaled variable *)
⟦x⟧(E_τ)         = E_τ(x)                 (* Variable *)
⟦e₁ + e₂⟧(E_τ)   = ⟦e₁⟧(E_τ) + ⟦e₂⟧(E_τ)
⟦e₁ - e₂⟧(E_τ)   = ⟦e₁⟧(E_τ) - ⟦e₂⟧(E_τ)
```

**Precondition**: For the interpretation to be defined, all referenced identifiers must be in `dom(E_τ)`. Well-formedness of derived constraints (Definition 4.4) and well-formedness of environment (Definition 3.5) ensure this.

**Definition 5.7 (Derived Constraint Interpretation)**.

```
⟦e ≤ n⟧(E_τ)     = true  iff  ⟦e⟧(E_τ) ≤ n
⟦e ≥ n⟧(E_τ)     = true  iff  ⟦e⟧(E_τ) ≥ n
⟦e = n⟧(E_τ)     = true  iff  ⟦e⟧(E_τ) = n
```

---

## 6. Feasibility Predicates

### 6.1 Structural Feasibility

**Definition 6.1 (Structural Feasibility)**.
Configuration `c` is **structurally feasible** under structural constraints `Φ^str`:
```
F^str(c, Φ^str) = ∧_{φ ∈ Φ^str} ⟦φ⟧(c)
```

### 6.2 Operational Feasibility

**Definition 6.2 (Operational Feasibility)**.
Under environment `E_τ` and derived constraints `Φ^der`:
```
F^op(E_τ, Φ^der) = ∧_{ψ ∈ Φ^der} ⟦ψ⟧(E_τ)
```

### 6.3 Total Feasibility

**Definition 6.3 (Feasible Configuration Space)**.
The set of feasible configurations:
```
Feasible(M) = {c ∈ Config(M.Δ, E_τ) | F^str(c, M.Φ^str) ∧ F^op(E_τ, M.Φ^der)}
```

**Definition 6.4 (Static Validity Predicate)**.
A configuration `c` is **statically valid** under module `M`:
```
Valid(c, M) ⟺ c ∈ Feasible(M)
           ⟺ c ∈ Config(M.Δ, E_τ) ∧ F^str(c, M.Φ^str) ∧ F^op(E_τ, M.Φ^der)
```

This is the Layer 1 predicate from §1.5.4. A configuration is valid iff:
1. Each TVAR value is within its declared domain
2. All structural constraints are satisfied
3. All declared operational preconditions are satisfied under the environment

**Note**: Validity is determined *before* evaluation. It does not require running the configuration.

---

## 7. Informative Metatheory

This section records formal results about the normative core under the stated assumptions. It does not define an optimizer, a search-efficiency guarantee, or additional surface-language requirements.

### 7.1 Decidability

**Theorem 7.1 (Structural Constraint Evaluation)**.
For any well-formed structural constraint set `Φ^str` and configuration `c`, determining `F^str(c, Φ^str)` is decidable in polynomial time.

*Proof*: Each atom is a comparison that can be evaluated in O(1). Formula structure is finite. Total complexity is O(|Φ^str| · |atoms|). □

**Theorem 7.2 (Satisfiability Decidability)**.
For any well-formed structural constraint set `Φ^str` over finite domains, determining whether `∃c: F^str(c, Φ^str) = true` is decidable (in NP).

*Proof sketch*:
1. All TVAR domains are finite (Definition 3.6, Lemma 3.1)
2. Therefore, the configuration space `Config(Δ, E_τ)` is finite
3. Satisfiability can be decided by guess-and-check: guess configuration, verify in polynomial time (Theorem 7.1)
4. This places satisfiability in NP
5. It is NP-hard (reduction from SAT via boolean TVARs)
6. Therefore, satisfiability is NP-complete

For practical implementation, TVL constraints compile to QF_LIA (quantifier-free linear integer arithmetic) which is handled efficiently by modern SMT solvers (§8). □

**Theorem 7.3 (Derived Constraint Decidability)**.
For well-formed derived constraints `Φ^der` under well-formed environment `E_τ`, evaluation is decidable in polynomial time.

*Proof*: Derived constraints are linear inequalities over constants (environment values). Each constraint evaluation requires O(|terms|) arithmetic operations. Total: O(|Φ^der| · |terms|). □

### 7.2 Constraint Consistency

**Definition 7.1 (Consistent Module)**.
Module `M` is **consistent** iff `Feasible(M) ≠ ∅`.

**Theorem 7.4 (Consistency is Decidable)**.
Determining whether `Feasible(M) ≠ ∅` is decidable.

*Proof*: Two-phase decision procedure:

**Phase 1**: Evaluate derived constraints against environment.
- Compute `F^op(E_τ, M.Φ^der)` (polynomial time, Theorem 7.3)
- If `F^op(E_τ, M.Φ^der) = false`, return INCONSISTENT (the pinned environment does not satisfy the module's operational preconditions)

**Phase 2**: Check structural constraint satisfiability.
- If Phase 1 passed, check `∃c ∈ Config(Δ, E_τ): F^str(c, M.Φ^str) = true`
- This is decidable (Theorem 7.2)
- If SAT, return CONSISTENT; else return INCONSISTENT

Both phases are decidable, so consistency is decidable. □

---

## 8. Informative Reference SMT Encoding

This section is non-normative. It demonstrates one implementation strategy for deciding structural feasibility. A conforming validator may use another solver or a direct decision procedure if it preserves the judgments defined in Sections 2–6. Internal solver representation is not part of the TVL interchange contract.

We define the compilation from TVL constraints to SMT-LIB format.

### 8.1 Encoding Function

**Definition 8.1 (SMT Encoding)**.
The encoding function has signature:
```
encode : (Δ, Φ^str, P, idx) → SMT-LIB
```

Where:
- `Δ` is the TVAR declaration context
- `Φ^str` is the structural constraint set
- `P` is the precision factor (for float scaling)
- `idx : ∀t ∈ Δ. 𝒟⟦t.domain⟧ → ℕ` is the domain indexing function for enums

The encoding produces:
1. **Variable declarations** for each TVAR
2. **Domain constraints** ensuring values stay within bounds
3. **Structural constraints** as assertions

### 8.2 Type Encoding

```
encode_type(bool)      = Bool
encode_type(int)       = Int
encode_type(float)     = Int          (* Scaled by precision factor P *)
encode_type(str)       = Int          (* Indexed; strings only appear in enums *)
encode_type(enum[τ])   = Int          (* 0..|domain|-1 *)
encode_type(tuple[τ₁,...,τₙ]) = (encode_type(τ₁), ..., encode_type(τₙ))  (* Flattened *)
encode_type(callable[P]) = ⊥          (* Outside verified subset; see §1.4 *)
```

**Tuple Encoding Strategy**: Tuple-typed TVARs are **flattened** into n separate SMT variables. A TVAR `t : tuple[int, float, bool]` becomes three SMT variables: `t_1 : Int`, `t_2 : Int` (scaled float), `t_3 : Bool`.

**Tuple Domain Encoding**: For a tuple domain `{components: [D₁, ..., Dₙ]}`:
```smt
(declare-const t_1 encode_type(τ₁))
(declare-const t_2 encode_type(τ₂))
...
(declare-const t_n encode_type(τₙ))
(assert (domain_constraint D₁ t_1))
(assert (domain_constraint D₂ t_2))
...
(assert (domain_constraint Dₙ t_n))
```

**Tuple Atom Encoding**:
```
encode(t = (v₁,...,vₙ)) = (and (= t_1 (encode_value v₁)) ... (= t_n (encode_value vₙ)))
encode(t ∈ S)           = (or (encode(t = s)) for each s ∈ S)
encode(t = u)           = (and (= t_1 u_1) ... (= t_n u_n))  (* TVAR equality *)
```

### 8.3 TVAR Encoding

**Definition 8.2 (Enum Value Encoding)**.
For enum domain `D = [v₁,...,vₙ]`, define indexing bijection:
```
idx_D : D → {0,...,n-1}
idx_D(vᵢ) = i-1

idx_D⁻¹ : {0,...,n-1} → D
idx_D⁻¹(i) = v_{i+1}
```

**Definition 8.3 (Value Encoding)**.
```
encode_value(b, bool)           = b
encode_value(n, int)            = n
encode_value(r, float)          = scale(r)
encode_value(v, enum[τ])        = idx_D(v)      (* where D is the domain *)
encode_value((v₁,...,vₙ), tuple[...]) = (encode_value(v₁), ..., encode_value(vₙ))
```

**TVAR Encoding by Domain Type**:

For **enum** TVAR `t` with domain `D`:
```smt
(declare-const t Int)
(assert (and (>= t 0) (<= t (- |D| 1))))
```

For **int range** TVAR `t` with domain `{range: [a, b], resolution: r}`:
```smt
; Index-variable encoding for discrete ranges
(declare-const t_idx Int)
(assert (and (>= t_idx 0) (<= t_idx N)))   ; where N = ⌊(b-a)/r⌋
(define-fun t () Int (+ a (* r t_idx)))
```

For **float range** TVAR `t` with domain `{range: [a, b], resolution: r}`:
```smt
; Index-variable encoding with scaling
(declare-const t_idx Int)
(assert (and (>= t_idx 0) (<= t_idx N)))   ; where N = ⌊(b-a)/r⌋
(define-fun t () Int (+ (scale a) (* (scale r) t_idx)))
```

**Rationale for index-variable encoding**: Simple bounds encoding `(and (>= x min) (<= x max))` allows non-domain values (e.g., values between grid points for discretized ranges). Index encoding ensures the SMT variable represents only domain values, which is necessary for soundness.

### 8.4 Comparison Encoding with Direction-Aware Rounding

**Definition 8.4 (Scaling Function)**.
For precision factor P:
```
scale(n) = n · P    for exact integer result when n is P-aligned
```

**Definition 8.5 (Threshold Rounding)**.
For comparison encoding of float TVARs against potentially non-aligned thresholds:

```
encode(x ≥ n)        = (>= x ⌈n · P⌉)
encode(x > n)        = (>= x (+ ⌊n · P⌋ 1))
encode(x ≤ n)        = (<= x ⌊n · P⌋)
encode(x < n)        = (<= x (- ⌈n · P⌉ 1))
encode(a ≤ x ≤ b)    = (and (>= x ⌈a · P⌉) (<= x ⌊b · P⌋))
```

**Lemma 8.1 (Rounding Soundness)**.
For domain value `v` (P-aligned) and threshold `n`:
- `v ≥ n` ⟺ `scale(v) ≥ ⌈n · P⌉`
- `v ≤ n` ⟺ `scale(v) ≤ ⌊n · P⌋`
- `v > n` ⟺ `scale(v) ≥ ⌊n · P⌋ + 1`
- `v < n` ⟺ `scale(v) ≤ ⌈n · P⌉ - 1`

*Proof*: Since `v` is P-aligned, `scale(v) = v · P ∈ ℤ`.
- `v ≥ n` ⟺ `v · P ≥ n · P` ⟺ `scale(v) ≥ ⌈n · P⌉` (ceiling captures "at least")
- `v ≤ n` ⟺ `v · P ≤ n · P` ⟺ `scale(v) ≤ ⌊n · P⌋` (floor captures "at most")
- Strict comparisons follow analogously. □

**Equality Encoding**:
```
encode(x = v)        = (= x (encode_value v))
encode(x ≠ v)        = (not (= x (encode_value v)))
encode(x ∈ S)        = (or (= x (encode_value v₁)) ... (= x (encode_value vₙ)))
```

### 8.5 Precision-Aligned Domains

**Definition 8.6 (Precision-Aligned Domain)**.
A float domain D is **precision-aligned** to precision factor P iff:

```
∀v ∈ D: v · P ∈ ℤ   (equivalently, v = k/P for some integer k)
```

**Examples**:

- Domain `{ range: [0.0, 1.0], resolution: 0.1 }` with P=1000 is aligned because 0.1 × 1000 = 100 ∈ ℤ
- Domain `{ range: [0.0, 1.0], resolution: 0.3 }` with P=1000 is aligned because 0.3 × 1000 = 300 ∈ ℤ
- Domain `{ range: [0.0001, 0.001], resolution: 0.0001 }` with P=1000 is **NOT aligned** because 0.0001 × 1000 = 0.1 ∉ ℤ

**Lemma 8.2 (Precision Adequacy)**.
For a precision-aligned domain D with precision P, the scaling function is bijective on D:

```
∀v₁, v₂ ∈ D: scale(v₁) = scale(v₂) ⟹ v₁ = v₂
```

*Proof*: Since v₁, v₂ ∈ D and D is precision-aligned, v₁ · P and v₂ · P are both integers. If v₁ · P = v₂ · P, then v₁ = v₂. □

**Corollary**: Scaling preserves order on precision-aligned domains:

```
∀v₁, v₂ ∈ D: v₁ < v₂ ⟺ scale(v₁) < scale(v₂)
```

**Choosing an exact precision**.
There is no valid general rule `P = ⌈1/min_gap(D)⌉`: separating adjacent values does not guarantee that every decimal value is represented exactly. An implementation using integer scaling needs a positive integer `P` for which every finite domain value and every value reconstructed from a range is `P`-aligned. For decimal inputs, one sufficient construction is a power of ten at least as large as the maximum decimal scale after parsing the values exactly. The normative conformance requirement and required fallback behavior are stated in §10.4.

### 8.6 Formula Encoding

```
encode(φ ∧ ψ)        = (and encode(φ) encode(ψ))
encode(φ ∨ ψ)        = (or encode(φ) encode(ψ))
encode(¬φ)           = (not encode(φ))
encode(φ ⇒ ψ)        = (or (not encode(φ)) encode(ψ))
```

### 8.7 Decoding Function

**Definition 8.7 (Decoding Function)**.
The decoding function `decode : (SMT-Model, Δ, P, idx) → Config` recovers TVL configurations from SMT solver models:

```
decode(m, t) =
    m(t)                             if t.type = bool
    m(t)                             if t.type = int
    m(t) / P                         if t.type = float  (* unscale *)
    idx_{t.domain}⁻¹(m(t))           if t.type = enum   (* index lookup *)
    (decode(m, t.1), ..., decode(m, t.n))  if t.type = tuple
```

Where:
- `m(t)` is the value assigned to TVAR `t` (or component) in SMT model `m`
- `P` is the precision factor used during encoding
- `idx_{t.domain}⁻¹` is the inverse of the domain indexing function

### 8.8 Encoding Soundness

**Theorem 8.1 (Encoding Soundness)**.
**Preconditions**:
1. All float TVAR domains in module M are precision-aligned to precision factor P
2. Encoding uses index-variable encoding for range domains (§8.3)
3. Encoding uses direction-aware rounding for comparison thresholds (§8.4)

For all configurations `c ∈ Config(Δ, E_τ)` and structural formulas `φ`:

```
m ⊨ encode(Δ, φ, P, idx) ⟺ ⟦φ⟧(decode(m, Δ, P, idx)) = true
```

*Proof*:

**Encoding direction** (`⟦φ⟧(c) = true ⟹ encode(c) ⊨ encode(φ)`):

Construct SMT model `m` from configuration `c` via `encode_value`. We show `m ⊨ encode(φ)`.

1. **Domain constraints**: By construction, `encode_value(c(t)) ∈ {0,...,N}` for index variables, so domain assertions hold.

2. **Atoms**:
   - Equality: `c(x) = v` ⟺ `idx(c(x)) = idx(v)` ⟺ `m(x) = encode_value(v)` ✓
   - Comparison (≥): `c(x) ≥ n` ⟹ `scale(c(x)) ≥ ⌈n·P⌉` by Lemma 8.1 ✓
   - Other comparisons: Analogous via Lemma 8.1

3. **Connectives**: Preserved exactly by SMT-LIB semantics.

**Decoding direction** (`m ⊨ encode(φ) ⟹ ⟦φ⟧(decode(m)) = true`):

Given `m ⊨ encode(φ)`, let `c = decode(m)`.

1. **Well-formedness**: Index-variable encoding ensures `m(t_idx) ∈ {0,...,N}`, so `decode(m)(t) ∈ D`. Thus `c ∈ Config(Δ, E_τ)`.

2. **Atoms**: By Lemma 8.1, comparison encodings preserve truth under decode.

3. **Connectives**: Boolean operations preserved. □

**Corollary 8.1 (Satisfiability Preservation)**.
Under the preconditions of Theorem 8.1:
```
(∃c ∈ Config: ⟦φ⟧(c) = true) ⟺ SAT(encode(φ))
```

### 8.9 Encoding Completeness

**Theorem 8.2 (Encoding Completeness)**.
If `⟦φ⟧(c) = true` for some `c ∈ Config(Δ, E_τ)`, then `encode(φ)` is satisfiable.

*Proof*: Construct SMT model from `c` via `encode_value`. By soundness (Theorem 8.1), this model satisfies `encode(φ)`. □

---

## 9. Promotion Semantics

### 9.1 Objective Vector Comparison

**Definition 9.1 (Direction-Normalized Comparison)**.
For objectives `O` and vectors `y, y' ∈ ℝᵏ`:
```
y ≻_i y'  ⟺  σ(O[i].direction) · y[i] > σ(O[i].direction) · y'[i]
y ≽_i y'  ⟺  σ(O[i].direction) · y[i] ≥ σ(O[i].direction) · y'[i]
```

### 9.2 Pareto Dominance

**Definition 9.2 (Pareto Dominance)**.
Configuration `c` with objective vector `y` **Pareto-dominates** `c'` with `y'`:
```
c ≻_P c'  ⟺  (∀i: y ≽_i y') ∧ (∃i: y ≻_i y')
```

### 9.3 ε-Pareto Dominance

**Definition 9.3 (ε-Pareto Dominance)**.
Given epsilon map `ε : Objective → ℝ⁺`, configuration `c` **ε-dominates** `c'`:
```
c ≻_ε c'  ⟺  ∀i: σ(O[i].direction) · (y[i] - y'[i]) ≥ -ε(O[i])
             ∧ ∃i: σ(O[i].direction) · (y[i] - y'[i]) > ε(O[i])
```

Intuition: `c` is at least as good as `c'` on all objectives (within tolerance ε), and strictly better on at least one (beyond tolerance ε).

### 9.4 Statistical Promotion Gate

**Definition 9.4 (Direction-Normalized Difference)**.
For standard objective `i` with direction `d_i`, the normalized difference is:
```
δ_i = σ(d_i) · (μ_cand[i] - μ_inc[i])
```

Where `μ_cand[i]` and `μ_inc[i]` are the estimated means for objective `i`.

**Interpretation**: `δ_i > 0` means candidate is better; `δ_i < 0` means candidate is worse.

**Definition 9.5 (Statistical Dominance)**.
At significance level `α`, configuration `c` with evaluation `Y_c` **statistically ε-dominates** configuration `c'` with evaluation `Y_{c'}`:

```
StatDominates(c, c', Y_c, Y_{c'}, M) ⟺
    AllNonInferior(c, c', Y_c, Y_{c'}, M)
  ∧ AnySuperior(c, c', Y_c, Y_{c'}, M)
```

For each standard objective `i` (non-banded), using normalized difference `δ_i`:

1. **Non-inferiority test**: H₀: `δ_i ≤ -ε[i]` (candidate is worse by at least ε)
   - If p-value < α, reject H₀ (evidence candidate is not worse)
2. **Superiority test**: H₀: `δ_i ≤ ε[i]` (candidate is not better by more than ε)
   - If p-value < α, reject H₀ (evidence candidate is strictly better)
3. **Inferiority test**: H₀: `δ_i ≥ -ε[i]` (candidate is within the allowed regression margin)
   - If p-value < α, reject H₀ (evidence candidate regressed beyond the margin)

**Statistical Test Specification**:
- For continuous objectives with raw samples: Use **Welch's t-test** (unequal variance assumed)
- For continuous objectives with aggregated statistics (mean, std, n): Use **Welch's t-test** with Welch-Satterthwaite degrees of freedom
- For paired samples (same evaluation instances): Use **paired t-test**
- When variance equality is known: Student's t-test is permitted as an optimization

Promotion requires:
- All non-inferiority tests pass (p < α for each standard objective)
- At least one superiority test passes (improvement > ε with p < α)

### 9.5 Banded Objectives (TOST)

**Definition 9.6 (TOST Equivalence)**.
For banded objective with target `[L, U]` and significance `α`:

```
TOST_pass(μ̂, s, n, [L,U], α) ⟺
    (H₀: μ ≤ L rejected at α) ∧ (H₀: μ ≥ U rejected at α)
```

Configuration passes the band constraint if the **(1 - 2α) confidence interval** for the mean falls entirely within `[L, U]`.

**Important**: TOST uses (1 - 2α) CI, not (1 - α). For α = 0.05, this means a **90% CI** must lie within [L, U], not a 95% CI. This is because TOST performs two one-sided tests, each at level α.

**Banded objectives are Layer 2 only**: Banded objectives are **excluded** from ε-Pareto dominance comparison (Layer 3). They function purely as acceptability filters:
- A configuration with a point estimate outside the declared band is rejected; an on-target result with insufficient evidence for TOST is inconclusive
- A configuration passing all band constraints is not "better" or "worse" on those objectives—it is simply acceptable
- Dominance comparison (§9.4) applies only to `StandardObjectives(M)` (Definition 3.11)

This design reflects the semantic distinction: standard objectives have a direction of improvement (maximize/minimize), while banded objectives define a region of acceptable values with no preference within the band.

### 9.6 Behavioral Acceptability

Before dominance comparison, evaluated configurations must pass **acceptability filters**. These are hard constraints that determine whether a configuration is viable, regardless of how well it performs on objectives.

**Definition 9.7 (Evaluation Result)**.
An evaluation result `Y_c` for configuration `c` contains:
```
Y_c = {
  objective_values: Objective → (μ̂, s, n),   (* mean, std dev, sample size *)
  chance_outcomes:  ChanceConstraint → (k, n)  (* violations and trials *)
}
```

Where:
- `μ̂` is the sample mean
- `s` is the sample standard deviation
- `n` is the sample size (number of observations)
- `SE = s / √n` is the standard error (derived)

**Rationale**: Including sample size `n` (not just SE) enables proper degrees-of-freedom calculation for t-tests and allows detection of underpowered comparisons.

**Definition 9.8 (Chance Constraint Satisfaction)**.
For chance constraint `χ = (name, threshold θ, confidence γ)` and observed outcome `(k, n)`, let `CI_upper(k, n, γ)` be the one-sided Clopper-Pearson upper bound at confidence level γ:
```
CI_upper(k, n, γ) = Beta.ppf(γ, k + 1, n - k)
```

and the satisfaction predicate is:

```
ChancePass(χ, k, n) ⟺ CI_upper(k, n, γ) ≤ θ
```

For `k = n`, the upper bound is 1 by convention.

**Intuition**: `threshold` is the maximum allowed violation rate. The evidence must support, at confidence `γ`, that the true violation rate does not exceed that threshold.

**Precondition**: n ≥ 1. If n = 0 (no trials), the chance constraint check is undefined; implementations MUST report an error.

**Edge case (k = 0)**: Zero observed violations can pass only when the one-sided upper bound for `n` trials is at or below `θ`; zero observed violations alone is not sufficient.

**Definition 9.9 (Band Objective Satisfaction)**.
For banded objective `b = (name, target [L, U], α)` and observed statistics `(μ̂, s, n)`:

```
BandPass(b, μ̂, s, n) ⟺ TOST_pass(μ̂, s, n, [L, U], α)
```

For the reference three-way decision, define a hard band failure separately:
```
BandHardFail(b, μ̂) ⟺ μ̂ < L ∨ μ̂ > U
```

If `BandPass` is false while `BandHardFail` is also false, the band result is inconclusive rather than a demonstrated failure.

**Note on direction**: Banded objectives do NOT use the `direction` field. The band [L, U] applies to the raw observed value μ̂, not a direction-normalized value. Banded objectives are *acceptability constraints*, not optimization targets—they define a range of acceptable values, not a direction of improvement.

**Definition 9.10 (Behavioral Acceptability)**.
Configuration `c` with evaluation result `Y_c` has **established behavioral acceptability** under module `M`:

```
Acceptable(c, Y_c, M) ⟺
    (∀χ ∈ M.promotion_policy.chance_constraints: ChancePass(χ, Y_c.chance_outcomes(χ)))
  ∧ (∀o ∈ BandedObjectives(M): BandPass(o.band, Y_c.objective_values(o)))
```

Where `BandedObjectives(M)` is defined in Definition 3.11.

**Key Properties**:

1. **Acceptability is absolute, not comparative**: `Acceptable(c, Y_c, M)` depends only on `c`'s own evaluation, not on any incumbent.

2. **Acceptability gates dominance**: A candidate with a failed chance constraint or a hard band failure is rejected, regardless of objective performance:
   ```
   ChanceFail(c_cand) ∨ BandHardFail(c_cand) ⟹ Decision = Reject
   ```

   An on-target band whose TOST is inconclusive produces `NoDecision`; it is neither acceptable enough to promote nor a demonstrated hard failure.

3. **Separate error budgets**: Chance constraint confidence `γ` is distinct from promotion policy `α`. This allows different risk tolerances for behavioral guarantees vs. objective comparison.

   **Note on risk tolerance**: A module MAY specify different values (e.g., `γ = 0.99` for safety-critical chance constraints, `α = 0.10` for exploratory objective comparison). This is permitted and meaningful: high confidence on behavioral guarantees with more lenient significance on dominance testing. The error budgets are independent; there is no required relationship between `γ` and `α`.

**Lemma 9.1 (Acceptability Independence)**.
Behavioral acceptability is independent of the incumbent:

```
Acceptable(c, Y_c, M) does not reference c_inc or Y_inc
```

*Proof*: Immediate from Definition 9.10; acceptability references only the candidate's own evaluation results (`Y_c`) and the module's constraints. The incumbent configuration plays no role in acceptability determination. □

**Implication**: Chance constraints are *filters*, not *comparisons*. A configuration either meets behavioral requirements or it doesn't—this is independent of what alternatives exist.

### 9.7 Complete Promotion Predicate

**Definition 9.11 (Promotion Decision)**.
Given incumbent `c_inc` with evaluation `Y_inc` and candidate `c_cand` with evaluation `Y_cand`:

```
Promote(c_cand, c_inc, Y_cand, Y_inc, M) ⟺
    Valid(c_cand, M)                              (* Layer 1: Static validity *)
  ∧ Acceptable(c_cand, Y_cand, M)                 (* Layer 2: Behavioral acceptability *)
  ∧ StatDominates(c_cand, c_inc, Y_cand, Y_inc, M) (* Layer 3: Dominance relation *)
```

Where:
- `Valid(c, M)` = domain membership ∧ structural feasibility ∧ operational preconditions (§6)
- `Acceptable(c, Y_c, M)` = chance constraint ∧ band objective satisfaction (Definition 9.10)
- `StatDominates` = statistical ε-Pareto dominance per §9.4

**Decision Logic**:
```
if ¬Valid(c_cand, M):
    return Error("invalid configuration")
if any chance constraint fails or any BandHardFail holds:
    return Reject("acceptability check failed")
if any adjusted inferiority test rejects its null:
    return Reject("regression beyond the allowed margin demonstrated")
if any band is not BandPass:
    return NoDecision("band acceptability not established")
if StatDominates(c_cand, c_inc, Y_cand, Y_inc, M):
    return Promote
return NoDecision("insufficient evidence")
```

### 9.8 Promotion Correctness

**Proposition 9.1 (Scope of Multiple-Testing Adjustment)**.
In the current promotion contract, non-inferiority is an intersection-union test: every per-objective non-inferiority test is evaluated at `α`. The configured `adjust` method applies separately to the superiority family used for the union claim that at least one objective improved beyond `ε` and the inferiority family used for the union claim that at least one objective regressed beyond `ε`.

- `none` provides no family-level correction for either union family.
- Bonferroni and Holm control family-wise error for each adjusted family under their standard conditions.
- Benjamini-Hochberg controls false discovery rate under independence or positive regression dependency; it does not control family-wise error.

These results do not by themselves bound every route to an erroneous promotion. Such a bound also depends on test validity, data generation, selection effects, evaluator reliability, chance and band checks, and whether the evidence was collected independently of candidate selection. A certificate MUST state the tests and assumptions actually used rather than generalize this proposition into a universal agent guarantee.

**Lemma 9.2 (ε-Dominance Composition)**.
*Weak* ε-Pareto dominance composes: if `c₁ ≽_ε c₂` and `c₂ ≽_ε c₃`, then `c₁ ≽_{2ε} c₃`.

Where weak dominance `c ≽_ε c'` means: `∀i: σ(O[i].direction) · (y[i] - y'[i]) ≥ -ε[i]` (no strict improvement required).

**Note on Proposition/Lemma Numbering**: Lemma 9.1 (Acceptability Independence) appears in §9.6. Proposition 9.1 (Scope of Multiple-Testing Adjustment) and Lemma 9.2 (ε-Dominance Composition) appear in §9.8.

*Proof*:

- From `c₁ ≽_ε c₂`: `σᵢ · (y₁[i] - y₂[i]) ≥ -ε[i]` for all `i`
- From `c₂ ≽_ε c₃`: `σᵢ · (y₂[i] - y₃[i]) ≥ -ε[i]` for all `i`
- Sum: `σᵢ · (y₁[i] - y₃[i]) ≥ -2ε[i]` for all `i` □

**Warning: Strict dominance does NOT compose.**
If `c₁ ≻_ε c₂` (c₁ strictly better on *some* objective) and `c₂ ≻_ε c₃` (c₂ strictly better on *some* objective), we cannot conclude `c₁ ≻_{2ε} c₃`.

*Counterexample*: Consider two objectives with `direction = maximize` for both, with `ε > 0` and any `δ > 0`. Let:

- y₁ = (0, 0)
- y₂ = (-ε - δ, ε)
- y₃ = (-δ, -δ)

Then:

- y₁ - y₂ = (ε + δ, -ε), so y₁ ≻_ε y₂
- y₂ - y₃ = (-ε, ε + δ), so y₂ ≻_ε y₃
- But y₁ - y₃ = (δ, δ), so y₁ ≽_{2ε} y₃ while y₁ ≯_{2ε} y₃ (no objective improves by more than 2ε)

Strict ε-dominance can disappear under composition even when weak ε-dominance composes (Lemma 9.2).

**Implication for TVL**: Do not chain promotion decisions transitively. Each promotion must be evaluated against the current incumbent, not inferred from prior promotions.

---

## 10. Conformance Requirements

For a TVL implementation to be **conformant**, it must satisfy:

### 10.1 Parser Requirements

1. Accept all syntactically valid modules per §2
2. Reject all syntactically invalid modules with appropriate error codes
3. Produce AST equivalent to abstract syntax definition

### 10.2 Type Checker Requirements

1. Implement all typing rules from §4 (including `elem()` for enum comparisons)
2. Report `constraint_type_mismatch` for ill-typed formulas
3. Report `undeclared_tvar` for undefined references

### 10.3 Constraint Validator Requirements

1. Check structural constraint satisfiability (Theorem 7.2)
2. Report `unsatisfiable_constraints` if `Feasible(M) = ∅`
3. Evaluate derived constraints against environment (Phase 1 of Theorem 7.4)
4. Report `derived_env_undefined` if environment lookup fails

### 10.4 Structural Decision Procedure Requirements

1. Preserve the normative structural satisfaction judgments in Sections 5 and 6
2. Decide satisfiability for the supported core subset
3. Preserve exact finite-domain membership and comparison behavior. If an implementation uses integer scaling, it MUST choose a positive integer precision that aligns every finite domain value and every value reconstructed from a range; otherwise it MUST use exact rational or index encoding, or report that the reference encoding is unavailable.
4. Report unsupported constructs rather than silently changing their meaning

An implementation MAY use the informative SMT encoding in §8, another solver encoding, or a direct decision procedure.

### 10.5 Promotion Gate Requirements

1. Implement ε-Pareto comparison per §9.3 with direction normalization (§9.4)
2. Support statistical testing with direction-normalized differences (Definition 9.4)
3. Apply the configured multiple-testing adjustment separately to the superiority and inferiority p-value families as specified in §9.8
4. Verify evaluation results include sample size for proper df calculation
5. Distinguish demonstrated failure (`Reject`) from insufficient evidence (`NoDecision`)

### 10.6 Runtime Monitor Requirements

An implementation claiming support for the TVL 1.3 language MUST:

1. Parse and validate the three runtime blocks and `tvl_pack` with the schema/lint layering and closed diagnostics of RFC 0003 §5; check the sealed kind/source/phase/method combinations and references in §12.1; refuse unsupported constructs at every reader entrypoint rather than ignoring or stripping them.
2. Leave every TVL 1.2 module, diagnostic and promotion result unchanged (§12.13, Theorem 12.1).
3. Compose only compatible identities and schedules, tighten fields in their declared orders, and reject an unreachable composition (§12.12). Organization floors belong in a separate `tvl_pack`.
4. Compile only to the closed hosted projection (§12.13), fail closed on an unresolved alias or unavailable token map, and test a privacy canary for every projection row. Observability carries no privacy guarantee; customer-side content checks never consume content-bearing observability evidence.
5. Join opt-in promotion monitors with §9 as specified in §12.7; leave a module with no such monitors unchanged. A built-in promotion evaluator decides only what Definition 12.16 allows and otherwise returns `NoDecision`.
6. Never present validation, compilation or language conformance as enablement of an evaluator or authorization of a response action.
7. Supply conformance cases for parsing, lints, composition, codecs, compilation, projection and the promotion join (RFC 0003 §13). Existing TVL 1.2 results MUST remain unchanged.

An evaluator claiming to implement a TVL 1.3 evaluator profile MUST meet the contracts of §§12.4–12.11. How it does so is specified by that profile, outside this document.

---

## 11. Future Work

### 11.1 Mechanization

Priority areas for mechanized proofs (Coq/Lean/Isabelle):

1. **Denotation totality** (Theorem 4.1)
2. **SMT encoding soundness** (Theorem 8.1)
3. **ε-dominance composition** (Lemma 9.2)

### 11.2 Extensions

Potential language extensions requiring formal treatment:

1. **Conditional domains**: Domain that depends on other TVAR values
2. **Hierarchical modules**: Module composition and refinement
3. **General temporal constraints**: Constructs beyond the sealed runtime catalogue in §12; the TVL 1.3 monitoring and response semantics themselves are specified there, not deferred

### 11.3 Verification

Connecting TVL to verification frameworks:

1. **Deployment verification**: Establish implementation and deployment evidence for the runtime semantics in §12
2. **Invariant checking**: Prove optimizer preserves feasibility
3. **Optimizer profiles**: Separately specified, algorithm-specific guarantees on exploration efficiency

---

## 12. Runtime Semantics (TVL 1.3)

| | |
|---|---|
| **Status** | **Accepted** 2026-10-21 with RFC 0003; design decisions D1–D5 recorded 2026-10-16 (RFC 0003 §16.1) |
| **Target language version** | TVL 1.3, conservative extension of TVL 1.2 |
| **Semantic layers** | Requirements → unit predicates on complete histories → window verdicts → episodes and obligations → declared responses |
| **Defined here** | The meaning of runtime declarations on complete histories, the meaning of every parameter, and the contract each verdict, episode, obligation state and response effect must satisfy |
| **Not defined here** | How an evaluator decides from partial, unordered or late evidence, which partial-evidence conditions leave a window undecided and in which order, how it accounts for units it cannot classify, how committed sampling selects and commits, how it tracks episodes and obligations over time, and how a controller executes and arbitrates responses. These belong to an evaluator profile outside TVL (Definition 12.7) |
| **Guarantee boundary** | Conditional statements in §12.14 about the language and about exact binomial tests; no claim of completed mechanization, conformance, or production enablement |

Definitions in this section extend, rather than replace, §§2–9. The three optional blocks are `requirements`, `monitors`, and `responses`. A requirement states a property; a monitor binds it to evidence and a decision method; a response declares allowed reactions. Runtime declarations inhabit a separate typing context `Γ_rt` and never enter the TVAR context `Γ`, `Config(Δ,E_τ)`, `F^str`, the SMT encoding, or ε-dominance. Write `erase(M)` for the otherwise unchanged legacy semantic module after removing these extension blocks (§12.13). General temporal logic is a mathematical interpretation device, not additional surface syntax.

TVL is a specification language. This section says what a requirement means on a unit's complete history and what each verdict promises. Verdicts themselves are produced by an evaluator profile outside TVL, which must meet the contracts stated here. TVL's own tools validate, compose and compile declarations; the only verdicts they compute are those of the release gate (Definition 12.16), which decides promotion monitors from complete counts and defers everything else.

### 12.1 Runtime Domains and Well-formedness

**Definition 12.1 (Runtime domains)**.

```
Class       = {sat, vio, unres}
Population  = {true, false, unknown}
Verdict     = {MET, BREACHED} ∪ {UNKNOWN(r) | r is a closed reason code}
ReqKind     = {rate_bound, zero_tolerance, recovery_time, evidence_liveness}
UnitKind    = {trace, invocation}
Phase       = {promotion, runtime}
Method      = {clopper_pearson_rational_v2, clopper_pearson_exact_v1, exact_count_v1}
```

`excluded` is a selection outcome, not a fourth classification. Write a unit as `v` to distinguish it from unresolved count `u`; write confidence as `c_conf` to distinguish it from configuration `c`. All decimal parameters in the rational method denote exact members of `ℚ`. Counts are natural numbers; durations are nonnegative rational multiples of a declared time unit. Runtime names, checker labels, and correlation keys are distinct from TVAR values.

Surface syntax, syntax-level closed enums and lexical constraints are normative in [RFC 0003](rfc-0003-runtime-requirements-monitors-responses.md), including status, severity, code identifiers, fingerprints, labels, SDK version strings, and checker registries. This section interprets their parsed semantic values rather than defining competing syntax. A response rule's event selector is its `trigger` field; a protocol transition's event selector is its `when` field (RFC §4.1). Diagnostic codes are defined only by RFC §5; Appendix B.4 supplies cross-references for codes explicitly named here.

**Definition 12.2 (Well-formed runtime contract)**. `WF_rt(M)` requires finite, uniquely named declarations, correctly typed references, acyclic monitor dependencies, deterministic selectors/checkers under their declared contracts, and the following compatibility table.

| Requirement | Evidence source | Phase | Decision method |
|---|---|---|---|
| `rate_bound` | `backend_trace_metadata` with `backend_v1`; `customer_side`; `evaluation_set` | runtime, or promotion with `evaluation_set` | rational `_v2`, or float `_v1` only with `backend_v1` |
| `zero_tolerance` | `customer_side`; `evaluation_set` | runtime, or promotion with `evaluation_set` | `exact_count_v1` |
| `recovery_time` | `episodes` | runtime | `exact_count_v1` |
| `evidence_liveness` | `windows` | runtime | `exact_count_v1` |

For a rate monitor, `0 < θ < 1`, `0 < α_w ≤ 1`, `0 ≤ c_conf ≤ 1`, `0 ≤ f ≤ 1`, and `min_samples ≥ 1`; a profile may impose narrower domains. `θ` is the maximum violation rate and `f` is `max_unresolved_fraction`. Episode parameters satisfy `K ≥ 1` and positive closure age. Recovery deadline `T` and liveness allowance `L` are positive integers in their declared units. Resource limits are positive and part of the compiled contract. Unsupported domains or missing evidence contracts are refused, never interpreted by an unspecified default.

`zero_tolerance` restricts its violation predicate to `exact_pred`; `rate_bound` may use a metric, exact pattern, or checker predicate. `backend_v1` fixes `rate_bound`, `unit: trace`, metric `wall_clock_latency_ms`, `source: backend_trace_metadata`, `method: clopper_pearson_exact_v1`, `sampling: unverified`, and the hosted latency profile's parameter domains and defaults; it forbids `among` and `threshold_factor`. It is not a synonym for the rational profile. A checker runs customer-side, including when evaluating an evaluation set. `single_producer: true` declares that every event of a unit is emitted by one producer; a unit that contradicts the declaration is not classified on its strength. A protocol is a finite deterministic automaton with declared handling of unlisted transitions. `trigger.hours` is present iff the trigger is `episode_open_for`; the referenced monitor must emit the selected event.

### 12.2 Units, Events, and Complete Histories

**Definition 12.3 (Units)**. A unit is what a requirement counts. Its kind is declared by `unit`:

- **`trace`**: one end-to-end handling of one request by the agent's deployment, recorded as one trace: from receipt of the request to the final response, including every model call, tool call and handoff made for it, in every component that contributes to it.
- **`invocation`**: one execution of the monitored agent itself: one call of its entry point, from receiving its input to returning its output, including the calls it makes.

A trace contains one or more invocations; when the agent is called once per request the two coincide. A requirement's counts and rate are over units of its declared kind, and `unit` is part of requirement identity (§12.12): a trace requirement and an invocation requirement with the same predicate are different requirements. Each unit has metadata: agent key, deployment environment label, start time, end time, final status, and the metric values of RFC §4.1 (`wall_clock_latency_ms` is end time minus start time). `episode` and `window` are the lifecycle units of obligation requirements (§12.9).

**Definition 12.4 (Events)**. The closed event alphabet `agent_trace_v1` is

```
{unit_start, unit_end(status), tool_call(tool), tool_result(tool,status),
 model_call, handoff, error(class), authorization_granted(ref), authorization_revoked(ref)}.

e = (producer, sequence, type, time, unit_id, correlation_id?, tool_call_id?, causal_parent?, fields)
```

| Event | Marks |
|---|---|
| `unit_start` | the unit begins |
| `unit_end(status)` | the unit ends; `status` is its final status, one of `completed`, `failed`, `rejected` (`running` is not final) |
| `tool_call(tool)` | the agent requests the tool `tool`, a code identifier (function, module or qualified name); carries the call's `tool_call_id` |
| `tool_result(tool,status)` | the result of a tool call returns with `status`; carries the same `tool_call_id` as its call |
| `model_call` | the agent calls a model |
| `handoff` | the agent hands control to another agent or to a person |
| `error(class)` | an error occurs; `class` is local-only metadata, not selectable and not exported |
| `authorization_granted(ref)` | an authorization of kind `ref` is granted inside the unit, for example a payment authorization or a user consent |
| `authorization_revoked(ref)` | an authorization of kind `ref` is withdrawn |

Events are emitted by the agent's customer-side instrumentation: an SDK, the agent framework, or the agent's own code. A **producer** is one emitting component with its own increasing sequence numbers; `(producer, sequence)` identifies an event. `time` is the producer's timestamp in milliseconds. `causal_parent`, when the producer knows it, identifies the event that caused this one; it records cause, not time. Hosted metadata monitors read no events (§12.5).

- **`ref`** is an identifier the author chooses for a kind of authorization; the instrumentation stamps it on the matching grant and revocation events. A selector with `ref` matches only events carrying that ref.
- **`correlation_id`** is an optional identifier the instrumentation stamps on the events of one logical transaction inside a unit (one payment, one booking). **`tool_call_id`** identifies one tool call and is carried by that call and its result.
- **`correlate_by`** ∈ {`unit`, `correlation_id`, `tool_call_id`} (default `unit`) selects the key under which a predicate matches events: two events match only if they carry the same key. Under `unit` every event of the unit has the unit's key. An event that lacks the selected key matches no event under any key.

A selector `s` tests the declared event type and optional tool/status/ref fields, subject to RFC §4's applicability rules: `tool` applies only to `tool_call`/`tool_result`, `status` only to `unit_end`/`tool_result`, and `ref` only to `authorization_granted`/`authorization_revoked`. A selector with `event: error` matches the event type only.

**Definition 12.5 (Complete history)**. The complete history `h` of a unit is its full, finite sequence of events in execution order — the order in which they actually happened, a total order — together with its metadata and, for each checker predicate position (`among` or `violation`), the label the checker returned for that position. Write `before_h(a,b)` when `a` precedes `b` in `h`. Unit predicates (§12.3) are defined on complete histories. An evaluator usually observes less than the complete history: events may be missing, late, or unordered across producers. What it may conclude from such evidence is governed by the classification contract (Definition 12.8), not by the predicates themselves.

### 12.3 Complete-History Unit Predicates

**Definition 12.6 (Violation predicates)**. For a complete history `h`, `V_q(h) ∈ 𝔹` denotes violation of requirement predicate `q`. Event sets below use matching correlation keys. A metric/checker value must be present, resolved, and valid under its declared source contract.

| Predicate `q` | `V_q(h) = true` iff |
|---|---|
| `metric m exceeds ℓ` | the resolved metric `md_h.m > ℓ` (strict inequality) |
| `absence(a)` | at least one event matches `a` |
| `bounded_existence(a,B)` | more than `B` distinct events match `a` |
| `precedence(a,b,mode,correlate_by)` | no legal authorization assignment exists for all matching `b` events, as defined below |
| `bounded_response(a,b,Δ,correlate_by)` | no legal one-to-one timely response assignment covers all matching `a` events |
| `protocol(DFA)` | an ordered run reaches a rejecting state, or ends outside the accepting states |
| `checker id label_in Λ` | the label returned by checker `id` for the `violation` position belongs to `Λ` |

A legal precedence assignment maps each matching `b` to a matching `a` of the same correlation key with `before_h(a,b)`, such that `a` is not revoked before `b`. A **revocation** matches a grant iff it is an `authorization_revoked` event with the same `ref` and the same correlation key as an `authorization_granted` event and occurs after it; it revokes every such earlier grant for every later `b`. A revocation affects only `authorization_granted` events: when the `a` selector names another event type, revocations do not apply. `single_use` (default) requires an injective assignment: an `a` can authorize at most one `b`. `reusable` drops injectivity; a reusable grant remains available until revoked. A consumed single-use grant is not restored by a later event.

A legal bounded-response assignment is an injective map from matching `a` events to matching `b` events of the same key, with `before_h(a,b)` and `0 ≤ t_b − t_a ≤ Δ`. A response exactly at the deadline counts. One response cannot discharge two obligations. Both predicates ask whether some assignment exists; neither depends on a particular matching order.

For a DFA `(Q,Σ,δ,q₀,F,R)`, project onto its declared alphabet in execution order and iterate `δ`. `R` is rejecting and absorbing for violation detection. For an unlisted `(state,event)` pair within the alphabet, extend `δ` to an implicit rejecting sink by default, or to the same state when `unlisted: ignore` is declared. Events outside the alphabet are not transitions. Overlapping selectors that make a transition ambiguous fail well-formedness.

The population expression `among` is interpreted as a membership test `A_q(h)`. In 1.3 `among` is always a checker predicate (RFC 0003 §16.3 question 20; a metric or exact predicate there is `runtime_among_not_checker`): for a checker predicate in the `among` position, `A_q(h)` holds iff the label returned for that position belongs to its `label_in`. For example, `among: {checker: C, label_in: [must_refuse]}` selects that label, while a violation label `[complied]` is tested separately, in the `violation` position. Omitted `among` means `true`. A checker returns, for one unit and one position, exactly one label of its declared list or no result; with no result the predicate has no truth value on that unit, and an evaluator cannot classify it (Definition 12.8).

**Prefix-fixed violations.** The violations of `absence`, `bounded_existence`, `precedence` and a `protocol` reaching a rejecting state are fixed by a finite prefix of the history: once a prefix violates, every extension violates. The violations of `bounded_response`, a `protocol` ending outside its accepting states, a metric threshold and a checker label are not; they depend on the whole unit. Only prefix-fixed violations can be acted on before an effect (§12.10).

### 12.4 Unit Classifications and Evaluator Profiles

**Definition 12.7 (Evaluator profile)**. An evaluator profile is a named, versioned specification, outside TVL, of a procedure that turns observed evidence about the units of a compiled contract into unit classifications, window verdicts, episode and obligation states, and response directives. Monitors select an evaluator profile through their declared method, evidence source and `profile`. TVL does not specify these procedures. It fixes the contracts below, which every conforming evaluator profile must meet; an evaluator that cannot meet them for some evidence returns `unres` or `UNKNOWN(r)` for it. TVL's public tools contain one minimal evaluator, the release gate of Definition 12.16.

**Definition 12.8 (Classification contract)**. For a unit `v` with complete history `h`, an evaluator's classification is a claim about `h`:

```
classify(v) = vio       ⟹  A_q(h) ∧ V_q(h)
classify(v) = sat       ⟹  A_q(h) ∧ ¬V_q(h)
classify(v) = excluded  ⟹  ¬A_q(h)
classify(v) = unres     asserts nothing.
```

The evaluator usually has not observed all of `h`; each claim must hold whatever the unobserved part of `h` is. Thus a missing event never establishes satisfaction, and a missing response never establishes a violation. A unit whose population membership is unknown is `unres`. An excluded unit contributes to neither `n`, `k` nor `u`. A unit whose events exceed a declared resource limit (`max_active_obligations`, `max_tracked_correlations`) need not be classified and is then `unres`.

A local guard (`block_action`, `halt_unit`) acts on a unit only when, before the effect it would prevent, the evaluator has established `A_q(h)` and a prefix-fixed violation of `q` (§12.3) on events that are already part of the unit. When it cannot establish both at that moment, the rule's declared `on_check_error` decides. A guard never acts on a unit with `A_q(h)` false.

### 12.5 Windows, Populations, Sampling, and Report Counts

**Definition 12.9 (Windows and populations)**. A runtime window monitor evaluates fixed tumbling windows `w=[s,s+W)` aligned to multiples of `W` hours from UTC midnight; `due(w)=s+W+grace`. A unit is **attributed** to the monitor's agent by the declared rule; under `agent_key_exact_v1`, iff exactly one active agent in the monitor's deployment scope has the unit's agent key. Unattributed units belong to no window's `n`, `k`, `u` or `pl`; they are reported only as `unattributed`. An attributed unit in the monitor's environment belongs to the window that contains its start time. An attributed unit whose start time is unknown cannot be placed by start time and is **unplaceable** (`pl`); it is never counted as resolved. A window's **population** is its placed units for which `A_q` holds.

Hosted metadata monitors (`backend_v1`) read only unit metadata. Their violation predicate is wall-clock latency strictly exceeding the threshold. Classification is supplied by the evaluator profile (Definition 12.7), subject to the guarantees of Definition 12.8.

**Definition 12.10 (Sampling declarations)**. Selection operates on whole units before their outcomes exist, never on selected events of an otherwise unobserved unit. The closed sampling modes mean:

1. `unverified`: the hosted latency profile's census of ingested traces, with no assertion that upstream capture is independent of outcomes.
2. `head_sampled_declared(r)`: each unit is selected or not at its start, before its outcome exists, with probability `r`, and the decision is recorded on the unit. A unit selected after its outcome is known (tail sampling) contradicts the declaration; a window containing one is `UNKNOWN(sampling_biased)`.
3. `hash_bernoulli_committed_v1(r)`: each unit is selected with probability `r` by a selection that is committed before the window starts, depends on nothing about the unit's outcome, and can be checked after the window. The selection rule and its commitment belong to the evaluator profile; the mode is usable only where an evaluator profile supports it. Any secret input of the selection stays customer-side.

An omitted `sampling` on `customer_side` means census: every unit in scope is selected. A sampling rate below one is never census evidence. Fixed-list strata are separate monitors with separate allocations; there is no implicit pooling. Sampling supports rate claims under the stated model, not “always” or “never” prevention. Customer reports are `client_attested`; metadata recount and verified configuration attribution are different evidence qualifications.

**Definition 12.11 (Report counts)**. A customer-side window report (RFC §11.4.3) is bound to a contract digest, monitor reference, monitor revision and window, and states the counts

```
selected      attributed in-scope units that sampling selected (all of them for census)
reported      selected units the report accounts for
dropped       selected units the report does not account for
n             reported in-population units classified sat or vio;   k = those classified vio
u_reported    reported units classified unres (including unknown population membership)
pl            reported units that are unplaceable
excluded      reported units with A_q false
unattributed  units outside the attributed partition; in no other count
tail_sampled  reported units selected after their outcome was known (head_sampled_declared only)

selected = reported + dropped,      reported = n + u_reported + pl + excluded,      0 ≤ k ≤ n,
tail_sampled ≤ reported.
```

The identities are validity conditions on a report; a report that violates one is rejected (`runtime_report_conservation`). Each selected unit identifier counts once. Units the report does not account for, and units it reports as unresolved, are units the evaluator could not classify: under the verdict contract (Definition 12.13) they can never strengthen a verdict. How an evaluator profile carries them into its decision counts is its applied counting rule, not part of TVL.

### 12.6 Window Verdicts and Decision Methods

**Definition 12.12 (Exact binomial tails)**. For `N ∈ ℕ`, `0 ≤ j ≤ N`, and `p ∈ [0,1]`, define

```
b(N,p,i) = (N choose i) · p^i · (1−p)^(N−i)
T⁺(N,p,j) = ∑_{i=j}^N b(N,p,i)       (* upper tail, including j *)
T⁻(N,p,j) = ∑_{i=0}^j b(N,p,i)       (* lower tail, including j *).
```

Empty upper tails are zero and lower tails at or above `N` are one. Endpoints use `0^0=1`. For rational inputs every summand, sum, and comparison is rational; casting into real probabilities preserves the value. No inverse beta approximation or floating-point tolerance appears in `clopper_pearson_rational_v2`.

**Definition 12.13 (Verdict contract)**. A window verdict is a claim about the window's population. Write `p_w` for the window's violation rate under the declared model `iid_bernoulli_within_window_v1`: within one window, the population's units violate independently, each with probability `p_w`. The claims are:

| Kind and method | `BREACHED` promises | `MET` promises |
|---|---|---|
| `rate_bound`, `clopper_pearson_rational_v2` | if `p_w ≤ θ`, the probability that the window is `BREACHED` is at most `α_w`; over the `m` predesignated windows of a horizon, the probability of any false `BREACHED` is at most `α_FA` | if `p_w ≥ θ`, the probability that the window is `MET` is at most `1 − c_conf` |
| `rate_bound`, `clopper_pearson_exact_v1` | the hosted latency profile's floating-point computation of the same tests (Definition 12.14); no probability bound is claimed | as for `BREACHED` |
| `zero_tolerance`, `exact_count_v1` | at least one unit of the population violates (`V_q(h)` for some population unit) | the window's population was completely covered — census selection, every selected unit accounted for and classified, none unplaceable, every unit's history complete — it has at least `min_samples` units, and none violates |

`UNKNOWN(r)` promises neither, with a closed reason `r`. The rate claims assume sound classifications, outcome-independent selection, and that each window's violation count is stochastically dominated by `Bin(N,θ)` when `p_w ≤ θ` (and dominates it when `p_w ≥ θ`); IID Bernoulli units are a sufficient special case. `sampling: unverified` does not satisfy the selection assumption by its name. Units the evaluator could not classify never strengthen a verdict: the promises hold whatever their complete histories turn out to be.

Each window reason names why a window carries no verdict:

| Reason | Meaning |
|---|---|
| `late_evaluation` | the window was not decided within its lateness allowance: `2W` after `due(w)` (a decision at exactly `2W` is timely) |
| `revision_gap` | the hosted latency profile could not decide the window because a profile revision interrupted it |
| `insufficient` | the window has fewer units than `min_samples` asks for, or none |
| `unplaceable` | more of the window's units could not be placed by start time than `max_unresolved_fraction` tolerates |
| `unresolved` | more of the window's units could not be classified than `max_unresolved_fraction` tolerates |
| `sampling_biased` | selection contradicted the declared sampling (Definition 12.10) |
| `inconclusive` | the evidence supports neither verdict |
| `incomplete` | zero tolerance only: no violation is established and the window is not completely covered |

Which of these conditions an evaluator profile checks, how it measures them from partial evidence, and in which order it applies them relative to each other and to the tests of Definition 12.14 are that profile's, within the contract above.

Parameter meanings: `min_samples` is the smallest window, in units, that the author accepts as the basis of a rate verdict, and the smallest population for a zero-tolerance `MET`; a zero-tolerance `BREACHED` needs one established violation at any size. `max_unresolved_fraction` `f` is the largest share of a window's units that the author tolerates as unclassifiable, and separately as unplaceable. How an evaluator profile counts units against these two parameters, including whether unresolved units count toward `min_samples`, is its counting rule (Definition 12.7); under `backend_v1` it is the hosted latency profile's. `grace_minutes` is how long after the window's end evidence for it still counts; at `due(w)` the window's evidence is final, and evidence that arrives later never changes a recorded verdict. `horizon_days` `H` and `false_alarm_budget` `α_FA` fix the predesignated statistical looks: for `W` dividing 24,

```
m = 24H/W ∈ ℕ,  m≥1;      α_w = α_FA/m.
```

More generally the same bound requires a finite predesignated family with `∑_w α_w ≤ α_FA`. Promotion has one look (§12.7). Revisions, repeat evaluations, new strata, or new burn monitors cannot acquire an unaccounted statistical look. A horizon bound is not an infinite-lifetime bound; multiple monitors require a separately stated aggregate budget (e.g. the sum of their budgets).

**Definition 12.14 (Decision methods)**. The methods are named tests; their plain statistical meaning is:

- **`clopper_pearson_rational_v2`**: the exact one-sided binomial tests, in exact rational arithmetic. With `N` counted units of which `k` violate and every counted unit resolved, the window is `BREACHED` iff `k ≥ 1 ∧ T⁺(N,θ,k) < α_w` (the probability of at least `k` violations at rate `θ` is below `α_w`), otherwise `MET` iff `k < N ∧ T⁻(N,θ,k) ≤ 1 − c_conf` (the one-sided Clopper–Pearson upper confidence bound at confidence `c_conf` is at most `θ`), and otherwise `UNKNOWN(inconclusive)`. These are the tests of a window that is decided; which windows an evaluator profile leaves undecided with a reason of Definition 12.13 is that profile's. Equality of the upper tail with `α_w` is not a breach; equality of the lower tail with `1−c_conf` passes; the two conditions cannot both hold when `c_conf ≥ α_w`. When some counted units are unresolved, the evaluator profile applies its own counting rule, subject to the verdict contract.
- **`clopper_pearson_exact_v1`**: the same two tests as the hosted latency profile computes them, in IEEE-754 floating point through inverse beta functions. It is defined by that computation, not by ideal real arithmetic; the name `_exact_v1` is a stored method identifier, not a claim of exact machine arithmetic. The two methods can disagree at near-ties, and no theorem relates them.
- **`exact_count_v1`**: deterministic counting. For zero tolerance: `BREACHED` on one established violation; `MET` only on a completely covered window of at least `min_samples` units with none violating; otherwise `UNKNOWN(insufficient)` or `UNKNOWN(incomplete)`; a window not decided within its lateness allowance is `UNKNOWN(late_evaluation)`. A census-complete empty window is `UNKNOWN(insufficient)`, never `MET`: the language does not conclude `MET` from no traffic, so an idle or suspended agent cannot close a breach episode or satisfy recovery through empty windows. For obligation monitors the method decides the obligation state of Definitions 12.18 and 12.20.

**Burn monitors.** A burn monitor is a separate rational-method monitor on the same requirement, with independent schedule/allocation and `threshold_factor=b`, where `b>1`, `bθ<1`, and breach is reachable at `min_samples`. Its breach test uses `bθ` in place of `θ`; it has no `MET` test and no episode, so a window it decides without a breach is `UNKNOWN(inconclusive)`. `burn_breached` is emitted on the first window of each streak of adjacent `BREACHED` windows; any non-`BREACHED` window or missing adjacent decision ends the streak. A burn monitor never opens, continues, or closes a primary episode and is forbidden under `backend_v1`.

### 12.7 Promotion Monitors and the Release Gate

**Definition 12.15 (Promotion refinement)**. A promotion monitor evaluates the candidate on the named evaluation set once. It has no window, horizon, or episode; `m=1`, `α_w=α_FA`, default `min_samples=1`, default `max_unresolved_fraction=0`. A rate monitor uses the rational method; a zero-tolerance monitor uses the compatible exact-count method. Its counts come from `monitor_outcomes[monitor_name]={n,k,u,pl}` in the candidate measurement bundle, produced by the evaluation harness (RFC §11.4.2); a missing/invalid outcome cannot pass. Zero-tolerance `MET` additionally requires the explicit boolean field `monitor_outcomes[monitor_name].complete: true`, the harness's attestation that every evaluation-set unit is accounted for, together with `u=0`, `pl=0`, and `N≥min_samples`. Neither omitted nor false `complete` can establish `MET`, and `u=0 ∧ pl=0` does not supply a default completeness assertion. Runtime lateness and window guards do not apply. No incumbent `monitor_outcomes` are required by this candidate-only refinement.

Let `D₁₂` be the existing §9.7 decision on `erase(M)` and valid legacy evidence. Set `J(MET)=pass`, `J(BREACHED)=Reject`, `J(UNKNOWN(r))=NoDecision(r)`. After preserving validation errors, define

```
D₁₃ = Reject       if D₁₂=Reject or any promotion monitor maps to Reject
    = NoDecision   otherwise, if D₁₂=NoDecision or any maps to NoDecision
    = D₁₂          otherwise.

Promote₁₃ ⟺ Promote₁₂ ∧ ∀μ ∈ PromotionMonitors(M), verdict_μ=MET.
```

Thus any rejection dominates any inconclusive monitor. Passing all monitors does not turn an existing `NoDecision` into promotion. A module without promotion monitors has exactly §9.7's meaning. Chance constraints retain Definition 9.8 and their existing failure behavior; no chance constraint is deleted or silently replaced by a monitor on the same quantity (`chance_constraint_shadowed` is a warning). Promotion monitors are acceptability evidence, not additions to the objective vector or the dominance relation.

**Definition 12.16 (Release gate)**. The public release gate is the evaluator of TVL's own tools (`tvl-ci-gate`, `tvl-measure-validate`). It decides a promotion monitor only from complete counts, using the standard exact binomial tests, and defers everything else. For a valid outcome `{n,k,u,pl}` (natural numbers, `k ≤ n`; anything else is the readiness issue `missing_monitor_counts`), apply the first matching row:

| Order | Condition | Result |
|---|---|---|
| 1 | `u > 0` or `pl > 0` | `UNKNOWN(engine_required)` |
| 2 | zero tolerance and `complete` is not `true` | `UNKNOWN(incomplete)` |
| 3 | zero tolerance and `k ≥ 1` | `BREACHED` |
| 4 | `n < min_samples` | `UNKNOWN(insufficient)` |
| 5 | zero tolerance | `MET` |
| 6 | rate bound and `k ≥ 1 ∧ T⁺(n,θ,k) < α_FA` | `BREACHED` |
| 7 | rate bound and `k < n ∧ T⁻(n,θ,k) ≤ 1 − c_conf` | `MET` |
| 8 | otherwise | `UNKNOWN(inconclusive)` |

`engine_required` means that the counts contain unresolved or unplaceable units, which the release gate does not interpret; an evaluator profile that handles them may decide such a monitor. It is a release-gate reason, not a window reason. The rows are the rational and exact-count methods of Definition 12.14 restricted to `u = pl = 0`, with `max_unresolved_fraction` unused. The results join by Definition 12.15.

**Chance constraints and promotion rate monitors.** A 1.2 chance constraint with threshold `θ` and confidence `c` passes on `k` violations in `n ≥ 1` trials iff the one-sided Clopper–Pearson upper bound at confidence `c` is at most `θ` (Definition 9.8). By the beta–binomial identity this holds, in exact arithmetic, iff `k < n ∧ T⁻(n,θ,k) ≤ 1 − c`: at `u = 0` and matched confidence, a chance-constraint pass is exactly the promotion monitor's `MET` test on the same counts. (The chance constraint computes the bound in floating point, so the two can differ at exact ties.) The monitor returns `MET` when, in addition, `n ≥ min_samples` and its breach test, which is checked first, does not hold; the breach and `MET` tests cannot both hold when `c_conf ≥ α_FA`. The two differ in what failure means. The chance constraint maps every non-pass to `Reject`, whether the counts demonstrate a breach or are merely inconclusive. The monitor maps a demonstrated breach (`k ≥ 1 ∧ T⁺(n,θ,k) < α_FA`) to `Reject` and an inconclusive result to `NoDecision`. Example: `n = 10`, `k = 1`, `θ = 0.1`, `c = 0.95`, `α_FA = 0.05`. `T⁻(10, 1/10, 1) = 0.7360989291 > 0.05`, so neither passes, and the chance constraint rejects (its upper bound is about 0.394). `T⁺(10, 1/10, 1) = 0.6513215599` is not below `0.05`, so the monitor does not breach: it returns `UNKNOWN(inconclusive)`, which maps to `NoDecision`. Legacy behaviour is unchanged: chance constraints keep Definition 9.8, a module without promotion monitors gates exactly as before, and when both are present the chance constraint's `Reject` still wins the join.

---

### 12.8 Episodes

**Definition 12.17 (Episodes)**. An episode is the lifecycle of one breach of a primary monitor (per effective monitor key, RFC §9.4). An episode is open or closed, and it ends exactly once: its terminal outcome is `resolved` or `withdrawn`, never both. An episode ID is determined by the effective monitor key and the opening evaluation's immutable identity. Its events mean:

1. **`episode_opened`**: a breach began — the monitor had a `BREACHED` window while no episode of it was open. **`episode_continued`**: the open episode's breach persists — a further `BREACHED` window.
2. **`episode_resolved`**: the requirement has been shown met again: the episode resolves after `K` consecutive `MET` windows of its monitor, `K = closure_windows`, all of which ended within `closure_max_age_hours` of the evaluation that resolves it, so that old evidence never closes an episode. When composition tightens these parameters (§12.12), the tighter values apply.
3. **`episode_withdrawn`**: the requirement the episode measures was weakened (`requirement_weakened`) or retired (`requirement_retired`, `agent_retired`, `floor_removed`) while the episode was open. Withdrawal is never resolution.

`episode_open_for(h)` occurs once per episode, when the recorded opening time plus `h` hours is reached and the episode is still open. Timers, acknowledgement, or mute never resolve an episode. Closure freshness and lifecycle timestamps use evaluation time; the recovery deadline does not (Definition 12.18). How an evaluator profile tracks episodes from a monitor's window verdicts, revisions and retirements, and how windows evaluated under different parameters count toward closure, are that profile's (Definition 12.7). It never chooses a favourable history: when it cannot establish those records, it has no lifecycle evidence for the affected episodes.

### 12.9 Recovery and Evidence Liveness

**Definition 12.18 (Window-time recovery)**. `recovery_time(μ,T)` creates one obligation per episode of `μ`. Its ID is `(episode_id, recovery_requirement_ref)`. Let `e₀` be the end of the episode's opening window and `D=e₀+T`. `D` is a WINDOW-TIME deadline (design decision D5): the closing window must end within `T` hours of the opening window's end. It is not `opened_at+T`. The obligation states mean:

| State | Meaning |
|---|---|
| `RECOVERED` | the episode resolved, and its closing window ends no later than `D` |
| `OVERDUE` | the evidence establishes that the episode did not resolve with a closing window ending by `D`; missing or late evidence never establishes it |
| `CANCELLED` | the episode was withdrawn before the obligation was `RECOVERED` or `OVERDUE` |
| `PENDING` | not decided yet: evidence about the windows ending by `D` can still arrive in time |
| `UNKNOWN(lifecycle_unavailable)` | none of the above can be established from the available evidence |

`RECOVERED`, `OVERDUE` and `CANCELLED` are terminal: once established, the obligation keeps that state. How an evaluator profile establishes these states from window and lifecycle records, and how it records later lifecycle changes beside a terminal state, are that profile's (Definition 12.7). `recovery_recovered`, `recovery_overdue` and `recovery_cancelled` mark the obligation reaching that state. Project `RECOVERED↦MET`, `OVERDUE↦BREACHED`, and `PENDING`, `CANCELLED` and lifecycle unavailability to `UNKNOWN` with their reasons (`pending`, `cancelled`, `lifecycle_unavailable`). The terminality of `OVERDUE` does not authorize effects forever: a service effect still needs its originating episode open (§12.10).

Report `window_recovery_duration = closing_window.end−e₀` when resolution exists and, separately, `wall_clock_lifecycle_duration = closed_at−opened_at` when both timestamps exist. A cancelled episode has a withdrawal duration, not a recovery duration. Neither displayed duration substitutes for the state.

**Definition 12.19 (Recovery feasibility)**. With the composed required closure count `K_close`, the earliest possible closing window after the opening window ends at `e₀+K_close·W`. Therefore `recovery_deadline_impossible` holds iff `T<K_close·W`; equality is feasible in window time. This is only an earliest separation: closure also needs its windows to be fresh at the closing evaluation (Definition 12.17), so delayed evaluations can postpone or prevent closure and yield `OVERDUE` although the windows were `MET` in time. When an episode has enough consecutive `MET` windows to close but they are too old at an evaluation, that fact is reported as `closure_blocked_by_lag` beside the state; it does not change the state.

**Definition 12.20 (Evidence liveness)**. `evidence_liveness(μ,L)` is a health obligation over the due windows of `μ` since its activation; a floor-only monitor activates at first attributed traffic. A window is due when `now≥due(w)`; the due windows include windows for which nothing was recorded. A due window carries **usable evidence** when it was decided from evidence that arrived; a window decided `UNKNOWN(inconclusive)` from real units carries it, because liveness concerns evidence arriving, not the requirement being met. Absence of evidence is never usable evidence: a due window for which nothing was recorded, or for which no customer-side report arrived by `due(w)`, never carries it. Which other windows carry it is the evaluator profile's (Definition 12.7). `L` is how many consecutive due windows may lack usable evidence. The states mean:

| State | Meaning |
|---|---|
| `LIVE` | at least one of the last `L+1` due windows carries usable evidence |
| `STALE` | none of the last `L+1` due windows carries usable evidence |
| `UNKNOWN(insufficient)` | fewer than `L+1` windows are due |
| `UNKNOWN(awaiting)` | neither `LIVE` nor `STALE` can be established yet |

Project `LIVE↦MET` and `STALE↦BREACHED`. `stale` marks the monitor becoming `STALE`; `live_again` marks it being `LIVE` again after it was `STALE`. Liveness does not invent a behavioral breach episode; recovery, behavior, coverage, and monitor health remain separate quantities.

### 12.10 Responses: Declarative Meaning

**Definition 12.21 (Actions and approval levels)**. The sealed action set, its meaning and its minimum authority are:

| Rank | Action | Meaning | Approval |
|---|---|---|---|
| 0 | implicit record | the originating event is recorded; not declarable | — |
| 1 | `notify` | deliver an alert with the rule's `severity` | `none` |
| 2 | `open_next_step` | open a recommended next step for the people or coding agent who maintain the agent, toward restoring the requirement; it is withdrawn when the episode closes. Opening it changes nothing in production; acting on it is a separate action with its own authority | `none` |
| 3 | `optimize` | start a bounded optimization of the agent's configuration; with `deploy: if_promoted` (default `never`), also deploy its candidate as a separate service effect (below) | `standing` or `human`, for each effect separately |
| 3 | `rollback` | redeploy the `target` configuration, which must be eligible now (Definition 12.24) | `standing` or `human` |
| 4 | `throttle` | lower the deployment's admission rate to at most `rate_floor` times its unthrottled admission rate | `standing` or `human` |
| 4 | `degrade` | route new work to the certified `fallback` configuration, which must be eligible now | `standing` or `human` |
| 5 | `suspend` | stop admitting new units and drain existing work under `fallback` (`static_unavailable` or `route_to_human`); requires an open episode with at least one `BREACHED` window and an escalation event | per-episode `human`, always |
| local | `block_action`, `halt_unit` | in-process, before the effect: suppress the violating event, or stop the unit (§12.4) | `none` |

Ranks describe impact, not permission to execute an undeclared intermediate rung. Repair alternatives share a rank. `rate_floor` is a fraction in `(0,1)`: a smaller value throttles harder. `block_action` and `halt_unit` act only on prefix-fixed violations of `absence`, `bounded_existence`, `precedence` or `protocol` (§12.3); metric, bounded-response and checker results do not authorize them, and neither authorizes a service-wide suspend. Every local guard declares `on_check_error ∈ {block,allow}`.

Authority levels are ordered `none < standing < human` for refinement, subject to each action's mandatory minimum. `none` means the installed contract itself permits the narrowly specified action, not that every effect is unrestricted. A **standing grant** is an owner-signed authority record outside TVL documents, bound to the agent, the current contract digest, the controller, a target scope and quantitative limits (occurrences and, for `optimize`, cost), with an expiry at most 30 days after issuance (design decision D2). Each occurrence, including each repeat, must fit its remaining limits; a retry of one occurrence does not consume it again. Human authorization is specific to the action and scope. A suspend requires a human approval for its episode even if a standing grant exists. A resume is a human control transition, not a declarable response action.

**Definition 12.22 (Triggers, scopes, and occurrences)**. The only alert events are

```
episode_opened, episode_continued, episode_open_for(h), episode_resolved,
episode_withdrawn, recovery_overdue, recovery_cancelled, recovery_recovered,
burn_breached, stale, live_again, unit_violation.
```

`unit_violation` occurs when a unit with `A_q(h)` true is established as violating a prefix-fixed predicate. Each event belongs to a **scope**, the thing whose state it reports:

| Event family | Scope |
|---|---|
| episode | the episode |
| recovery | the recovery obligation `(episode ID, recovery requirement ref)` |
| burn | the burn monitor's current `BREACHED` streak, identified by its first window |
| liveness | the liveness monitor's transition window |
| unit | the monitor and the SDK unit identifier |

Each response rule has an immutable `rule.id`, unique in its response revision. A rule's first firing in a scope is occurrence 0; each `repeat_after_hours` firing is a new occurrence, measured in lifecycle time, only while the scope is active, at most `max_repeats` times. Further deliveries of the same trigger, and retries of one occurrence, are the same occurrence. Repeating effectful actions require a finite `max_repeats`.

**Definition 12.23 (Effect authority)**. `notify` has **event authority**: its recorded event authorizes delivery after the scope closes, including resolved, withdrawn and recovered notifications and notifications from an older response revision. It requires neither an open scope nor a standing grant. Acknowledgement or mute affects delivery only.

Every other remote action has **service-effect authority**: at the time of its effect, its rule must still exist in the current response revision, its contract must be current, its approval must be valid, and its originating scope must still require intervention:

| Scope | Still requires intervention iff |
|---|---|
| episode | the episode is open |
| recovery | the obligation is not `RECOVERED` or `CANCELLED` (`OVERDUE`, `PENDING` and `UNKNOWN` qualify) **and** its episode is still open |
| burn | the `BREACHED` streak persists |
| liveness | the state is still `STALE` |
| unit | never, for a remote service effect: a unit event authorizes only `notify` and the local guards |

A service effect that has not taken place when its scope closes or its response revision changes never takes place. Terminal recovery and liveness events can notify, but cannot create a new service-effect scope.

**Deploying an optimize candidate.** An `optimize` rule with `deploy: if_promoted` declares a second service effect of its episode scope, the deploy (RFC §7.6). A deploy occurrence is `(response, rule.id, episode, j, fp)` for optimize occurrence `j` and candidate fingerprint `fp`, at most one per optimize occurrence (rule IDs are response-local). Its authority is its own: a human approval of that occurrence, or a standing grant that names the deploy of this rule; authority for the optimization is not authority for the deploy. Either way the occurrence is bound, before the effect and for all its retries, to `fp`, the gate-result digest, the contract digest and the deployment precondition. It takes place only if, at the time of the effect, the service-effect conditions above hold for the episode (rule and `deploy: if_promoted` still current, contract current, authority valid, episode open), `fp` came from an optimize occurrence of this rule in this episode, the promotion join of Definition 12.15 over `fp`'s measurement bundle under the current contract is `Promote` (the module has a promotion monitor on the trigger's requirement), `fp` did not breach in an open episode, and the bound deployment precondition still holds when the deploy is written (checked atomically); otherwise nothing is deployed. Unreachable authority or promotion records hold it. A deploy is a repair attempt, not resolution: it never counts toward episode closure (Definition 12.17) or a recovery obligation (Definition 12.18); only production windows close the episode. A unit guard is the local exception: it acts on its installed rule and current evidence, without a reachable remote authority.

### 12.11 Controls, Eligibility, and Release

**Definition 12.24 (Target eligibility)**. A certified fingerprint `fp` is eligible as a rollback target or degrade fallback at the time of the effect iff its certificate is valid, unrevoked and fresh then, it is **configuration-attributed** (an agent-scoped certificate is insufficient), it establishes the current composed requirements, its environment and dependencies are compatible, it is not a configuration that breached in a currently open episode, and the customer's configuration store holds a configuration whose hash is `fp`. Store membership alone is not eligibility. A `last_certified` target resolves, at the time of the effect, to the certificate with the latest certification time for this agent; if that target is ineligible, the effect is held and a notification is raised — no other fingerprint is substituted. Rollback is a repair attempt, not episode resolution; its undo is a new promotion, not blind restoration of the previous fingerprint. An unfinished optimization may be cancelled, but spent resources are not undone.

**Definition 12.25 (Active controls and release)**. Effective controls are combined per type, not by taking a maximum action rank:

1. **Suspend**: admission is stopped while ANY suspend is active. Resolution, withdrawal, a response revision, disconnection, or recomputing other controls never removes it. Resolution OR withdrawal of the originating episode makes a human `resume` eligible; neither releases the suspend. Each release requires an authorized human resume; other active suspends keep admissions closed.
2. **Throttle**: the effective `rate_floor` is the minimum over the active throttles, or the unthrottled rate if none remains.
3. **Degrade**: new work is routed only to a fallback that is eligible at the time of the effect (Definition 12.24). How a controller arbitrates between active degrades that name different fallbacks is its evaluator profile's (Definition 12.7); no arbitration routes work in a way that violates another active obligation.
4. **Rollback**: each rollback redeploys a target that is eligible at the time of its effect (Definition 12.24); how a controller orders several pending rollbacks is its evaluator profile's. A completed rollback does not assert that the breached requirement recovered.

Only an authorized human may release a throttle or degrade; release recomputes the effective control from the controls that remain. Scope closure, grant expiry or an eligible route never releases a control. Release of one control never neutralizes another still-active control. A conflict does not itself authorize a suspend; the suspend preconditions and human gate still apply.

**Hold when unreachable (design decision D2)**. While remote authority — the controller, an approver, or grant verification — is unreachable, no new service-level effect and no release starts. Applied controls stay applied; an active suspend stays active. Installed local `block_action`/`halt_unit` guards continue, and notifications may be recorded locally. A pending next step or optimization waits. Unreachability never supplies human approval or an automatic suspend or resume.

No declared action is silently inert: a platform that cannot execute a declared action refuses the registration that declares it (`response_action_unsupported`). Registration is outside TVL (RFC §12).

### 12.12 Refinement, Meet, Reachability, and Packs

**Definition 12.26 (Refinement order)**. Write `A ⊑_rt B` to mean A is at least as strict as B, after canonical name/effective-key resolution under RFC §9.4, including pack-to-module reference rewriting and retained floor provenance. Compatibility first requires identical predicate, unit, population expression, evidence source, `deployment_environment`, attribution rule, `resolution`, decision method, `decision.model`, `threshold_factor`, and schedule. Schedule includes alignment, window width, grace, horizon and false-alarm allocation. Sampling mode/rate, single-producer, checker/DFA and resource-limit contracts must be identical unless a separate verified refinement rule exists; this revision supplies none. Changing an immutable component is an incompatible replacement, not an ordered numeric update.

For compatible entries the coordinate orders are:

| Field | Condition for `A ⊑_rt B` | Raw meet coordinate |
|---|---|---|
| `max_rate` | `θ_A ≤ θ_B` | minimum |
| `confidence` | `c_A ≥ c_B` | maximum |
| `min_samples` | `a_A ≥ a_B` | maximum |
| `max_unresolved_fraction` | `f_A ≤ f_B` | minimum |
| `closure_windows` | `K_A ≥ K_B` | maximum |
| `closure_max_age_hours` | `age_A ≤ age_B` | minimum |
| `within_hours` | `T_A ≤ T_B` | minimum |
| `max_stale_windows` | `L_A ≤ L_B` | minimum |

For responses, A must retain every base rule of B under the same `rule.id`, trigger, action, target, fallback, rate floor, and `on_check_error`; approval cannot weaken, repeat bounds cannot widen, and on `optimize` rules `deploy` cannot widen: it is ordered `never` stricter than `if_promoted`, with absent normalized to `never`. Standing grants are not TVL declarations, so refinement never compares them. On `notify` rules, severity is a coordinate ordered `info < warning < critical`, with absent severity normalized to `critical` before comparison (RFC §4.6). Require `severity_A ≥ severity_B`; lowering is rejected after default filling, including when either side omits severity. Non-`notify` rules have no severity coordinate. Additional rules must themselves be well-formed. `repeat_after_hours` is immutable in this revision; a retained `max_repeats` may only decrease, and no repeat is added to a rule that had none. An omitted mandatory base rule is not an empty or more permissive override. Equal names with different immutable fields fail composition rather than creating parallel conflicting definitions.

**Definition 12.27 (Partial composition)**. On compatible coordinates the raw meet `A ⊓ B` takes the table's bounds, unions declarations/rules by canonical identity, takes the stronger required approval, takes `never` as the `deploy` of each compatible retained `optimize` rule unless both sides have `if_promoted`, takes the maximum normalized severity on each compatible retained `notify` rule, and takes the smaller `max_repeats` of each compatible retained rule. Cross-namespace/effective-key collisions are rejected. The raw meet is the greatest lower bound in this product order, before feasibility validation:

```
A ⊓ B ⊑_rt A,     A ⊓ B ⊑_rt B,
(C ⊑_rt A ∧ C ⊑_rt B) ⇒ C ⊑_rt A ⊓ B.
```

Validated `compose(A,B)` is defined iff the compatible raw meet is well-formed and passes all mandatory reachability checks. These require the method-specific domain and mandatory power checks, each action's minimum approval, every reference, and, for each episode/recovery pair, closure freshness reachability and `T≥K_close·W`. A power warning under `backend_v1` does not invalidate an otherwise valid profile or meet. In the inherited fixed-window closure contract, in hours/minutes,

```
60·closure_max_age_hours ≥ 60·closure_windows·W + grace_minutes + 60.
```

This is the hosted latency profile's guard, not a promise that delayed evaluations will close an episode. A composed max closure count and min age can fail it even when both inputs pass individually.

For a primary runtime rate monitor, test `MET` reachability at `N=min_samples` with `k=0` and every unit resolved. For the rational method this is `(1−θ)^N ≤ 1−c_conf` with `N≥1`; the float profile uses its own computation, not a rational substitution. Failure emits `runtime_met_unreachable_at_min_samples`: a **warning** under `profile: backend_v1`, an **error** otherwise (RFC §5.5). The warning preserves valid legacy profiles even when their minimum-sized windows cannot establish `MET`. Breach reachability at that count is `θ^N<α_w` for the rational method; report `runtime_breach_unreachable_at_min_samples` as a warning if it fails on a primary monitor, using the method's own computation for the float profile. Burn escalation requires breach reachability at `bθ` and fails its burn validity check otherwise. These minimum-sample power lints do not apply to promotion monitors. Tightening is validated again after meet; a failed mandatory check rejects composition rather than weakening a bound. Whether a platform can execute the composed declarations is a registration question outside TVL (RFC §12), not part of validated composition.

A `tvl_pack` is a separate TVL 1.3 document containing pack identity, requirements, tenant-floor monitors, and optional responses, without dummy TVARs, objectives, or evaluation sets. Only pack monitors may declare `applies_to: tenant_floor`; ordinary module monitors apply to the agent. Activated, digest-bound packs compose with agent declarations by the same compatible meet. An agent overlay cannot weaken or delete a floor. A standalone composed module is rejected with `tenant_floor_outside_pack` only if it carries a tenant-floor monitor without floor provenance. An all-paired composition containing only agent-scoped monitors may validate as an ordinary module; source bytes alone neither reveal composition nor establish pack activation (RFC §9.4). Floor-only monitoring starts at first attributed traffic; retiring a floor is a retirement with reason `floor_removed` (Definition 12.17). Activation is an authorized registration operation, not an effect inferred merely from parsing a file.

### 12.13 Hosted Projection and Module Denotation

**Definition 12.28 (Closed projection)**. Let `Π_host` project a local runtime contract using an available per-tenant token map. The map must consistently preserve identity and joins; it is not a pass-through for customer-chosen strings. Export ONLY:

| Local field | Hosted representation |
|---|---|
| requirement/monitor/response/rule names, protocol states, module/pack module names, selector `ref` | opaque locally minted references |
| suspend fallback | closed enum `static_unavailable` or `route_to_human` |
| degrade fallback / rollback target | certified fingerprint or `last_certified` |
| customer labels in `label_in` / `among` | indices in the declared checker label list |
| customer checker ID | keyed commitment `customer:<commitment>`; catalogue IDs retain their catalogue identity |
| environment label | opaque environment reference, resolved only at the authorized read edge |
| selector tool names | validated code identifiers |
| numbers, enums, event types, method/sampling names | closed values; exact parameters serialized as decimal strings |

Anything unlisted is not exported. Unit IDs in reports/commitments must be SDK-minted opaque IDs, not arbitrary supplied names. Digests over contracts are computed after projection/tokenization, never used as an excuse to hash and export arbitrary raw content. An unresolved alias or unavailable token map fails closed (`runtime_unresolved_alias`); errors are closed codes without echoing inputs. Reports carry only closed counts, references, method/version identities, and commitments. Customer content/checkers remain customer-side. Only metadata monitors read observability data, and observability carries no privacy guarantee. This is a required data boundary, not a claim that a particular wire implementation has passed its canaries.

**Definition 12.29 (Erasure and denotation)**. `erase(M)` deletes only `requirements`, `monitors`, and `responses` and their extension-specific annotations, yielding the otherwise identical TVL 1.2 semantic module. A version label is administrative; erasure does not rewrite a TVAR, objective, chance constraint, band, policy, composite, or evaluation binding. The meaning of a module is

```
⟦M⟧₁.₃ = ⟨ Gate_M, Req_M, Resp_M ⟩
  Gate_M = ⟦erase(M)⟧₁.₂ with promotion refined by §12.7
  Req_M  = for each runtime monitor μ, the relation between complete unit histories and the
           verdict, episode and obligation records that satisfy the contracts of §§12.4–12.9
  Resp_M = for each history of recorded events, the response effects permitted by §§12.10–12.11
```

`Req_M` and `Resp_M` are specifications, not programs: an evaluator profile realises them, and its outputs at every finite prefix may depend only on evidence received by then and on explicit clock inputs. A missing future report is not evidence already received. Compilation into `tvl-runtime-contract/1` and `tvl-runtime-local/1` (RFC §11.5) is a declaration projection: it preserves the normalized declarations, their identities and their hosted forms, and installs, enables or runs nothing.

The **conservative-extension claim** is equality of the legacy projection with `⟦erase(M)⟧₁.₂`; an embedded 1.2 module has no runtime declarations and exactly its prior promotion decision. Runtime-only declarations do not alter legacy promotion. Opt-in promotion monitors restrict promotion as in §12.7, never redefine §9.7. Unsupported extension constructs are refused, not erased by an older reader. A document using 1.3 constructs requires explicit `tvl_version: "1.3"`; omission is diagnosed with `runtime_version_required`, while an explicitly incompatible declaration is diagnosed with `declared_version_below_constructs` (RFC §5). Omission on legacy modules retains legacy version handling. No change to legacy construct detection is part of this denotation.

---

### 12.14 Theorem Statements and Explicit Limits

The numbered statements below are **claimed proof obligations** about the language and about exact binomial tests, not declarations that Lean files compile or that any implementation satisfies them. `proofs/PROOF_SUMMARY.md` is the authority for each statement's proof status. Obligations about how an evaluator profile meets the contracts of §§12.4–12.11 — the soundness of its classification and counting rules, its episode and obligation procedures, and its response execution — are stated with that profile, outside TVL. Every statement assumes the relevant `WF_rt` conditions.

For statistical statements require `N∈ℕ`, `θ,α,c_conf∈ℚ`, `0<θ<1`, `0<α≤1`, `0≤c_conf≤1`. A true rate `p` may be real with `0≤p≤1`. Under a binomial model, a Lean representation uses the nonnegative real cast of `p` (e.g. `p_nn : NNReal` with real value `p`) and a proof `p_nn≤1` for `PMF.binomial`; rational thresholds/budgets are cast without rounding. Tail probabilities can then be expressed as finite sums of PMF masses, cast from `ENNReal` to real using finiteness. This describes the required mathematical types, not an unverified pinned-library API signature.

Write `X ≤st Y` for first-order stochastic domination on natural counts: `∀j, Pr[X≥j]≤Pr[Y≥j]`. A count `K` is a **good window** for `(N,θ)` when `K ≤st Bin(N,θ)` and a **bad window** when `Bin(N,θ) ≤st K`; IID Bernoulli units with `p≤θ` (respectively `p≥θ`) suffice. For random `N`, require these conditions for each conditional law given `N`, not just an unconditional marginal. No independence between different windows is required below.

1. **Theorem 12.1 — `conservative_extension` (claimed)**. For every well-formed TVL 1.2 semantic module `M₁₂`, embed it with empty runtime blocks as `ι(M₁₂)`. For every valid legacy evidence bundle `Y`, `D₁₃(ι(M₁₂),Y)=D₁₂(M₁₂,Y)`, and its runtime declarations are empty. More generally, if `PromotionMonitors(M)=∅`, the legacy component of `⟦M⟧₁.₃` equals `⟦erase(M)⟧₁.₂` on every such `Y`.

2. **Theorem 12.2 — `structural_projection` (claimed)**. For every `WF_rt(M)`, environment `E_τ`, configuration `c`, and admissible §8 encoding parameters `(P,idx)`, the TVAR context, configuration domain, `F^str(c,·)`, `F^op(E_τ,·)`, and structural encoding of `M` are identical to those of `erase(M)`. Runtime names do not occur in `Γ` or generated structural variables.

3. **Theorem 12.3 — `promotion_refinement`, `join_promote_iff`, `join_empty` (claimed)**. For the join of Definition 12.15: `Promote₁₃ ⟺ Promote₁₂ ∧ ∀μ, verdict_μ=MET`; if `D₁₂=Reject` or some monitor maps to `Reject` then `D₁₃=Reject`; with no promotion monitors `D₁₃=D₁₂`. The statement is about the join over supplied verdicts, not about how a verdict was computed.

4. **Theorem 12.4 — `tail_mono_p` (claimed, exact binomial model)**. For `0≤p≤q≤1` and `0≤j≤N`, `T⁺(N,p,j)≤T⁺(N,q,j)` and `T⁻(N,q,j)≤T⁻(N,p,j)`. For `j≤j'≤N`, `T⁺(N,p,j')≤T⁺(N,p,j)` and `T⁻(N,p,j)≤T⁻(N,p,j')`. These are statements about exact finite sums, not computed beta quantiles.

5. **Theorem 12.5 — exact upper-tail test level (claimed, generic)**. If `K` is a good window for `(N,θ)`, then `Pr[K≥1 ∧ T⁺(N,θ,K)<α] ≤ α`. The rejection set is upward closed in `K` (Theorem 12.4), so its probability is at most the upper tail at its least member, which is below `α`. IID Bernoulli counts with `p≤θ` are good windows. This is a paper result: no Lean declaration states it; its mechanised ingredients are `upper_mono_count` and `binomial_good_window`.

6. **Theorem 12.6 — exact lower-tail test level (claimed, generic)**. If `K` is a bad window for `(N,θ)`, then `Pr[K<N ∧ T⁻(N,θ,K)≤1−c_conf] ≤ 1−c_conf`. The acceptance set is downward closed in `K`, so its probability is at most the lower tail at its greatest member. IID Bernoulli counts with `p≥θ` are bad windows, including at equality. This is a paper result: no Lean declaration states it; its mechanised ingredients are `bad_lower_bound`, `lower_mono_count` and `binomial_bad_window`.

7. **Theorem 12.7 — `horizon_false_alarm` (claimed, generic)**. For a predesignated finite family of events `E₁,…,E_m` with `Pr[E_i]≤α_i` and `∑_i α_i≤α_FA`, `Pr[⋃_i E_i]≤α_FA`. No independence is assumed. With `E_i` the false-`BREACHED` event of window `i`, this is the horizon budget of Definition 12.13. Data-dependent redefinition of windows, looks, budgets, or horizon is not covered without the corresponding conditional bound.

8. **Theorem 12.8 — `compose_partial` (claimed, static; Lean target `compose_partial_statement`)**. On compatible normalized contracts, with absent `notify` severity filled as `critical` and severity ordered `info < warning < critical`, raw `A⊓B` (maximum severity on shared notify rules) is a greatest lower bound for `⊑_rt`. Validated `compose(A,B)` succeeds iff that raw meet satisfies `WF_rt` and all reachability conditions in Definition 12.27. On success, `compose(A,B)⊑_rt A` and `compose(A,B)⊑_rt B`; an unreachable raw meet is an error, not a weakened composition. Incompatible identity/schedule is outside the raw meet's domain.

9. **Theorem 12.9 — `severity_meet_glb` (claimed)**. Normalizing an absent `notify` severity yields `critical`, and the maximum of two normalized severities is their greatest lower bound in the strictness order (higher severity is stricter).

10. **Theorem 12.10 — `backend_profile_roundtrip` (claimed, representation only)**. Fix the hosted profile schema/version and a bijective local token map. On normalized valid `backend_v1` profile records consisting only of the representable profile fields, with no additional local-only rules/annotations, `lift(lower(p))=p`; symmetrically lowering a lifted canonical hosted profile preserves its field values and stored method/sampling names. Required numeric serialization preserves the stored values. This is an identity of representations, not equality of `_v1` and rational `_v2` window verdicts or proof of a deployed adapter.

11. **Theorem 12.11 — `compiled_contract_correct_statement` (open target)**. For `WF_rt(M)`, compilation returns a contract whose normalized declarations, predicates, identities and notify severities equal those of `M` after default filling and projection. This is a target for declaration normalization and projection only; no parser, canonical wire encoding or source-to-contract preservation proof is supplied, and it says nothing about evaluator behaviour.

12. **Deferred — float/rational numerical refinement**. No theorem here relates `clopper_pearson_exact_v1` to `clopper_pearson_rational_v2`. A wider equivalence would require an explicit numerical-refinement hypothesis and separate verification; neither follows from Theorems 12.4–12.7 or 12.10.

13. **Not claimed / deferred — stronger statistical and behavioral guarantees**. Episode-level false-closure probability, heterogeneous-unit bounds (including a Hoeffding-based extension), anytime-valid sequences, infinite-horizon control, unsampled prevention, checker accuracy, and repair efficacy are outside these claims. A finite-horizon false-alarm bound and a consecutive-`MET` rule do not establish them.

---

## Appendix A: Notation Summary

| Symbol | Meaning |
|--------|---------|
| `Δ` | TVAR declaration context (list of declarations) |
| `Γ` | Typing context (map from identifiers to types) |
| `Γ_env` | Environment typing context |
| `E_τ` | Environment snapshot at time τ |
| `c` | Configuration (TVAR assignment) |
| `φ, ψ` | Formulas (constraints) |
| `⟦·⟧` | Denotation (semantic interpretation) |
| `⦃·⦄` | Type interpretation |
| `𝒟⟦·⟧` | Domain interpretation |
| `elem(τ)` | Element type extraction |
| `⊢` | Typing judgment |
| `⊨` | Satisfaction |
| `≻_P` | Pareto dominance |
| `≻_ε` | ε-Pareto dominance |
| `≽_ε` | Weak ε-Pareto dominance |
| `σ(·)` | Direction sign (+1 for max, -1 for min) |
| `δ_i` | Direction-normalized difference |
| `Γ_rt` | Separate runtime declaration typing context; never extends TVAR context `Γ` |
| `v`, `h` | Unit and its complete history |
| `before_h(a,b)` | Event `a` precedes event `b` in the complete history `h` |
| `A_q(h)`, `V_q(h)` | Population-membership and violation predicates on a complete history |
| `sat`, `vio`, `unres` | Satisfied, violating, unresolved unit classifications; exclusion is separate |
| `n`, `k`, `u`, `pl`, `N` | Resolved, violating, unresolved, unplaceable counts; `N` the counted units of a decision (`N=n` when every counted unit is resolved) |
| `u_reported`, `dropped` | Reported unresolved units; selected units a report does not account for |
| `p_w` | A window's violation rate under the declared model |
| `θ`, `c_conf`, `f` | Maximum violation rate, window confidence, maximum unresolved fraction |
| `α_FA`, `α_w`, `m` | Predesignated horizon budget, per-window allocation, number of looks |
| `T⁺(N,p,j)`, `T⁻(N,p,j)` | Inclusive exact binomial upper and lower tails |
| `X ≤st Y` | First-order stochastic domination on natural counts; good and bad windows |
| `W`, `due(w)` | Tumbling window width; window end plus grace |
| `K_close` | Required consecutive MET count for closing an episode, after composition |
| `e₀`, `D` | Opening window end and window-time recovery deadline `e₀+T` |
| `A ⊑_rt B`, `A ⊓ B` | A tightens compatible B; their raw greatest lower bound |
| `Π_host` | Closed hosted projection after tokenization |
| `erase(M)`, `⟦M⟧₁.₃` | Legacy semantic projection and extended module denotation |

## Appendix B: Error Code Mapping

### B.1 Static Validation Errors

| Formal Property Violated | Error Code |
|-------------------------|------------|
| `Γ(x) undefined` | `undeclared_tvar` |
| `Γ ⊢ e : τ` fails | `constraint_type_mismatch` |
| `v ∉ 𝒟⟦d⟧(E_τ)` | `constraint_value_out_of_domain` |
| `Feasible(M) = ∅` | `unsatisfiable_constraints` |
| Non-linear term in structural | `non_linear_structural` |
| TVAR in derived constraint | `derived_references_tvar` |
| Float domain not precision-aligned | `inadequate_precision` |
| Environment lookup fails | `derived_env_undefined` |
| Range domain ill-formed (r ≤ 0 or a > b) | `invalid_range_domain` |

### B.2 Promotion Gate Errors

| Formal Property Violated | Error Code |
|-------------------------|------------|
| `¬ChancePass(χ, k, n)` | `chance_constraint_failed` |
| `BandHardFail(b, μ̂)` | `band_objective_failed` |
| `¬BandPass(b, μ̂, s, n) ∧ ¬BandHardFail(b, μ̂)` | `band_objective_inconclusive` |
| `¬StatDominates(c_cand, c_inc, ...)` | `insufficient_dominance` |
| `n = 0` in chance constraint | `zero_trials` |
| `n < 2` in objective evaluation | `insufficient_samples` |

### B.3 Formal Verification Scope Warnings

| Construct Outside Verified Subset | Warning Code |
|----------------------------------|--------------|
| Registry domain used | `unverifiable_registry_domain` |
| Callable type used | `unverifiable_callable_type` |
| Float precision inadequate | `inadequate_precision` |

### B.4 Runtime Validation and Lint Codes (TVL 1.3)

[RFC 0003 §5](rfc-0003-runtime-requirements-monitors-responses.md#5-static-semantics-diagnostics) is the single normative source for TVL 1.3 diagnostic codes, conditions, and severities. This appendix does not define aliases or a second registry. The following are only cross-references for codes explicitly used in §12; all other runtime diagnostics, syntax-level enums, and lexical constraints are specified in the RFC. These references do not assert that an implementation already emits the diagnostics.

| Use in §12 | Canonical diagnostic in RFC §5 |
|---|---|
| Refuse unsupported constructs (Definition 12.29) or an unexecutable declared action at registration (Definition 12.25) | `unsupported_construct`, `response_action_unsupported` |
| Reject a report that violates its count identities (Definition 12.11) | `runtime_report_conservation` |
| Report MET power at the minimum sample count (Definition 12.27) | `runtime_met_unreachable_at_min_samples` — warning under `backend_v1`, error otherwise |
| Report breach power at the minimum sample count (Definition 12.27) | `runtime_breach_unreachable_at_min_samples` — warning for primary monitors; burn reachability is mandatory |
| Reject an impossible window-time recovery deadline (Definition 12.19) | `recovery_deadline_impossible` |
| Retain both overlapping promotion checks (Definition 12.15) | `chance_constraint_shadowed` — warning |
| Report missing or invalid promotion counts (Definitions 12.15–12.16) | `missing_monitor_counts` — a readiness issue |
| Fail closed on an unresolved alias or unavailable token map (Definition 12.28) | `runtime_unresolved_alias` |
| Require a version for 1.3 constructs while preserving legacy omission handling (Definition 12.29) | `runtime_version_required` when omitted; `declared_version_below_constructs` for an explicitly incompatible value |

Verdict reasons such as `insufficient`, `incomplete`, `sampling_biased`, `awaiting`, `lifecycle_unavailable`, and `engine_required` are evaluation outcomes, not static lint errors. Their syntax-level closed values are normative in the RFC; §12 defines their meaning.

## Appendix C: References

1. Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society: Series B*, 57(1), 289-300.
2. Bradley, A. R., & Manna, Z. (2007). *The Calculus of Computation*. Springer.
3. Clopper, C. J., & Pearson, E. S. (1934). The use of confidence or fiducial limits illustrated in the case of the binomial. *Biometrika*, 26(4), 404-413.
4. de Moura, L., & Bjørner, N. (2008). Z3: An Efficient SMT Solver. *TACAS*.
5. Deb, K., et al. (2002). A Fast and Elitist Multiobjective Genetic Algorithm: NSGA-II. *IEEE TEC*.
6. Holm, S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*, 6(2), 65-70.
7. Pierce, B. C. (2002). *Types and Programming Languages*. MIT Press.
8. Schuirmann, D. J. (1987). A comparison of the two one-sided tests procedure and the power approach for assessing the equivalence of average bioavailability. *Journal of Pharmacokinetics and Biopharmaceutics*, 15(6), 657-680.

---

*End of Document*
