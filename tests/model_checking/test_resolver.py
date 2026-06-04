"""Small-scope checks of RFC §3.4 — the Accept biconditional (P3 + P4).

The central theorem: Accept ⟺ ¬(R1∨...∨R8) ∧ all calibrators ≠ ⊥.
The model resolver collects every applicable rejection, so the check is an
exhaustive enumeration over a small instance space where each R_i is driven
reachable (or, for R1 in v1, proven unreachable).
"""

from __future__ import annotations

import itertools

import pytest

from .model import (
    ALL_REJECTIONS,
    Calibrator,
    CVar,
    Certificate,
    Evidence,
    FreshnessContext,
    Gate,
    Module,
    NO_DECISION_VERDICT,
    Policy,
    R1_CYCLE,
    R2_MISSING_REF,
    R3_DUPLICATE_PROVIDER,
    R4_PHASE_MISMATCH,
    R5_INFEASIBLE_VALUE,
    R6_STALE_CERTIFICATE,
    R7_EVIDENCE_LEAKAGE,
    R8_INSUFFICIENT_EVIDENCE,
    TVar,
    h_c,
    issue_certificate,
    resolve,
)


def _ctx(cvar: str, parents=(), n: int = 10) -> FreshnessContext:
    return FreshnessContext(
        cvar_name=cvar,
        tuned_parent_values=tuple(sorted(parents)),
        calibration_source_id="src",
        signal_spec_hash=h_c("sig_v1"),
        calibrator_id="cal_v1",
        calibrator_version="1",
        calibrator_params_hash=h_c({}),
        dataset_hash="pool_v1",
        evidence_n=n,
        calibration_split="cal",
        eval_split="eval",
        target="tgt",
    )


def _happy_inputs():
    """A fully-valid baseline instance: must Accept (P4 witness)."""
    module = Module(
        tvars=(TVar("model", ("m1", "m2")),),
        cvars=(CVar("theta", source="src", depends_on=("model",), require_calibration=True),),
        policies=(Policy("p", "cascade", ("s1", "s2"), (Gate("margin_below", "theta"),)),),
    )
    suggestion = {"model": "m1"}
    ctx = _ctx("theta", parents=(("model", "m1"),))
    cal = Calibrator(value=0.5)
    ev = Evidence(items=tuple(f"i{j}" for j in range(10)), split="cal")
    cert = issue_certificate("theta", 0.5, ctx)
    return module, suggestion, {}, {"theta": cal}, {"theta": ev}, {"theta": cert}, {"theta": ctx}


def test_p4_completeness_happy_path_accepts():
    module, sugg, fixed, cals, evs, certs, ctxs = _happy_inputs()
    res = resolve(module, sugg, fixed, cals, evs, certs, ctxs)
    assert res.accepted, res.rejections
    assert res.config == {"model": "m1", "theta": 0.5}


# --- Per-R_i reachability: mutate exactly one aspect of the happy instance ---


def _mutations():
    """(name, mutator) pairs — each drives exactly one rejection reachable."""

    def missing_ref(m, s, f, c, e, ce, cx):
        bad = Module(
            tvars=m.tvars,
            cvars=(CVar("theta", source="src", depends_on=("ghost",)),),
            policies=m.policies,
        )
        return bad, s, f, c, e, ce, cx, R2_MISSING_REF

    def gate_ref_missing(m, s, f, c, e, ce, cx):
        bad = Module(
            tvars=m.tvars,
            cvars=m.cvars,
            policies=(Policy("p", "cascade", ("s1", "s2"), (Gate("margin_below", "ghost"),)),),
        )
        return bad, s, f, c, e, ce, cx, R2_MISSING_REF

    def duplicate_provider_fixed(m, s, f, c, e, ce, cx):
        return m, s, {"model": "m2"}, c, e, ce, cx, R3_DUPLICATE_PROVIDER

    def duplicate_provider_partition(m, s, f, c, e, ce, cx):
        bad = Module(
            tvars=m.tvars,
            cvars=(CVar("model", source="src"),),  # collides with the tvar
            policies=(),
        )
        return bad, s, f, {"model": Calibrator(0.5)}, {"model": e["theta"]}, {}, {}, R3_DUPLICATE_PROVIDER

    def phase_mismatch(m, s, f, c, e, ce, cx):
        # gate consumes theta but no calibrator/evidence registered for it
        return m, s, f, {}, {}, ce, cx, R4_PHASE_MISMATCH

    def infeasible(m, s, f, c, e, ce, cx):
        bad = Module(
            tvars=m.tvars,
            cvars=(CVar("theta", source="src", validity_domain=(0.0, 0.4)),),
            policies=(),
        )
        return bad, s, f, c, e, {}, {}, R5_INFEASIBLE_VALUE  # 0.5 outside [0, 0.4]

    def stale_cert(m, s, f, c, e, ce, cx):
        stale_ctx = _ctx("theta", parents=(("model", "m2"),))  # parent changed
        return m, s, f, c, e, ce, {"theta": stale_ctx}, R6_STALE_CERTIFICATE

    def leakage(m, s, f, c, e, ce, cx):
        leaky = {"theta": Evidence(items=("i0",) * 10, split="eval")}
        return m, s, f, c, leaky, ce, cx, R7_EVIDENCE_LEAKAGE

    def insufficient(m, s, f, c, e, ce, cx):
        tiny = {"theta": Evidence(items=("i0",), split="cal")}
        return m, s, f, c, tiny, ce, cx, R8_INSUFFICIENT_EVIDENCE

    return [
        ("R2_depends_on", missing_ref),
        ("R2_gate_threshold", gate_ref_missing),
        ("R3_fixed", duplicate_provider_fixed),
        ("R3_partition", duplicate_provider_partition),
        ("R4", phase_mismatch),
        ("R5", infeasible),
        ("R6", stale_cert),
        ("R7", leakage),
        ("R8", insufficient),
    ]


@pytest.mark.parametrize("name,mutator", _mutations())
def test_p3_each_rejection_reachable_and_blocks(name, mutator):
    base = _happy_inputs()
    module, sugg, fixed, cals, evs, certs, ctxs, expected = mutator(*base)
    kwargs = {"evidence_floor": 2} if name == "R8" else {}
    res = resolve(module, sugg, fixed, cals, evs, certs, ctxs, **kwargs)
    assert not res.accepted
    assert expected in res.rejections, (name, res.rejections)


def test_r1_unreachable_in_v1_by_construction():
    """RFC §3.3: v1 graphs are bipartite CVAR→TVAR — exhaustively verify that
    no v1-well-formed module (depends_on ⊆ N_T) can produce R1."""
    tvar_names = ("t1", "t2")
    cvar_names = ("c1", "c2")
    found_cycle = False
    for deps1 in itertools.chain.from_iterable(
        itertools.combinations(tvar_names, k) for k in range(3)
    ):
        for deps2 in itertools.chain.from_iterable(
            itertools.combinations(tvar_names, k) for k in range(3)
        ):
            module = Module(
                tvars=tuple(TVar(n, (0,)) for n in tvar_names),
                cvars=(
                    CVar("c1", source="s", depends_on=deps1),
                    CVar("c2", source="s", depends_on=deps2),
                ),
            )
            cals = {n: Calibrator(0.5) for n in cvar_names}
            evs = {n: Evidence(("i0", "i1"), "cal") for n in cvar_names}
            res = resolve(module, {"t1": 0, "t2": 0}, {}, cals, evs, {}, {})
            if R1_CYCLE in res.rejections:
                found_cycle = True
    assert not found_cycle  # unreachability proof at this scope


def test_r1_reachable_only_with_deferred_cvar_to_cvar_edges():
    """Forward-compat guard: the R1 machinery itself works (counterexample for
    the DEFERRED extension, proving the rejection is not dead code)."""
    module = Module(
        cvars=(
            CVar("c1", source="s", depends_on=("c2",)),
            CVar("c2", source="s", depends_on=("c1",)),
        ),
    )
    cals = {n: Calibrator(0.5) for n in ("c1", "c2")}
    evs = {n: Evidence(("i0", "i1"), "cal") for n in ("c1", "c2")}
    res = resolve(module, {}, {}, cals, evs, {}, {})
    # v1 also flags R2 (refs must be TVARs) — both fire; R1 must be among them.
    assert R1_CYCLE in res.rejections and R2_MISSING_REF in res.rejections


def test_calibrator_bottom_is_no_decision_not_a_rejection():
    """§3.4: ⊥ with no rejection condition ⇒ no_decision verdict."""
    module, sugg, fixed, cals, evs, certs, ctxs = _happy_inputs()
    module = Module(tvars=module.tvars, cvars=(CVar("theta", source="src"),))
    res = resolve(module, sugg, fixed, {"theta": Calibrator(value=None)}, evs, {}, {})
    assert not res.accepted
    assert res.rejections == (NO_DECISION_VERDICT,)


def test_biconditional_exhaustive_small_scope():
    """The P3/P4 biconditional over a product space of toggles: acceptance
    holds EXACTLY when no rejection condition is induced and the calibrator
    returns a value."""
    toggles = list(itertools.product([False, True], repeat=4))
    # (bad_ref, fixed_collision, leaky_evidence, calibrator_bottom)
    for bad_ref, fixed_collision, leaky, bottom in toggles:
        module = Module(
            tvars=(TVar("model", ("m1",)),),
            cvars=(
                CVar(
                    "theta",
                    source="src",
                    depends_on=("ghost",) if bad_ref else ("model",),
                ),
            ),
        )
        fixed = {"model": "m1"} if fixed_collision else {}
        ev = Evidence(("i0", "i1"), "eval" if leaky else "cal")
        cal = Calibrator(value=None if bottom else 0.5)
        res = resolve(module, {"model": "m1"}, fixed, {"theta": cal}, {"theta": ev}, {}, {})
        should_accept = not (bad_ref or fixed_collision or leaky or bottom)
        assert res.accepted == should_accept, (bad_ref, fixed_collision, leaky, bottom, res)
        if not should_accept and not (bad_ref or fixed_collision or leaky):
            assert res.rejections == (NO_DECISION_VERDICT,)
