/-
  TVL - Tuned Variables Language
  Basic Definitions

  This file defines the core types and structures used throughout the
  TVL formalization, corresponding to Section 3 (Language) of the paper.
-/

import Mathlib.Tactic

namespace TVL

/-- Base value types in TVL -/
inductive BaseType where
  | bool : BaseType
  | int : BaseType
  | float : BaseType
  | str : BaseType
  deriving DecidableEq, Repr, BEq

/-- TVL types including enums and tuples -/
inductive Ty where
  | base : BaseType -> Ty
  | enum : BaseType -> Ty        -- enum[τ]
  | tuple : List Ty -> Ty        -- tuple[τ₁, ..., τₙ]
  deriving Repr

-- Derive BEq for recursive type
deriving instance BEq for Ty

/-- Values in TVL -/
inductive Val where
  | vbool : Bool -> Val
  | vint : Int -> Val
  | vfloat : Int -> Val         -- Scaled by precision factor P
  | vstr : String -> Val
  | vtuple : List Val -> Val
  deriving Repr

mutual
  /-- Structural boolean equality on TVL values. -/
  def valBeq : Val -> Val -> Bool
    | .vbool x, .vbool y => x == y
    | .vint x, .vint y => x == y
    | .vfloat x, .vfloat y => x == y
    | .vstr x, .vstr y => x == y
    | .vtuple xs, .vtuple ys => listValBeq xs ys
    | _, _ => false

  /-- Structural boolean equality on lists of TVL values. -/
  def listValBeq : List Val -> List Val -> Bool
    | [], [] => true
    | x :: xs, y :: ys => valBeq x y && listValBeq xs ys
    | _, _ => false
end

instance : BEq Val where
  beq := valBeq

mutual
  theorem valBeq_comm : ∀ a b : Val, valBeq a b = valBeq b a
    | .vbool x, .vbool y => by simp [valBeq, Bool.beq_comm]
    | .vbool _, .vint _ => by simp [valBeq]
    | .vbool _, .vfloat _ => by simp [valBeq]
    | .vbool _, .vstr _ => by simp [valBeq]
    | .vbool _, .vtuple _ => by simp [valBeq]
    | .vint _, .vbool _ => by simp [valBeq]
    | .vint x, .vint y => by
        by_cases h : x = y
        · subst h
          simp [valBeq]
        · have h' : y ≠ x := by
            intro hyx
            exact h hyx.symm
          simp [valBeq, h, h']
    | .vint _, .vfloat _ => by simp [valBeq]
    | .vint _, .vstr _ => by simp [valBeq]
    | .vint _, .vtuple _ => by simp [valBeq]
    | .vfloat _, .vbool _ => by simp [valBeq]
    | .vfloat _, .vint _ => by simp [valBeq]
    | .vfloat x, .vfloat y => by
        by_cases h : x = y
        · subst h
          simp [valBeq]
        · have h' : y ≠ x := by
            intro hyx
            exact h hyx.symm
          simp [valBeq, h, h']
    | .vfloat _, .vstr _ => by simp [valBeq]
    | .vfloat _, .vtuple _ => by simp [valBeq]
    | .vstr _, .vbool _ => by simp [valBeq]
    | .vstr _, .vint _ => by simp [valBeq]
    | .vstr _, .vfloat _ => by simp [valBeq]
    | .vstr x, .vstr y => by
        by_cases h : x = y
        · subst h
          simp [valBeq]
        · have h' : y ≠ x := by
            intro hyx
            exact h hyx.symm
          simp [valBeq, h, h']
    | .vstr _, .vtuple _ => by simp [valBeq]
    | .vtuple _, .vbool _ => by simp [valBeq]
    | .vtuple _, .vint _ => by simp [valBeq]
    | .vtuple _, .vfloat _ => by simp [valBeq]
    | .vtuple _, .vstr _ => by simp [valBeq]
    | .vtuple xs, .vtuple ys => by
        simpa [valBeq] using listValBeq_comm xs ys

  theorem listValBeq_comm : ∀ xs ys : List Val, listValBeq xs ys = listValBeq ys xs
    | [], [] => by simp [listValBeq]
    | [], _ :: _ => by simp [listValBeq]
    | _ :: _, [] => by simp [listValBeq]
    | x :: xs, y :: ys => by
        have hHead : valBeq x y = valBeq y x := valBeq_comm x y
        have hTail : listValBeq xs ys = listValBeq ys xs := listValBeq_comm xs ys
        simp [listValBeq, hHead, hTail, Bool.and_comm]
end

/-- BEq symmetry for Val (equality form).

    This is proven by mutual structural recursion over `Val` and `List Val`.
-/
theorem Val.beq_comm (a b : Val) : (a == b) = (b == a) := by
  simpa [BEq.beq] using valBeq_comm a b

/-- The element type function: extracts underlying type from enum -/
def elemType : Ty -> BaseType
  | Ty.base b => b
  | Ty.enum b => b
  | Ty.tuple _ => BaseType.bool  -- Non-numeric; tuples don't support comparison operations

/-- Check if a base type is numeric -/
def BaseType.isNumeric : BaseType -> Bool
  | .int => true
  | .float => true
  | _ => false

/-- Variable names -/
abbrev VarName := String

/-- Typing context: maps variable names to types -/
abbrev Context := VarName -> Option Ty

/-- Empty context -/
def Context.empty : Context := fun _ => none

/-- Extend context with a new binding -/
def Context.extend (Γ : Context) (x : VarName) (τ : Ty) : Context :=
  fun y => if y == x then some τ else Γ y

/-- Configuration: maps variable names to values -/
abbrev Config := VarName -> Option Val

/-- Domain: finite set of values -/
abbrev Domain := List Val

/-- Check if value is in domain -/
def Domain.contains (D : Domain) (v : Val) : Bool :=
  D.any (· == v)

end TVL
