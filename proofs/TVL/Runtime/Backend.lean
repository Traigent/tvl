/-
  TVL 1.3 (DRAFT), Theorem 12.10: representable backend_v1 fields only.
  Numeric and token codecs are explicit bijections on normalized values.
  Proving a particular IEEE-754/shortest-decimal codec implements that bijection
  is outside this representation theorem. No window-verdict equivalence follows.
-/
import Mathlib.Tactic

namespace TVL.Runtime.Backend

inductive Method where
  | clopperPearsonExactV1
  deriving DecidableEq
inductive Sampling where
  | unverified
  deriving DecidableEq
inductive Model where
  | iidBernoulliWithinWindowV1
  deriving DecidableEq
inductive Scope where
  | agent | tenantFloor
  deriving DecidableEq

/-- The thirteen normalized profile fields plus scope and stored evaluation names. -/
structure Profile (Environment Number : Type) where
  latencyThresholdMs : ℕ
  environment : Environment
  maxViolationRate : Number
  confidence : Number
  windowHours : ℕ
  graceMinutes : ℕ
  minSamples : ℕ
  maxUnresolvedFraction : Number
  falseAlarmBudget : Number
  horizonDays : ℕ
  closureWindows : ℕ
  closureMaxAgeHours : ℕ
  /-- Backend's singleton `latency_violation_rate` kind, represented by Unit. -/
  kind : Unit
  scope : Scope
  method : Method
  sampling : Sampling
  model : Model

/-- Renamed TVL fields; identity names/local annotations are intentionally absent. -/
structure LocalProfile (Environment Decimal : Type) where
  exceeds : ℕ
  deploymentEnvironment : Environment
  maxRate : Decimal
  confidence : Decimal
  tumblingHours : ℕ
  graceMinutes : ℕ
  minSamples : ℕ
  maxUnresolvedFraction : Decimal
  falseAlarmBudget : Decimal
  horizonDays : ℕ
  closureWindows : ℕ
  closureMaxAgeHours : ℕ
  appliesTo : Scope
  method : Method
  sampling : Sampling
  model : Model

def lower {LocalEnv Token Decimal Number : Type}
    (tokens : LocalEnv ≃ Token) (numeric : Decimal ≃ Number)
    (p : LocalProfile LocalEnv Decimal) : Profile Token Number :=
  ⟨p.exceeds, tokens p.deploymentEnvironment, numeric p.maxRate, numeric p.confidence,
   p.tumblingHours, p.graceMinutes, p.minSamples, numeric p.maxUnresolvedFraction,
   numeric p.falseAlarmBudget, p.horizonDays, p.closureWindows, p.closureMaxAgeHours,
   (), p.appliesTo, p.method, p.sampling, p.model⟩

def lift {LocalEnv Token Decimal Number : Type}
    (tokens : LocalEnv ≃ Token) (numeric : Decimal ≃ Number)
    (p : Profile Token Number) : LocalProfile LocalEnv Decimal :=
  ⟨p.latencyThresholdMs, tokens.symm p.environment, numeric.symm p.maxViolationRate,
   numeric.symm p.confidence, p.windowHours, p.graceMinutes, p.minSamples,
   numeric.symm p.maxUnresolvedFraction, numeric.symm p.falseAlarmBudget, p.horizonDays,
   p.closureWindows, p.closureMaxAgeHours, p.scope, p.method, p.sampling, p.model⟩

/-- Theorem 12.10 in both directions, retaining method/model/sampling fields. -/
theorem backend_profile_roundtrip {LocalEnv Token Decimal Number : Type}
    (tokens : LocalEnv ≃ Token) (numeric : Decimal ≃ Number)
    (p : LocalProfile LocalEnv Decimal) (b : Profile Token Number) :
    lift tokens numeric (lower tokens numeric p) = p ∧
    lower tokens numeric (lift tokens numeric b) = b := by
  constructor
  · cases p; simp [lift, lower]
  · cases b; simp [lift, lower]

end TVL.Runtime.Backend
