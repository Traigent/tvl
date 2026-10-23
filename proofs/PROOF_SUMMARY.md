# TVL Mechanized Proofs - Comprehensive Summary for Review

**Date**: 2026-02-01
**Lean Version**: 4.28.0-rc1
**Mathlib**: Commit 6a596ab9
**Historical baseline build status (2026-02-01)**: All modules compiled successfully.

**Current RFC 0005 check**: The new module passed direct Lean checking; the full
`lake build` was blocked fetching dependencies. See [Local verification](#local-verification)
for commands, logs and scope.

> **Coverage note (added after RFC 0001/0002):** this proof tree covers the
> TVL core subset as it stood on 2026-02-01 — `tvars`, `constraints`,
> `objectives`, and `promotion_policy`. **`cvars`/`policies` (RFC 0001,
> 2026-06-05) and `composites` (RFC 0002, 2026-06-06) are not formalized
> here**; nothing in `proofs/TVL/*.lean` models those constructs. See
> `formalization/tvl-formal-semantics.md` §1.4 for the full disclosure (a
> lint warning for this is tracked as follow-up work, not yet implemented).

---

## Overview

This document provides a comprehensive summary of the Lean 4 formalizations of key theorems from the TVL (Tuned Variables Language) paper. The proofs establish the theoretical foundations for the TVL constraint system used in AI agent optimization.

For OPAL declarative-core mechanization (assignment vs. `in`, `given`, callable interfaces, nested template typing/completeness), see:

- [`OPALCORE_README.md`](OPALCORE_README.md)

---

## File Structure

```
tvl/proofs/
├── lakefile.lean           # Lake project configuration (with Mathlib)
├── lean-toolchain          # Lean 4.28.0-rc1
├── Main.lean               # Entry point
└── TVL/
    ├── Basic.lean          # Core definitions (85 lines)
    ├── Types.lean          # Type system formalization (123 lines)
    ├── TypeSoundness.lean  # Theorem 4.2 (191 lines)
    ├── SMTEncoding.lean    # Theorem 5.6 (416 lines)
    └── Dominance.lean      # Lemma 6.18 (118 lines)
```

---

## 1. Core Definitions (TVL/Basic.lean)

### Types Defined

| Definition | Lean Type | Description |
|------------|-----------|-------------|
| `BaseType` | `inductive` | `bool`, `int`, `float`, `str` |
| `Ty` | `inductive` | `base b`, `enum b`, `tuple [τ₁,...,τₙ]` |
| `Val` | `inductive` | Runtime values: `vbool`, `vint`, `vfloat`, `vstr`, `vtuple` |
| `Context` | `VarName → Option Ty` | Typing context Γ |
| `Config` | `VarName → Option Val` | Runtime configuration c |
| `Domain` | `List Val` | Finite value domains |

### Key Functions

- `elemType : Ty → BaseType` - Extracts underlying type from enum
- `BaseType.isNumeric : BaseType → Bool` - Checks if type supports comparisons
- `Context.extend` - Extends context with new binding

---

## 2. Type System (TVL/Types.lean)

### Atomic Formulas

```lean
inductive Atom where
  | eq : VarName → Val → Atom              -- x = v
  | neq : VarName → Val → Atom             -- x ≠ v
  | geq : VarName → Int → Atom             -- x ≥ n
  | leq : VarName → Int → Atom             -- x ≤ n
  | mem : VarName → List Val → Atom        -- x ∈ S
```

### Propositional Formulas

```lean
inductive Formula where
  | atom : Atom → Formula
  | and : Formula → Formula → Formula
  | or : Formula → Formula → Formula
  | not : Formula → Formula
  | impl : Formula → Formula → Formula     -- φ ⇒ ψ ≜ ¬φ ∨ ψ
```

### Typing Rules Formalized

| Rule | Lean Constructor | Paper Section |
|------|------------------|---------------|
| T-Eq | `AtomWellTyped.tEq` | 4.1 |
| T-Neq | `AtomWellTyped.tNeq` | 4.1 |
| T-Cmp (≥) | `AtomWellTyped.tGeq` | 4.1 |
| T-Cmp (≤) | `AtomWellTyped.tLeq` | 4.1 |
| T-Mem | `AtomWellTyped.tMem` | 4.1 |
| T-And | `FormulaWellTyped.tAnd` | 4.1 |
| T-Or | `FormulaWellTyped.tOr` | 4.1 |
| T-Not | `FormulaWellTyped.tNot` | 4.1 |
| T-Impl | `FormulaWellTyped.tImpl` | 4.1 |

### Ty.isAtomType Predicate (NEW)

All atom typing rules require `τ.isAtomType = true`, which explicitly blocks tuples:

```lean
def Ty.isAtomType : Ty -> Bool
  | Ty.base _ => true
  | Ty.enum _ => true
  | Ty.tuple _ => false  -- Tuples blocked in atoms
```

### ConfigRespectsContext

```lean
def ConfigRespectsContext (c : Config) (Γ : Context) : Prop :=
  ∀ x τ, Γ x = some τ → ∃ v, c x = some v ∧
    match τ with
    | Ty.base b => HasValType v b
    | Ty.enum b => HasValType v b
    | Ty.tuple _ => True  -- Simplified
```

---

## 3. Type Soundness (TVL/TypeSoundness.lean)

### Theorem 4.2 - **FULLY PROVEN** ✓

**Statement**: If Γ ⊢ φ : prop and configuration c respects Γ, then ⟦φ⟧(c) ∈ 𝔹.

**Lean Statement**:
```lean
theorem type_soundness (Γ : Context) (φ : Formula) (c : Config) :
    FormulaWellTyped Γ φ →
    ConfigRespectsContext c Γ →
    ∃ b : Bool, evalFormula φ c = some b
```

**Proof Strategy**: Structural induction on the typing derivation.

**Key Lemma**:
```lean
theorem atom_eval_defined (Γ : Context) (a : Atom) (c : Config) :
    AtomWellTyped Γ a →
    ConfigRespectsContext c Γ →
    ∃ b, evalAtom a c = some b
```

**Proof Details**:
- **Base cases (atoms)**: Each atom typing rule (T-Eq, T-Cmp, etc.) ensures operands have compatible types. The proof uses case analysis on the atom type and type τ, showing that well-typed atoms always evaluate to a boolean.
- **Inductive cases (connectives)**: Boolean connectives preserve totality by the induction hypothesis.

**Lines of Code**: 191
**Sorry Count**: 0

---

## 4. ε-Dominance Composition (TVL/Dominance.lean)

### Lemma 6.18 - **FULLY PROVEN** ✓

**Statement**: Weak ε-dominance composes:
```
c₁ ≽ε c₂ ∧ c₂ ≽ε c₃ ⟹ c₁ ≽₂ε c₃
```

**Lean Statement**:
```lean
theorem normalized_diff_composition (d : Direction) (y₁ y₂ y₃ ε : Int)
    (h12 : normalizedDiff d y₁ y₂ >= -ε)
    (h23 : normalizedDiff d y₂ y₃ >= -ε) :
    normalizedDiff d y₁ y₃ >= -(2 * ε)
```

**Proof**: Algebraic manipulation using `linarith` tactic.
```lean
  simp only [normalizedDiff] at *
  have key : d.sign * (y₁ - y₃) = d.sign * (y₁ - y₂) + d.sign * (y₂ - y₃) := by ring
  linarith
```

**Key Insight**: Tolerances add when composing dominance relations.

### List-Based Corollary

```lean
theorem eps_dominance_composition_list
    (n : Nat)
    (directions : List Direction) (ε y₁ y₂ y₃ : List Int)
    (hlen_d : directions.length = n) ...
    (h12 : ∀ (i : Fin n), normalizedDiff ... >= -(ε.get ...))
    (h23 : ∀ (i : Fin n), normalizedDiff ... >= -(ε.get ...)) :
    ∀ (i : Fin n), normalizedDiff ... >= -(2 * (ε.get ...))
```

### Warning: Strict Dominance Does NOT Compose

```lean
theorem strict_dominance_does_not_compose_informal : True := trivial
```

**Counter-example documented**:
- y₁ = [100, 50], y₂ = [90, 50], y₃ = [90, 40], ε = [10, 10]
- y₁ ≻ε y₂ (strictly better on A)
- y₂ ≻ε y₃ (strictly better on B)
- But y₁ ≽₂ε y₃, NOT y₁ ≻₂ε y₃

**Lines of Code**: 118
**Sorry Count**: 0

---

## 5. SMT Encoding Soundness (TVL/SMTEncoding.lean)

### Rounding Soundness (Lemma 5.4) - **FULLY PROVEN** ✓

**Statement**: For P-aligned domain value v and threshold n (both non-negative):
```
v ≥ n ⟺ scale(v) ≥ ⌈n/P⌉
```

**Lean Statement**:
```lean
theorem rounding_soundness_nonneg (v n : Nat) (P : PrecisionFactor) (hP : P > 0) :
    v * P >= n ↔ v >= (n + P - 1) / P
```

**Proof Strategy**:
1. Handle n = 0 case separately (trivially true)
2. For n > 0: Use contraposition for forward direction
3. Use ceiling division property `⌈n/P⌉ * P ≥ n` for backward direction

**Helper Lemmas**:
```lean
private lemma ceil_div_mul_ge (n P : Nat) (hP : P > 0) :
    (n + P - 1) / P * P ≥ n

private lemma le_div_imp_mul_le (k m n : Nat) (hn : n > 0) (h : k ≤ m / n) :
    k * n ≤ m
```

### SMT Encoding Soundness (Theorem 5.6) - **COMPLETE** ✓

**Statement**:
```
m ⊨ encode(Δ, φ, P) ⟺ ⟦φ⟧(decode(m)) = true
```

**Lean Statement**:
```lean
theorem smt_encoding_soundness
    (φ : Formula) (P : PrecisionFactor) (_hP : P > 0)
    (idx : Val → Option Nat)
    (_idx_bij : ∀ v₁ v₂, idx v₁ = idx v₂ → idx v₁ ≠ none → v₁ = v₂)
    (m : SMTModel)
    (decode_val : SMTVar → SMTVal → Option Val)
    (hwf : WellFormedDecode decode_val idx)
    (_encode_val : VarName → Val → Option SMTVal)
    (_roundtrip : ∀ x v, (do let n ← _encode_val x v; decode_val x n) = some v)
    (ψ : SMTFormula)
    (henc : encodeFormula φ P idx = some ψ) :
    evalSMT ψ m = some true ↔
    evalFormula φ (decodeModel m decode_val) = some true
```

**Key Addition - WellFormedDecode Structure**:

```lean
structure WellFormedDecode (decode_val : SMTVar → SMTVal → Option Val)
    (idx : Val → Option Nat) where
  definedness : DecodeDefinedness decode_val
  numeric : NumericDecodePreservation decode_val
  equality : EqualityDecodeCorrespondence decode_val idx
```

**Key Addition - ModelDefinedOn Precondition** (NEW):

The main theorem requires the SMT model to be defined on all formula variables:

```lean
def ModelDefinedOn (m : SMTModel) (φ : Formula) : Prop :=
  ∀ x, x ∈ formulaVars φ → ∃ n, m x = some n
```

This handles the semantic corner case where SMT `ff` (for empty list membership)
is always defined, but TVL `x ∈ []` requires the variable to be defined.

**NumericDecodePreservation (Conditional Form)** (UPDATED):

The axiom now uses a conditional form that's satisfiable for all decode functions:

```lean
def NumericDecodePreservation (decode_val : SMTVar → SMTVal → Option Val) : Prop :=
  ∀ x n v, decode_val x n = some v → ∀ m, v.toInt? = some m → m = n
```

This says: "If the decoded value has an integer representation m, then m = n."
For boolean/string values where `toInt?` returns none, no constraint is imposed.

**Proof Structure**:

- **Induction on φ**: All 5 cases (atom, and, or, not, impl) fully addressed
- **Boolean connectives (and, or, not, impl)**: ✓ Fully proven using definedness lemmas
- **Equality atoms (eq, neq)**: ✓ Proven using `EqualityDecodeCorrespondence`
- **Comparison atoms (geq, leq)**: ✓ Proven using `NumericDecodePreservation`
- **Membership atoms (mem)**:
  - ✓ Empty list `[]`: Proven (encodes to `ff`, trivially false)
  - ✓ Singleton `[v]`: Proven using `Val.beq_comm` for BEq symmetry
  - ✓ Multi-element `v :: v' :: vs`: Proven via `mem_encoding_soundness` with list induction

**Helper Lemmas**:

- `Val.beq_comm`: BEq symmetry for all `Val` constructors (including tuples)
- `mem_encoding_soundness`: Membership encoding (fully proven via list induction)
- `mem_encoding_undefined`: When SMT model has no value, membership encoding is undefined
- `mem_encoding_defined`: When SMT model has a value, membership encoding is defined
- `encoding_definedness`: SMT definedness → formula definedness (fully proven)
- `encoding_definedness_rev`: formula definedness → SMT definedness (fully proven)

**Documented Edge Cases**: None in Lean source (zero `sorry` terms).

### Satisfiability Preservation (Corollary) - **FULLY PROVEN** ✓

**Statement**:

```
(∃ c ∈ Config: ⟦φ⟧(c) = true) ⟺ SAT(encode(φ))
```

**Proof Status**:

- **Backward direction**: ✓ Proven using `smt_encoding_soundness`
- **Forward direction**: ✓ Proven using `decode_encode_config_agree` and `evalFormula_ext`

**Lines of Code**: ~900
**Sorry Terms**: 0

---

## 6. Verification Summary

| Theorem | Paper Ref | Status | Sorry Count | Notes |
|---------|-----------|--------|-------------|-------|
| Type Soundness | 4.2 | ✓ Complete | 0 | All proofs verified |
| ε-Composition | 6.18 | ✓ Complete | 0 | `normalized_diff_composition` proven |
| Rounding Soundness | 5.4 | ✓ Complete | 0 | `rounding_soundness_nonneg` proven |
| SMT Encoding | 5.6 | ✓ Complete | 0 | All previously documented numeric decode branches discharged |
| Val.beq_comm | Helper | ✓ Complete | 0 | Tuple/list recursion discharged |
| Satisfiability | Cor. | ✓ Complete | 0 | Both directions fully proven |

**Total Sorry Terms**: 0

---

## 7. Correspondence to Paper Notation

| Paper | Lean | File |
|-------|------|------|
| Γ ⊢ φ : prop | `FormulaWellTyped Γ φ` | Types.lean |
| ⟦φ⟧(c) | `evalFormula φ c` | TypeSoundness.lean |
| c ≽ε c' | `weakEpsDominates objs ε y y'` | Dominance.lean |
| c ≻ε c' | `strictEpsDominates objs ε y y'` | Dominance.lean |
| σ(d) | `Direction.sign d` | Dominance.lean |
| encode(φ) | `encodeFormula φ P idx` | SMTEncoding.lean |
| ⌈n/P⌉ | `(n + P - 1) / P` | SMTEncoding.lean |

---

## 8. Design Decisions

### Float Representation (Scaling Convention)

- Floats are represented as scaled integers (`Val.vfloat : Int → Val`)
- The precision factor P is used to align domains for SMT encoding
- This avoids non-linear arithmetic in SMT solvers
- **Pre-scaling assumption**: All float values and comparison thresholds are assumed to be PRE-SCALED by P before entering the formalization:
  - `Val.vfloat r` stores r = v * P where v is the true floating-point value
  - Thresholds n in `Atom.geq x n` are pre-scaled: n = threshold * P
- The SMT encoding is "passthrough" - no additional scaling during encoding

### Empty Set Membership
- `x ∈ []` encodes to `SMTFormula.ff` (always false)
- This is always unsatisfiable, which is correct semantics

### Comparison Thresholds
- Restricted to non-negative values per paper spec
- Negative thresholds would need different ceiling formula

### Tuples
- Included in type grammar for completeness
- Not supported in atoms (blocked by type system)
- `ConfigRespectsContext` uses `True` for tuples (simplified)

---

## 9. What's Complete

All major proof obligations have been completed:

- ✓ All boolean connective cases (and, or, not, impl) in `smt_encoding_soundness`
- ✓ Equality atoms (eq, neq) using `EqualityDecodeCorrespondence`
- ✓ Comparison atoms (geq, leq) using `NumericDecodePreservation`
- ✓ All membership atom cases (empty, singleton, multi-element lists) via `mem_encoding_soundness`
- ✓ Val.beq_comm for non-tuple cases (vbool, vint, vfloat, vstr)
- ✓ Rounding soundness theorem for ceiling division
- ✓ Satisfiability preservation (both directions)
- ✓ Type soundness and ε-dominance composition (fully proven)
- ✓ Definedness helper lemmas (encoding_definedness, encoding_definedness_rev)

### Documented Edge Cases

None in Lean source (`rg` over `tvl/proofs/TVL/*.lean` returns no `sorry` terms).

### Future Extensions

- Formalize promotion correctness (Theorem 6.15)
- Add Welch's t-test properties for statistical dominance
- Mechanize sequential testing error bounds
- Extend the formalization to cover `cvars`/`policies` (RFC 0001) and
  `composites` (RFC 0002) — currently unformalized, see the coverage note
  above and `formalization/tvl-formal-semantics.md` §1.4

---

## 10. Build Instructions

```bash
# Install elan (Lean version manager)
curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh

# Build the proofs
cd tvl/proofs
lake exe cache get    # Download pre-built Mathlib (saves ~30 min)
lake build
```

**Expected Output**:
```
Build completed successfully (6136 jobs).
```

---

## 11. Conclusion

The TVL mechanized proofs provide strong formal guarantees for the core theoretical foundations:

- **Type Soundness (Theorem 4.2)**: Guarantees that well-typed formulas always evaluate to boolean values
- **ε-Dominance Composition (Lemma 6.18)**: Proves the key property used in multi-objective optimization
- **Rounding Soundness (Lemma 5.4)**: Establishes the correctness of float-to-integer encoding
- **QF-LIA Encoding Soundness (Theorem 5.6)**: Proves the bidirectional correspondence between SMT satisfiability and TVL formula truth

All major proof obligations have been completed with no `sorry` terms in Lean source.

**Total Lines of Proof Code**: ~950 (excluding Mathlib)
**Theorems Fully Proven**: 5 (Type Soundness, ε-Composition, Rounding Soundness, SMT Encoding, Satisfiability)
**Documented Edge Cases**: 0

---

## Runtime (TVL 1.3)

**DRAFT; language results and generic mathematics only.** The results are stated
against formal semantics §§9.7/12 and RFC 0003 as published in this repository.
This scope applies the language/evaluator boundary of RFC 0003 §3.5:
complete-history meaning, static declarations/composition, abstract verdict joins
and generic probability. How an evaluator decides from partial evidence is outside
this library. This section supersedes the historical core summary's old
promotion-gate roadmap note.

Each entry uses exactly one class. A helper's class concerns only its own statement and never upgrades a WEAKER or OPEN result.

| Class | Meaning |
|---|---|
| SUBSTANTIVE | Proved, with content beyond its definitions. |
| BY-CONSTRUCTION | Proved, but true by definition or the chosen representation/transition construction. |
| WEAKER: what dropped | Proved, with the named part of the original obligation omitted. |
| OPEN | Unproved target defined as a proposition, never an assumption. |

| Theorem | File | Class | Checked scope |
|---|---|---|---|
| `gate_sound` | `TVL/Gate.lean` | SUBSTANTIVE | Legacy ordered decision; completeness requires coherent evaluated predicates. |
| `gate_complete` | `TVL/Gate.lean` | SUBSTANTIVE | Legacy ordered decision; completeness requires coherent evaluated predicates. |
| `gate_correct` | `TVL/Gate.lean` | SUBSTANTIVE | Legacy ordered decision; completeness requires coherent evaluated predicates. |
| `join_empty` | `TVL/Gate.lean` | BY-CONSTRUCTION |  |
| `join_promote_iff` | `TVL/Gate.lean` | SUBSTANTIVE |  |
| `backend_profile_roundtrip` | `TVL/Runtime/Backend.lean` | BY-CONSTRUCTION | Normalized representable fields round-trip under supplied bijective codecs. No specific codec, adapter or float/rational numerical equivalence. |
| `mass_nonneg` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `upper_mono_count` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `lower_mono_count` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `cast_upper` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `cast_lower` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `real_mass_nonneg` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `real_mass_total` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `real_tail_complement` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `real_upper_mono_count` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `real_mass_succ` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `real_upper_shift` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `real_upper_succ` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `real_upper_mono_parameter` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `tail_mono_p` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE | Exact finite binomial sums, parameter/count monotonicity and rational casts. |
| `upper_mono_parameter` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `lower_antitone_parameter` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `bad_lower_bound` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE |  |
| `horizon_false_alarm` | `TVL/Runtime/BinomialGeneric.lean` | SUBSTANTIVE | Generic finite union bound, without independence or any verdict procedure. |
| `pmf_binomial_mass` | `TVL/Runtime/BinomialLaw.lean` | SUBSTANTIVE |  |
| `pmf_binomial_upper` | `TVL/Runtime/BinomialLaw.lean` | SUBSTANTIVE |  |
| `binomial_good_window` | `TVL/Runtime/BinomialLaw.lean` | SUBSTANTIVE |  |
| `binomial_bad_window` | `TVL/Runtime/BinomialLaw.lean` | SUBSTANTIVE |  |
| `compiled_contract_correct_statement` | `TVL/Runtime/Compiler.lean` | OPEN | Normalized-language compiler target; no actual source parser, normalization or wire-projection proof. |
| `raw_bounds_glb` | `TVL/Runtime/Compose.lean` | SUBSTANTIVE |  |
| `checked_bounds_meet_iff` | `TVL/Runtime/Compose.lean` | BY-CONSTRUCTION |  |
| `compose_partial_statement` | `TVL/Runtime/Compose.lean` | OPEN | OPEN static normalized-contract GLB/reachability target. Authored rule identity/survival, approval/severity/deploy order, repeat bounds and provenance remain; platform grants and registration are external. Catalogue-wide refinement is unproved. |
| `severity_meet_glb` | `TVL/Runtime/Declarations.lean` | SUBSTANTIVE |  |
| `absent_notify_severity` | `TVL/Runtime/Declarations.lean` | BY-CONSTRUCTION |  |
| `deploy_meet_glb` | `TVL/Runtime/Declarations.lean` | SUBSTANTIVE | `optimize.deploy` order (`never` stricter than `if_promoted`, RFC 0003 §7.6); finite case analysis, like `severity_meet_glb`. |
| `absent_deploy` | `TVL/Runtime/Declarations.lean` | BY-CONSTRUCTION |  |
| `conservative_extension` | `TVL/Runtime/Extension.lean` | BY-CONSTRUCTION | Empty-runtime embedding preserves the semantic product model and gate join. |
| `no_promotion_monitors` | `TVL/Runtime/Extension.lean` | BY-CONSTRUCTION |  |
| `structural_projection` | `TVL/Runtime/Extension.lean` | BY-CONSTRUCTION | Stored legacy fields are projected unchanged. Runtime spelling exclusion from source Γ/generated variables is not modeled or proved. |
| `promotion_refinement` | `TVL/Runtime/Extension.lean` | SUBSTANTIVE |  |

### Scope and remaining gaps

- `History.lean` defines complete-history event/selector/predicate meaning only;
  how an evaluator decides from partial evidence is outside this library (RFC 0003
  §3.5).
- `Gate.lean` consumes supplied evaluated predicates/verdicts. Coherence of the
  legacy test results is an explicit completeness premise; numerical tests and
  evaluator implementations are not certified by the join algebra.
- Generic exact rational/real tails are connected to `PMF.binomial`; parameter
  inequalities supply `GoodWindow`/`BadWindow` stochastic-domination contracts.
  These generic names denote tail-law inequalities, without unresolved counts or
  verdict definitions. No real population's independence, representativeness,
  attribution or unbiased selection is inferred. The finite union bound needs
  per-event bounds and a predesignated allocation; it needs no independence.
- `compose_partial_statement` is OPEN and ranges over static normalized
  contracts; its record and validity predicate carry no enabled actions.
  `NormalizedRule` contains only authored identity, approval, repeat bounds,
  severity and `deploy`. Rule survival and the approval/severity/deploy orders are stated; standing
  grants (their scopes, limits and expiry, and any order on them) are outside this
  library. Static composition neither compares grants nor checks enabled
  capabilities.
  Full catalogue validation, opaque identity binding, pack activation and source
  refinement remain unproved. Equal floor-provenance maps are still required.
- `Compiler.lean` states an OPEN declaration-normalization/projection
  obligation over a normalized source fragment. It is not an
  implementation or proof of the Python compiler, parser or canonical wire codec.
- Product erasure is BY-CONSTRUCTION, not syntax-level runtime-name exclusion
  from the typing context or a source-to-SMT preservation proof.
- Backend-profile fields round-trip under supplied token/numeric equivalences.
  The codec definitions live in `python/tvl/backend_profile_codec.py`.
  The theorem does not verify those concrete serializers, IEEE-754 conversions,
  deployed adapters, or floating-point/rational verdict equivalence.
- No existing core Lean file is changed. Building this library establishes local
  mathematical compilation; it does not establish operational readiness.

### Reproduce

```bash
export PATH=$HOME/.elan/toolchains/leanprover--lean4---v4.28.0-rc1/bin:$PATH
cd proofs
timeout 3000 lake build
rg -n '^import' Main.lean TVL --glob '*.lean'
```

`Main.lean` imports every module. Mathlib and Lean stay pinned by the
existing manifest/toolchain; the TVL 1.3 modules add no dependency. See README.md
for the boundary and trusted-input limits.


## RFC 0004: Reactive notification guards (TVL 1.4)

`TVL/Runtime/Guards.lean` is imported by `Main.lean`. The model uses strong Kleene folds,
a validated notify-only rule type, unchanged occurrence identity/scope, and the exact monitor
unless graph (attempt guards add no edge). These statements do not prove controller execution,
source parsing, wire projection, attempt lifecycle or undecided-run implementation.

| Statement | Class | Scope |
|---|---|---|
| `undecided_never_suppresses` | SUBSTANTIVE | Arbitrary valuation and guard replacement by UNDECIDED; arbitrary finite conjunction/disjunction lists, including shared guards. |
| `notify_only` | BY-CONSTRUCTION | The validated reactive rule type has only the notify action; no effect authorization is introduced by the type. |
| `guards_preserve_identity` | BY-CONSTRUCTION | Guard evaluation adds a delivery decision while preserving identity and scope. |
| `no_mutual_silencing` | SUBSTANTIVE | Finite nonempty S of simultaneously triggered rules, non-FALSE only_while, no TRUE attempt inhibitor, and monitor inhibitors confined to sources in S; absence of nonempty directed cycles yields a sink and a delivered rule. The graph includes all rules, and outcome sources are supplied after validation. External inhibitors remain allowed. |

No new OPEN theorem or admitted proof is used in this module. Formal semantics §13 specifies
attempts and undecided histories relationally; this is outside these four Lean claims.

## RFC 0005: Persistence and exact mean comparison (TVL 1.5)

`TVL/Runtime/Persistence.lean`, imported by `Main.lean`, models arbitrary finite
lists of base window verdicts. Missing slots must already be represented as
UNKNOWN by the caller. The model does not select windows or validate the authored
`1 ≤ k ≤ n ≤ 168` constraints; its mathematical results hold for every natural
threshold, including zero, and every finite list.

| Statement | Class | Scope |
|---|---|---|
| `breach_necessity` | SUBSTANTIVE | A BREACHED persistence result requires at least k already BREACHED base slots. No UNKNOWN slot is counted as an established breach. |
| `refinement_bounds` | SUBSTANTIVE | Arbitrary positional refinement preserves decided slots and narrows the lower/upper possible breach-count interval. |
| `breached_iff_all_completions` | SUBSTANTIVE | BREACHED iff every completion has at least k breaches. Uniform MET replacement constructs the lower endpoint. |
| `met_iff_all_completions` | SUBSTANTIVE | MET iff every completion has fewer than k breaches. Uniform BREACHED replacement constructs the upper endpoint. |
| `unknown_iff_mixed_completions` | SUBSTANTIVE | UNKNOWN iff there exist both a meeting and a breaching complete history; completion existence is constructed rather than assumed. |
| `decided_refinement` | SUBSTANTIVE | Resolving any collection of UNKNOWN slots cannot reverse a definite MET or BREACHED result. |
| `mean_lte_iff`, `mean_gte_iff` | SUBSTANTIVE | For positive natural member count and exact rational sum/bound, division comparison equals comparison of sum against count times bound, in either direction. Equality is included. |

`Refines` preserves list positions; `Completion` additionally has no UNKNOWN
slots. These statements concern the historical condition, not the current base
verdict. They do not establish event eligibility, delivery or replay behavior,
false-alarm probabilities, source-contract correctness, census completeness,
finalization, attestation correctness, parsing, or controller execution. Exact
rational comparison does not certify a decimal codec or bounded-resource
arithmetic implementation. There are no new admitted proofs or assumptions.

### Local verification

The full build command `/home/nimrod/.elan/bin/lake build`, run from `proofs/`,
exited **1** during dependency acquisition. Its final lines were:

```text
warning: manifest out of date: git revision of dependency 'mathlib' changed; use `lake update mathlib` to update it
info: mathlib: cloning https://github.com/leanprover-community/mathlib4.git
error: external command 'git' exited with code 128
```

Full output is in `/tmp/tvl-impl1-lake-build.log`. No dependency/configuration
files were changed. The warning is reported without inferring its cause:
`lakefile.lean`'s requested Mathlib revision, `lake-manifest.json`'s resolved
Mathlib revision, and the existing sibling cache's `git rev-parse HEAD` all equal
`6a596ab93c06c66333edc70d52d8955648f6669c`; the manifest's `inputRev` is null.

A separate direct Lean check of this new module exited **0**, with no diagnostics,
using read-only existing cached dependency libraries. This checks the new module,
not the complete `Main.lean` dependency graph. From the worktree root, reproduce:

```bash
LEAN_PATH=$(find ../runtime-1-3/proofs/.lake/packages -path '*/.lake/build/lib/lean' -type d -printf '%p:') \
  /home/nimrod/.elan/toolchains/leanprover--lean4---v4.28.0-rc1/bin/lean \
  proofs/TVL/Runtime/Persistence.lean
```

The direct check's diagnostic log is `/tmp/tvl-impl1-direct-lean.log` (empty on
success). `git diff --check` also exited 0. These are local mathematical checks,
not runtime implementation evidence or a claim that the full library builds.
