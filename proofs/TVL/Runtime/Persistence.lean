/- TVL 1.5 draft, RFC 0005. Static historical semantics and exact arithmetic;
   source selection, attestations, finalization and delivery execution are external. -/
import Mathlib

namespace TVL.Runtime.Persistence

inductive Verdict where
  | met | breached | unknown
  deriving DecidableEq, Repr

def breaches : List Verdict → Nat
  | [] => 0
  | .breached :: xs => breaches xs + 1
  | _ :: xs => breaches xs

def unknowns : List Verdict → Nat
  | [] => 0
  | .unknown :: xs => unknowns xs + 1
  | _ :: xs => unknowns xs

def result (k : Nat) (xs : List Verdict) : Verdict :=
  if k ≤ breaches xs then .breached
  else if breaches xs + unknowns xs < k then .met else .unknown

theorem breached_iff (k : Nat) (xs : List Verdict) :
    result k xs = .breached ↔ k ≤ breaches xs := by
  simp only [result]
  split_ifs <;> simp_all

theorem met_iff (k : Nat) (xs : List Verdict) :
    result k xs = .met ↔ breaches xs + unknowns xs < k := by
  simp only [result]
  split_ifs <;> simp_all
  all_goals omega

theorem unknown_iff (k : Nat) (xs : List Verdict) :
    result k xs = .unknown ↔ breaches xs < k ∧ k ≤ breaches xs + unknowns xs := by
  simp only [result]
  split_ifs <;> simp_all

/-- Refinement preserves positions and every decided slot. -/
inductive Refines : List Verdict → List Verdict → Prop where
  | nil : Refines [] []
  | cons {a b xs ys} : (a = .unknown ∨ a = b) → Refines xs ys →
      Refines (a :: xs) (b :: ys)

/-- Arbitrary-list refinement narrows the possible breach-count interval. -/
theorem refinement_bounds {xs ys : List Verdict} (h : Refines xs ys) :
    breaches xs ≤ breaches ys ∧
      breaches ys + unknowns ys ≤ breaches xs + unknowns xs := by
  induction h with
  | nil => simp [breaches, unknowns]
  | @cons a b xs ys hab h ih =>
    cases a <;> cases b <;> simp_all [breaches, unknowns] <;> omega

def Completion (xs ys : List Verdict) : Prop := Refines xs ys ∧ unknowns ys = 0

/-- Uniform resolutions construct the two extreme completions. -/
def fill (v : Verdict) : List Verdict → List Verdict
  | [] => []
  | .unknown :: xs => v :: fill v xs
  | a :: xs => a :: fill v xs

theorem fill_refines (xs : List Verdict) (v : Verdict) : Refines xs (fill v xs) := by
  induction xs with
  | nil => exact .nil
  | cons a xs ih =>
    cases a <;> simp only [fill] <;> apply Refines.cons <;> simp_all

theorem fill_met_counts (xs : List Verdict) :
    breaches (fill .met xs) = breaches xs ∧ unknowns (fill .met xs) = 0 := by
  induction xs with
  | nil => simp [fill, breaches, unknowns]
  | cons a xs ih => cases a <;> simp_all [fill, breaches, unknowns]

theorem fill_breached_counts (xs : List Verdict) :
    breaches (fill .breached xs) = breaches xs + unknowns xs ∧
      unknowns (fill .breached xs) = 0 := by
  induction xs with
  | nil => simp [fill, breaches, unknowns]
  | cons a xs ih => cases a <;> simp_all [fill, breaches, unknowns] <;> omega

theorem breach_necessity {k : Nat} {xs : List Verdict}
    (h : result k xs = .breached) : k ≤ breaches xs := (breached_iff k xs).mp h

/-- Definite BREACHED is exactly agreement of all possible complete histories. -/
theorem breached_iff_all_completions (k : Nat) (xs : List Verdict) :
    result k xs = .breached ↔
      ∀ ys, Completion xs ys → k ≤ breaches ys := by
  rw [breached_iff]
  constructor
  · intro hk ys h
    exact le_trans hk (refinement_bounds h.1).1
  · intro h
    have counts := fill_met_counts xs
    have hc : Completion xs (fill .met xs) := ⟨fill_refines xs .met, counts.2⟩
    simpa only [counts.1] using h (fill .met xs) hc

/-- Definite MET is exactly agreement of all possible complete histories. -/
theorem met_iff_all_completions (k : Nat) (xs : List Verdict) :
    result k xs = .met ↔
      ∀ ys, Completion xs ys → breaches ys < k := by
  rw [met_iff]
  constructor
  · intro hk ys h
    have hb := (refinement_bounds h.1).2
    omega
  · intro h
    have counts := fill_breached_counts xs
    have hc : Completion xs (fill .breached xs) := ⟨fill_refines xs .breached, counts.2⟩
    simpa only [counts.1] using h (fill .breached xs) hc

/-- UNKNOWN is precisely disagreement between complete histories. -/
theorem unknown_iff_mixed_completions (k : Nat) (xs : List Verdict) :
    result k xs = .unknown ↔
      (∃ ys, Completion xs ys ∧ breaches ys < k) ∧
      (∃ zs, Completion xs zs ∧ k ≤ breaches zs) := by
  rw [unknown_iff]
  constructor
  · intro h
    have hm := fill_met_counts xs
    have hb := fill_breached_counts xs
    exact ⟨⟨fill .met xs, ⟨fill_refines xs .met, hm.2⟩, by omega⟩,
      ⟨fill .breached xs, ⟨fill_refines xs .breached, hb.2⟩, by omega⟩⟩
  · rintro ⟨⟨ys, hy, hyl⟩, ⟨zs, hz, hzl⟩⟩
    have hl := (refinement_bounds hy.1).1
    have hu := (refinement_bounds hz.1).2
    omega

/-- Resolving unknown slots cannot reverse a definite result. -/
theorem decided_refinement {xs ys : List Verdict} {k : Nat} (h : Refines xs ys) :
    (result k xs = .breached → result k ys = .breached) ∧
      (result k xs = .met → result k ys = .met) := by
  have hb := refinement_bounds h
  constructor
  · simp only [breached_iff]
    omega
  · simp only [met_iff]
    omega

theorem mean_lte_iff (sum bound : ℚ) (count : Nat) (hc : 0 < count) :
    sum / (count : ℚ) ≤ bound ↔ sum ≤ (count : ℚ) * bound := by
  have hp : (0 : ℚ) < (count : ℚ) := by exact_mod_cast hc
  simpa only [mul_comm] using (div_le_iff₀ hp :
    sum / (count : ℚ) ≤ bound ↔ sum ≤ bound * (count : ℚ))

theorem mean_gte_iff (sum bound : ℚ) (count : Nat) (hc : 0 < count) :
    bound ≤ sum / (count : ℚ) ↔ (count : ℚ) * bound ≤ sum := by
  have hp : (0 : ℚ) < (count : ℚ) := by exact_mod_cast hc
  simpa only [mul_comm] using (le_div_iff₀ hp :
    bound ≤ sum / (count : ℚ) ↔ bound * (count : ℚ) ≤ sum)

end TVL.Runtime.Persistence
