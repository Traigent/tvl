# TVL Formal Foundations: Status and Roadmap

**Purpose**: What is formalized in TVL, where each result lives, and what remains
**Audience**: Traigent engineering, academic collaborators, technical due diligence

---

## Summary

TVL is a **specification language** for AI agent configuration. This page was first written in January 2026 as a
plan for its formal foundations. Most of the core items it planned now exist: a formal semantics, paper proofs of the
core results, and Lean 4 proofs of several of them. This revision records that state for TVL 1.5 and lists the work
that remains. No dates are set for the remaining work.

The authority for meaning is [`tvl-formal-semantics.md`](tvl-formal-semantics.md) (the formal semantics). The
mechanized results and their exact statements are in [`../proofs/PROOF_SUMMARY.md`](../proofs/PROOF_SUMMARY.md).
Where this page and those documents differ, they win.

### Current state

| Item | Status | Where |
|------|--------|-------|
| **Concrete syntax** | Done | `spec/grammar/tvl.ebnf` (EBNF grammar) and `spec/grammar/tvl.schema.json` (JSON Schema) |
| **Abstract syntax** | Done | Formal semantics §2 |
| **Denotational semantics** | Done for the core; runtime extensions in §§12–14 | Formal semantics §§3–6 and §9 |
| **Type soundness** (denotation totality) | Paper proof; Lean proof for the core subset | Theorem 4.1; `type_soundness` in `proofs/TVL/TypeSoundness.lean` |
| **Decidability** | Paper proofs for finite-domain structural constraints; not mechanized | Theorems 7.1–7.4 |
| **Encoding soundness** | Paper theorem; Lean proof of a formula-level form | Theorem 8.1, Corollary 8.1; `smt_encoding_soundness`, `satisfiability_preservation` in `proofs/TVL/SMTEncoding.lean` |
| **ε-dominance composition** | Paper proof; Lean proof | Lemma 9.2; `normalized_diff_composition` in `proofs/TVL/Dominance.lean` |
| **Promotion correctness** | Scoped statement; not mechanized | Proposition 9.1; listed as future work in `PROOF_SUMMARY.md` |
| **Runtime extensions** (TVL 1.3–1.5) | Lean results, each classed by strength; two statements are OPEN (not proved) | `PROOF_SUMMARY.md`, sections "Runtime (TVL 1.3)", "RFC 0004" and "RFC 0005"; `proofs/TVL/Gate.lean`, `proofs/TVL/Runtime/` |
| **`cvars`, `policies`, `composites`** (RFC 0001, RFC 0002) | Not formalized | Formal semantics §1.4 |

**Scope of the Lean results for the core.** They cover the core subset as it stood on 2026-02-01: `tvars`,
`constraints`, `objectives` and `promotion_policy`. The Lean atoms are `=`, `≠`, `≥`, `≤` and `∈` over non-tuple
TVARs, with `and`, `or`, `not` and implication. Float values and thresholds are taken as already scaled to integers,
and comparison thresholds are non-negative. The encoding theorem is stated over the encoded formula; it does not model
the domain assertions of semantics §8.3. See `PROOF_SUMMARY.md` §2 and §8.

**Build status.** `PROOF_SUMMARY.md` records that all modules compiled on 2026-02-01. The latest full `lake build`
recorded there stopped while fetching dependencies; the new RFC 0005 module was checked on its own.

---

## Core statements

These are the precise forms of the core results. The notation is defined in the formal semantics:

- `Δ` is the list of TVAR declarations, and `Γ` the typing context derived from it, which maps each TVAR name to its
  declared type (§4.1).
- `Γ ⊢ φ : prop` means the formula `φ` is well typed under `Γ` (§4.2–4.8).
- `⟦φ⟧(c)` is the truth value of `φ` under configuration `c` (§5).
- A configuration `c` **respects** `Γ` when every declared TVAR has a value of its declared type:
  `∀x ∈ dom(Γ): c(x) ∈ ⦃Γ(x)⦄` (Theorem 4.1).

### Configuration space and satisfaction (§3.4, Definition 5.5)

```
Config(Δ, E_τ) = ∏_{t ∈ Δ} 𝒟⟦t.domain⟧(E_τ)

c ⊨ Φ ⟺ ∀φ ∈ Φ: ⟦φ⟧(c) = true
```

`𝒟⟦t.domain⟧(E_τ)` is the finite set of values that the domain of `t` denotes under environment `E_τ`
(Definition 3.6).

### Type soundness (Theorem 4.1)

If `Γ ⊢ φ : prop` and `c` respects `Γ`, then `⟦φ⟧(c)` is defined and is `true` or `false`. This holds for core
formulas; modules that use the constructs listed in semantics §1.4 are outside it. The Lean proof covers the Lean atom
set above.

### Encoding soundness (Theorem 8.1)

The informative reference encoding (§8) translates structural constraints to a solver problem. SMT means
Satisfiability Modulo Theories: deciding whether a formula has a model in a background theory, here linear integer
arithmetic. Under the preconditions of Theorem 8.1 (every float domain is precision-aligned to the precision factor
`P`, ranges use index variables, and thresholds are rounded by direction), for every solver model `m` and structural
formula `φ`:

```
m ⊨ encode(Δ, φ, P, idx) ⟺ decode(m, Δ, P, idx) ∈ Config(Δ, E_τ) ∧ ⟦φ⟧(decode(m, Δ, P, idx)) = true
```

Corollary 8.1 follows: a satisfying configuration exists if and only if the encoding is satisfiable.

### Decidability (Theorems 7.1–7.4)

For a well-formed set of structural constraints over finite domains, checking one configuration takes polynomial
time (Theorem 7.1), and deciding whether any configuration satisfies the set is decidable. That problem is in NP
(nondeterministic polynomial time: a proposed configuration can be checked in polynomial time) and is NP-complete,
because Boolean satisfiability (SAT) reduces to it through boolean TVARs (Theorem 7.2). Derived constraints are
evaluated directly against the environment (Theorem 7.3), so deciding whether a module has any feasible configuration
is decidable (Theorem 7.4). Compiling to quantifier-free linear integer arithmetic (QF_LIA) is one implementation
strategy, not part of the result. Registry domains and the other constructs of §1.4 are outside it.

### Promotion (Proposition 9.1)

Promotion requires static validity, acceptability (chance constraints and banded objectives) and statistical
ε-dominance on the standard objectives (§9.7). The statistical result is scoped to the tests used:

- Each non-inferiority test runs at level `α`; the configured `adjust` method applies separately to the superiority
  and inferiority families.
- `none` gives no family-level correction. Bonferroni and Holm control the family-wise error rate of each adjusted
  family. Benjamini-Hochberg controls the false discovery rate under independence or positive regression dependency;
  it does not control the family-wise error rate.
- These results do not bound every route to a wrong promotion. That also depends on test validity, data generation,
  selection effects, evaluator reliability and how the evidence was collected (§9.8).

---

## Remaining work

None of these items has a date.

1. **Mechanize decidability** (Theorems 7.1–7.4).
2. **Extend the Lean core model** to strict comparisons, intervals, TVAR-to-TVAR equality, tuple atoms and negative
   thresholds, and to the domain assertions of the reference encoding.
3. **Formalize promotion correctness**, including properties of Welch's t-test and sequential testing error bounds
   (`PROOF_SUMMARY.md`, "Future Extensions").
4. **Formalize `cvars`/`policies` (RFC 0001) and `composites` (RFC 0002)** (semantics §1.4).
5. **Close the OPEN runtime statements** `compiled_contract_correct_statement` (`proofs/TVL/Runtime/Compiler.lean`)
   and `compose_partial_statement` (`proofs/TVL/Runtime/Compose.lean`).
6. **Re-run the full `lake build`** at the pinned Lean toolchain and Mathlib revision and record the result in
   `PROOF_SUMMARY.md`.
7. **Cross-check the reference implementation** in `python/tvl/` against the typing rules (§4) and the conformance
   requirements (§10), and record differences as issues.

---

## What can be claimed

For technical reviews, state results with their scope:

1. **Decidable structural checking**: for finite-domain structural constraints in the core subset, satisfiability is
   decidable (Theorem 7.2). Registry domains and the constructs of §1.4 are outside this.
2. **Type soundness**: well-typed core formulas evaluate to `true` or `false` under any configuration that respects
   the typing context (Theorem 4.1).
3. **Promotion**: a promotion decision rests on the tests and assumptions recorded for it (Proposition 9.1). There is
   no proof that a promoted configuration is better in general.
4. **Same inputs, same feasible set**: the feasible set is a function of the module and the pinned environment
   (Definition 6.3).

### FAQ for technical review

**Q: How do you know constraints are satisfiable?**
> A: The reference checker (`python/tvl/structural_sat.py`) uses OR-Tools CP-SAT when it is installed. Without it, a
> fallback search reports satisfiable when it finds a witness, unsatisfiable only when it has tried every value of
> every domain, and otherwise the error `structural_undecided_without_solver`. The formal semantics allows any solver
> or direct procedure that preserves its judgments (§10.4).

**Q: What if floats cause precision issues?**
> A: The reference encoding represents float values as integers scaled by a precision factor. In the reference
> checker the default factor is 1000 (steps of 0.001), and a float range's `resolution` changes it. Comparisons stay
> exact when every domain value lies on the scaled grid (precision-aligned, §8.5) and thresholds are rounded by
> direction (§8.4). Otherwise an implementation must use an exact encoding or report that the reference encoding is
> unavailable (§10.4).

**Q: How do you ensure promotion decisions are correct?**
> A: Promotion uses ε-Pareto dominance with statistical hypothesis tests (§9.4). The `adjust` setting selects the
> multiple-testing correction: Holm (the reference default), Bonferroni, Benjamini-Hochberg (false discovery rate) or
> none. What each one controls is stated in Proposition 9.1; none of them alone makes a promotion correct.

---

## Tools

- **OR-Tools CP-SAT**: optional dependency of the reference structural checker (`python/tvl/structural_sat.py`).
- **Lean 4 with Mathlib**: the proof tree in `proofs/`; versions are pinned in `proofs/lean-toolchain` and
  `proofs/lakefile.lean`.

---

## Appendix: Quick reference for implementers

### Encoding rules

This sketch follows semantics §8.3–8.4 and the reference checker. Integer values stay unscaled; only float values and
float thresholds are scaled by `P`.

```python
import math

def encode_threshold(op: str, n: float, P: int) -> int:
    # Float TVAR compared with a constant n (semantics Definition 8.5).
    if op == ">=":
        return math.ceil(n * P)
    if op == ">":
        return math.floor(n * P) + 1
    if op == "<=":
        return math.floor(n * P)
    if op == "<":
        return math.ceil(n * P) - 1
    raise ValueError(op)

# Interval a <= x <= b on a float TVAR:  ceil(a * P) <= x_scaled <= floor(b * P)
# Equality x = v on a float TVAR: v * P must be an integer; otherwise the atom is false.
# Enum TVARs are encoded by index 0..|D|-1; membership x in S is a disjunction of index equalities.
```

### Verification checklist

- [ ] Every error code in `docs/reference/error-codes.md` that maps to a formal judgment cites it (Appendix B of the
      semantics)
- [ ] The type checker implements the rules of §4
- [ ] The structural checker preserves the judgments of §§5–6 (§10.4); the §8 encoding is one permitted way
- [ ] The promotion gate implements §9.3–9.8 and §10.5
- [ ] Float scaling is precision-aligned, or the checker uses an exact encoding or refuses (§10.4)

---

*Document version: 2.0*
*Last updated: October 2026 (TVL 1.5)*
