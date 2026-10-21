/- TVL 1.3 (DRAFT), §12.12. Numeric product order and explicit full-contract gaps. -/
import TVL.Runtime.Declarations

namespace TVL.Runtime

structure RuntimeBounds where
  maxRate : ℚ
  confidence : ℚ
  minSamples : ℕ
  maxUnresolved : ℚ
  closureWindows : ℕ
  closureAge : ℚ
  recoveryWithin : ℚ
  staleWindows : ℕ
  deriving DecidableEq

def Tightens (a b : RuntimeBounds) : Prop :=
  a.maxRate ≤ b.maxRate ∧ b.confidence ≤ a.confidence ∧ b.minSamples ≤ a.minSamples ∧
  a.maxUnresolved ≤ b.maxUnresolved ∧ b.closureWindows ≤ a.closureWindows ∧
  a.closureAge ≤ b.closureAge ∧ a.recoveryWithin ≤ b.recoveryWithin ∧
  a.staleWindows ≤ b.staleWindows

def rawBoundsMeet (a b : RuntimeBounds) : RuntimeBounds :=
  ⟨min a.maxRate b.maxRate, max a.confidence b.confidence,
   max a.minSamples b.minSamples, min a.maxUnresolved b.maxUnresolved,
   max a.closureWindows b.closureWindows, min a.closureAge b.closureAge,
   min a.recoveryWithin b.recoveryWithin, min a.staleWindows b.staleWindows⟩

theorem raw_bounds_glb (a b c : RuntimeBounds) :
    Tightens (rawBoundsMeet a b) a ∧ Tightens (rawBoundsMeet a b) b ∧
    (Tightens c (rawBoundsMeet a b) ↔ Tightens c a ∧ Tightens c b) := by
  simp only [Tightens, rawBoundsMeet, min_le_iff, le_max_iff, le_min_iff, max_le_iff]
  constructor
  · exact ⟨Or.inl le_rfl, Or.inl le_rfl, Or.inl le_rfl, Or.inl le_rfl,
      Or.inl le_rfl, Or.inl le_rfl, Or.inl le_rfl, Or.inl le_rfl⟩
  constructor
  · exact ⟨Or.inr le_rfl, Or.inr le_rfl, Or.inr le_rfl, Or.inr le_rfl,
      Or.inr le_rfl, Or.inr le_rfl, Or.inr le_rfl, Or.inr le_rfl⟩
  · tauto

/-- Mandatory numeric reachability for primary rational runtime rate/recovery pairs.
    The legacy backend power warning is deliberately not replaced by this check. -/
def numericReachable (b : RuntimeBounds) (width grace alpha : ℚ) : Prop :=
  0 < b.maxRate ∧ b.maxRate < 1 ∧ 0 ≤ b.confidence ∧ b.confidence ≤ 1 ∧
  1 ≤ b.minSamples ∧ 0 ≤ b.maxUnresolved ∧ b.maxUnresolved ≤ 1 ∧
  1 ≤ b.closureWindows ∧ 0 < b.closureAge ∧ 0 < b.recoveryWithin ∧ 1 ≤ b.staleWindows ∧
  0 < width ∧ 0 ≤ grace ∧ 0 < alpha ∧ alpha ≤ 1 ∧
  (1 - b.maxRate) ^ b.minSamples ≤ 1 - b.confidence ∧
  60 * b.closureAge ≥ 60 * b.closureWindows * width + grace + 60 ∧
  b.recoveryWithin ≥ b.closureWindows * width

/-- Validation never repairs an unreachable meet by weakening it. The supplied
    check is the complete well-formedness/reachability check of its caller. -/
def checkedBoundsMeet (a b : RuntimeBounds) (check : RuntimeBounds → Bool) : Option RuntimeBounds :=
  let raw := rawBoundsMeet a b
  if check raw then some raw else none

theorem checked_bounds_meet_iff (a b : RuntimeBounds) (check : RuntimeBounds → Bool) :
    checkedBoundsMeet a b check = some (rawBoundsMeet a b) ↔
      check (rawBoundsMeet a b) = true := by
  simp [checkedBoundsMeet]

/-- Immutable identity binds trigger/action/target/fallback/rate floor/error policy
    and repeat interval; equality is required before meeting two retained rules. -/
structure RuleIdentity where
  trigger : ℕ
  action : Action
  target : Option ℕ
  fallback : Option ℕ
  rateFloor : Option ℚ
  onCheckError : Option Bool
  repeatAfter : Option ℚ
  deriving DecidableEq

/-- Authored response fields only; platform grants are not TVL declarations. -/
structure NormalizedRule where
  identity : RuleIdentity
  approval : Approval
  maxRepeats : ℕ
  severity : Severity
  /-- Normalized `deploy` (absent = `never`); meaningful only on `optimize`. -/
  deploy : DeployMode

def approvalRank : Approval → ℕ
  | .none => 0 | .standing => 1 | .human => 2

def RuleTightens (a b : NormalizedRule) : Prop :=
  a.identity = b.identity ∧ approvalRank b.approval ≤ approvalRank a.approval ∧
  a.maxRepeats ≤ b.maxRepeats ∧
  (b.identity.action = .notify → b.severity.rank ≤ a.severity.rank) ∧
  b.deploy.rank ≤ a.deploy.rank

def rawRuleMeet (a b : NormalizedRule) : NormalizedRule :=
  { identity := a.identity,
    approval := if approvalRank a.approval ≤ approvalRank b.approval then b.approval else a.approval,
    maxRepeats := min a.maxRepeats b.maxRepeats,
    severity := severityMeet a.severity b.severity,
    deploy := deployMeet a.deploy b.deploy }

structure ContractIdentity where
  /-- Canonical predicate/unit/population/source/environment/attribution/checker,
      sampling declarations, method/model/resource contract identity. -/
  fixedContract : ℕ
  width : ℚ
  grace : ℚ
  horizon : ℕ
  alpha : ℚ
  deriving DecidableEq

structure NormalizedContract where
  identity : ContractIdentity
  bounds : RuntimeBounds
  declarations : Finset ℕ
  rules : ℕ → Option NormalizedRule
  floorMonitors : Finset ℕ
  floorProvenance : ℕ → Option ℕ
  /-- Canonical referenced declarations, checked after union. -/
  references : Finset ℕ

def ContractCompatible (a b : NormalizedContract) : Prop :=
  a.identity = b.identity ∧
  (∀ id ra rb, a.rules id = some ra → b.rules id = some rb → ra.identity = rb.identity) ∧
  a.floorProvenance = b.floorProvenance

def ContractTightens (a b : NormalizedContract) : Prop :=
  a.identity = b.identity ∧ Tightens a.bounds b.bounds ∧ b.declarations ⊆ a.declarations ∧
  (∀ id rb, b.rules id = some rb → ∃ ra, a.rules id = some ra ∧ RuleTightens ra rb) ∧
  b.floorMonitors ⊆ a.floorMonitors ∧
  (∀ id ∈ b.floorMonitors, a.floorProvenance id = b.floorProvenance id)

def rawContractMeet (a b : NormalizedContract) : NormalizedContract :=
  { identity := a.identity,
    bounds := rawBoundsMeet a.bounds b.bounds,
    declarations := a.declarations ∪ b.declarations,
    rules := fun id => match a.rules id, b.rules id with
      | some ra, some rb => some (rawRuleMeet ra rb)
      | some ra, none => some ra
      | none, some rb => some rb
      | none, none => none,
    floorMonitors := a.floorMonitors ∪ b.floorMonitors,
    floorProvenance := fun id => (a.floorProvenance id).or (b.floorProvenance id),
    references := a.references ∪ b.references }

def ValidReachableContract (c : NormalizedContract) : Prop :=
  numericReachable c.bounds c.identity.width c.identity.grace c.identity.alpha ∧
  c.references ⊆ c.declarations ∧
  (∀ id ∈ c.floorMonitors, (c.floorProvenance id).isSome = true) ∧
  (∀ id r, c.rules id = some r →
    (r.identity.action = .suspend → r.approval = .human) ∧
    (r.approval = .none → nonePermitted r.identity.action) ∧
    (r.deploy = .ifPromoted → r.identity.action = .optimize))

noncomputable def composeContracts (a b : NormalizedContract) : Option NormalizedContract := by
  classical
  exact if ContractCompatible a b ∧ ValidReachableContract (rawContractMeet a b)
    then some (rawContractMeet a b) else none

/-- OPEN: this concrete finite rule model includes approval/severity/deploy order,
    repeat bounds, declaration union and floor provenance, but its WF/reachability predicate is
    only the rational static fragment. Catalogue-wide validator refinement
    remains OPEN; platform grants and registration are outside TVL composition. -/
def compose_partial_statement : Prop :=
  ∀ a b, ContractCompatible a b →
    ContractTightens (rawContractMeet a b) a ∧ ContractTightens (rawContractMeet a b) b ∧
    (∀ c, ContractCompatible c a → ContractTightens c a → ContractTightens c b →
      ContractTightens c (rawContractMeet a b)) ∧
    (composeContracts a b = some (rawContractMeet a b) ↔
      ValidReachableContract (rawContractMeet a b))

end TVL.Runtime
