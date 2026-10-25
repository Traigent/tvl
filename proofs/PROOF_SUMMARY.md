# TVL Mechanized Proofs - Comprehensive Summary for Review

**Date**: 2026-02-01
**Lean Version**: 4.28.0-rc1
**Mathlib**: Commit 6a596ab9
**Historical baseline build status (2026-02-01)**: All modules compiled successfully.

**Current check**: CI (`.github/workflows/lean-proofs.yml`) runs `lake build` in `proofs/`
on every change and fails if any Lean source contains `sorry` (an unproved placeholder),
`admit` or an `axiom` declaration. The last local check of the RFC 0005 module is described in
[Local verification](#local-verification).

**Numbering**: the Lean docstrings and the core sections below keep the numbering of the
original TVL paper (Theorem 4.2, Lemma 5.4, Theorem 5.6, Lemma 6.18). Each core section gives
the matching statement in `formalization/tvl-formal-semantics.md`.

> **Coverage note (added after RFC 0001/0002):** this proof tree covers the
> TVL core subset as it stood on 2026-02-01 — `tvars`, `constraints`,
> `objectives`, and `promotion_policy`. **`cvars`/`policies` (RFC 0001,
> 2026-06-05) and `composites` (RFC 0002, 2026-06-06) are not formalized
> here**; nothing in `proofs/TVL/*.lean` models those constructs. See
> `formalization/tvl-formal-semantics.md` §1.4 for the full disclosure. The
> linter reports this with the info diagnostic `outside_proved_subset`, once
> per construct family present (`cvars`, `policies`, `composites`); info
> severity never affects the exit status.

---

## Overview

This document provides a comprehensive summary of the Lean 4 formalizations of key theorems from the TVL (Tuned Variables Language) paper. The proofs establish the theoretical foundations for the TVL constraint system used in AI agent optimization.

For OPAL declarative-core mechanization (assignment vs. `in`, `given`, callable interfaces, nested template typing/completeness), see:

- [`OPALCORE_README.md`](OPALCORE_README.md)

---

## File Structure

Line counts are `wc -l` on 2026-10-24. Theorem and lemma numbers in the comments are the
original paper's (see **Numbering** above).

```
proofs/
├── lakefile.lean           # Lake project configuration (with Mathlib)
├── lake-manifest.json      # pinned dependency revisions
├── lean-toolchain          # Lean 4.28.0-rc1
├── Main.lean               # Entry point; imports every module below
└── TVL/
    ├── Basic.lean          # Core definitions (162 lines)
    ├── Types.lean          # Type system formalization (133 lines)
    ├── TypeSoundness.lean  # Theorem 4.2 (194 lines)
    ├── SMTEncoding.lean    # SMT (satisfiability modulo theories) encoding: Lemma 5.4, Theorem 5.6 (1988 lines)
    ├── Dominance.lean      # Lemma 6.18 (119 lines)
    ├── OPALCore.lean       # OPAL declarative core (929 lines; see OPALCORE_README.md)
    ├── Gate.lean           # Promotion decision join (84 lines; see Runtime (TVL 1.3))
    └── Runtime/            # TVL 1.3, 1.4 and 1.5 modules (see the sections below)
        ├── History.lean, Declarations.lean, Compose.lean, Compiler.lean
        ├── Extension.lean, Backend.lean, BinomialGeneric.lean, BinomialLaw.lean
        ├── Guards.lean       # TVL 1.4 (RFC 0004)
        └── Persistence.lean  # TVL 1.5 (RFC 0005)
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

| Rule | Lean Constructor | Formal semantics |
|------|------------------|------------------|
| T-Eq | `AtomWellTyped.tEq` | §4.6 |
| T-Neq | `AtomWellTyped.tNeq` | §4.6 |
| T-Cmp (≥) | `AtomWellTyped.tGeq` | §4.6 |
| T-Cmp (≤) | `AtomWellTyped.tLeq` | §4.6 |
| T-Mem | `AtomWellTyped.tMem` | §4.6 |
| T-And | `FormulaWellTyped.tAnd` | §4.8 |
| T-Or | `FormulaWellTyped.tOr` | §4.8 |
| T-Not | `FormulaWellTyped.tNot` | §4.8 |
| T-Impl | `FormulaWellTyped.tImpl` | §4.8 |

The other §4.6–4.7 rules (T-Interval, T-TVarEq and the tuple rules) are not modelled.

### Ty.isAtomType Predicate

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

### Theorem 4.2 (paper numbering; formal semantics Theorem 4.1) - **FULLY PROVEN** ✓

Formal semantics: Theorem 4.1 (Denotation Totality), for the atoms and connectives above.

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

**Lines of Code**: 194
**Sorry Count** (unproved `sorry` placeholders in the file): 0

---

## 4. ε-Dominance Composition (TVL/Dominance.lean)

### Lemma 6.18 (paper numbering; formal semantics Lemma 9.2) - **FULLY PROVEN** ✓

Formal semantics: Lemma 9.2 (ε-Dominance Composition). `normalized_diff_composition` proves it
for one objective; `eps_dominance_composition_list` applies it to every objective of a list.

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

**Proof**: Algebraic manipulation, closed by `linarith` (Lean's tactic for linear arithmetic).
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

This Lean theorem only states `True`; nothing about strict dominance is proved. The
counter-example is given in the file's comments. It matches the counter-example in the formal
semantics (§9.8, after Lemma 9.2), with two maximized objectives and ε = δ = 10:
- y₁ = [0, 0], y₂ = [-20, 10], y₃ = [-10, -10]
- y₁ ≻ε y₂ (y₁ − y₂ = [20, -10]: better by more than ε on A, within ε on B)
- y₂ ≻ε y₃ (y₂ − y₃ = [-10, 20]: within ε on A, better by more than ε on B)
- But y₁ − y₃ = [10, 10], so y₁ ≽₂ε y₃, NOT y₁ ≻₂ε y₃

**Lines of Code**: 119
**Sorry Count** (unproved `sorry` placeholders in the file): 0

---

## 5. SMT (Satisfiability Modulo Theories) Encoding Soundness (TVL/SMTEncoding.lean)

An SMT solver decides whether a logical formula over
integers (here, quantifier-free linear integer arithmetic, QF-LIA) has a satisfying model.

### Rounding Soundness (Lemma 5.4, paper numbering) - **FULLY PROVEN** ✓

**Statement** (what the Lean theorem proves): for natural numbers v and n and a precision
factor P > 0,
```
v · P ≥ n ⟺ v ≥ ⌈n/P⌉        where ⌈n/P⌉ is computed as (n + P - 1) / P
```

This is a ceiling-division identity on natural numbers (`PrecisionFactor` is `Nat`). The formal
semantics' Lemma 8.1 is the scaled form of the same rounding fact: for a P-aligned value v and a
threshold n, `v ≥ n ⟺ scale(v) ≥ ⌈n · P⌉` with `scale(v) = v · P` (and the matching ≤, >, <
forms). Both are instances of `x ≥ t ⟺ x ≥ ⌈t⌉` for an integer x: the Lean lemma takes x = v
and t = n/P (it moves a threshold n on the scaled quantity v · P back to v), while Lemma 8.1 takes
x = scale(v) and t = n · P (it moves a threshold n on v to the scaled integer). So the Lean lemma
divides by P where Lemma 8.1 multiplies, and the Lean lemma does not prove Lemma 8.1. The Lean
encoding takes values and thresholds as already scaled by P (see
[Design Decisions](#8-design-decisions)), so the rounding of `n · P` is outside the Lean model, and
`smt_encoding_soundness` does not use this lemma. Lemma 8.1 is not mechanized.

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

### SMT Encoding Soundness (Theorem 5.6, paper numbering; formal semantics Theorem 8.1, formula-level) - **PROVEN under the hypotheses below** ✓

Formal semantics: a formula-level form of Theorem 8.1. Values and thresholds are taken as
already scaled, and the §8.3 domain assertions are not modelled.

**Statement**: if encoding φ succeeds (`encodeFormula φ P idx = some ψ`), the decoder is
well formed (`WellFormedDecode`), the model m assigns every variable of φ (`ModelDefinedOn m φ`)
and the decoder gives an integer value to every variable used in a comparison
(`FormulaNumericInvariant`), then
```
evalSMT ψ m = some true ⟺ ⟦φ⟧(decode(m)) = true
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
    (hmodel : ModelDefinedOn m φ)
    (hinv : FormulaNumericInvariant decode_val φ)
    (_encode_val : VarName → Val → Option SMTVal)
    (_roundtrip : ∀ x v, (do let n ← _encode_val x v; decode_val x n) = some v)
    (ψ : SMTFormula)
    (henc : encodeFormula φ P idx = some ψ) :
    evalSMT ψ m = some true ↔
    evalFormula φ (decodeModel m decode_val) = some true
```

**WellFormedDecode structure**:

```lean
structure WellFormedDecode (decode_val : SMTVar → SMTVal → Option Val)
    (idx : Val → Option Nat) where
  definedness : DecodeDefinedness decode_val
  numeric : NumericDecodePreservation decode_val
  equality : EqualityDecodeCorrespondence decode_val idx
```

**ModelDefinedOn precondition**:

The main theorem requires the SMT model to be defined on all formula variables:

```lean
def ModelDefinedOn (m : SMTModel) (φ : Formula) : Prop :=
  ∀ x, x ∈ formulaVars φ → ∃ n, m x = some n
```

This handles the semantic corner case where SMT `ff` (for empty list membership)
is always defined, but TVL `x ∈ []` requires the variable to be defined.

**NumericDecodePreservation**:

This is a hypothesis on the decoder (a field of `WellFormedDecode`), not a Lean `axiom`.
It requires that whenever a decoded value has an integer representation, that integer equals
the SMT integer it was decoded from. A decoder that returns `vint (n + 1)` for SMT value `n`
does not satisfy it.

```lean
def NumericDecodePreservation (decode_val : SMTVar → SMTVal → Option Val) : Prop :=
  ∀ x n v, decode_val x n = some v → ∀ m, v.toInt? = some m → m = n
```

For boolean/string values, where `toInt?` returns none, it imposes no constraint.

**FormulaNumericInvariant**: for every comparison atom (`geq`, `leq`) in φ, every value the
decoder returns for that variable has an integer representation.

**Proof Structure**:

- **Induction on φ**: All 5 cases (atom, and, or, not, impl) fully addressed
- **Boolean connectives (and, or, not, impl)**: ✓ Fully proven using definedness lemmas
- **Equality atoms (eq, neq)**: ✓ Proven using `EqualityDecodeCorrespondence`
- **Comparison atoms (geq, leq)**: ✓ Proven using `NumericDecodePreservation`
- **Membership atoms (mem)**:
  - ✓ Empty list `[]`: Proven (encodes to `ff`, trivially false)
  - ✓ Singleton `[v]`: Proven using `Val.beq_comm`, the symmetry of Lean's Boolean equality `==` (`BEq`; see Helper Lemmas)
  - ✓ Multi-element `v :: v' :: vs`: Proven via `mem_encoding_soundness` with list induction

**Helper Lemmas**:

- `Val.beq_comm`: symmetry of Lean's Boolean equality (`BEq`, the `==` operator) on `Val`,
  `(a == b) = (b == a)`, for all constructors (including tuples)
- `mem_encoding_soundness`: Membership encoding (fully proven via list induction)
- `mem_encoding_undefined`: for a **nonempty** list S, when the SMT model has no value for x,
  the encoding of `x ∈ S` evaluates to undefined (the empty list encodes to `ff`, which is
  always defined)
- `mem_encoding_defined`: When SMT model has a value, membership encoding is defined
- `encoding_definedness`: SMT definedness → formula definedness (fully proven)
- `encoding_definedness_rev`: formula definedness → SMT definedness (fully proven)

**Proof holes**: none (zero `sorry` terms).

**Edge case handled by a hypothesis**: `x ∈ []` encodes to `ff`, which is defined even when the
model has no value for x, while TVL `x ∈ []` is then undefined. The `ModelDefinedOn` hypothesis
excludes this case.

### Satisfiability Preservation (Corollary) - **FULLY PROVEN** ✓

**Statement**:

```
(∃ c ∈ Config: ⟦φ⟧(c) = true) ⟺ SAT(encode(φ))
```

Formal semantics: Corollary 8.1, in the same formula-level form.

The Lean theorem `satisfiability_preservation` states
`(∃ c, evalFormula φ c = some true) ↔ (∃ m, ModelDefinedOn m φ ∧ evalSMT ψ m = some true)`,
under the decoder hypotheses above plus an encoder `encode_val` that is total and round-trips
through `decode_val`.

**Proof Status**:

- **Backward direction**: ✓ Proven using `smt_encoding_soundness`
- **Forward direction**: ✓ Proven using `decode_encode_config_agree` and `evalFormula_ext`

**Lines of Code**: 1988
**Sorry Terms**: 0

---

## 6. Verification Summary

| Theorem | Paper Ref | Formal semantics | Status | Sorry Count | Notes |
|---------|-----------|------------------|--------|-------------|-------|
| Type Soundness | 4.2 | Theorem 4.1 | ✓ Complete | 0 | Requires `ConfigRespectsContext` |
| ε-Composition | 6.18 | Lemma 9.2 | ✓ Complete | 0 | `normalized_diff_composition` proven |
| Rounding Soundness | 5.4 | none (Lemma 8.1 is the scaled form, not mechanized) | ✓ Complete | 0 | Natural-number ceiling division |
| SMT Encoding | 5.6 | Theorem 8.1, formula-level | ✓ Complete | 0 | Requires the decoder, model and encoding hypotheses |
| Val.beq_comm | Helper | | ✓ Complete | 0 | Tuple/list recursion discharged |
| Satisfiability | Cor. | Corollary 8.1, formula-level | ✓ Complete | 0 | Both directions fully proven |

**Total Sorry Terms**: 0

---

## 7. Correspondence to Paper Notation

| Paper | Lean | File |
|-------|------|------|
| Γ ⊢ φ : prop | `FormulaWellTyped Γ φ` | Types.lean |
| ⟦φ⟧(c) | `evalFormula φ c` | TypeSoundness.lean |
| σ(d) · (y − y') (one objective) | `normalizedDiff d y y'` | Dominance.lean |
| c ≽ε c' (all objectives) | hypotheses of `eps_dominance_composition_list` (no named definition) | Dominance.lean |
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
- Comparison atoms take any integer threshold (`Atom.geq`/`Atom.leq` take an `Int`), and the
  grammar admits signed numbers
- Only the separate rounding lemma `rounding_soundness_nonneg` is restricted to natural numbers;
  negative thresholds would need a different ceiling formula there

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
- ✓ Val.beq_comm for all `Val` constructors, including tuples
- ✓ Rounding soundness theorem for ceiling division
- ✓ Satisfiability preservation (both directions)
- ✓ Type soundness and ε-dominance composition (fully proven)
- ✓ Definedness helper lemmas (encoding_definedness, encoding_definedness_rev)

### Proof holes and edge cases

No `sorry` terms: `rg -n '\bsorry\b' proofs/TVL --glob '*.lean'` returns nothing, and CI rejects
them. The empty-membership case is handled by the `ModelDefinedOn` hypothesis (Section 5).

### Future Extensions

- Formalize promotion correctness (formal semantics Proposition 9.1 and the statistical tests
  of §9.4–9.5; `Gate.lean` covers only the decision join over supplied test results)
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

# Build the proofs (from the repository root)
cd proofs
lake exe cache get    # Download pre-built Mathlib (saves ~30 min)
lake build
```

**Expected final line**: `Build completed successfully (N jobs).` The job count depends on
the module set; it was 6136 at the 2026-02-01 baseline, before the Gate, OPAL and Runtime
modules were added.

---

## 11. Conclusion

The core TVL proofs establish, for the modelled subset (atoms `=`, `≠`, `≥`, `≤`, `∈` over
non-tuple TVARs, and the four connectives):

- **Type Soundness (Theorem 4.2)**: a well-typed formula evaluates to a boolean under every
  configuration that respects the typing context (`ConfigRespectsContext`)
- **ε-Dominance Composition (Lemma 6.18)**: weak ε-dominance composes with tolerance 2ε
- **Rounding Soundness (Lemma 5.4)**: the natural-number ceiling-division identity
  `v · P ≥ n ⟺ v ≥ ⌈n/P⌉`; the semantics' scaled form `v ≥ n ⟺ v · P ≥ ⌈n · P⌉` (Lemma 8.1) is not mechanized
- **QF-LIA Encoding Soundness (Theorem 5.6)**: SMT truth of the encoded formula matches TVL truth
  under the decoded model, given the decoder, model-totality, numeric-invariant and successful-encoding
  hypotheses of Section 5, with values and thresholds already scaled

These core files contain no `sorry` terms.

**Lines of core proof code**: 2596 (`Basic`, `Types`, `TypeSoundness`, `SMTEncoding`, `Dominance`;
`wc -l`, 2026-10-24; the whole `proofs/` library, excluding Mathlib, is 4808 lines)
**Theorems proven**: 5 (Type Soundness, ε-Composition, Rounding Soundness, SMT Encoding, Satisfiability)

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
| `compose_partial_statement` | `TVL/Runtime/Compose.lean` | OPEN | OPEN static normalized-contract target for the greatest lower bound (GLB) and reachability. Authored rule identity/survival, approval/severity/deploy order, repeat bounds and provenance remain; platform grants and registration are external. Catalogue-wide refinement is unproved. |
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
  inequalities supply `GoodWindow`/`BadWindow` stochastic-domination contracts
  (`BinomialGeneric.lean`: a count K is a good window when each upper tail `Pr[K ≥ j]` is at
  most the exact binomial upper tail at θ, and a bad window when it is at least that tail).
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
  refinement remain unproved. Here identity binding is how a contract's identity is tied to
  its source, and pack activation is the authorized registration that gives a tenant-floor
  pack its authority (formal semantics §12.12; RFC 0003 §9.4). Compatible contracts must still
  have equal floor-provenance maps (`ContractCompatible` in `Compose.lean`): the record, per
  composed monitor taken from a pack, of which pack monitor it came from (RFC 0003 §9.4, step 7).
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

`TVL/Runtime/Guards.lean` is imported by `Main.lean`. The model folds guard lists with the
three-valued (strong Kleene) connectives of formal semantics Definition 13.8: a conjunction is
FALSE if any guard is FALSE, TRUE if every guard is TRUE, and UNDECIDED otherwise; a
disjunction is TRUE if any guard is TRUE, FALSE if every guard is FALSE, and UNDECIDED
otherwise. It also uses a validated notify-only rule type, unchanged occurrence identity/scope,
and the exact monitor unless graph of Definition 13.10 (an edge from a rule's source monitor to
each monitor named by an episode guard in its `unless`; attempt guards add no edge). These statements do not prove controller execution,
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
lists of base window verdicts: one slot per counted window of the source monitor, each MET,
BREACHED or UNKNOWN. In RFC 0005 §2.2 the threshold k is `breached_in` and the list length n is
`of_last`; the result is BREACHED when at least k slots are BREACHED. Missing slots must already
be represented as UNKNOWN by the caller. The model does not select windows or validate the authored
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

When this module was added, a local full `lake build` in `proofs/` stopped with exit
status **1** while fetching dependencies (cloning Mathlib failed). Its final lines were:

```text
warning: manifest out of date: git revision of dependency 'mathlib' changed; use `lake update mathlib` to update it
info: mathlib: cloning https://github.com/leanprover-community/mathlib4.git
error: external command 'git' exited with code 128
```

No dependency or configuration files were changed. `lakefile.lean` and
`lake-manifest.json` both pin Mathlib `6a596ab93c06c66333edc70d52d8955648f6669c`; the
manifest's `inputRev` is null. The cause of the warning was not investigated.

A direct Lean check of `TVL/Runtime/Persistence.lean` alone, against already-built
Mathlib libraries, exited **0** with no diagnostics. This checks that one module, not the
complete `Main.lean` dependency graph. With the dependencies built (see
[Build Instructions](#10-build-instructions)), the same check is:

```bash
cd proofs
lake env lean TVL/Runtime/Persistence.lean
```

These are mathematical checks of the Lean model, not evidence about any runtime
implementation. The CI workflow above is the check of the full library.
