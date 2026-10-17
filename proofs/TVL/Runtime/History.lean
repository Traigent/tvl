/- DRAFT TVL 1.3: events, selectors and predicate meaning on complete histories. -/
import Mathlib.Tactic

namespace TVL.Runtime

inductive UnitKind where
  | trace | invocation
  deriving DecidableEq, Repr

inductive EventType where
  | unitStart | unitEnd | toolCall | toolResult | modelCall | handoff | error
  | authorizationGranted | authorizationRevoked
  deriving DecidableEq, Repr

inductive Status where
  | running | completed | failed | rejected
  deriving DecidableEq, Repr

structure EventId where
  producer : ℕ
  sequence : ℕ
  deriving DecidableEq, Repr

structure Event where
  id : EventId
  kind : EventType
  time : ℚ
  unitId : ℕ
  correlation : Option ℕ
  toolCallId : Option ℕ
  parent : Option EventId
  tool : Option ℕ
  status : Option Status
  ref : Option ℕ
  deriving DecidableEq, Repr

structure Selector where
  kind : EventType
  tool : Option ℕ := none
  status : Option Status := none
  ref : Option ℕ := none
  deriving DecidableEq, Repr

def Selector.matches (s : Selector) (e : Event) : Prop :=
  e.kind = s.kind ∧ (s.tool = none ∨ e.tool = s.tool) ∧
  (s.status = none ∨ e.status = s.status) ∧ (s.ref = none ∨ e.ref = s.ref)

inductive Correlation where
  | unit | correlationId | toolCallId
  deriving DecidableEq, Repr

def correlationKey (c : Correlation) (e : Event) : Option ℕ :=
  match c with
  | .unit => some e.unitId
  | .correlationId => e.correlation
  | .toolCallId => e.toolCallId

def sameKey (c : Correlation) (a b : Event) : Prop :=
  ∃ k, correlationKey c a = some k ∧ correlationKey c b = some k

structure History where
  events : List Event
  metric : Option ℚ
  checker : Option ℕ

def before (h : History) (a b : Event) : Prop :=
  a ∈ h.events ∧ b ∈ h.events ∧ h.events.idxOf a < h.events.idxOf b

structure Protocol where
  states : Finset ℕ
  start : ℕ
  accepting : Finset ℕ
  rejecting : Finset ℕ
  alphabet : Event → Bool
  /-- Includes the declared ignore/reject treatment of unlisted transitions. -/
  transition : ℕ → Event → ℕ

def protocolStates (d : Protocol) (h : History) : List ℕ :=
  (h.events.filter d.alphabet).scanl d.transition d.start

inductive Predicate where
  | metricExceeds (limit : ℚ)
  | absence (a : Selector)
  | boundedExistence (a : Selector) (bound : ℕ)
  | precedence (a b : Selector) (reusable : Bool) (correlate : Correlation)
  | boundedResponse (a b : Selector) (deadline : ℚ) (correlate : Correlation)
  | protocol (dfa : Protocol)
  | checkerLabel (labels : Finset ℕ)

def exactPredicate : Predicate → Bool
  | .metricExceeds _ | .checkerLabel _ => false
  | _ => true

def legalPrecedence (h : History) (a b : Selector) (reusable : Bool)
    (c : Correlation) : Prop :=
  ∃ assign : Event → Event,
    (∀ e ∈ h.events, b.matches e →
      a.matches (assign e) ∧ sameKey c (assign e) e ∧ before h (assign e) e ∧
      ¬∃ r ∈ h.events, r.kind = .authorizationRevoked ∧
        (assign e).kind = .authorizationGranted ∧ sameKey c (assign e) r ∧
        r.ref = (assign e).ref ∧ r.ref ≠ none ∧ before h (assign e) r ∧ before h r e) ∧
    (reusable = false → ∀ e ∈ h.events, ∀ f ∈ h.events,
      b.matches e → b.matches f → assign e = assign f → e = f)

def legalResponse (h : History) (a b : Selector) (deadline : ℚ)
    (c : Correlation) : Prop :=
  ∃ assign : Event → Event,
    (∀ e ∈ h.events, a.matches e →
      b.matches (assign e) ∧ sameKey c e (assign e) ∧ before h e (assign e) ∧
      0 ≤ (assign e).time - e.time ∧ (assign e).time - e.time ≤ deadline) ∧
    (∀ e ∈ h.events, ∀ f ∈ h.events,
      a.matches e → a.matches f → assign e = assign f → e = f)

noncomputable def violation (q : Predicate) (h : History) : Prop := by
  classical
  exact match q with
  | .metricExceeds limit => ∃ x, h.metric = some x ∧ limit < x
  | .absence a => ∃ e ∈ h.events, a.matches e
  | .boundedExistence a B => B < (h.events.filter (fun e => decide (a.matches e))).length
  | .precedence a b reusable c => ¬legalPrecedence h a b reusable c
  | .boundedResponse a b deadline c => ¬legalResponse h a b deadline c
  | .protocol d =>
      (∃ s ∈ protocolStates d h, s ∈ d.rejecting) ∨
      (h.events.filter d.alphabet).foldl d.transition d.start ∉ d.accepting
  | .checkerLabel labels => ∃ label, h.checker = some label ∧ label ∈ labels

end TVL.Runtime
