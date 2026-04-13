# TVL Formal Semantics

**Version 1.0 — Formal Foundations**

**Authors**: Traigent Research
**Date**: January 2026
**Status**: Draft Specification

---

## Abstract

This document provides the formal mathematical foundations for the Tuned Variables Language (TVL). We define TVL's abstract syntax, semantic domains, type system, and denotational semantics. We state and prove (or sketch proofs for) the key metatheoretic properties: type soundness, constraint decidability, SMT encoding soundness, and promotion correctness. These foundations establish TVL as a rigorous specification language suitable for safety-critical AI agent configuration.

---

## 1. Introduction

### 1.1 Specification Languages vs. Programming Languages

TVL is a **domain-specific specification language** (DSL) for AI agent configuration optimization. Unlike programming languages, which describe *how* to compute results, specification languages describe *what* properties must hold.

| Property | Programming Language | Specification Language (TVL) |
|----------|---------------------|------------------------------|
| Primary purpose | Describe computation | Describe valid configurations |
| Execution model | Operational | Declarative (validated/checked) |
| Expressiveness | Typically Turing-complete | Intentionally restricted |
| Key property | Termination | Decidability |

### 1.2 Formal Requirements

For TVL to serve as a trustworthy specification language, we must establish:

1. **Well-defined syntax**: Unambiguous grammar with formal AST
2. **Well-defined semantics**: Mathematical meaning for every construct
3. **Type soundness**: Well-typed modules don't produce runtime type errors
4. **Decidability**: All validation questions are decidable
5. **Soundness**: If tooling accepts a module, stated properties hold
6. **Completeness**: If properties hold, tooling can verify them

### 1.3 Document Structure

- **§2**: Abstract Syntax — formal AST definitions
- **§3**: Semantic Domains — mathematical structures for meanings
- **§4**: Type System — typing rules and judgments
- **§5**: Denotational Semantics — meaning functions
- **§6**: Feasibility Predicates — structural and operational constraints
- **§7**: Metatheory — soundness, completeness, decidability theorems
- **§8**: SMT Encoding — compilation to solver format
- **§9**: Promotion Semantics — acceptability, dominance, and promotion correctness

### 1.4 Scope of Formal Guarantees

The formal semantics and soundness proofs in this document apply to the **core TVL subset**. The following constructs are **outside the formally verified subset**:

| Construct | Reason | Status |
|-----------|--------|--------|
| Registry domains (`domain: { registry: ... }`) | External state interaction | Future work |
| Filter expressions in registry refs | Filter language not formalized | Future work |
| Callable types (`type: callable[Protocol]`) | Protocol typing not defined | Future work |

**Implications**:

1. **Modules using excluded constructs**: The soundness theorems (Theorem 8.1, etc.) do not apply. Validation may pass, but formal correctness guarantees are not provided.

2. **Warnings**: Conformant validators SHOULD emit warnings when excluded constructs are used:
   - `W6001: unverifiable_registry_domain` — "Module uses registry domain; formal soundness guarantees do not apply"
   - `W6002: unverifiable_callable_type` — "Module uses callable type; type safety is not formally verified"

3. **Workaround**: For formal guarantees, resolve registry domains to explicit enum domains before validation, and replace callable types with enum types listing known implementations.

**Rationale**: Registry domains require interaction with external state (registries), which introduces semantic complexity beyond the scope of this static specification. Callable types require a protocol typing system that would significantly expand the formalization. These features are valuable for practical use but are excluded from the formally verified core to keep the proofs tractable.

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
| **Static Validity** | `constraints.derived` | Budget predicates evaluated on E_τ |
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
| `evaluation_set.dataset` | Dataset URI for reproducibility |
| `evaluation_set.seed` | RNG seed for determinism |

#### 1.5.4 Semantic Layer Architecture

The semantic fields operate at three distinct layers:

**Layer 1: Static Validity (Pre-Evaluation)**

Determines which configurations are *structurally valid* before any evaluation:

```
Valid(c, M) ⟺ c ∈ Config(Δ, E_τ) ∧ F^str(c, Φ^str) ∧ F^op(E_τ, Φ^der)
```

- **Structural constraints** (`constraints.structural`): Boolean formulas over TVARs
- **Budget constraints** (`constraints.derived`): Linear predicates over environment

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
| Evaluation context | `evaluation_set.*` | Operational (where to run, not what to run) |
| Tie-breaking | `promotion_policy.tie_breakers` | Heuristic (not part of dominance relation) |
| Module metadata | `tvl.module`, `tvl_version` | Informational (no semantic content) |

These fields affect *how* optimization is performed, not *what* constitutes a valid or acceptable configuration.

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
  adjust?: AdjustMethod,                 (* Default: none *)
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
3. All derived (budget) constraints are satisfied under the environment

**Note**: Validity is determined *before* evaluation. It does not require running the configuration.

---

## 7. Metatheory

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
- If `F^op(E_τ, M.Φ^der) = false`, return INCONSISTENT (no configuration can satisfy budget constraints regardless of structural constraints)

**Phase 2**: Check structural constraint satisfiability.
- If Phase 1 passed, check `∃c ∈ Config(Δ, E_τ): F^str(c, M.Φ^str) = true`
- This is decidable (Theorem 7.2)
- If SAT, return CONSISTENT; else return INCONSISTENT

Both phases are decidable, so consistency is decidable. □

---

## 8. SMT Encoding

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

**Minimum Precision Calculation**.
For a domain D with minimum gap `min_gap(D) = min{|v₁ - v₂| : v₁, v₂ ∈ D, v₁ ≠ v₂}`, the minimum adequate precision is:

```
P_min(D) = ⌈1 / min_gap(D)⌉
```

A domain defined with `resolution: r` has `min_gap(D) = r`, so `P_min = ⌈1/r⌉`.

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

1. **Non-inferiority test**: H₀: `δ_i < -ε[i]` (candidate is worse by more than ε)
   - If p-value < α, reject H₀ (evidence candidate is not worse)
2. **Superiority test**: H₀: `δ_i ≤ ε[i]` (candidate is not better by more than ε)
   - If p-value < α, reject H₀ (evidence candidate is strictly better)

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
- A configuration failing a band constraint is rejected via `Acceptable(c, Y_c, M) = false`
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
  chance_outcomes:  ChanceConstraint → (k, n)  (* successes and trials *)
}
```

Where:
- `μ̂` is the sample mean
- `s` is the sample standard deviation
- `n` is the sample size (number of observations)
- `SE = s / √n` is the standard error (derived)

**Rationale**: Including sample size `n` (not just SE) enables proper degrees-of-freedom calculation for t-tests and allows detection of underpowered comparisons.

**Definition 9.8 (Chance Constraint Satisfaction)**.
For chance constraint `χ = (name, threshold θ, confidence γ)` and observed outcome `(k, n)`:

```
ChancePass(χ, k, n) ⟺ CI_lower(k, n, γ) ≥ θ
```

Where `CI_lower(k, n, γ)` is the Clopper-Pearson lower bound at confidence level γ:
```
CI_lower(k, n, γ) = Beta.ppf(1 - γ, k, n - k + 1)
```

**Intuition**: We require γ-confidence that the true success rate exceeds threshold θ. This is a one-sided lower bound because we only care that the rate is *above* the threshold.

**Precondition**: n ≥ 1. If n = 0 (no trials), the chance constraint check is undefined; implementations MUST report an error.

**Edge case (k = 0)**: When k = 0 (zero successes), `CI_lower(0, n, γ) = 0` for any γ < 1, so any threshold θ > 0 will fail. This is correct: zero observed successes provides no evidence the true rate exceeds any positive threshold.

**Definition 9.9 (Band Objective Satisfaction)**.
For banded objective `b = (name, target [L, U], α)` and observed statistics `(μ̂, s, n)`:

```
BandPass(b, μ̂, s, n) ⟺ TOST_pass(μ̂, s, n, [L, U], α)
```

**Note on direction**: Banded objectives do NOT use the `direction` field. The band [L, U] applies to the raw observed value μ̂, not a direction-normalized value. Banded objectives are *acceptability constraints*, not optimization targets—they define a range of acceptable values, not a direction of improvement.

**Definition 9.10 (Behavioral Acceptability)**.
Configuration `c` with evaluation result `Y_c` is **behaviorally acceptable** under module `M`:

```
Acceptable(c, Y_c, M) ⟺
    (∀χ ∈ M.promotion_policy.chance_constraints: ChancePass(χ, Y_c.chance_outcomes(χ)))
  ∧ (∀o ∈ BandedObjectives(M): BandPass(o.band, Y_c.objective_values(o)))
```

Where `BandedObjectives(M)` is defined in Definition 3.11.

**Key Properties**:

1. **Acceptability is absolute, not comparative**: `Acceptable(c, Y_c, M)` depends only on `c`'s own evaluation, not on any incumbent.

2. **Acceptability gates dominance**: A candidate failing any acceptability check is rejected *immediately*, regardless of objective performance:
   ```
   ¬Acceptable(c_cand, Y_cand, M) ⟹ Decision = Reject
   ```

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
- `Valid(c, M)` = structural feasibility ∧ budget constraint satisfaction (§6)
- `Acceptable(c, Y_c, M)` = chance constraint ∧ band objective satisfaction (Definition 9.10)
- `StatDominates` = statistical ε-Pareto dominance per §9.4

**Decision Logic**:
```
if ¬Valid(c_cand, M):
    return Error("invalid configuration")
if ¬Acceptable(c_cand, Y_cand, M):
    return Reject("acceptability check failed")
if StatDominates(c_cand, c_inc, Y_cand, Y_inc, M):
    return Promote
if StatDominates(c_inc, c_cand, Y_inc, Y_cand, M):
    return Reject("incumbent dominates")
return NoDecision("insufficient evidence")
```

### 9.8 Promotion Correctness

**Theorem 9.1 (Promotion Error Guarantees)**.
The promotion gate provides the following error control guarantees for per-objective non-inferiority tests:

**(a) With no adjustment (`adjust: "none"`):**
- Each per-objective non-inferiority test has type-I error ≤ α
- No family-wise error rate (FWER) control across objectives
- P(false positive on objective i) ≤ α, for each i

**(b) With Bonferroni adjustment (`adjust: "bonferroni"`):**
- Controls FWER: P(at least one false rejection) ≤ α
- More conservative: individual tests use α/k threshold (k = number of standard objectives)
- Guarantees: If all non-inferiority tests pass, P(ANY objective truly regressed > ε) ≤ α

**(c) With Holm adjustment (`adjust: "holm"`):**
- Controls FWER: P(at least one false rejection) ≤ α
- Less conservative than Bonferroni (step-down procedure)
- Tests sorted by p-value; threshold for i-th smallest is α/(k-i+1)

**(d) With Benjamini-Hochberg adjustment (`adjust: "BH"`):**
- Controls FDR: E[false rejections / total rejections] ≤ α
- Less conservative than Bonferroni/Holm, more powerful
- Guarantees: Expected proportion of objectives where we wrongly claim no-regression ≤ α
- **Note**: FDR ≠ FWER. BH does NOT guarantee P(any false positive) ≤ α

*Proof sketch*:
- (a) Follows from individual test construction at level α
- (b) Bonferroni inequality: P(∪ᵢ Aᵢ) ≤ Σᵢ P(Aᵢ) ≤ k · (α/k) = α
- (c) Holm (1979): Step-down refinement of Bonferroni maintaining FWER
- (d) BH procedure: Sort p-values, reject H₀₍ᵢ₎ for i ≤ max{j : p₍ⱼ₎ ≤ jα/k}. Under independence or PRDS, FDR ≤ α (Benjamini & Hochberg, 1995). □

**Clarification on "False Promotion"**:
- A *false promotion* occurs when promoting a candidate that truly regressed on ≥1 objective by more than ε
- Bonferroni and Holm control P(false promotion) ≤ α
- BH controls the expected *proportion* of incorrectly claimed no-regressions, not P(false promotion)

**Recommendation**: For safety-critical applications where any regression is unacceptable, use `adjust: "bonferroni"` or `adjust: "holm"`. For exploratory optimization where some false positives are tolerable in exchange for power, use `adjust: "BH"`.

**Lemma 9.2 (ε-Dominance Composition)**.
*Weak* ε-Pareto dominance composes: if `c₁ ≽_ε c₂` and `c₂ ≽_ε c₃`, then `c₁ ≽_{2ε} c₃`.

Where weak dominance `c ≽_ε c'` means: `∀i: σ(O[i].direction) · (y[i] - y'[i]) ≥ -ε[i]` (no strict improvement required).

**Note on Theorem/Lemma Numbering**: Lemma 9.1 (Acceptability Independence) appears in §9.6. Theorem 9.1 (Promotion Error Guarantees) and Lemma 9.2 (ε-Dominance Composition) appear in §9.8.

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

## 10. Implementation Requirements

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

### 10.4 SMT Backend Requirements

1. Implement encoding per §8
2. Use index-variable encoding for range domains (§8.3)
3. Use direction-aware rounding for comparisons (§8.4)
4. Use conformant SMT solver (Z3, CVC5, etc.)
5. Correctly decode models to configurations

### 10.5 Promotion Gate Requirements

1. Implement ε-Pareto comparison per §9.3 with direction normalization (§9.4)
2. Support statistical testing with direction-normalized differences (Definition 9.4)
3. Apply multiple-testing adjustment when configured (bonferroni, holm, BH)
4. Verify evaluation results include sample size for proper df calculation

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
3. **Temporal constraints**: Constraints over configuration sequences

### 11.3 Verification

Connecting TVL to verification frameworks:

1. **Runtime monitoring**: Verify configurations satisfy constraints at deployment
2. **Invariant checking**: Prove optimizer preserves feasibility
3. **Regret bounds**: Formal guarantees on exploration efficiency

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
| `¬BandPass(b, μ̂, s, n)` | `band_objective_failed` |
| `¬StatDominates(c_cand, c_inc, ...)` | `insufficient_dominance` |
| `¬Acceptable(c, Y_c, M)` | `acceptability_failed` |
| `n = 0` in chance constraint | `zero_trials` |
| `n < 2` in objective evaluation | `insufficient_samples` |

### B.3 Formal Verification Scope Warnings

| Construct Outside Verified Subset | Warning Code |
|----------------------------------|--------------|
| Registry domain used | `unverifiable_registry_domain` |
| Callable type used | `unverifiable_callable_type` |
| Float precision inadequate | `inadequate_precision` |

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
