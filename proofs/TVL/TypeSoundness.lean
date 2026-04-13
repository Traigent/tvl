/-
  TVL - Tuned Variables Language
  Type Soundness Proof

  This file proves Theorem 4.2 (Type Soundness):
  If Γ ⊢ φ : prop and configuration c respects Γ,
  then ⟦φ⟧(c) ∈ 𝔹.

  The proof proceeds by structural induction on the typing derivation.
-/

import TVL.Types

namespace TVL

/-- Semantic interpretation of values -/
def Val.toInt? : Val -> Option Int
  | Val.vint n => some n
  | Val.vfloat n => some n  -- Scaled representation
  | _ => none

/-- Semantic interpretation of atoms -/
def evalAtom (a : Atom) (c : Config) : Option Bool :=
  match a with
  | Atom.eq x v =>
      match c x with
      | some cv => some (cv == v)
      | none => none
  | Atom.neq x v =>
      match c x with
      | some cv => some (cv != v)
      | none => none
  | Atom.geq x n =>
      match c x with
      | some cv =>
          match cv.toInt? with
          | some m => some (m >= n)
          | none => none
      | none => none
  | Atom.leq x n =>
      match c x with
      | some cv =>
          match cv.toInt? with
          | some m => some (m <= n)
          | none => none
      | none => none
  | Atom.mem x S =>
      match c x with
      | some cv => some (S.any (· == cv))
      | none => none

/-- Semantic interpretation of formulas: ⟦φ⟧(c) -/
def evalFormula (φ : Formula) (c : Config) : Option Bool :=
  match φ with
  | Formula.atom a => evalAtom a c
  | Formula.and φ₁ φ₂ =>
      match evalFormula φ₁ c, evalFormula φ₂ c with
      | some b₁, some b₂ => some (b₁ && b₂)
      | _, _ => none
  | Formula.or φ₁ φ₂ =>
      match evalFormula φ₁ c, evalFormula φ₂ c with
      | some b₁, some b₂ => some (b₁ || b₂)
      | _, _ => none
  | Formula.not φ₁ =>
      match evalFormula φ₁ c with
      | some b => some (!b)
      | none => none
  | Formula.impl φ₁ φ₂ =>
      match evalFormula φ₁ c, evalFormula φ₂ c with
      | some b₁, some b₂ => some (!b₁ || b₂)
      | _, _ => none

/-- Atom evaluation is total for well-typed atoms under respecting configs -/
theorem atom_eval_defined (Γ : Context) (a : Atom) (c : Config) :
    AtomWellTyped Γ a ->
    ConfigRespectsContext c Γ ->
    ∃ b, evalAtom a c = some b := by
  intro hwt hresp
  cases hwt with
  | tEq x v τ hΓx _ hv =>
      -- _ is the isAtomType hypothesis (not needed for this proof)
      obtain ⟨cv, hcx, _⟩ := hresp x τ hΓx
      simp only [evalAtom, hcx]
      exact ⟨cv == v, rfl⟩
  | tNeq x v τ hΓx _ hv =>
      obtain ⟨cv, hcx, _⟩ := hresp x τ hΓx
      simp only [evalAtom, hcx]
      exact ⟨cv != v, rfl⟩
  | tGeq x n τ hΓx hAtom hnum =>
      obtain ⟨cv, hcx, hty⟩ := hresp x τ hΓx
      simp only [evalAtom, hcx]
      -- Need to show cv.toInt? is defined. Tuples are excluded by hAtom.
      cases τ with
      | base b =>
          simp only [elemType] at hnum
          cases b with
          | int =>
              cases hty with
              | vint m => exact ⟨m >= n, rfl⟩
          | float =>
              cases hty with
              | vfloat r => exact ⟨r >= n, rfl⟩
          | bool => exact absurd hnum Bool.false_ne_true
          | str => exact absurd hnum Bool.false_ne_true
      | enum b =>
          simp only [elemType] at hnum
          cases b with
          | int =>
              cases hty with
              | vint m => exact ⟨m >= n, rfl⟩
          | float =>
              cases hty with
              | vfloat r => exact ⟨r >= n, rfl⟩
          | bool => exact absurd hnum Bool.false_ne_true
          | str => exact absurd hnum Bool.false_ne_true
      | tuple _ =>
          -- Tuples are blocked by isAtomType
          simp only [Ty.isAtomType] at hAtom
          exact absurd hAtom Bool.false_ne_true
  | tLeq x n τ hΓx hAtom hnum =>
      obtain ⟨cv, hcx, hty⟩ := hresp x τ hΓx
      simp only [evalAtom, hcx]
      -- Tuples are excluded by hAtom
      cases τ with
      | base b =>
          simp only [elemType] at hnum
          cases b with
          | int =>
              cases hty with
              | vint m => exact ⟨m <= n, rfl⟩
          | float =>
              cases hty with
              | vfloat r => exact ⟨r <= n, rfl⟩
          | bool => exact absurd hnum Bool.false_ne_true
          | str => exact absurd hnum Bool.false_ne_true
      | enum b =>
          simp only [elemType] at hnum
          cases b with
          | int =>
              cases hty with
              | vint m => exact ⟨m <= n, rfl⟩
          | float =>
              cases hty with
              | vfloat r => exact ⟨r <= n, rfl⟩
          | bool => exact absurd hnum Bool.false_ne_true
          | str => exact absurd hnum Bool.false_ne_true
      | tuple _ =>
          -- Tuples are blocked by isAtomType
          simp only [Ty.isAtomType] at hAtom
          exact absurd hAtom Bool.false_ne_true
  | tMem x S τ hΓx _ _ =>
      obtain ⟨cv, hcx, _⟩ := hresp x τ hΓx
      simp only [evalAtom, hcx]
      exact ⟨S.any (· == cv), rfl⟩

/--
  **Theorem 4.2 (Type Soundness)**

  If Γ ⊢ φ : prop and configuration c respects Γ (i.e.,
  ∀ x ∈ dom(Γ): c(x) ∈ ⟦Γ(x)⟧), then ⟦φ⟧(c) ∈ 𝔹.

  Proof: By structural induction on the derivation of Γ ⊢ φ : prop.
-/
theorem type_soundness (Γ : Context) (φ : Formula) (c : Config) :
    FormulaWellTyped Γ φ ->
    ConfigRespectsContext c Γ ->
    ∃ b : Bool, evalFormula φ c = some b := by
  intro hwt hresp
  induction hwt generalizing c with
  | tAtom a ha =>
      -- Base case: atoms
      obtain ⟨b, hb⟩ := atom_eval_defined Γ a c ha hresp
      exact ⟨b, by simp only [evalFormula, hb]⟩
  | tAnd φ₁ φ₂ _ _ ih₁ ih₂ =>
      -- Inductive case: conjunction
      obtain ⟨b₁, hb₁⟩ := ih₁ c hresp
      obtain ⟨b₂, hb₂⟩ := ih₂ c hresp
      exact ⟨b₁ && b₂, by simp only [evalFormula, hb₁, hb₂]⟩
  | tOr φ₁ φ₂ _ _ ih₁ ih₂ =>
      -- Inductive case: disjunction
      obtain ⟨b₁, hb₁⟩ := ih₁ c hresp
      obtain ⟨b₂, hb₂⟩ := ih₂ c hresp
      exact ⟨b₁ || b₂, by simp only [evalFormula, hb₁, hb₂]⟩
  | tNot φ₁ _ ih =>
      -- Inductive case: negation
      obtain ⟨b, hb⟩ := ih c hresp
      exact ⟨!b, by simp only [evalFormula, hb]⟩
  | tImpl φ₁ φ₂ _ _ ih₁ ih₂ =>
      -- Inductive case: implication (syntactic sugar for ¬φ₁ ∨ φ₂)
      obtain ⟨b₁, hb₁⟩ := ih₁ c hresp
      obtain ⟨b₂, hb₂⟩ := ih₂ c hresp
      exact ⟨!b₁ || b₂, by simp only [evalFormula, hb₁, hb₂]⟩

end TVL
