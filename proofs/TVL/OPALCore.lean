/-
  OPAL Core (Declarative Fragment) - Mechanized Lemmas

  This file mechanizes a compact declarative subset used by the OPAL appendix:
  - assignment (`x = v`)
  - domain binding (`x in D`) resolved from an optimizer snapshot Ω
  - guarded structural constraints (`when x is v: φ`) lowered to (¬(x=v) ∨ φ)

  The theorems here are intentionally scoped to the declarative layer and are
  independent of opaque host-language `def` payloads.
-/

import TVL.Basic
import Mathlib.Tactic

namespace TVL
namespace OPALCore

/-- Snapshot and store reuse TVL `Config` shape. -/
abbrev Store := Config
abbrev Snapshot := Config

/-- Point update on stores/configurations. -/
def storeUpdate (σ : Store) (x : VarName) (v : Val) : Store :=
  fun y => if y == x then some v else σ y

/-- OPAL core domains (finite-only in this mechanized fragment). -/
inductive OpalDomain where
  | finite : Domain -> OpalDomain
  deriving Repr

def OpalDomain.contains : OpalDomain -> Val -> Bool
  | .finite d, v => d.contains v

/-- Resolver reads candidate value from snapshot Ω and checks domain membership. -/
def resolve (x : VarName) (D : OpalDomain) (Ω : Snapshot) : Option Val :=
  match Ω x with
  | some v =>
      if OpalDomain.contains D v then some v else none
  | none => none

inductive Decl where
  | assign : VarName -> Val -> Decl
  | bind : VarName -> OpalDomain -> Decl
  deriving Repr

/-- Declarative small-step evaluation over (store, snapshot). -/
def evalDecl : Decl -> Store -> Snapshot -> Option (Store × Snapshot)
  | .assign x v, σ, Ω => some (storeUpdate σ x v, Ω)
  | .bind x D, σ, Ω =>
      match resolve x D Ω with
      | some v => some (storeUpdate σ x v, Ω)
      | none => none

/-- Multi-declaration evaluation (left-to-right). -/
def evalDecls : List Decl -> Store -> Snapshot -> Option (Store × Snapshot)
  | [], σ, Ω => some (σ, Ω)
  | d :: ds, σ, Ω =>
      match evalDecl d σ Ω with
      | some (σ₁, Ω₁) => evalDecls ds σ₁ Ω₁
      | none => none

theorem resolve_sound_finite (x : VarName) (d : Domain) (Ω : Snapshot) (v : Val) :
    resolve x (.finite d) Ω = some v -> d.contains v = true := by
  intro h
  unfold resolve at h
  cases hx : Ω x with
  | none =>
      simp [hx] at h
  | some cv =>
      by_cases hmem : d.contains cv = true
      · simp [hx] at h
        rcases h with ⟨hcontains, hEq⟩
        have hdcv : d.contains cv = true := by
          simpa [OpalDomain.contains] using hcontains
        exact hEq ▸ hdcv
      · simp [hx] at h
        rcases h with ⟨hcontains, _⟩
        have hdcv : d.contains cv = true := by
          simpa [OpalDomain.contains] using hcontains
        exact (False.elim (hmem hdcv))

theorem evalDecl_deterministic
    (δ : Decl) (σ : Store) (Ω : Snapshot) (r₁ r₂ : Store × Snapshot) :
    evalDecl δ σ Ω = some r₁ ->
    evalDecl δ σ Ω = some r₂ ->
    r₁ = r₂ := by
  intro h₁ h₂
  have hs : some r₁ = some r₂ := by
    rw [← h₁, h₂]
  exact Option.some.inj hs

theorem evalDecl_preserves_snapshot
    (δ : Decl) (σ : Store) (Ω : Snapshot) (σ' : Store) (Ω' : Snapshot) :
    evalDecl δ σ Ω = some (σ', Ω') -> Ω' = Ω := by
  intro h
  cases δ with
  | assign x v =>
      simp [evalDecl] at h
      rcases h with ⟨hσ, hΩ⟩
      exact hΩ.symm
  | bind x D =>
      cases hres : resolve x D Ω with
      | none =>
          simp [evalDecl, hres] at h
      | some v =>
          simp [evalDecl, hres] at h
          rcases h with ⟨hσ, hΩ⟩
          exact hΩ.symm

theorem evalDecls_preserves_snapshot
    (ds : List Decl) (σ : Store) (Ω : Snapshot) (σ' : Store) (Ω' : Snapshot) :
    evalDecls ds σ Ω = some (σ', Ω') -> Ω' = Ω := by
  induction ds generalizing σ Ω σ' Ω' with
  | nil =>
      intro h
      simp [evalDecls] at h
      rcases h with ⟨hσ, hΩ⟩
      exact hΩ.symm
  | cons d ds ih =>
      intro h
      cases hstep : evalDecl d σ Ω with
      | none =>
          simp [evalDecls, hstep] at h
      | some step =>
          rcases step with ⟨σ₁, Ω₁⟩
          have hΩ₁ : Ω₁ = Ω := by
            have hstep' : evalDecl d σ Ω = some (σ₁, Ω₁) := by
              simp [hstep]
            exact evalDecl_preserves_snapshot (δ := d) (σ := σ) (Ω := Ω) (σ' := σ₁) (Ω' := Ω₁) hstep'
          have h' : evalDecls ds σ₁ Ω₁ = some (σ', Ω') := by
            simpa [evalDecls, hstep] using h
          have hΩtail : Ω' = Ω₁ := ih (σ := σ₁) (Ω := Ω₁) (σ' := σ') (Ω' := Ω') h'
          exact hΩtail.trans hΩ₁

/-- Boolean atoms used for structural-constraint lowering proofs. -/
inductive BAtom where
  | eq : VarName -> Val -> BAtom
  deriving Repr

inductive BFormula where
  | atom : BAtom -> BFormula
  | not : BFormula -> BFormula
  | or : BFormula -> BFormula -> BFormula
  deriving Repr

def evalBAtom (σ : Store) : BAtom -> Bool
  | .eq x v =>
      match σ x with
      | some cv => cv == v
      | none => false

def evalBFormula (σ : Store) : BFormula -> Bool
  | .atom a => evalBAtom σ a
  | .not φ => !(evalBFormula σ φ)
  | .or φ ψ => evalBFormula σ φ || evalBFormula σ ψ

/-- Source-level semantics of `when x is v: φ`. -/
def evalWhen (σ : Store) (x : VarName) (v : Val) (φ : BFormula) : Bool :=
  if evalBAtom σ (.eq x v) then evalBFormula σ φ else true

/-- Target-level lowering: (when x is v: φ) ↦ (¬(x=v) ∨ φ). -/
def lowerWhen (x : VarName) (v : Val) (φ : BFormula) : BFormula :=
  .or (.not (.atom (.eq x v))) φ

theorem when_lowering_faithful
    (σ : Store) (x : VarName) (v : Val) (φ : BFormula) :
    evalWhen σ x v φ = evalBFormula σ (lowerWhen x v φ) := by
  unfold evalWhen lowerWhen
  cases h : evalBAtom σ (BAtom.eq x v) <;> simp [evalBFormula, h]

/-! ### Extended Core: callable interfaces, `given`, and explicit errors -/

abbrev InterfaceName := String
abbrev CallableName := String
abbrev InterfaceRegistry := CallableName -> Option InterfaceName
abbrev GivenInput := String
abbrev GivenPolicy := GivenInput -> Snapshot -> Snapshot

inductive EvalError where
  | unresolvedBinding : VarName -> EvalError
  deriving Repr, DecidableEq

/-- Extended domains include callable choices with required interface. -/
inductive OpalDomainT where
  | finite : Domain -> OpalDomainT
  | callable : InterfaceName -> List CallableName -> OpalDomainT
  deriving Repr

def callableMatches (sigmaI : InterfaceRegistry) (f : CallableName) (iface : InterfaceName) : Bool :=
  match sigmaI f with
  | some iface' => iface' == iface
  | none => false

/-- Resolver for typed domains (including callable interface checks). -/
def resolveTyped (x : VarName) (D : OpalDomainT) (Ω : Snapshot) (sigmaI : InterfaceRegistry) : Option Val :=
  match D with
  | .finite d =>
      match Ω x with
      | some v => if d.contains v then some v else none
      | none => none
  | .callable iface choices =>
      match Ω x with
      | some (.vstr f) =>
          if choices.any (· == f) then
            if callableMatches sigmaI f iface then some (.vstr f) else none
          else none
      | _ => none

theorem resolve_callable_interface_sound
    (x : VarName) (iface : InterfaceName) (choices : List CallableName)
    (Ω : Snapshot) (sigmaI : InterfaceRegistry) (f : CallableName) :
    resolveTyped x (.callable iface choices) Ω sigmaI = some (.vstr f) ->
    callableMatches sigmaI f iface = true := by
  intro h
  unfold resolveTyped at h
  cases hΩ : Ω x with
  | none =>
      simp [hΩ] at h
  | some v =>
      cases v with
      | vbool b =>
          simp [hΩ] at h
      | vint n =>
          simp [hΩ] at h
      | vfloat q =>
          simp [hΩ] at h
      | vtuple vs =>
          simp [hΩ] at h
      | vstr g =>
          by_cases hmem : choices.any (· == g) = true
          · simp [hΩ, hmem, callableMatches] at h
            rcases h with ⟨hmatch, hfg⟩
            subst hfg
            exact hmatch
          · simp [hΩ, hmem] at h

inductive DeclE where
  | assign : VarName -> Val -> DeclE
  | bind : VarName -> OpalDomainT -> DeclE
  | bindGiven : VarName -> OpalDomainT -> GivenPolicy -> DeclE


/-- Error-typed declarative evaluation over (store, snapshot). -/
def evalDeclE :
    DeclE -> Store -> Snapshot -> InterfaceRegistry -> GivenInput -> Except EvalError (Store × Snapshot)
  | .assign x v, σ, Ω, _, _ => .ok (storeUpdate σ x v, Ω)
  | .bind x D, σ, Ω, sigmaI, _ =>
      match resolveTyped x D Ω sigmaI with
      | some v => .ok (storeUpdate σ x v, Ω)
      | none => .error (.unresolvedBinding x)
  | .bindGiven x D policy, σ, Ω, sigmaI, input =>
      let Ωg := policy input Ω
      match resolveTyped x D Ωg sigmaI with
      | some v => .ok (storeUpdate σ x v, Ω)
      | none => .error (.unresolvedBinding x)

def evalDeclsE :
    List DeclE -> Store -> Snapshot -> InterfaceRegistry -> GivenInput -> Except EvalError (Store × Snapshot)
  | [], σ, Ω, _, _ => .ok (σ, Ω)
  | d :: ds, σ, Ω, sigmaI, input =>
      match evalDeclE d σ Ω sigmaI input with
      | .ok (σ₁, Ω₁) => evalDeclsE ds σ₁ Ω₁ sigmaI input
      | .error err => .error err

theorem evalDecl_preservation_except
    (δ : DeclE) (σ : Store) (Ω : Snapshot) (sigmaI : InterfaceRegistry)
    (input : GivenInput) (σ' : Store) (Ω' : Snapshot) :
    evalDeclE δ σ Ω sigmaI input = .ok (σ', Ω') -> Ω' = Ω := by
  intro h
  cases δ with
  | assign x v =>
      simp [evalDeclE] at h
      rcases h with ⟨hσ, hΩ⟩
      exact hΩ.symm
  | bind x D =>
      cases hres : resolveTyped x D Ω sigmaI with
      | none =>
          simp [evalDeclE, hres] at h
      | some v =>
          simp [evalDeclE, hres] at h
          rcases h with ⟨hσ, hΩ⟩
          exact hΩ.symm
  | bindGiven x D policy =>
      cases hres : resolveTyped x D (policy input Ω) sigmaI with
      | none =>
          simp [evalDeclE, hres] at h
      | some v =>
          simp [evalDeclE, hres] at h
          rcases h with ⟨hσ, hΩ⟩
          exact hΩ.symm

theorem evalDecl_given_preserves_snapshot
    (x : VarName) (D : OpalDomainT) (policy : GivenPolicy)
    (σ : Store) (Ω : Snapshot) (sigmaI : InterfaceRegistry)
    (input : GivenInput) (σ' : Store) (Ω' : Snapshot) :
    evalDeclE (.bindGiven x D policy) σ Ω sigmaI input = .ok (σ', Ω') -> Ω' = Ω := by
  intro h
  exact evalDecl_preservation_except
    (δ := .bindGiven x D policy) (σ := σ) (Ω := Ω) (sigmaI := sigmaI)
    (input := input) (σ' := σ') (Ω' := Ω') h

theorem core_progress_except
    (ds : List DeclE) (σ : Store) (Ω : Snapshot) (sigmaI : InterfaceRegistry)
    (input : GivenInput) :
    (∃ σ' Ω', evalDeclsE ds σ Ω sigmaI input = .ok (σ', Ω')) ∨
    (∃ err, evalDeclsE ds σ Ω sigmaI input = .error err) := by
  let r := evalDeclsE ds σ Ω sigmaI input
  cases hr : r with
  | ok result =>
      rcases result with ⟨σ', Ω'⟩
      left
      refine ⟨σ', Ω', ?_⟩
      simpa [r] using hr
  | error err =>
      right
      refine ⟨err, ?_⟩
      simpa [r] using hr

theorem evalDeclsE_preserves_snapshot
    (ds : List DeclE) (σ : Store) (Ω : Snapshot) (sigmaI : InterfaceRegistry)
    (input : GivenInput) (σ' : Store) (Ω' : Snapshot) :
    evalDeclsE ds σ Ω sigmaI input = .ok (σ', Ω') -> Ω' = Ω := by
  induction ds generalizing σ Ω σ' Ω' with
  | nil =>
      intro h
      simp [evalDeclsE] at h
      rcases h with ⟨hσ, hΩ⟩
      exact hΩ.symm
  | cons d ds ih =>
      intro h
      cases hstep : evalDeclE d σ Ω sigmaI input with
      | error err =>
          simp [evalDeclsE, hstep] at h
      | ok step =>
          rcases step with ⟨σ₁, Ω₁⟩
          have hΩ₁ : Ω₁ = Ω := by
            have hstep' : evalDeclE d σ Ω sigmaI input = .ok (σ₁, Ω₁) := by
              simp [hstep]
            exact evalDecl_preservation_except
              (δ := d) (σ := σ) (Ω := Ω) (sigmaI := sigmaI) (input := input)
              (σ' := σ₁) (Ω' := Ω₁) hstep'
          have h' : evalDeclsE ds σ₁ Ω₁ sigmaI input = .ok (σ', Ω') := by
            simpa [evalDeclsE, hstep] using h
          have hΩtail : Ω' = Ω₁ := ih (σ := σ₁) (Ω := Ω₁) (σ' := σ') (Ω' := Ω') h'
          exact hΩtail.trans hΩ₁

/-! ### Template-aware callable resolution and argument typing -/

structure CallableSig where
  iface : InterfaceName
  params : List (String × Ty)
  deriving Repr

abbrev CallableRegistryT := CallableName -> Option CallableSig

inductive ArgExpr where
  | lit : Val -> ArgExpr
  | ref : VarName -> ArgExpr
  deriving Repr

structure ArgBinding where
  name : String
  expr : ArgExpr
  deriving Repr

structure CallableTemplate where
  fn : CallableName
  args : List ArgBinding
  deriving Repr

def valHasType (v : Val) (τ : Ty) : Bool :=
  match τ, v with
  | .base .bool, .vbool _ => true
  | .base .int, .vint _ => true
  | .base .float, .vfloat _ => true
  | .base .str, .vstr _ => true
  | .enum .bool, .vbool _ => true
  | .enum .int, .vint _ => true
  | .enum .float, .vfloat _ => true
  | .enum .str, .vstr _ => true
  | _, _ => false

def evalArgExpr (a : ArgExpr) (σ : Store) : Option Val :=
  match a with
  | .lit v => some v
  | .ref x => σ x

def findParamType (params : List (String × Ty)) (argName : String) : Option Ty :=
  match params with
  | [] => none
  | (p, τ) :: ps => if p == argName then some τ else findParamType ps argName

def argBindingWellTyped (σ : Store) (params : List (String × Ty)) (ab : ArgBinding) : Bool :=
  match findParamType params ab.name, evalArgExpr ab.expr σ with
  | some τ, some v => valHasType v τ
  | _, _ => false

def templateArgsWellTyped (tmpl : CallableTemplate) (σ : Store) (sig : CallableSig) : Bool :=
  tmpl.args.all (fun ab => argBindingWellTyped σ sig.params ab)

def findTemplate (choices : List CallableTemplate) (f : CallableName) : Option CallableTemplate :=
  match choices with
  | [] => none
  | t :: ts => if t.fn == f then some t else findTemplate ts f

theorem findTemplate_sound_fn
    (choices : List CallableTemplate) (f : CallableName) (tmpl : CallableTemplate) :
    findTemplate choices f = some tmpl -> tmpl.fn = f := by
  induction choices with
  | nil =>
      intro h
      simp [findTemplate] at h
  | cons t ts ih =>
      intro h
      unfold findTemplate at h
      by_cases hmatch : t.fn == f
      · simp [hmatch] at h
        subst h
        exact of_decide_eq_true hmatch
      · simp [hmatch] at h
        exact ih h

def resolveTemplateChoice
    (x : VarName) (iface : InterfaceName) (choices : List CallableTemplate)
    (Ω : Snapshot) (σ : Store) (sigmaC : CallableRegistryT) : Option CallableTemplate :=
  match Ω x with
  | some (.vstr f) =>
      match findTemplate choices f with
      | some tmpl =>
          match sigmaC f with
          | some sig =>
              if sig.iface == iface then
                if templateArgsWellTyped tmpl σ sig then some tmpl else none
              else none
          | none => none
      | none => none
  | _ => none

theorem resolve_template_interface_sound
    (x : VarName) (iface : InterfaceName) (choices : List CallableTemplate)
    (Ω : Snapshot) (σ : Store) (sigmaC : CallableRegistryT) (tmpl : CallableTemplate) :
    resolveTemplateChoice x iface choices Ω σ sigmaC = some tmpl ->
    ∃ sig, sigmaC tmpl.fn = some sig ∧ (sig.iface == iface) = true := by
  intro h
  unfold resolveTemplateChoice at h
  cases hΩ : Ω x with
  | none =>
      simp [hΩ] at h
  | some v =>
      cases v with
      | vbool b =>
          simp [hΩ] at h
      | vint n =>
          simp [hΩ] at h
      | vfloat q =>
          simp [hΩ] at h
      | vtuple vs =>
          simp [hΩ] at h
      | vstr f =>
          cases hfind : findTemplate choices f with
          | none =>
              simp [hΩ, hfind] at h
          | some t =>
              cases hsig : sigmaC f with
              | none =>
                  simp [hΩ, hfind, hsig] at h
              | some sig =>
                  by_cases hiface : (sig.iface == iface) = true
                  · by_cases hargs : (templateArgsWellTyped t σ sig) = true
                    · simp [hΩ, hfind, hsig, hiface, hargs] at h
                      subst h
                      have htf : t.fn = f := findTemplate_sound_fn choices f t hfind
                      refine ⟨sig, ?_⟩
                      constructor
                      · simpa [htf] using hsig
                      · exact hiface
                    · simp [hΩ, hfind, hsig, hiface, hargs] at h
                  · simp [hΩ, hfind, hsig, hiface] at h

theorem templateArgsWellTyped_member_sound
    (tmpl : CallableTemplate) (σ : Store) (sig : CallableSig) :
    templateArgsWellTyped tmpl σ sig = true ->
    ∀ ab, ab ∈ tmpl.args -> argBindingWellTyped σ sig.params ab = true := by
  intro h ab hab
  exact (List.all_eq_true.mp h) ab hab

theorem resolve_template_arguments_sound
    (x : VarName) (iface : InterfaceName) (choices : List CallableTemplate)
    (Ω : Snapshot) (σ : Store) (sigmaC : CallableRegistryT) (tmpl : CallableTemplate) :
    resolveTemplateChoice x iface choices Ω σ sigmaC = some tmpl ->
    ∃ sig, sigmaC tmpl.fn = some sig ∧ templateArgsWellTyped tmpl σ sig = true := by
  intro h
  unfold resolveTemplateChoice at h
  cases hΩ : Ω x with
  | none =>
      simp [hΩ] at h
  | some v =>
      cases v with
      | vbool b =>
          simp [hΩ] at h
      | vint n =>
          simp [hΩ] at h
      | vfloat q =>
          simp [hΩ] at h
      | vtuple vs =>
          simp [hΩ] at h
      | vstr f =>
          cases hfind : findTemplate choices f with
          | none =>
              simp [hΩ, hfind] at h
          | some t =>
              cases hsig : sigmaC f with
              | none =>
                  simp [hΩ, hfind, hsig] at h
              | some sig =>
                  by_cases hiface : (sig.iface == iface) = true
                  · by_cases hargs : (templateArgsWellTyped t σ sig) = true
                    · simp [hΩ, hfind, hsig, hiface, hargs] at h
                      subst h
                      have htf : t.fn = f := findTemplate_sound_fn choices f t hfind
                      refine ⟨sig, ?_⟩
                      constructor
                      · simpa [htf] using hsig
                      · exact hargs
                    · simp [hΩ, hfind, hsig, hiface, hargs] at h
                  · simp [hΩ, hfind, hsig, hiface] at h

inductive DeclTemplate where
  | assign : VarName -> Val -> DeclTemplate
  | bindTemplate : VarName -> InterfaceName -> List CallableTemplate -> DeclTemplate
  | bindGivenTemplate : VarName -> InterfaceName -> List CallableTemplate -> GivenPolicy -> DeclTemplate

def evalDeclTemplateE :
    DeclTemplate -> Store -> Snapshot -> CallableRegistryT -> GivenInput -> Except EvalError (Store × Snapshot)
  | .assign x v, σ, Ω, _, _ => .ok (storeUpdate σ x v, Ω)
  | .bindTemplate x iface choices, σ, Ω, sigmaC, _ =>
      match resolveTemplateChoice x iface choices Ω σ sigmaC with
      | some tmpl => .ok (storeUpdate σ x (.vstr tmpl.fn), Ω)
      | none => .error (.unresolvedBinding x)
  | .bindGivenTemplate x iface choices policy, σ, Ω, sigmaC, input =>
      let Ωg := policy input Ω
      match resolveTemplateChoice x iface choices Ωg σ sigmaC with
      | some tmpl => .ok (storeUpdate σ x (.vstr tmpl.fn), Ω)
      | none => .error (.unresolvedBinding x)

def evalDeclTemplatesE :
    List DeclTemplate -> Store -> Snapshot -> CallableRegistryT -> GivenInput -> Except EvalError (Store × Snapshot)
  | [], σ, Ω, _, _ => .ok (σ, Ω)
  | d :: ds, σ, Ω, sigmaC, input =>
      match evalDeclTemplateE d σ Ω sigmaC input with
      | .ok (σ₁, Ω₁) => evalDeclTemplatesE ds σ₁ Ω₁ sigmaC input
      | .error err => .error err

theorem evalDeclE_template_preservation_except
    (δ : DeclTemplate) (σ : Store) (Ω : Snapshot) (sigmaC : CallableRegistryT)
    (input : GivenInput) (σ' : Store) (Ω' : Snapshot) :
    evalDeclTemplateE δ σ Ω sigmaC input = .ok (σ', Ω') -> Ω' = Ω := by
  intro h
  cases δ with
  | assign x v =>
      simp [evalDeclTemplateE] at h
      rcases h with ⟨hσ, hΩ⟩
      exact hΩ.symm
  | bindTemplate x iface choices =>
      cases hres : resolveTemplateChoice x iface choices Ω σ sigmaC with
      | none =>
          simp [evalDeclTemplateE, hres] at h
      | some tmpl =>
          simp [evalDeclTemplateE, hres] at h
          rcases h with ⟨hσ, hΩ⟩
          exact hΩ.symm
  | bindGivenTemplate x iface choices policy =>
      cases hres : resolveTemplateChoice x iface choices (policy input Ω) σ sigmaC with
      | none =>
          simp [evalDeclTemplateE, hres] at h
      | some tmpl =>
          simp [evalDeclTemplateE, hres] at h
          rcases h with ⟨hσ, hΩ⟩
          exact hΩ.symm

theorem core_progress_except_template
    (ds : List DeclTemplate) (σ : Store) (Ω : Snapshot) (sigmaC : CallableRegistryT)
    (input : GivenInput) :
    (∃ σ' Ω', evalDeclTemplatesE ds σ Ω sigmaC input = .ok (σ', Ω')) ∨
    (∃ err, evalDeclTemplatesE ds σ Ω sigmaC input = .error err) := by
  let r := evalDeclTemplatesE ds σ Ω sigmaC input
  cases hr : r with
  | ok result =>
      rcases result with ⟨σ', Ω'⟩
      left
      refine ⟨σ', Ω', ?_⟩
      simpa [r] using hr
  | error err =>
      right
      refine ⟨err, ?_⟩
      simpa [r] using hr

/-! ### Nested/compositional templates + completeness + well-formed registry -/

structure ParamSpec where
  pname : String
  ptype : Ty
  required : Bool
  deriving Repr

structure CallableSigN where
  iface : InterfaceName
  params : List ParamSpec
  deriving Repr

abbrev CallableRegistryN := CallableName -> Option CallableSigN

def paramNamesN (ps : List ParamSpec) : List String :=
  ps.map (fun p => p.pname)

def wellFormedRegistryN (sigmaCN : CallableRegistryN) : Prop :=
  ∀ f sig, sigmaCN f = some sig -> (paramNamesN sig.params).Nodup

mutual
  inductive CallableTemplateN where
    | mk : CallableName -> List ArgBindingN -> CallableTemplateN
    deriving Repr

  inductive ArgExprN where
    | lit : Val -> ArgExprN
    | ref : VarName -> ArgExprN
    | template : CallableTemplateN -> ArgExprN
    deriving Repr

  inductive ArgBindingN where
    | mk : String -> ArgExprN -> ArgBindingN
    deriving Repr
end

def templateFnN : CallableTemplateN -> CallableName
  | .mk fn _ => fn

def templateArgsN : CallableTemplateN -> List ArgBindingN
  | .mk _ args => args

def argBindingNameN : ArgBindingN -> String
  | .mk n _ => n

def argBindingExprN : ArgBindingN -> ArgExprN
  | .mk _ e => e

def findParamSpecN (params : List ParamSpec) (argName : String) : Option ParamSpec :=
  match params with
  | [] => none
  | p :: ps => if p.pname == argName then some p else findParamSpecN ps argName

def paramProvidedN (args : List ArgBindingN) (pname : String) : Bool :=
  args.any (fun ab => argBindingNameN ab == pname)

def argsCompleteN (args : List ArgBindingN) (params : List ParamSpec) : Bool :=
  params.all (fun p => if p.required then paramProvidedN args p.pname else true)

def findTemplateN (choices : List CallableTemplateN) (f : CallableName) : Option CallableTemplateN :=
  match choices with
  | [] => none
  | t :: ts => if templateFnN t == f then some t else findTemplateN ts f

theorem findTemplateN_sound_fn
    (choices : List CallableTemplateN) (f : CallableName) (tmpl : CallableTemplateN) :
    findTemplateN choices f = some tmpl -> templateFnN tmpl = f := by
  induction choices with
  | nil =>
      intro h
      simp [findTemplateN] at h
  | cons t ts ih =>
      intro h
      unfold findTemplateN at h
      by_cases hmatch : templateFnN t == f
      · simp [hmatch] at h
        subst h
        exact of_decide_eq_true hmatch
      · simp [hmatch] at h
        exact ih h

mutual
  def argExprWellTypedFuel : Nat -> ArgExprN -> Ty -> Store -> CallableRegistryN -> Bool
    | 0, _, _, _, _ => false
    | fuel + 1, e, τ, σ, sigmaCN =>
        match e with
        | .lit v => valHasType v τ
        | .ref x =>
            match σ x with
            | some v => valHasType v τ
            | none => false
        | .template t =>
            match τ with
            | .base .str => templateWellTypedFuel fuel t σ sigmaCN
            | .enum .str => templateWellTypedFuel fuel t σ sigmaCN
            | _ => false

  def argBindingWellTypedFuel : Nat -> ArgBindingN -> List ParamSpec -> Store -> CallableRegistryN -> Bool
    | 0, _, _, _, _ => false
    | fuel + 1, ab, params, σ, sigmaCN =>
        match findParamSpecN params (argBindingNameN ab) with
        | some p => argExprWellTypedFuel fuel (argBindingExprN ab) p.ptype σ sigmaCN
        | none => false

  def argsAllValidFuel : Nat -> List ArgBindingN -> List ParamSpec -> Store -> CallableRegistryN -> Bool
    | 0, _, _, _, _ => false
    | fuel + 1, args, params, σ, sigmaCN =>
        args.all (fun ab => argBindingWellTypedFuel fuel ab params σ sigmaCN)

  def templateWellTypedFuel : Nat -> CallableTemplateN -> Store -> CallableRegistryN -> Bool
    | 0, _, _, _ => false
    | fuel + 1, tmpl, σ, sigmaCN =>
        match sigmaCN (templateFnN tmpl) with
        | some sig =>
            let valid := argsAllValidFuel fuel (templateArgsN tmpl) sig.params σ sigmaCN
            let complete := argsCompleteN (templateArgsN tmpl) sig.params
            valid && complete
        | none => false
end

def templateFuelN : Nat := 64
def templateArgFuelN : Nat := 63

def templateWellTypedN (tmpl : CallableTemplateN) (σ : Store) (sigmaCN : CallableRegistryN) : Bool :=
  templateWellTypedFuel templateFuelN tmpl σ sigmaCN

def argsAllValidN (tmpl : CallableTemplateN) (sig : CallableSigN) (σ : Store) (sigmaCN : CallableRegistryN) : Bool :=
  argsAllValidFuel templateArgFuelN (templateArgsN tmpl) sig.params σ sigmaCN

def resolveTemplateChoiceN
    (x : VarName) (iface : InterfaceName) (choices : List CallableTemplateN)
    (Ω : Snapshot) (σ : Store) (sigmaCN : CallableRegistryN) : Option CallableTemplateN :=
  match Ω x with
  | some (.vstr f) =>
      match findTemplateN choices f with
      | some tmpl =>
          match sigmaCN f with
          | some sig =>
              if (sig.iface == iface) then
                if templateWellTypedN tmpl σ sigmaCN then some tmpl else none
              else none
          | none => none
      | none => none
  | _ => none

theorem templateWellTypedN_components
    (tmpl : CallableTemplateN) (σ : Store) (sigmaCN : CallableRegistryN) (sig : CallableSigN) :
    sigmaCN (templateFnN tmpl) = some sig ->
    templateWellTypedN tmpl σ sigmaCN = true ->
    argsAllValidN tmpl sig σ sigmaCN = true ∧
    argsCompleteN (templateArgsN tmpl) sig.params = true := by
  intro hs hwt
  have hcore :
      argsAllValidFuel templateArgFuelN (templateArgsN tmpl) sig.params σ sigmaCN = true ∧
      argsCompleteN (templateArgsN tmpl) sig.params = true := by
    have hwt' :
        argsAllValidFuel templateArgFuelN (templateArgsN tmpl) sig.params σ sigmaCN &&
          argsCompleteN (templateArgsN tmpl) sig.params = true := by
      simpa [templateWellTypedN, templateWellTypedFuel, templateFuelN, templateArgFuelN, hs] using hwt
    simpa [Bool.and_eq_true_iff] using hwt'
  simpa [argsAllValidN] using hcore

theorem resolve_template_choice_sound_nested
    (x : VarName) (iface : InterfaceName) (choices : List CallableTemplateN)
    (Ω : Snapshot) (σ : Store) (sigmaCN : CallableRegistryN) (tmpl : CallableTemplateN) :
    resolveTemplateChoiceN x iface choices Ω σ sigmaCN = some tmpl ->
    ∃ f sig,
      findTemplateN choices f = some tmpl ∧
      sigmaCN f = some sig ∧
      (sig.iface == iface) = true ∧
      templateWellTypedN tmpl σ sigmaCN = true := by
  intro h
  unfold resolveTemplateChoiceN at h
  cases hΩ : Ω x with
  | none =>
      simp [hΩ] at h
  | some v =>
      cases v with
      | vbool b =>
          simp [hΩ] at h
      | vint n =>
          simp [hΩ] at h
      | vfloat q =>
          simp [hΩ] at h
      | vtuple vs =>
          simp [hΩ] at h
      | vstr f =>
          cases hfind : findTemplateN choices f with
          | none =>
              simp [hΩ, hfind] at h
          | some t =>
              cases hsig : sigmaCN f with
              | none =>
                  simp [hΩ, hfind, hsig] at h
              | some sig =>
                  by_cases hiface : (sig.iface == iface) = true
                  · by_cases hwt : (templateWellTypedN t σ sigmaCN) = true
                    · simp [hΩ, hfind, hsig, hiface, hwt] at h
                      subst h
                      exact ⟨f, sig, hfind, hsig, hiface, hwt⟩
                    · simp [hΩ, hfind, hsig, hiface, hwt] at h
                  · simp [hΩ, hfind, hsig, hiface] at h

theorem resolve_template_interface_sound_nested
    (x : VarName) (iface : InterfaceName) (choices : List CallableTemplateN)
    (Ω : Snapshot) (σ : Store) (sigmaCN : CallableRegistryN) (tmpl : CallableTemplateN) :
    resolveTemplateChoiceN x iface choices Ω σ sigmaCN = some tmpl ->
    ∃ sig, sigmaCN (templateFnN tmpl) = some sig ∧ (sig.iface == iface) = true := by
  intro h
  rcases resolve_template_choice_sound_nested
      (x := x) (iface := iface) (choices := choices)
      (Ω := Ω) (σ := σ) (sigmaCN := sigmaCN) (tmpl := tmpl) h
    with ⟨f, sig, hfind, hsig, hiface, _⟩
  have htf : templateFnN tmpl = f := findTemplateN_sound_fn choices f tmpl hfind
  refine ⟨sig, ?_⟩
  constructor
  · simpa [htf] using hsig
  · exact hiface

theorem resolve_template_arguments_sound_nested
    (x : VarName) (iface : InterfaceName) (choices : List CallableTemplateN)
    (Ω : Snapshot) (σ : Store) (sigmaCN : CallableRegistryN) (tmpl : CallableTemplateN) :
    resolveTemplateChoiceN x iface choices Ω σ sigmaCN = some tmpl ->
    ∃ sig, sigmaCN (templateFnN tmpl) = some sig ∧
      argsAllValidN tmpl sig σ sigmaCN = true := by
  intro h
  rcases resolve_template_choice_sound_nested
    (x := x) (iface := iface) (choices := choices)
    (Ω := Ω) (σ := σ) (sigmaCN := sigmaCN) (tmpl := tmpl) h
    with ⟨f, sig, hfind, hsigf, _, hwt⟩
  have htf : templateFnN tmpl = f := findTemplateN_sound_fn choices f tmpl hfind
  have hsigtmpl : sigmaCN (templateFnN tmpl) = some sig := by
    simpa [htf] using hsigf
  have hcomp := templateWellTypedN_components
    (tmpl := tmpl) (σ := σ) (sigmaCN := sigmaCN) (sig := sig) hsigtmpl hwt
  exact ⟨sig, hsigtmpl, hcomp.1⟩

theorem resolve_template_arguments_complete
    (x : VarName) (iface : InterfaceName) (choices : List CallableTemplateN)
    (Ω : Snapshot) (σ : Store) (sigmaCN : CallableRegistryN)
    (wf : wellFormedRegistryN sigmaCN) (tmpl : CallableTemplateN) :
    resolveTemplateChoiceN x iface choices Ω σ sigmaCN = some tmpl ->
    ∃ sig, sigmaCN (templateFnN tmpl) = some sig ∧
      argsCompleteN (templateArgsN tmpl) sig.params = true ∧
      (paramNamesN sig.params).Nodup := by
  intro h
  rcases resolve_template_choice_sound_nested
    (x := x) (iface := iface) (choices := choices)
    (Ω := Ω) (σ := σ) (sigmaCN := sigmaCN) (tmpl := tmpl) h
    with ⟨f, sig, hfind, hsigf, _, hwt⟩
  have htf : templateFnN tmpl = f := findTemplateN_sound_fn choices f tmpl hfind
  have hsigtmpl : sigmaCN (templateFnN tmpl) = some sig := by
    simpa [htf] using hsigf
  have hcomp := templateWellTypedN_components
    (tmpl := tmpl) (σ := σ) (sigmaCN := sigmaCN) (sig := sig) hsigtmpl hwt
  refine ⟨sig, hsigtmpl, hcomp.2, ?_⟩
  exact wf (templateFnN tmpl) sig hsigtmpl

inductive DeclTemplateN where
  | assign : VarName -> Val -> DeclTemplateN
  | bindTemplate : VarName -> InterfaceName -> List CallableTemplateN -> DeclTemplateN
  | bindGivenTemplate : VarName -> InterfaceName -> List CallableTemplateN -> GivenPolicy -> DeclTemplateN

def evalDeclTemplateNE :
    DeclTemplateN -> Store -> Snapshot -> CallableRegistryN -> GivenInput -> Except EvalError (Store × Snapshot)
  | .assign x v, σ, Ω, _, _ => .ok (storeUpdate σ x v, Ω)
  | .bindTemplate x iface choices, σ, Ω, sigmaCN, _ =>
      match resolveTemplateChoiceN x iface choices Ω σ sigmaCN with
      | some tmpl => .ok (storeUpdate σ x (.vstr (templateFnN tmpl)), Ω)
      | none => .error (.unresolvedBinding x)
  | .bindGivenTemplate x iface choices policy, σ, Ω, sigmaCN, input =>
      let Ωg := policy input Ω
      match resolveTemplateChoiceN x iface choices Ωg σ sigmaCN with
      | some tmpl => .ok (storeUpdate σ x (.vstr (templateFnN tmpl)), Ω)
      | none => .error (.unresolvedBinding x)

def evalDeclTemplatesNE :
    List DeclTemplateN -> Store -> Snapshot -> CallableRegistryN -> GivenInput -> Except EvalError (Store × Snapshot)
  | [], σ, Ω, _, _ => .ok (σ, Ω)
  | d :: ds, σ, Ω, sigmaCN, input =>
      match evalDeclTemplateNE d σ Ω sigmaCN input with
      | .ok (σ₁, Ω₁) => evalDeclTemplatesNE ds σ₁ Ω₁ sigmaCN input
      | .error err => .error err

theorem evalDeclE_template_preservation_except_nested
    (δ : DeclTemplateN) (σ : Store) (Ω : Snapshot) (sigmaCN : CallableRegistryN)
    (input : GivenInput) (σ' : Store) (Ω' : Snapshot) :
    evalDeclTemplateNE δ σ Ω sigmaCN input = .ok (σ', Ω') -> Ω' = Ω := by
  intro h
  cases δ with
  | assign x v =>
      simp [evalDeclTemplateNE] at h
      rcases h with ⟨hσ, hΩ⟩
      exact hΩ.symm
  | bindTemplate x iface choices =>
      cases hres : resolveTemplateChoiceN x iface choices Ω σ sigmaCN with
      | none =>
          simp [evalDeclTemplateNE, hres] at h
      | some tmpl =>
          simp [evalDeclTemplateNE, hres] at h
          rcases h with ⟨hσ, hΩ⟩
          exact hΩ.symm
  | bindGivenTemplate x iface choices policy =>
      cases hres : resolveTemplateChoiceN x iface choices (policy input Ω) σ sigmaCN with
      | none =>
          simp [evalDeclTemplateNE, hres] at h
      | some tmpl =>
          simp [evalDeclTemplateNE, hres] at h
          rcases h with ⟨hσ, hΩ⟩
          exact hΩ.symm

theorem core_progress_except_template_nested
    (ds : List DeclTemplateN) (σ : Store) (Ω : Snapshot) (sigmaCN : CallableRegistryN)
    (input : GivenInput) :
    (∃ σ' Ω', evalDeclTemplatesNE ds σ Ω sigmaCN input = .ok (σ', Ω')) ∨
    (∃ err, evalDeclTemplatesNE ds σ Ω sigmaCN input = .error err) := by
  let r := evalDeclTemplatesNE ds σ Ω sigmaCN input
  cases hr : r with
  | ok result =>
      rcases result with ⟨σ', Ω'⟩
      left
      refine ⟨σ', Ω', ?_⟩
      simpa [r] using hr
  | error err =>
      right
      refine ⟨err, ?_⟩
      simpa [r] using hr

end OPALCore
end TVL
