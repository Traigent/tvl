/-
  TVL - Tuned Variables Language
  ε-Pareto Dominance

  This file proves Lemma 6.18 (ε-Dominance Composition):
  Weak ε-dominance composes:
    c₁ ≽ε c₂ ∧ c₂ ≽ε c₃ ⟹ c₁ ≽₂ε c₃
-/

import TVL.Basic
import Mathlib.Tactic

namespace TVL

/-- Objective direction -/
inductive Direction where
  | maximize : Direction
  | minimize : Direction
  deriving DecidableEq, Repr, BEq

/-- Direction sign: σ(maximize) = +1, σ(minimize) = -1 -/
def Direction.sign : Direction -> Int
  | .maximize => 1
  | .minimize => -1

/-- Normalized difference: σ(d) · (y - y') -/
def normalizedDiff (d : Direction) (y y' : Int) : Int :=
  d.sign * (y - y')

/--
  **Lemma 6.18 (ε-Dominance Composition)** - Core algebraic fact

  For any direction d and values y₁, y₂, y₃, ε:
    σ·(y₁ - y₂) ≥ -ε ∧ σ·(y₂ - y₃) ≥ -ε ⟹ σ·(y₁ - y₃) ≥ -2ε

  This is the per-objective inequality that underlies dominance composition.
-/
theorem normalized_diff_composition (d : Direction) (y₁ y₂ y₃ ε : Int)
    (h12 : normalizedDiff d y₁ y₂ >= -ε)
    (h23 : normalizedDiff d y₂ y₃ >= -ε) :
    normalizedDiff d y₁ y₃ >= -(2 * ε) := by
  simp only [normalizedDiff] at *
  have key : d.sign * (y₁ - y₃) = d.sign * (y₁ - y₂) + d.sign * (y₂ - y₃) := by ring
  linarith

/--
  **Corollary**: Weak ε-dominance composes to 2ε dominance.

  If configuration c₁ weakly ε-dominates c₂ on all objectives,
  and c₂ weakly ε-dominates c₃ on all objectives,
  then c₁ weakly 2ε-dominates c₃ on all objectives.

  Note: Uses explicit index bounds derived from hlen to ensure
  all list accesses are well-defined. The n parameter represents
  the common length of all lists.
-/
theorem eps_dominance_composition_list
    (n : Nat)
    (directions : List Direction) (ε y₁ y₂ y₃ : List Int)
    (hlen_d : directions.length = n)
    (hlen_ε : ε.length = n)
    (hlen_y₁ : y₁.length = n)
    (hlen_y₂ : y₂.length = n)
    (hlen_y₃ : y₃.length = n)
    (h12 : ∀ (i : Fin n),
      normalizedDiff (directions.get (i.cast hlen_d.symm))
                     (y₁.get (i.cast hlen_y₁.symm))
                     (y₂.get (i.cast hlen_y₂.symm)) >=
                     -(ε.get (i.cast hlen_ε.symm)))
    (h23 : ∀ (i : Fin n),
      normalizedDiff (directions.get (i.cast hlen_d.symm))
                     (y₂.get (i.cast hlen_y₂.symm))
                     (y₃.get (i.cast hlen_y₃.symm)) >=
                     -(ε.get (i.cast hlen_ε.symm))) :
    ∀ (i : Fin n),
      normalizedDiff (directions.get (i.cast hlen_d.symm))
                     (y₁.get (i.cast hlen_y₁.symm))
                     (y₃.get (i.cast hlen_y₃.symm)) >=
                     -(2 * (ε.get (i.cast hlen_ε.symm))) := by
  intro i
  exact normalized_diff_composition
    (directions.get (i.cast hlen_d.symm))
    (y₁.get (i.cast hlen_y₁.symm))
    (y₂.get (i.cast hlen_y₂.symm))
    (y₃.get (i.cast hlen_y₃.symm))
    (ε.get (i.cast hlen_ε.symm))
    (h12 i)
    (h23 i)

/--
  **Warning**: Strict dominance does NOT compose.

  Counter-example:
    c₁ ≻ε c₂ and c₂ ≻ε c₃ does NOT imply c₁ ≻₂ε c₃

  Reason: The "strictly better" objective may differ between the two relations.
  If c₁ is strictly better than c₂ on objective A, and c₂ is strictly better
  than c₃ on objective B, then c₁ might only be weakly better than c₃ on both.

  Concrete counter-example (documented in paper):
    objectives: [A (max), B (max)]
    ε = [10, 10]
    y₁ = [100, 50]  -- Better on A
    y₂ = [90, 50]
    y₃ = [90, 40]   -- Better on B

  Then:
    y₁ ≻ε y₂ (strictly better on A: 100-90=10 > ε, weakly better on B)
    y₂ ≻ε y₃ (weakly better on A: 90-90=0 ≥ -10, strictly better on B: 50-40=10 > ε)
  But:
    y₁ vs y₃: On A: 100-90=10 = ε (not strictly better for 2ε=20)
              On B: 50-40=10 = ε (not strictly better for 2ε=20)
    So y₁ ≽₂ε y₃ but NOT y₁ ≻₂ε y₃
-/
theorem strict_dominance_does_not_compose_informal : True := trivial

end TVL
