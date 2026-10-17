/- DRAFT TVL 1.3: generic exact binomial tails, stochastic domination and finite unions. -/
import Mathlib.Probability.ProbabilityMassFunction.Binomial
import Mathlib.MeasureTheory.Measure.ProbabilityMeasure

namespace TVL.Runtime
open scoped BigOperators ENNReal NNReal

def binomialMass (N : ℕ) (p : ℚ) (i : ℕ) : ℚ :=
  (N.choose i : ℚ) * p ^ i * (1 - p) ^ (N - i)

def upperTail (N : ℕ) (p : ℚ) (j : ℕ) : ℚ :=
  ∑ i ∈ Finset.range (N + 1), if j ≤ i then binomialMass N p i else 0

def lowerTail (N : ℕ) (p : ℚ) (j : ℕ) : ℚ :=
  ∑ i ∈ Finset.range (N + 1), if i ≤ j then binomialMass N p i else 0

theorem mass_nonneg (N i : ℕ) (p : ℚ) (hp : 0 ≤ p) (hp1 : p ≤ 1) :
    0 ≤ binomialMass N p i := by
  unfold binomialMass
  exact mul_nonneg (mul_nonneg (Nat.cast_nonneg _) (pow_nonneg hp _))
    (pow_nonneg (sub_nonneg.mpr hp1) _)

theorem upper_mono_count (N j j' : ℕ) (p : ℚ)
    (hp : 0 ≤ p) (hp1 : p ≤ 1) (hjj : j ≤ j') :
    upperTail N p j' ≤ upperTail N p j := by
  apply Finset.sum_le_sum
  intro i hi
  have hm := mass_nonneg N i p hp hp1
  split_ifs <;> first | omega | exact hm | exact le_rfl

theorem lower_mono_count (N j j' : ℕ) (p : ℚ)
    (hp : 0 ≤ p) (hp1 : p ≤ 1) (hjj : j ≤ j') :
    lowerTail N p j ≤ lowerTail N p j' := by
  apply Finset.sum_le_sum
  intro i hi
  have hm := mass_nonneg N i p hp hp1
  split_ifs <;> first | omega | exact hm | exact le_rfl

/-- Real finite sums for the population-law statements; no beta quantiles. -/
def realMass (N : ℕ) (p : ℝ) (i : ℕ) : ℝ :=
  (N.choose i : ℝ) * p ^ i * (1 - p) ^ (N - i)
def realUpper (N : ℕ) (p : ℝ) (j : ℕ) : ℝ :=
  ∑ i ∈ Finset.range (N + 1), if j ≤ i then realMass N p i else 0
def realLower (N : ℕ) (p : ℝ) (j : ℕ) : ℝ :=
  ∑ i ∈ Finset.range (N + 1), if i ≤ j then realMass N p i else 0

theorem cast_upper (N j : ℕ) (p : ℚ) :
    (upperTail N p j : ℝ) = realUpper N (p : ℝ) j := by
  rw [upperTail, realUpper, Rat.cast_sum]
  apply Finset.sum_congr rfl
  intro i hi
  by_cases h : j ≤ i <;> simp [h, binomialMass, realMass]

theorem cast_lower (N j : ℕ) (p : ℚ) :
    (lowerTail N p j : ℝ) = realLower N (p : ℝ) j := by
  rw [lowerTail, realLower, Rat.cast_sum]
  apply Finset.sum_congr rfl
  intro i hi
  by_cases h : i ≤ j <;> simp [h, binomialMass, realMass]

theorem real_mass_nonneg (N i : ℕ) (p : ℝ) (hp : 0 ≤ p) (hp1 : p ≤ 1) :
    0 ≤ realMass N p i :=
  mul_nonneg (mul_nonneg (Nat.cast_nonneg _) (pow_nonneg hp _))
    (pow_nonneg (sub_nonneg.mpr hp1) _)

theorem real_mass_total (N : ℕ) (p : ℝ) :
    (∑ i ∈ Finset.range (N + 1), realMass N p i) = 1 := by
  have h := add_pow p (1 - p) N
  have heq : p + (1 - p) = 1 := by ring
  rw [heq, one_pow] at h
  rw [h]
  apply Finset.sum_congr rfl
  intro i hi
  simp only [realMass]
  ring

theorem real_tail_complement (N j : ℕ) (p : ℝ) :
    realLower N p j + realUpper N p (j + 1) = 1 := by
  rw [realLower, realUpper, ← Finset.sum_add_distrib, ← real_mass_total N p]
  apply Finset.sum_congr rfl
  intro i hi
  by_cases h : i ≤ j
  · simp [h, show ¬j + 1 ≤ i by omega]
  · simp [h, show j + 1 ≤ i by omega]

theorem real_upper_mono_count (N j j' : ℕ) (p : ℝ)
    (hp : 0 ≤ p) (hp1 : p ≤ 1) (hjj : j ≤ j') :
    realUpper N p j' ≤ realUpper N p j := by
  apply Finset.sum_le_sum
  intro i hi
  have hm := real_mass_nonneg N i p hp hp1
  split_ifs <;> first | omega | exact hm | exact le_rfl

theorem real_mass_succ (N i : ℕ) (p : ℝ) (hi : i ≤ N) :
    realMass (N + 1) p (i + 1) =
      p * realMass N p i + (1 - p) * realMass N p (i + 1) := by
  by_cases heq : i = N
  · subst i
    simp [realMass, pow_succ, mul_comm]
  · have hi' : i < N := by omega
    have hs : N - i = (N - (i + 1)) + 1 := by omega
    simp only [realMass, Nat.choose_succ_succ', Nat.cast_add, Nat.add_sub_add_right,
      pow_succ, hs]
    ring

theorem real_upper_shift (N j : ℕ) (p : ℝ) :
    (∑ i ∈ Finset.range (N + 1), if j ≤ i then realMass N p (i + 1) else 0) =
      realUpper N p (j + 1) := by
  let f := fun i => if j + 1 ≤ i then realMass N p i else 0
  have hfirst : f 0 = 0 := by simp [f]
  have hlast : f (N + 1) = 0 := by simp [f, realMass]
  have hshift := Finset.sum_range_succ' f (N + 1)
  have hlastSum := Finset.sum_range_succ f (N + 1)
  rw [hfirst, add_zero] at hshift
  rw [hlast, add_zero] at hlastSum
  calc
    _ = ∑ i ∈ Finset.range (N + 1), f (i + 1) := by
      apply Finset.sum_congr rfl
      intro i hi
      simp [f]
    _ = ∑ i ∈ Finset.range (N + 2), f i := hshift.symm
    _ = realUpper N p (j + 1) := hlastSum

theorem real_upper_succ (N j : ℕ) (p : ℝ) :
    realUpper (N + 1) p (j + 1) =
      p * realUpper N p j + (1 - p) * realUpper N p (j + 1) := by
  rw [realUpper, Finset.sum_range_succ']
  simp only [show ¬j + 1 ≤ 0 by omega, ↓reduceIte, add_zero, Nat.add_le_add_iff_right]
  calc
    _ = ∑ i ∈ Finset.range (N + 1),
        (p * (if j ≤ i then realMass N p i else 0) +
         (1 - p) * (if j ≤ i then realMass N p (i + 1) else 0)) := by
      apply Finset.sum_congr rfl
      intro i hi
      have hle : i ≤ N := by simpa only [Finset.mem_range, Nat.lt_succ_iff] using hi
      by_cases hj : j ≤ i <;> simp [hj, real_mass_succ N i p hle]
    _ = _ := by
      rw [Finset.sum_add_distrib, ← Finset.mul_sum, ← Finset.mul_sum,
        real_upper_shift]
      rfl

theorem real_upper_mono_parameter (N j : ℕ) (p q : ℝ)
    (hp : 0 ≤ p) (hpq : p ≤ q) (hq : q ≤ 1) :
    realUpper N p j ≤ realUpper N q j := by
  induction N generalizing j with
  | zero => simp [realUpper, realMass]
  | succ N ih =>
      cases j with
      | zero =>
          simp only [realUpper, Nat.zero_le, ↓reduceIte, real_mass_total]
          exact le_rfl
      | succ j =>
          rw [real_upper_succ, real_upper_succ]
          have h1 := ih j
          have h2 := ih (j + 1)
          have horder := real_upper_mono_count N j (j + 1) q (hp.trans hpq) hq (by omega)
          have hw1 : 0 ≤ p := hp
          have hw2 : 0 ≤ 1 - p := by linarith
          have step1 := mul_le_mul_of_nonneg_left h1 hw1
          have step2 := mul_le_mul_of_nonneg_left h2 hw2
          nlinarith [mul_nonneg (sub_nonneg.mpr hpq) (sub_nonneg.mpr horder)]

/-- Full two-parameter/count statement of Theorem 12.4. -/
def tail_mono_p_statement : Prop :=
  ∀ (N j j' : ℕ) (p q : ℝ), 0 ≤ p → p ≤ q → q ≤ 1 → j ≤ j' → j' ≤ N →
    realUpper N p j ≤ realUpper N q j ∧ realLower N q j ≤ realLower N p j ∧
    realUpper N p j' ≤ realUpper N p j ∧ realLower N p j ≤ realLower N p j'

/-- Theorem 12.4: exact finite-sum parameter and count monotonicity. Parameter
    monotonicity follows by the Bernoulli recurrence, not numerical quantiles. -/
theorem tail_mono_p : tail_mono_p_statement := by
  intro N j j' p q hp hpq hq hj hjN
  have hu := real_upper_mono_parameter N j p q hp hpq hq
  have hul := real_upper_mono_parameter N (j + 1) p q hp hpq hq
  have hc := real_upper_mono_count N j j' p hp (hpq.trans hq) hj
  have hcl := real_upper_mono_count N (j + 1) (j' + 1) p hp (hpq.trans hq) (by omega)
  refine ⟨hu, ?_, hc, ?_⟩
  · linarith [real_tail_complement N j p, real_tail_complement N j q]
  · linarith [real_tail_complement N j p, real_tail_complement N j' p]

theorem upper_mono_parameter (N j : ℕ) (p q : ℚ)
    (hp : 0 ≤ p) (hpq : p ≤ q) (hq : q ≤ 1) :
    upperTail N p j ≤ upperTail N q j := by
  have h := real_upper_mono_parameter N j (p : ℝ) (q : ℝ)
    (by exact_mod_cast hp) (by exact_mod_cast hpq) (by exact_mod_cast hq)
  rw [← cast_upper, ← cast_upper] at h
  exact_mod_cast h

theorem lower_antitone_parameter (N j : ℕ) (p q : ℚ)
    (hp : 0 ≤ p) (hpq : p ≤ q) (hq : q ≤ 1) :
    lowerTail N q j ≤ lowerTail N p j := by
  have h := real_upper_mono_parameter N (j + 1) (p : ℝ) (q : ℝ)
    (by exact_mod_cast hp) (by exact_mod_cast hpq) (by exact_mod_cast hq)
  have h' : realLower N (q : ℝ) j ≤ realLower N (p : ℝ) j := by
    linarith [real_tail_complement N j (p : ℝ), real_tail_complement N j (q : ℝ)]
  rw [← cast_lower, ← cast_lower] at h'
  exact_mod_cast h'

open MeasureTheory

/-- Upper-tail stochastic domination by the exact binomial finite sums. -/
def GoodWindow {Ω : Type*} [MeasurableSpace Ω] (μ : Measure Ω)
    (K : Ω → ℕ) (N : ℕ) (theta : ℚ) : Prop :=
  ∀ j, μ {ω | j ≤ K ω} ≤ ENNReal.ofReal (realUpper N (theta : ℝ) j)

def BadWindow {Ω : Type*} [MeasurableSpace Ω] (μ : Measure Ω)
    (K : Ω → ℕ) (N : ℕ) (theta : ℚ) : Prop :=
  ∀ j, ENNReal.ofReal (realUpper N (theta : ℝ) j) ≤ μ {ω | j ≤ K ω}

/-- Reverse upper-tail domination bounds each lower-tail acceptance region. -/
theorem bad_lower_bound {Ω : Type*} [MeasurableSpace Ω] (μ : Measure Ω)
    [IsProbabilityMeasure μ] (K : Ω → ℕ) (hK : Measurable K)
    (N j : ℕ) (theta : ℚ) (ht0 : 0 ≤ theta) (ht1 : theta ≤ 1)
    (bad : BadWindow μ K N theta) :
    μ {ω | K ω ≤ j} ≤ ENNReal.ofReal (realLower N (theta : ℝ) j) := by
  have hmeas : MeasurableSet {ω | j + 1 ≤ K ω} :=
    measurableSet_le measurable_const hK
  have hcomp : {ω | K ω ≤ j} = {ω | j + 1 ≤ K ω}ᶜ := by
    ext ω
    simp only [Set.mem_setOf_eq, Set.mem_compl_iff]
    omega
  rw [hcomp, prob_compl_eq_one_sub hmeas]
  have hn : 0 ≤ realUpper N (theta : ℝ) (j + 1) := by
    apply Finset.sum_nonneg
    intro i hi
    split_ifs
    · exact real_mass_nonneg _ _ _ (by exact_mod_cast ht0) (by exact_mod_cast ht1)
    · exact le_rfl
  calc
    1 - μ {ω | j + 1 ≤ K ω} ≤
        1 - ENNReal.ofReal (realUpper N (theta : ℝ) (j + 1)) :=
      tsub_le_tsub_left (bad (j + 1)) 1
    _ = ENNReal.ofReal (1 - realUpper N (theta : ℝ) (j + 1)) := by
      rw [ENNReal.ofReal_sub _ hn, ENNReal.ofReal_one]
    _ = ENNReal.ofReal (realLower N (theta : ℝ) j) := by
      congr 1
      linarith [real_tail_complement N j (theta : ℝ)]

/-- Theorem 12.7: finite union bound, conditional on each indicated good-null
    event bound. The events may be dependent; no independence is used. -/
theorem horizon_false_alarm {Ω : Type*} [MeasurableSpace Ω]
    {m : ℕ} (μ : Measure Ω) (falseAlarm : Fin m → Set Ω)
    (allocation : Fin m → ℝ≥0∞) (budget : ℝ≥0∞)
    (hwindow : ∀ i, μ (falseAlarm i) ≤ allocation i)
    (hbudget : ∑ i, allocation i ≤ budget) :
    μ (⋃ i, falseAlarm i) ≤ budget := by
  exact (measure_iUnion_fintype_le μ falseAlarm).trans
    ((Finset.sum_le_sum (fun i _ => hwindow i)).trans hbudget)

end TVL.Runtime
