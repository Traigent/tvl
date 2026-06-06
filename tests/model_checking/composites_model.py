"""Finite abstraction of RFC 0002 §3 — the sealed composite-knob algebra.

This is a MODEL, not the implementation: the value spaces are tiny and the
derived functions transcribe the RFC clauses one-to-one so the property checks
in ``test_composites_c1_c6.py`` read like the spec. It follows the RFC 0001
house convention (``model.py``): small dataclasses + plain functions, no new
dependencies, exhaustive enumeration in the tests.

PINNED RFC REVISION: DRAFT v7 — formalization/rfc-0002-composite-knobs.md.
Where the /tmp/p3-alloy-final.md skeleton (a conceptual map) conflicts with
v7's final text, THE RFC WINS. In particular this model follows the v6/v7
semantics the captain note flagged: closed ``ArmResult`` (§3.2.1),
``gate_arm_incompatible`` / ``gate_kind_placement_mismatch`` /
``missing_gate_signal`` gate typing (§3.2 item 5), ``signal_inputs`` freshness
(§3.2 item 11), and the K-chain semantic compilation (§3.8).

Section references are to that revision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

# ---------------------------------------------------------------------------
# Sealed registries — §3.2. Each is a CLOSED enum: a fourth member is a new
# RFC, not a registry entry (the sealing that buys the C1/C2 theorems).
# ---------------------------------------------------------------------------


class CompositeKind(Enum):
    """SEALED constructor registry — §3.2. Exactly three kinds."""

    CASCADE = "cascade"
    ENSEMBLE = "ensemble"
    LOOP = "loop"


class Placement(Enum):
    PRE = "pre"
    POST = "post"


class GateKind(Enum):
    MARGIN_BELOW = "margin_below"  # POST-only, margin-bearing gated arm
    SIGNAL_BELOW = "signal_below"  # PRE-only, requires a signal


class AggregateKind(Enum):
    MAJORITY_VOTE = "majority_vote"
    JUDGE_MAX = "judge_max"


class AcceptKind(Enum):
    STAT_AT_LEAST = "stat_at_least"  # acceptance direction ≥ (distinct from < )


class AcceptStat(Enum):
    VOTE_MARGIN = "vote_margin"
    VOTE_AGREEMENT = "vote_agreement"


class StopKind(Enum):
    SIGNAL_ACCEPT = "signal_accept"  # the only unroll-eligible kind (§3.8)
    EXTERNAL_ACCEPT = "external_accept"
    EXHAUSTED = "exhausted"


# Canonical vote-statistic ids that live in the SAME registry namespace as
# named signals (§3.2 item 11): sig(margin_below) = "vote_margin".
CANONICAL_VOTE_MARGIN = "vote_margin"


# ---------------------------------------------------------------------------
# Sub-declarations — §3.2.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignalUse:
    """A named signal reference + its declared input keys (§3.2 / §3.9)."""

    signal: str
    inputs: Tuple[str, ...] = ()  # default [] ; for stops MUST ⊆ state_keys


@dataclass(frozen=True)
class GateDecl:
    kind: GateKind
    threshold: str  # MUST resolve to an int/float CVAR
    signal: Optional[SignalUse] = None  # REQUIRED iff kind=signal_below


@dataclass(frozen=True)
class AcceptDecl:
    stat: AcceptStat
    threshold: str  # MUST resolve to a CVAR
    kind: AcceptKind = AcceptKind.STAT_AT_LEAST


@dataclass(frozen=True)
class StopDecl:
    kind: StopKind
    threshold: Optional[str] = None  # REQUIRED iff signal_accept
    signal: Optional[SignalUse] = None  # REQUIRED iff signal_accept
    predicate: Optional[str] = None  # REQUIRED iff external_accept (opaque)


# ---------------------------------------------------------------------------
# Tagged Arm — §3.2. stage(name, tuned_params) | composite(name).
# (The model uses two explicit tags; the surface "bare = stage" sugar of §3.9
# is a parsing concern, not an algebra distinction — a bare arm is a
# ``stage_arm`` with empty tuned_params here.)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Arm:
    """A TAGGED arm. Exactly one of (stage, composite_ref) is populated."""

    stage: Optional[str] = None
    tuned_params: Tuple[str, ...] = ()  # TVAR refs parameterizing the stage
    composite_ref: Optional[str] = None  # exact-match into N_X

    @property
    def is_stage(self) -> bool:
        return self.stage is not None and self.composite_ref is None

    @property
    def is_composite(self) -> bool:
        return self.composite_ref is not None and self.stage is None


def stage_arm(name: str, tuned_params: Sequence[str] = ()) -> Arm:
    return Arm(stage=name, tuned_params=tuple(tuned_params))


def composite_arm(name: str) -> Arm:
    return Arm(composite_ref=name)


# ---------------------------------------------------------------------------
# Constructor bodies — §3.2 (discriminated by kind).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregateDecl:
    kind: AggregateKind
    judge: Optional[Arm] = None  # REQUIRED iff kind=judge_max
    accept: Optional[AcceptDecl] = None


@dataclass(frozen=True)
class Cascade:
    arms: Tuple[Arm, ...]  # |arms| = m ≥ 1
    gates: Tuple[GateDecl, ...] = ()  # |gates| = m − 1
    placement: Placement = Placement.POST


@dataclass(frozen=True)
class Ensemble:
    arms: Tuple[Arm, ...]  # |arms| ≥ 1
    aggregate: AggregateDecl = field(
        default_factory=lambda: AggregateDecl(AggregateKind.MAJORITY_VOTE)
    )
    cardinality: Optional[str] = None  # REQUIRED iff |arms|==1, FORBIDDEN if >1


@dataclass(frozen=True)
class Loop:
    body: Arm
    stop: StopDecl
    max_iters: int  # REQUIRED bound ≥ 1
    state_keys: Tuple[str, ...] = ()  # [] ⟺ body treated pure


@dataclass(frozen=True)
class Composite:
    """A CompositeKnob — §3.2. ``binds_value`` models the §3.1 rejection.

    Exactly one body field matches ``kind`` for a well-formed node (C1).
    """

    name: str
    kind: CompositeKind
    cascade: Optional[Cascade] = None
    ensemble: Optional[Ensemble] = None
    loop: Optional[Loop] = None
    binds_value: bool = False  # §3.1: a value bound on a composite -> reject


# A module-level environment for resolving names (TVARs / CVARs / N_X).
@dataclass(frozen=True)
class Env:
    n_t: FrozenSet[str] = frozenset()  # declared TVAR names
    n_c: FrozenSet[str] = frozenset()  # declared CVAR names
    composites: Tuple[Composite, ...] = ()

    @property
    def n_x(self) -> Dict[str, Composite]:
        return {c.name: c for c in self.composites}


# ===========================================================================
# C1 — Kind partition. Exactly one body matches the kind, no value bound.
# ===========================================================================


def body_fields(c: Composite) -> List[str]:
    """Names of the populated body fields (for partition checking)."""
    present = []
    if c.cascade is not None:
        present.append("cascade")
    if c.ensemble is not None:
        present.append("ensemble")
    if c.loop is not None:
        present.append("loop")
    return present


_KIND_TO_FIELD = {
    CompositeKind.CASCADE: "cascade",
    CompositeKind.ENSEMBLE: "ensemble",
    CompositeKind.LOOP: "loop",
}


def well_formed_kind(c: Composite) -> bool:
    """C1 / §3.2 item 1: exactly the one body field of the declared kind is
    present, and no value is bound (§3.1)."""
    if c.binds_value:
        return False
    present = body_fields(c)
    return present == [_KIND_TO_FIELD[c.kind]]


# --- The closed, total, deterministic result algebra — §3.2.1. -------------


class ArmResultKind(Enum):
    OUTPUT = "output"
    NO_ACCEPT = "no_accept"
    ERROR = "error"


@dataclass(frozen=True)
class ArmResult:
    """``output(o, vote_stats?) | no_accept | error`` — §3.2.1.

    ``out`` present iff OUTPUT; ``vote_stats`` (a margin) present iff the
    producer is margin-bearing (stage or majority_vote ensemble).
    """

    kind: ArmResultKind
    out: Optional[str] = None
    vote_stats: Optional[float] = None  # margin, iff margin-bearing


def result_well_formed(r: ArmResult) -> bool:
    """§3.2.1: the three kinds are disjoint & exhaustive; ``out`` present iff
    OUTPUT. (vote_stats is an optional annotation on OUTPUT only.)"""
    if r.kind == ArmResultKind.OUTPUT:
        return r.out is not None
    # non-output carries neither an output nor vote stats
    return r.out is None and r.vote_stats is None


def output(o: str, vote_stats: Optional[float] = None) -> ArmResult:
    return ArmResult(ArmResultKind.OUTPUT, out=o, vote_stats=vote_stats)


NO_ACCEPT = ArmResult(ArmResultKind.NO_ACCEPT)
ERROR = ArmResult(ArmResultKind.ERROR)


# ===========================================================================
# C2 — Nesting acyclicity & finite expansion. §3.2 item 4.
# ===========================================================================


def child_refs(c: Composite) -> List[str]:
    """The composite names ``c`` references as nested arms (§3.2 item 4).

    Covers cascade arms, ensemble arms + judge, and loop body — every Arm
    position. ``stage(·)`` is opaque and never consults the namespace.
    """
    refs: List[str] = []
    arms: List[Arm] = []
    if c.cascade is not None:
        arms.extend(c.cascade.arms)
    if c.ensemble is not None:
        arms.extend(c.ensemble.arms)
        if c.ensemble.aggregate.judge is not None:
            arms.append(c.ensemble.aggregate.judge)
    if c.loop is not None:
        arms.append(c.loop.body)
    for a in arms:
        if a.is_composite:
            refs.append(a.composite_ref)  # type: ignore[arg-type]
    return refs


def reachable(env: Env, start: str) -> Set[str]:
    """Transitive closure of ``child_refs`` from ``start`` (may be missing)."""
    seen: Set[str] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        comp = env.n_x.get(cur)
        if comp is None:
            continue
        for ref in child_refs(comp):
            if ref not in seen:
                seen.add(ref)
                stack.append(ref)
    return seen


def has_cycle(env: Env) -> bool:
    """C2 / §3.2 item 4: is the ``composite(·)`` reference graph over N_X
    cyclic? DFS with a recursion stack (catches self-loops and k-cycles)."""
    WHITE, GREY, BLACK = 0, 1, 2
    color: Dict[str, int] = {c.name: WHITE for c in env.composites}

    def visit(name: str) -> bool:
        color[name] = GREY
        for ref in child_refs(env.n_x[name]):
            if ref not in color:
                continue  # dangling ref — a different lint (missing_composite_ref)
            if color[ref] == GREY:
                return True
            if color[ref] == WHITE and visit(ref):
                return True
        color[name] = BLACK
        return False

    return any(color[c.name] == WHITE and visit(c.name) for c in env.composites)


def missing_composite_refs(env: Env) -> List[Tuple[str, str]]:
    """§3.2 item 3: ``composite(x)`` that resolves to no N_X member."""
    gaps: List[Tuple[str, str]] = []
    for c in env.composites:
        for ref in child_refs(c):
            if ref not in env.n_x:
                gaps.append((c.name, ref))
    return gaps


def roots(env: Env) -> List[Composite]:
    """§3.6 root consumption: every declared composite NOT referenced as a
    nested arm of another. (Computed over the whole N_X graph.)"""
    referenced: Set[str] = set()
    for c in env.composites:
        referenced.update(child_refs(c))
    return [c for c in env.composites if c.name not in referenced]


# ===========================================================================
# C6 — leafT (§3.5) and required_parents (§3.5). TVAR-only codomain.
# ===========================================================================


def _arms_body_judge(c: Composite) -> List[Arm]:
    """The arms/body/judge over which leafT(composite(x)) recurses (§3.5)."""
    arms: List[Arm] = []
    if c.cascade is not None:
        arms.extend(c.cascade.arms)
    if c.ensemble is not None:
        arms.extend(c.ensemble.arms)
        if c.ensemble.aggregate.judge is not None:
            arms.append(c.ensemble.aggregate.judge)
    if c.loop is not None:
        arms.append(c.loop.body)
    return arms


def leaf_t_arm(env: Env, a: Arm) -> FrozenSet[str]:
    """leafT over an Arm — §3.5.

    leafT(stage(s, ps)) = ps  (intersected with N_T — declared TVARs only)
    leafT(composite(x)) = ⋃ leafT(arms/body/judge) ∪ ({cardinality} ∩ N_T)
    """
    if a.is_stage:
        # tuned_params resolve to TVARs only (§3.2 item 9); the intersection
        # keeps the codomain TVAR-only even if an entry is malformed.
        return frozenset(p for p in a.tuned_params if p in env.n_t)
    if a.is_composite:
        comp = env.n_x.get(a.composite_ref)  # type: ignore[arg-type]
        if comp is None:
            return frozenset()
        return leaf_t_composite(env, comp)
    return frozenset()


def leaf_t_composite(env: Env, c: Composite) -> FrozenSet[str]:
    """leafT(composite(x)) — §3.5, folding in the tuned ensemble cardinality."""
    acc: Set[str] = set()
    for a in _arms_body_judge(c):
        acc |= leaf_t_arm(env, a)
    # ({cardinality} ∩ N_T): a sampling-form ensemble whose k is a TVAR.
    if c.ensemble is not None and c.ensemble.cardinality is not None:
        if c.ensemble.cardinality in env.n_t:
            acc.add(c.ensemble.cardinality)
    return frozenset(acc)


def required_parents(env: Env, c: Composite) -> Dict[str, FrozenSet[str]]:
    """required_parents(θ) per §3.5, keyed by threshold CVAR name.

    Post-cascade θ_i : leafT(a₁) ∪ … ∪ leafT(a_i)
    Pre-cascade  θ_i : leafT(a_i)            (the arm the gate admits)
    Ensemble.accept θ: ⋃_j leafT(a_j) ∪ leafT(judge?) ∪ ({cardinality} ∩ N_T)
    Loop.stop θ      : leafT(body)
    """
    out: Dict[str, FrozenSet[str]] = {}
    if c.cascade is not None:
        casc = c.cascade
        if casc.placement == Placement.POST:
            # gate g_i (0-based i) reads arms a_1..a_{i+1}; in the post form
            # the gated arm i (1-based) is arms[i], so the obligation accrues
            # leafT(a_1)..leafT(a_i). Gate j (0-based) gates arm index j+1.
            prefix: Set[str] = set()
            for j, gate in enumerate(casc.gates):
                # accumulate through the arm the gate guards (arms[0..j+1])
                for k in range(j + 2):
                    if k < len(casc.arms):
                        prefix |= leaf_t_arm(env, casc.arms[k])
                out[gate.threshold] = frozenset(prefix)
        else:  # PRE: each routing gate i admits arm a_i (the arm the gate guards)
            for j, gate in enumerate(casc.gates):
                arm = casc.arms[j] if j < len(casc.arms) else None
                out[gate.threshold] = (
                    leaf_t_arm(env, arm) if arm is not None else frozenset()
                )
    if c.ensemble is not None:
        ens = c.ensemble
        if ens.aggregate.accept is not None:
            acc: Set[str] = set()
            for a in ens.arms:
                acc |= leaf_t_arm(env, a)
            if ens.aggregate.judge is not None:
                acc |= leaf_t_arm(env, ens.aggregate.judge)
            if ens.cardinality is not None and ens.cardinality in env.n_t:
                acc.add(ens.cardinality)
            out[ens.aggregate.accept.threshold] = frozenset(acc)
    if c.loop is not None:
        loop = c.loop
        if loop.stop.kind == StopKind.SIGNAL_ACCEPT and loop.stop.threshold:
            out[loop.stop.threshold] = leaf_t_arm(env, loop.body)
    return out


def missing_composite_parent(
    env: Env, depends_on: Dict[str, FrozenSet[str]]
) -> List[Tuple[str, FrozenSet[str]]]:
    """§3.5 lint: required_parents(θ) ⊆ depends_on(θ) for every threshold CVAR
    over all roots. Returns the (θ, missing-set) gaps."""
    gaps: List[Tuple[str, FrozenSet[str]]] = []
    for r in roots(env):
        for theta, req in required_parents(env, r).items():
            have = depends_on.get(theta, frozenset())
            missing = req - have
            if missing:
                gaps.append((theta, missing))
    return gaps


# ===========================================================================
# C3 — Certificate coverage fold Cal (§3.6) + a ground-truth member walk.
# ===========================================================================


def cal_aggregate(env: Env, agg: AggregateDecl) -> FrozenSet[str]:
    acc: Set[str] = set()
    if agg.judge is not None:
        # Cal(agg.judge if present): a stage judge contributes ∅; a composite
        # judge contributes Cal(body(judge)).
        acc |= cal_arm(env, agg.judge)
    if agg.accept is not None:
        acc.add(agg.accept.threshold)
    return frozenset(acc)


def cal_arm(env: Env, a: Arm) -> FrozenSet[str]:
    """Cal(stage) = ∅ ; Cal(composite(x)) = Cal(body(x)) — §3.6."""
    if a.is_composite:
        comp = env.n_x.get(a.composite_ref)  # type: ignore[arg-type]
        if comp is None:
            return frozenset()
        return cal_composite(env, comp)
    return frozenset()


def cal_composite(env: Env, c: Composite) -> FrozenSet[str]:
    """Cal : Composite → ℘(N_C) — §3.6 (the fold under test)."""
    acc: Set[str] = set()
    if c.cascade is not None:
        for a in c.cascade.arms:
            acc |= cal_arm(env, a)
        for g in c.cascade.gates:
            acc.add(g.threshold)
    if c.ensemble is not None:
        for a in c.ensemble.arms:
            acc |= cal_arm(env, a)
        acc |= cal_aggregate(env, c.ensemble.aggregate)
        # ({k} ∩ N_C): a calibrated cardinality is a member of Cal.
        if c.ensemble.cardinality is not None and c.ensemble.cardinality in env.n_c:
            acc.add(c.ensemble.cardinality)
    if c.loop is not None:
        acc |= cal_arm(env, c.loop.body)
        if c.loop.stop.kind == StopKind.SIGNAL_ACCEPT and c.loop.stop.threshold:
            acc.add(c.loop.stop.threshold)
    return frozenset(acc)


def cal_roots(env: Env) -> FrozenSet[str]:
    """⋃_{r ∈ roots(M)} Cal(r) — the strict-selection coverage set (§3.6)."""
    acc: Set[str] = set()
    for r in roots(env):
        acc |= cal_composite(env, r)
    return frozenset(acc)


def member_walk_cal(env: Env, c: Composite, _seen: Optional[Set[str]] = None) -> FrozenSet[str]:
    """INDEPENDENT ground-truth: walk every member of the whole expansion and
    collect every gate/accept/stop threshold + calibrated cardinality, through
    nesting incl. judge arms. Implemented differently from ``cal_composite``
    (explicit recursive descent over expanded members) so the C3 equality is a
    real cross-check, not a tautology."""
    seen = set() if _seen is None else _seen
    found: Set[str] = set()

    def descend_arm(a: Arm) -> None:
        if a.is_composite:
            ref = a.composite_ref
            if ref is None or ref in seen:
                return
            comp = env.n_x.get(ref)
            if comp is None:
                return
            seen.add(ref)
            found.update(member_walk_cal(env, comp, seen))

    if c.cascade is not None:
        for g in c.cascade.gates:
            found.add(g.threshold)
        for a in c.cascade.arms:
            descend_arm(a)
    if c.ensemble is not None:
        for a in c.ensemble.arms:
            descend_arm(a)
        agg = c.ensemble.aggregate
        if agg.accept is not None:
            found.add(agg.accept.threshold)
        if agg.judge is not None:
            descend_arm(agg.judge)
        if c.ensemble.cardinality is not None and c.ensemble.cardinality in env.n_c:
            found.add(c.ensemble.cardinality)
    if c.loop is not None:
        descend_arm(c.loop.body)
        if c.loop.stop.kind == StopKind.SIGNAL_ACCEPT and c.loop.stop.threshold:
            found.add(c.loop.stop.threshold)
    return frozenset(found)


def calibration_pass(certified_fresh: FrozenSet[str], coverage: FrozenSet[str]) -> bool:
    """Strict selection — §3.6: every CVAR in ``coverage`` must carry a valid,
    fresh certificate. Fail-closed: any gap ⇒ no certified selection."""
    return coverage <= certified_fresh


# A deliberately-broken fold variant (C3 teeth): drops judge arms. The
# ground-truth walk must CATCH the difference.
def cal_composite_drop_judge(env: Env, c: Composite) -> FrozenSet[str]:
    acc: Set[str] = set()
    if c.cascade is not None:
        for a in c.cascade.arms:
            acc |= cal_arm_drop_judge(env, a)
        for g in c.cascade.gates:
            acc.add(g.threshold)
    if c.ensemble is not None:
        for a in c.ensemble.arms:
            acc |= cal_arm_drop_judge(env, a)
        if c.ensemble.aggregate.accept is not None:
            acc.add(c.ensemble.aggregate.accept.threshold)
        # BUG: judge arm's Cal is dropped entirely.
        if c.ensemble.cardinality is not None and c.ensemble.cardinality in env.n_c:
            acc.add(c.ensemble.cardinality)
    if c.loop is not None:
        acc |= cal_arm_drop_judge(env, c.loop.body)
        if c.loop.stop.kind == StopKind.SIGNAL_ACCEPT and c.loop.stop.threshold:
            acc.add(c.loop.stop.threshold)
    return frozenset(acc)


def cal_arm_drop_judge(env: Env, a: Arm) -> FrozenSet[str]:
    if a.is_composite:
        comp = env.n_x.get(a.composite_ref)  # type: ignore[arg-type]
        if comp is None:
            return frozenset()
        return cal_composite_drop_judge(env, comp)
    return frozenset()


# ===========================================================================
# C4 — Cost forms (§3.4). Structural FORM closure only — symbolic terms.
# ===========================================================================


class CostForm(Enum):
    """The five §3.4 cost forms (symbolic — no arithmetic)."""

    STAGE = "stage"  # cost(stage s) = c(s)
    CASCADE_POST = "cascade_post"  # cost(a1) + Σ P·cost(a_{i+1})
    CASCADE_PRE = "cascade_pre"  # Σ P·c(σ) + Σ P·cost(a_i)
    ENSEMBLE_SAMPLING = "ensemble_sampling"  # k·cost(a) + c(agg)
    ENSEMBLE_COMMITTEE = "ensemble_committee"  # Σ cost(a_j) + c(agg)
    LOOP = "loop"  # E[iters]·(cost(b)+c(stop))


@dataclass(frozen=True)
class CostTerm:
    """A symbolic cost term. ``kids`` are the sub-terms (arms' own forms).

    A well-formed (closed) cost term has NO unexpanded composite reference in
    its subtree — the §3.4 equations close over the algebra (C4)."""

    form: CostForm
    kids: Tuple["CostTerm", ...] = ()
    composite_ref: Optional[str] = None  # set only on an UNEXPANDED ref (teeth)


def cost_of_arm(env: Env, a: Arm, _seen: Optional[Set[str]] = None) -> CostTerm:
    """Substituting an arm's cost form: a stage arm is a STAGE term; a
    composite arm IS the referenced composite's cost form (§3.4)."""
    seen = set() if _seen is None else _seen
    if a.is_stage:
        return CostTerm(CostForm.STAGE)
    if a.is_composite:
        ref = a.composite_ref
        comp = env.n_x.get(ref) if ref is not None else None
        if comp is None or (ref is not None and ref in seen):
            # dangling/cyclic — represent as an unexpanded reference (not used
            # in WF instances; cycles are rejected by C2).
            return CostTerm(CostForm.STAGE, composite_ref=ref)
        return cost_of_composite(env, comp, seen | ({ref} if ref else set()))
    return CostTerm(CostForm.STAGE)


def cost_of_composite(env: Env, c: Composite, _seen: Optional[Set[str]] = None) -> CostTerm:
    """The composite's cost term, recursing into arm cost forms (§3.4)."""
    seen = set() if _seen is None else _seen
    if c.cascade is not None:
        kids = tuple(cost_of_arm(env, a, seen) for a in c.cascade.arms)
        form = (
            CostForm.CASCADE_POST
            if c.cascade.placement == Placement.POST
            else CostForm.CASCADE_PRE
        )
        return CostTerm(form, kids)
    if c.ensemble is not None:
        kids = tuple(cost_of_arm(env, a, seen) for a in c.ensemble.arms)
        if c.ensemble.aggregate.judge is not None:
            kids = kids + (cost_of_arm(env, c.ensemble.aggregate.judge, seen),)
        form = (
            CostForm.ENSEMBLE_SAMPLING
            if len(c.ensemble.arms) == 1
            else CostForm.ENSEMBLE_COMMITTEE
        )
        return CostTerm(form, kids)
    if c.loop is not None:
        return CostTerm(CostForm.LOOP, (cost_of_arm(env, c.loop.body, seen),))
    return CostTerm(CostForm.STAGE)


def cost_is_closed(t: CostTerm) -> bool:
    """C4: no unexpanded composite reference anywhere in the term tree —
    the cost forms close over the algebra."""
    if t.composite_ref is not None:
        return False
    return all(cost_is_closed(k) for k in t.kids)


# ===========================================================================
# C5 — Loop → K-chain semantic compilation (§3.8). signal_accept ONLY.
# ===========================================================================


def signal_accept_unrollable(loop: Loop) -> bool:
    """§3.8: the unroll offer exists ONLY for signal_accept loops; K ≤ 4 here
    (the model checking scope). external_accept / exhausted offer NO unroll."""
    return loop.stop.kind == StopKind.SIGNAL_ACCEPT and 1 <= loop.max_iters <= 4


@dataclass(frozen=True)
class IterStep:
    """One modeled iteration: the body's result this iteration and whether the
    signal_accept stop fired (σ(state) ≥ θ). ``ambient`` models a hidden state
    mutation that condition 1 of §3.8 forbids."""

    body_result: ArmResult  # output / no_accept / error
    stop_accepts: bool  # σ(state) ≥ θ — acceptance fired
    ambient: bool = False  # condition-1 violation if True


def loop_execute(loop: Loop, steps: Sequence[IterStep]) -> Tuple[ArmResult, Optional[int]]:
    """Reference Loop semantics — §3.2.1 / §3.2 loop sentence.

    Returns (final_result, selected_iteration_index | None).
    - error is absorbing (first error fails the loop);
    - signal_accept: an OUTPUT body whose stop fired is the accepted result;
    - no_accept body continues to next iteration;
    - reaching max_iters without acceptance yields no_accept.
    """
    n = min(loop.max_iters, len(steps))
    for i in range(n):
        st = steps[i]
        if st.body_result.kind == ArmResultKind.ERROR:
            return ERROR, None
        if (
            loop.stop.kind == StopKind.SIGNAL_ACCEPT
            and st.body_result.kind == ArmResultKind.OUTPUT
            and st.stop_accepts
        ):
            return st.body_result, i
        # no_accept (or output-without-acceptance): continue
    return NO_ACCEPT, None


def kchain_execute(loop: Loop, steps: Sequence[IterStep]) -> Tuple[ArmResult, Optional[int]]:
    """Internal K-chain semantics — §3.8.

    KChain stages b₍₁₎..b₍K₎; escalate after stage i ⟺ ¬stop₍ᵢ₎ (σ < θ). The
    chain's selected link is the first stage whose stop FIRED on an output.
    This is a SEPARATE implementation from ``loop_execute`` so the C5 trace
    comparison is a genuine cross-check.
    """
    K = loop.max_iters
    for i in range(min(K, len(steps))):
        st = steps[i]
        if st.body_result.kind == ArmResultKind.ERROR:
            return ERROR, None
        escalate = not st.stop_accepts
        if not escalate and st.body_result.kind == ArmResultKind.OUTPUT:
            return st.body_result, i  # stop fired -> selected link
        # escalate to next link
    return NO_ACCEPT, None


# ---------------------------------------------------------------------------
# Static well-formedness lints used by several claims (subset, §3.2 items).
# Returns a sorted list of (code, composite-name) — house diagnostic shape.
# ---------------------------------------------------------------------------


def gate_typing_diagnostics(env: Env, c: Composite) -> List[Tuple[str, str]]:
    """§3.2 item 5 gate typing for a cascade composite (the subset C-tests
    exercise): placement/kind symmetry, signal_below needs a signal, and
    margin_below gates a margin-bearing arm."""
    diags: List[Tuple[str, str]] = []
    if c.cascade is None:
        return diags
    casc = c.cascade
    for j, g in enumerate(casc.gates):
        # placement / kind symmetry (covers both directions)
        if g.kind == GateKind.MARGIN_BELOW and casc.placement == Placement.PRE:
            diags.append(("gate_kind_placement_mismatch", c.name))
        if g.kind == GateKind.SIGNAL_BELOW and casc.placement == Placement.POST:
            diags.append(("gate_kind_placement_mismatch", c.name))
        # signal_below requires a declared signal
        if g.kind == GateKind.SIGNAL_BELOW and g.signal is None:
            diags.append(("missing_gate_signal", c.name))
        # margin_below (post) gates the arm at index j+1 -> must be margin-bearing
        if g.kind == GateKind.MARGIN_BELOW and casc.placement == Placement.POST:
            gated_idx = j + 1
            if gated_idx < len(casc.arms):
                if not arm_is_margin_bearing(env, casc.arms[gated_idx]):
                    diags.append(("gate_arm_incompatible", c.name))
    return diags


def arm_is_margin_bearing(env: Env, a: Arm) -> bool:
    """§3.2 item 5: a stage arm, or an ensemble arm whose aggregate is
    majority_vote, is margin-bearing. judge_max / loop / pre-cascade / nested
    post-cascade are NOT."""
    if a.is_stage:
        return True
    if a.is_composite:
        comp = env.n_x.get(a.composite_ref)  # type: ignore[arg-type]
        if comp is None:
            return False
        if comp.ensemble is not None:
            return comp.ensemble.aggregate.kind == AggregateKind.MAJORITY_VOTE
        return False
    return False
