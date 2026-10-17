/-
  TVL 1.3 (DRAFT), §§12.7/12.13. Erasure is relative to the existing Lean
  TVL.Context, Config, Domain, Formula, evalFormula and encodeFormula definitions.
  Legacy statistical test implementations are opaque inputs to TVL.Gate.
-/
import TVL.Gate
import TVL.SMTEncoding
import TVL.Runtime.History

namespace TVL.Runtime

structure LegacyModule (Env Evidence : Type) where
  context : TVL.Context
  domains : Env → TVL.VarName → TVL.Domain
  structural : TVL.Formula
  operational : Env → Bool
  gateEvidence : Evidence → TVL.Gate.Evidence

def legacyDecision {Env Evidence} (m : LegacyModule Env Evidence) (y : Evidence) : TVL.Gate.Decision :=
  TVL.Gate.decideGate (m.gateEvidence y)

/-- Distinct typing namespace; these identifiers cannot extend the TVAR context. -/
structure RuntimeName where
  id : ℕ
  deriving DecidableEq

structure ExtendedModule (Env Evidence Input Output Control : Type) where
  legacy : LegacyModule Env Evidence
  requirements : List (RuntimeName × Predicate)
  promotionMonitors : List (Evidence → TVL.Gate.MonitorVerdict)
  runtimeMonitors : List (Input → Output)
  responses : List (Input → Control)

def erase {Env Evidence Input Output Control}
    (m : ExtendedModule Env Evidence Input Output Control) : LegacyModule Env Evidence := m.legacy

def embed {Env Evidence Input Output Control} (m : LegacyModule Env Evidence) :
    ExtendedModule Env Evidence Input Output Control := ⟨m, [], [], [], []⟩

def extendedDecision {Env Evidence Input Output Control}
    (m : ExtendedModule Env Evidence Input Output Control) (y : Evidence) : TVL.Gate.Decision :=
  TVL.Gate.joinMonitors (legacyDecision (erase m) y) (m.promotionMonitors.map (fun f => f y))

def runtimeOutput {Env Evidence Input Output Control}
    (m : ExtendedModule Env Evidence Input Output Control) (o : Input) : List Output × List Control :=
  (m.runtimeMonitors.map (fun f => f o), m.responses.map (fun f => f o))

/-- Theorem 12.1: embedding has the same gate and empty runtime/control outputs. -/
theorem conservative_extension {Env Evidence Input Output Control}
    (m : LegacyModule Env Evidence) (y : Evidence) (o : Input) :
    extendedDecision (embed (Input := Input) (Output := Output) (Control := Control) m) y =
      legacyDecision m y ∧
    runtimeOutput (embed (Output := Output) (Control := Control) m) o = ([], []) := by
  simp [extendedDecision, embed, erase, runtimeOutput]

theorem no_promotion_monitors {Env Evidence Input Output Control}
    (m : ExtendedModule Env Evidence Input Output Control) (y : Evidence)
    (h : m.promotionMonitors = []) :
    extendedDecision m y = legacyDecision (erase m) y := by
  simp [extendedDecision, h]

def structuralFeasible {Env Evidence} (m : LegacyModule Env Evidence) (c : TVL.Config) : Prop :=
  TVL.evalFormula m.structural c = some true

def configDomain {Env Evidence} (m : LegacyModule Env Evidence) (env : Env) (c : TVL.Config) : Prop :=
  ∀ x v, c x = some v → (m.domains env x).contains v = true

/-- BY-CONSTRUCTION (§12.2): projection preserves the stored legacy fields.
    This does not prove syntax-level exclusion of runtime spellings from Γ or
    generated variables; that substantive source-erasure obligation remains OPEN. -/
theorem structural_projection {Env Evidence Input Output Control}
    (m : ExtendedModule Env Evidence Input Output Control)
    (env : Env) (c : TVL.Config) (P : TVL.PrecisionFactor) (idx : TVL.Val → Option ℕ) :
    m.legacy.context = (erase m).context ∧
    configDomain m.legacy env c = configDomain (erase m) env c ∧
    structuralFeasible m.legacy c = structuralFeasible (erase m) c ∧
    m.legacy.operational env = (erase m).operational env ∧
    TVL.encodeFormula m.legacy.structural P idx = TVL.encodeFormula (erase m).structural P idx ∧
    TVL.formulaVars m.legacy.structural = TVL.formulaVars (erase m).structural := by
  exact ⟨rfl, rfl, rfl, rfl, rfl, rfl⟩

theorem promotion_refinement {Env Evidence Input Output Control}
    (m : ExtendedModule Env Evidence Input Output Control) (y : Evidence) :
    extendedDecision m y = .promote ↔ legacyDecision (erase m) y = .promote ∧
      ∀ f ∈ m.promotionMonitors, f y = .met := by
  simp [extendedDecision, TVL.Gate.join_promote_iff]

end TVL.Runtime
