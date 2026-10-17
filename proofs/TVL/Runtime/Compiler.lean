/- DRAFT TVL 1.3: normalized language source/projection and an OPEN preservation target. -/
import TVL.Runtime.Compose
import TVL.Runtime.History

namespace TVL.Runtime

structure RuntimeSource where
  contract : NormalizedContract
  predicates : ℕ → Option Predicate
  /-- Omitted notify severity must become critical before comparison/meet. -/
  rawSeverity : ℕ → Option Severity

def RuntimeSource.WellFormed (source : RuntimeSource) : Prop :=
  ValidReachableContract source.contract ∧
  ∀ id r, source.contract.rules id = some r → r.identity.action = .notify →
    r.severity = normalizeSeverity (source.rawSeverity id)

/-- A normalized declaration projection (declarations only; no evaluation state).
    This is not a concrete wire encoder or a verified implementation. -/
structure CompiledContract where
  contract : NormalizedContract
  predicates : ℕ → Option Predicate

def LanguageLowering (source : RuntimeSource) (output : CompiledContract) : Prop :=
  output.contract = source.contract ∧ output.predicates = source.predicates ∧
  (∀ id r, output.contract.rules id = some r → r.identity.action = .notify →
    r.severity = normalizeSeverity (source.rawSeverity id))

/-- OPEN: declaration normalization/projection must be connected to an actual
    compiler and complete source syntax. No parser, canonical wire encoding or
    source-to-contract preservation proof is supplied by this target. -/
def compiled_contract_correct_statement
    (compile : RuntimeSource → Option CompiledContract) : Prop :=
  ∀ source output, source.WellFormed → compile source = some output →
    LanguageLowering source output

end TVL.Runtime
