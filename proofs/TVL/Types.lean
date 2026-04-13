/-
  TVL - Tuned Variables Language
  Type System

  This file formalizes the type system from Section 4 of the paper,
  including typing rules T-Eq, T-Cmp, T-And, T-Or, T-Not, T-Impl.

  **Design Note on Tuples:**
  Tuples (Ty.tuple) are included in the type grammar for completeness but
  are EXPLICITLY BLOCKED in atoms via the `Ty.isAtomType` predicate:
  - All atom typing rules require `τ.isAtomType = true`
  - `Ty.isAtomType (Ty.tuple _) = false`, so tuples cannot appear in atoms
  - This ensures Val.beq_comm's vtuple case is never reached in SMT encoding

  In practice, TVL specs use base types and enums for TVARs; tuples are
  primarily for structured return values, not constraint atoms.
-/

import TVL.Basic

namespace TVL

/-- Atomic formulas (comparison operations) -/
inductive Atom where
  | eq : VarName -> Val -> Atom              -- x = v
  | neq : VarName -> Val -> Atom             -- x ≠ v
  | geq : VarName -> Int -> Atom             -- x ≥ n
  | leq : VarName -> Int -> Atom             -- x ≤ n
  | mem : VarName -> List Val -> Atom        -- x ∈ S
  deriving Repr

deriving instance BEq for Atom

/-- Propositional formulas over atoms -/
inductive Formula where
  | atom : Atom -> Formula
  | and : Formula -> Formula -> Formula
  | or : Formula -> Formula -> Formula
  | not : Formula -> Formula
  | impl : Formula -> Formula -> Formula     -- Syntactic sugar: φ ⇒ ψ ≜ ¬φ ∨ ψ
  deriving Repr

deriving instance BEq for Formula

/-- Value typing judgment: Γ ⊢ v : τ -/
inductive HasValType : Val -> BaseType -> Prop where
  | vbool : ∀ b, HasValType (Val.vbool b) BaseType.bool
  | vint : ∀ n, HasValType (Val.vint n) BaseType.int
  | vfloat : ∀ r, HasValType (Val.vfloat r) BaseType.float
  | vstr : ∀ s, HasValType (Val.vstr s) BaseType.str

/-- Check if a type is valid for use in atoms (base types and enums only, NOT tuples) -/
def Ty.isAtomType : Ty -> Bool
  | Ty.base _ => true
  | Ty.enum _ => true
  | Ty.tuple _ => false

/-- Atom typing: well-typed atom under context -/
inductive AtomWellTyped : Context -> Atom -> Prop where
  /-- T-Eq: Γ(x) = τ, τ is not a tuple, and v : elem(τ) implies (x = v) : prop -/
  | tEq : ∀ Γ x v τ,
      Γ x = some τ ->
      τ.isAtomType = true ->
      HasValType v (elemType τ) ->
      AtomWellTyped Γ (Atom.eq x v)

  /-- T-Neq: analogous to T-Eq -/
  | tNeq : ∀ Γ x v τ,
      Γ x = some τ ->
      τ.isAtomType = true ->
      HasValType v (elemType τ) ->
      AtomWellTyped Γ (Atom.neq x v)

  /-- T-Cmp: Γ(x) = τ, τ is not a tuple, and elem(τ) ∈ {int, float} implies (x ≥ n) : prop -/
  | tGeq : ∀ Γ x n τ,
      Γ x = some τ ->
      τ.isAtomType = true ->
      (elemType τ).isNumeric = true ->
      AtomWellTyped Γ (Atom.geq x n)

  /-- T-Cmp: analogous for ≤ -/
  | tLeq : ∀ Γ x n τ,
      Γ x = some τ ->
      τ.isAtomType = true ->
      (elemType τ).isNumeric = true ->
      AtomWellTyped Γ (Atom.leq x n)

  /-- T-Mem: membership test, τ must not be a tuple -/
  | tMem : ∀ Γ x S τ,
      Γ x = some τ ->
      τ.isAtomType = true ->
      (∀ v, v ∈ S -> HasValType v (elemType τ)) ->
      AtomWellTyped Γ (Atom.mem x S)

/-- Formula typing: Γ ⊢ φ : prop -/
inductive FormulaWellTyped : Context -> Formula -> Prop where
  /-- Atoms -/
  | tAtom : ∀ Γ a,
      AtomWellTyped Γ a ->
      FormulaWellTyped Γ (Formula.atom a)

  /-- T-And: Γ ⊢ φ : prop and Γ ⊢ ψ : prop implies Γ ⊢ (φ ∧ ψ) : prop -/
  | tAnd : ∀ Γ φ ψ,
      FormulaWellTyped Γ φ ->
      FormulaWellTyped Γ ψ ->
      FormulaWellTyped Γ (Formula.and φ ψ)

  /-- T-Or: Γ ⊢ φ : prop and Γ ⊢ ψ : prop implies Γ ⊢ (φ ∨ ψ) : prop -/
  | tOr : ∀ Γ φ ψ,
      FormulaWellTyped Γ φ ->
      FormulaWellTyped Γ ψ ->
      FormulaWellTyped Γ (Formula.or φ ψ)

  /-- T-Not: Γ ⊢ φ : prop implies Γ ⊢ (¬φ) : prop -/
  | tNot : ∀ Γ φ,
      FormulaWellTyped Γ φ ->
      FormulaWellTyped Γ (Formula.not φ)

  /-- T-Impl: Γ ⊢ φ : prop and Γ ⊢ ψ : prop implies Γ ⊢ (φ ⇒ ψ) : prop -/
  | tImpl : ∀ Γ φ ψ,
      FormulaWellTyped Γ φ ->
      FormulaWellTyped Γ ψ ->
      FormulaWellTyped Γ (Formula.impl φ ψ)

/-- Configuration respects context -/
def ConfigRespectsContext (c : Config) (Γ : Context) : Prop :=
  ∀ x τ, Γ x = some τ -> ∃ v, c x = some v ∧
    match τ with
    | Ty.base b => HasValType v b
    | Ty.enum b => HasValType v b
    | Ty.tuple _ => True  -- Simplified for tuples

end TVL
