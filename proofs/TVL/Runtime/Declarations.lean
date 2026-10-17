/- DRAFT TVL 1.3: declarable actions, approval categories and severity order. -/
import Mathlib.Tactic

namespace TVL.Runtime

inductive Action where
  | notify | openNextStep | optimize | rollback | throttle | degrade | suspend
  | blockAction | haltUnit
  deriving DecidableEq, Repr

inductive Approval where
  | none | standing | human
  deriving DecidableEq, Repr

inductive Severity where
  | info | warning | critical
  deriving DecidableEq, Repr

def Severity.rank : Severity → ℕ
  | .info => 0
  | .warning => 1
  | .critical => 2

def normalizeSeverity (s : Option Severity) : Severity := s.getD .critical

def severityMeet (a b : Severity) : Severity :=
  if a.rank ≤ b.rank then b else a

theorem severity_meet_glb (a b c : Severity) :
    a.rank ≤ (severityMeet a b).rank ∧ b.rank ≤ (severityMeet a b).rank ∧
    ((severityMeet a b).rank ≤ c.rank ↔ a.rank ≤ c.rank ∧ b.rank ≤ c.rank) := by
  cases a <;> cases b <;> cases c <;> decide

theorem absent_notify_severity : normalizeSeverity none = .critical := rfl

def remoteAction (a : Action) : Prop :=
  a ≠ .notify ∧ a ≠ .blockAction ∧ a ≠ .haltUnit

def nonePermitted (a : Action) : Prop :=
  a = .notify ∨ a = .openNextStep ∨ a = .blockAction ∨ a = .haltUnit

def standingPermitted (a : Action) : Prop :=
  a = .optimize ∨ a = .rollback ∨ a = .throttle ∨ a = .degrade

end TVL.Runtime
