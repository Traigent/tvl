"""Finite abstraction of RFC 0001 §3 — binding partition, resolution, certificates.

This is a MODEL, not the implementation: types are tiny, value spaces are
finite, and the semantics transcribe the RFC clauses one-to-one so that
property checks read like the spec. Section references are to
formalization/rfc-0001-knob-bindings-cvars-policies.md (Draft v2).
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Canonical hashing H_c — model form of RFC §3.5.
# The model uses sorted-key JSON with the RFC's value restrictions; the
# cross-implementation RFC 8785 known-answer fixtures are a Phase 4 artifact.
# ---------------------------------------------------------------------------


def h_c(value: Any) -> str:
    """Model canonical hash: NFC-normalised, sorted-key, finite-number JSON."""

    def _norm(v: Any) -> Any:
        if isinstance(v, str):
            return unicodedata.normalize("NFC", v)
        if isinstance(v, float):
            if v != v or v in (float("inf"), float("-inf")):
                raise ValueError("non-finite numbers are rejected, never hashed")
            if v == 0.0:
                return 0.0  # -0.0 -> 0.0
            return v
        if isinstance(v, Mapping):
            keys = list(v.keys())
            if len(keys) != len(set(keys)):
                raise ValueError("duplicate keys rejected")
            return {_norm(k): _norm(val) for k, val in v.items()}
        if isinstance(v, (list, tuple)):
            return [_norm(item) for item in v]
        return v

    payload = json.dumps(_norm(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Declarations — RFC §3.1, §3.3, §3.8.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TVar:
    name: str
    domain: Tuple[Any, ...]  # finite searched domain (model scope)


@dataclass(frozen=True)
class CVar:
    name: str
    source: str
    cvar_type: str = "float"
    depends_on: Tuple[str, ...] = ()
    validity_domain: Optional[Tuple[float, float]] = None  # closed interval (§3.3)
    require_calibration: bool = False
    signal: str = "sig_v1"
    calibrator: str = "cal_v1"
    calibrator_version: str = "1"
    calibrator_params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Gate:
    kind: str  # v1 registry: "margin_below"
    threshold: str  # namespace ref -> MUST resolve to a CVar (§3.8)


@dataclass(frozen=True)
class Policy:
    name: str
    strategy: str  # v1 registry: "cascade"
    stages: Tuple[str, ...]  # opaque runtime ids, NOT namespace refs (§3.8)
    gates: Tuple[Gate, ...] = ()


@dataclass(frozen=True)
class Module:
    tvars: Tuple[TVar, ...] = ()
    cvars: Tuple[CVar, ...] = ()
    policies: Tuple[Policy, ...] = ()
    # promotion_policy strict-mode declarations (§3.6)
    require_calibration_enabled: bool = False
    has_chance_constraints: bool = False

    @property
    def n_t(self) -> FrozenSet[str]:
        return frozenset(t.name for t in self.tvars)

    @property
    def n_c(self) -> FrozenSet[str]:
        return frozenset(c.name for c in self.cvars)

    @property
    def declared_names(self) -> Tuple[str, ...]:
        """All declared names in order — the shared namespace (§3.7(3))."""
        return tuple(
            [t.name for t in self.tvars]
            + [c.name for c in self.cvars]
            + [p.name for p in self.policies]
        )


# ---------------------------------------------------------------------------
# Static namespace diagnostics — RFC §3.7.
# ---------------------------------------------------------------------------


def namespace_diagnostics(module: Module) -> List[Tuple[str, str]]:
    """Return (code, name) diagnostics for the shared-namespace rules.

    Errors: duplicate names anywhere across tvars ∪ cvars ∪ policies.
    Warning-or-error: namespace_prefix_collision — severity is decided by the
    caller per §3.7(5) (warning on 1.0-valid modules, error with 1.1
    constructs); the model just detects.
    """
    diags: List[Tuple[str, str]] = []
    names = module.declared_names
    seen: Dict[str, int] = {}
    for name in names:
        seen[name] = seen.get(name, 0) + 1
    for name, count in seen.items():
        if count > 1:
            diags.append(("duplicate_name", name))
    unique = sorted(seen)
    for shorter in unique:
        prefix = shorter + "."
        for longer in unique:
            if longer.startswith(prefix):
                diags.append(("namespace_prefix_collision", shorter))
                break
    return diags


def uses_11_constructs(module: Module) -> bool:
    """§3.7(5): the new-surface opt-in that escalates prefix collisions."""
    return bool(module.cvars or module.policies or module.require_calibration_enabled)


# ---------------------------------------------------------------------------
# Certificates and freshness — RFC §3.5.
# ---------------------------------------------------------------------------

CTX_SCHEMA_VERSION = 1
CTX_EXT_KEYS = frozenset(
    {"stage_versions", "model_versions", "budget_assumptions", "cost_assumptions"}
)


@dataclass(frozen=True)
class FreshnessContext:
    """ctx_core (always hashed) + selected extension keys."""

    cvar_name: str
    tuned_parent_values: Tuple[Tuple[str, Any], ...]  # sorted by name
    calibration_source_id: str
    signal_spec_hash: str
    calibrator_id: str
    calibrator_version: str
    calibrator_params_hash: str
    dataset_hash: str
    evidence_n: int
    calibration_split: str
    eval_split: str
    target: str
    extensions: Tuple[Tuple[str, Any], ...] = ()  # subset of CTX_EXT_KEYS

    def freshness_hash(self) -> str:
        core = {
            "ctx_schema_version": CTX_SCHEMA_VERSION,
            "cvar_name": self.cvar_name,
            "tuned_parent_values": list(self.tuned_parent_values),
            "calibration_source_id": self.calibration_source_id,
            "signal_spec_hash": self.signal_spec_hash,
            "calibrator_id": self.calibrator_id,
            "calibrator_version": self.calibrator_version,
            "calibrator_params_hash": self.calibrator_params_hash,
            "dataset_hash": self.dataset_hash,
            "evidence_n": self.evidence_n,
            "calibration_split": self.calibration_split,
            "eval_split": self.eval_split,
            "target": self.target,
        }
        for key, _ in self.extensions:
            if key not in CTX_EXT_KEYS:
                raise ValueError(f"invalid_calibration_context: {key}")
        return h_c({"core": core, "ext": list(self.extensions)})


CERTIFIED = "CERTIFIED"
NO_DECISION = "NO_DECISION"
BEST_EFFORT_UNCERTIFIED = "BEST_EFFORT_UNCERTIFIED"


@dataclass(frozen=True)
class Certificate:
    subject_cvar: str
    subject_type: str
    subject_value_hash: str
    target: str
    issued_hash: str
    decision: str
    evidence_n: int
    evidence_pool_hash: str

    def valid_for(
        self, cvar: str, cvar_type: str, value: Any, ctx: FreshnessContext
    ) -> bool:
        """RFC §3.5 (Draft v4) validity — every field participates; the audit
        copies (target, evidence) must agree with the live context, and the
        live context must itself name the queried CVAR (round-3 fix: closes
        the forged-subject hole)."""
        return (
            ctx.cvar_name == cvar
            and self.subject_cvar == cvar
            and self.subject_type == cvar_type
            and self.subject_value_hash == h_c(value)
            and self.target == ctx.target
            and self.evidence_n == ctx.evidence_n
            and self.evidence_pool_hash == ctx.dataset_hash
            and self.issued_hash == ctx.freshness_hash()
            and self.decision == CERTIFIED
        )


def issue_certificate(
    cvar: str, value: Any, ctx: FreshnessContext, cvar_type: str = "float"
) -> Certificate:
    return Certificate(
        subject_cvar=cvar,
        subject_type=cvar_type,
        subject_value_hash=h_c(value),
        target=ctx.target,
        issued_hash=ctx.freshness_hash(),
        decision=CERTIFIED,
        evidence_n=ctx.evidence_n,
        evidence_pool_hash=ctx.dataset_hash,
    )


# ---------------------------------------------------------------------------
# Resolution — RFC §3.4 (R1-R8 + Accept).
# ---------------------------------------------------------------------------

R1_CYCLE = "cycle"
R2_MISSING_REF = "missing_ref"
R3_DUPLICATE_PROVIDER = "duplicate_provider"
R4_PHASE_MISMATCH = "phase_mismatch"
R5_INFEASIBLE_VALUE = "infeasible_value"
R6_STALE_CERTIFICATE = "stale_certificate"
R7_EVIDENCE_LEAKAGE = "evidence_leakage"
R8_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
NO_DECISION_VERDICT = "no_decision"

ALL_REJECTIONS = (
    R1_CYCLE,
    R2_MISSING_REF,
    R3_DUPLICATE_PROVIDER,
    R4_PHASE_MISMATCH,
    R5_INFEASIBLE_VALUE,
    R6_STALE_CERTIFICATE,
    R7_EVIDENCE_LEAKAGE,
    R8_INSUFFICIENT_EVIDENCE,
)


@dataclass(frozen=True)
class Evidence:
    """Calibration evidence pool (model form)."""

    items: Tuple[str, ...]  # item ids
    split: str  # which split the pool was drawn from
    pool_hash: str = "pool_v1"


@dataclass
class Calibrator:
    """Model calibrator 𝒦_n: returns a fixed value, ⊥ (None), or raises."""

    value: Optional[Any] = 0.5
    raises: bool = False

    def __call__(self, parents: Mapping[str, Any], evidence: Evidence) -> Optional[Any]:
        if self.raises:
            raise RuntimeError("calibrator exception")
        return self.value


@dataclass(frozen=True)
class Resolution:
    accepted: bool
    config: Optional[Mapping[str, Any]]
    rejections: Tuple[str, ...]  # subset of ALL_REJECTIONS, or (no_decision,)
    used_fallback: Tuple[str, ...] = ()


def resolve(
    module: Module,
    suggestion: Mapping[str, Any],
    fixed: Mapping[str, Any],
    calibrators: Mapping[str, Calibrator],
    evidence: Mapping[str, Evidence],
    certificates: Mapping[str, Certificate],
    contexts: Mapping[str, FreshnessContext],
    *,
    eval_split: str = "eval",
    evidence_floor: int = 0,
) -> Resolution:
    """Transcription of RFC §3.4: Accept ⟺ ¬(R1∨...∨R8) ∧ ∀ calibrators ≠ ⊥.

    The implementation collects EVERY applicable rejection (no short-circuit)
    so the property checks can assert exact complementarity.
    """
    rejections: List[str] = []
    n_t, n_c = module.n_t, module.n_c

    # R2: depends_on must resolve to a declared TVAR (exact match, §3.7(4)).
    for cvar in module.cvars:
        for ref in cvar.depends_on:
            if ref not in n_t:
                rejections.append(R2_MISSING_REF)
    # gates[].threshold must resolve to a CVAR (kind-checked) — also R2.
    for policy in module.policies:
        for gate in policy.gates:
            if gate.threshold not in n_c:
                rejections.append(R2_MISSING_REF)

    # R1: cycles. v1 graphs are bipartite CVAR→TVAR; detect anyway (the
    # checker proves this unreachable for well-formed v1 modules).
    adjacency = {c.name: set(c.depends_on) & n_c for c in module.cvars}
    visited: Dict[str, int] = {}

    def _has_cycle(node: str) -> bool:
        state = visited.get(node, 0)
        if state == 1:
            return True
        if state == 2:
            return False
        visited[node] = 1
        for nxt in adjacency.get(node, ()):
            if _has_cycle(nxt):
                return True
        visited[node] = 2
        return False

    if any(_has_cycle(name) for name in adjacency):
        rejections.append(R1_CYCLE)

    # R3: duplicate providers — fixed assignment colliding with declarations,
    # or static partition collisions.
    if set(fixed) & (n_t | n_c):
        rejections.append(R3_DUPLICATE_PROVIDER)
    if n_t & n_c:
        rejections.append(R3_DUPLICATE_PROVIDER)

    # R4: phase mismatch — a CVAR consumed (as gate threshold) must be
    # resolvable, i.e. its calibrator/evidence present before use.
    consumed = {g.threshold for p in module.policies for g in p.gates}
    for name in consumed & n_c:
        if name not in calibrators or name not in evidence:
            rejections.append(R4_PHASE_MISMATCH)

    # R7: evidence leakage — calibration evidence drawn from the eval split.
    for cvar in module.cvars:
        ev = evidence.get(cvar.name)
        if ev is not None and ev.split == eval_split:
            rejections.append(R7_EVIDENCE_LEAKAGE)

    # R8: insufficient evidence.
    for cvar in module.cvars:
        ev = evidence.get(cvar.name)
        if ev is not None and len(ev.items) < evidence_floor:
            rejections.append(R8_INSUFFICIENT_EVIDENCE)

    # Run calibrators (only meaningful if structurally sane so far).
    values: Dict[str, Any] = {}
    bottom: List[str] = []
    for cvar in module.cvars:
        cal = calibrators.get(cvar.name)
        ev = evidence.get(cvar.name)
        if cal is None or ev is None:
            continue  # already covered by R4 when consumed
        try:
            out = cal(
                {p: suggestion.get(p) for p in cvar.depends_on},
                ev,
            )
        except Exception:
            # A raising calibrator yields no value: at the RESOLVER layer this
            # is ⊥ (no_decision). "Gate exception" is a distinct verdict at
            # the PROMOTION layer (RFC §3.6), modeled in promotion_outcome.
            out = None
        if out is None:
            bottom.append(cvar.name)
            continue
        values[cvar.name] = out
        # R5: validity domain.
        if cvar.validity_domain is not None:
            lo, hi = cvar.validity_domain
            if not (lo <= out <= hi):
                rejections.append(R5_INFEASIBLE_VALUE)
        # R6: certificate required and must be valid for (cvar, value, ctx).
        if cvar.require_calibration:
            cert = certificates.get(cvar.name)
            ctx = contexts.get(cvar.name)
            if (
                cert is None
                or ctx is None
                or not cert.valid_for(cvar.name, cvar.cvar_type, out, ctx)
            ):
                rejections.append(R6_STALE_CERTIFICATE)

    # R5 for fixed values: model fixed-domain as "value must not be the
    # sentinel INVALID".
    for name, value in fixed.items():
        if value == "INVALID":
            rejections.append(R5_INFEASIBLE_VALUE)

    unique_rejections = tuple(dict.fromkeys(rejections))
    if unique_rejections:
        return Resolution(False, None, unique_rejections)
    if bottom:
        return Resolution(False, None, (NO_DECISION_VERDICT,))

    config = dict(suggestion)
    config.update(fixed)
    config.update(values)
    return Resolution(True, config, ())


# ---------------------------------------------------------------------------
# Strict promotion — RFC §3.6.
# ---------------------------------------------------------------------------

PROMOTE = "promote"
REJECT = "reject"
NO_CERTIFIED_SELECTION = "no_certified_selection"

P7_VERDICTS = (
    "insufficient_evidence",
    "gate_exception",
    "stale_certificate",
    "calibrator_bottom",
    "gate_no_decision",
)


def strict(module: Module, consumed_cvars: Sequence[CVar]) -> bool:
    """RFC §3.6 strict(M, c)."""
    return (
        module.require_calibration_enabled
        or module.has_chance_constraints
        or any(c.require_calibration for c in consumed_cvars)
    )


def promotion_outcome(
    module: Module,
    consumed_cvars: Sequence[CVar],
    verdict: Optional[str],
    candidate_beats_incumbent: bool,
) -> str:
    """Finite promotion machine: the fail-closed law (P7).

    verdict ∈ P7_VERDICTS means an evidence failure occurred; None means
    clean evidence. Non-strict modules with clean evidence promote on
    dominance; the model intentionally allows the LEGACY behavior (simple
    best wins) only outside strict mode, mirroring the SDK repair scope.
    """
    if strict(module, consumed_cvars):
        if verdict is not None:
            return NO_CERTIFIED_SELECTION
        return PROMOTE if candidate_beats_incumbent else REJECT
    # non-strict: legacy semantics, unchanged by the RFC
    return PROMOTE if candidate_beats_incumbent else REJECT


# ---------------------------------------------------------------------------
# Cascade execution — RFC §3.8.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VoteStats:
    margin: float
    tie: bool = False


def cascade_select(
    stages: Sequence[str],
    thetas: Sequence[float],
    votes: Sequence[VoteStats],
) -> int:
    """Return the 0-based index of the stage whose output is returned.

    Transcribes  j = min{ i : i = m ∨ g_i(vote_i) = stop }  with the v1 gate
    escalate ⟺ margin < θ_i.  len(thetas) == len(stages) - 1 is the arity
    invariant; votes are the per-stage vote statistics (votes[i] consumed by
    gate i, the gate AFTER stage i+1's would-be source — only the first m-1
    stages vote in this model).
    """
    m = len(stages)
    if m < 1:
        raise ValueError("cascade requires |stages| >= 1")
    if len(thetas) != m - 1:
        raise ValueError("|gates| must equal |stages| - 1")
    for i in range(m - 1):
        escalate = votes[i].margin < thetas[i]
        if not escalate:
            return i
    return m - 1
