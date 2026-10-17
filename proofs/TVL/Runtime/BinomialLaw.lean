/- DRAFT TVL 1.3: instantiate the finite-sum model with Mathlib's binomial PMF. -/
import TVL.Runtime.BinomialGeneric

namespace TVL.Runtime
open MeasureTheory
open scoped BigOperators ENNReal NNReal

theorem pmf_binomial_mass (N : ℕ) (p : ℝ≥0) (hp : p ≤ 1) (i : Fin (N + 1)) :
    PMF.binomial p hp N i = ENNReal.ofReal (realMass N (p : ℝ) i) := by
  have hm : realMass N (p : ℝ) i =
      ((p ^ (i : ℕ) * (1 - p) ^ (N - i) * (N.choose i : ℝ≥0) : ℝ≥0) : ℝ) := by
    simp only [NNReal.coe_mul, NNReal.coe_pow, NNReal.coe_sub hp,
      NNReal.coe_one, NNReal.coe_natCast, realMass]
    ring
  rw [PMF.binomial_apply, hm, ENNReal.ofReal_coe_nnreal]
  simp only [Fin.val_last, ENNReal.coe_mul, ENNReal.coe_pow, ENNReal.coe_sub,
    ENNReal.coe_one, ENNReal.coe_natCast]

theorem pmf_binomial_upper (N j : ℕ) (p : ℝ≥0) (hp : p ≤ 1) :
    (PMF.binomial p hp N).toMeasure {i | j ≤ (i : ℕ)} =
      ENNReal.ofReal (realUpper N (p : ℝ) j) := by
  classical
  rw [PMF.toMeasure_apply_fintype]
  simp only [Set.indicator_apply, Set.mem_setOf_eq, pmf_binomial_mass]
  rw [realUpper, ← Fin.sum_univ_eq_sum_range]
  rw [ENNReal.ofReal_sum_of_nonneg (fun i _ => by
    split_ifs
    · exact real_mass_nonneg _ _ _ p.coe_nonneg (by exact_mod_cast hp)
    · exact le_rfl)]
  apply Finset.sum_congr rfl
  intro i hi
  split_ifs <;> simp_all

/-- IID Bernoulli counts have PMF.binomial as their law; p≤theta supplies
    the required good-window domination without a further tail-law assumption. -/
theorem binomial_good_window (N : ℕ) (p : ℝ≥0) (hp : p ≤ 1) (theta : ℚ)
    (_ht0 : 0 ≤ theta) (ht1 : theta ≤ 1) (hpt : (p : ℝ) ≤ theta) :
    GoodWindow (PMF.binomial p hp N).toMeasure (fun i => (i : ℕ)) N theta := by
  intro j
  rw [pmf_binomial_upper]
  apply ENNReal.ofReal_le_ofReal
  exact real_upper_mono_parameter N j p theta p.coe_nonneg hpt (by exact_mod_cast ht1)

/-- Includes equality at the null boundary. No claim about an arbitrary dataset
    being IID is inferred: its latent count must actually have this binomial law. -/
theorem binomial_bad_window (N : ℕ) (p : ℝ≥0) (hp : p ≤ 1) (theta : ℚ)
    (ht0 : 0 ≤ theta) (_ht1 : theta ≤ 1) (htp : (theta : ℝ) ≤ p) :
    BadWindow (PMF.binomial p hp N).toMeasure (fun i => (i : ℕ)) N theta := by
  intro j
  rw [pmf_binomial_upper]
  apply ENNReal.ofReal_le_ofReal
  exact real_upper_mono_parameter N j theta p (by exact_mod_cast ht0) htp (by exact_mod_cast hp)

end TVL.Runtime
