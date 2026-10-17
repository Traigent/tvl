/-
  TVL 1.2 promotion decision, formal semantics §9.7.
  Inputs are the results of the legacy validity/statistical predicates. This
  module proves the decision logic, not the numerical tests producing them.
-/
import TVL.Dominance

namespace TVL.Gate

inductive Decision where
  | error | reject | noDecision | promote
  deriving DecidableEq, Repr

/-- Evaluated §9 predicates; the two coherence conditions below are explicit. -/
structure Evidence where
  valid : Bool
  chancePass : Bool
  bandHardFail : Bool
  inferior : Bool
  bandPass : Bool
  allNonInferior : Bool
  anySuperior : Bool
  deriving DecidableEq, Repr

def Evidence.statDominates (e : Evidence) : Bool :=
  e.allNonInferior && e.anySuperior

def Promote (e : Evidence) : Prop :=
  e.valid = true ∧ e.chancePass = true ∧ e.bandPass = true ∧
    e.statDominates = true

/-- Consistency of the legacy test results, not a statistical guarantee. -/
def Coherent (e : Evidence) : Prop :=
  (e.bandPass = true → e.bandHardFail = false) ∧
  (e.statDominates = true → e.inferior = false)

def decideGate (e : Evidence) : Decision :=
  if !e.valid then .error
  else if !e.chancePass || e.bandHardFail then .reject
  else if e.inferior then .reject
  else if !e.bandPass then .noDecision
  else if e.statDominates then .promote
  else .noDecision

theorem gate_sound (e : Evidence) (h : decideGate e = .promote) : Promote e := by
  simp only [decideGate] at h
  split_ifs at h; simp_all [Promote, Bool.not_eq_true]

theorem gate_complete (e : Evidence) (hc : Coherent e) (h : Promote e) :
    decideGate e = .promote := by
  rcases h with ⟨hv, hch, hb, hd⟩
  simp [decideGate, hv, hch, hb, hd, hc.1 hb, hc.2 hd]

theorem gate_correct (e : Evidence) (hc : Coherent e) :
    decideGate e = .promote ↔ Promote e :=
  ⟨gate_sound e, gate_complete e hc⟩

inductive MonitorVerdict where
  | met | breached | unknown
  deriving DecidableEq, Repr

/-- §12.7: preserve errors; any rejection dominates any inconclusive result. -/
def joinMonitors (d : Decision) (vs : List MonitorVerdict) : Decision :=
  if d = .error then .error
  else if d = .reject ∨ .breached ∈ vs then .reject
  else if d = .noDecision ∨ .unknown ∈ vs then .noDecision
  else d

@[simp] theorem join_empty (d : Decision) : joinMonitors d [] = d := by
  cases d <;> simp [joinMonitors]

theorem join_promote_iff (d : Decision) (vs : List MonitorVerdict) :
    joinMonitors d vs = .promote ↔ d = .promote ∧ ∀ v ∈ vs, v = .met := by
  have h : (∀ v ∈ vs, v = .met) ↔
      MonitorVerdict.breached ∉ vs ∧ MonitorVerdict.unknown ∉ vs := by
    constructor
    · intro h
      constructor <;> intro hx <;> have := h _ hx <;> contradiction
    · rintro ⟨hb, hu⟩ v hv
      cases v <;> simp_all
  rw [h]
  cases d <;> simp [joinMonitors] <;> split_ifs <;> simp_all

end TVL.Gate
