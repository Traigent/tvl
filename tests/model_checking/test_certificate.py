"""Small-scope checks of RFC §3.5 — certificate subject binding + freshness.

The two review-driven theorems:
  (finding 2) a certificate is valid only for ITS cvar and ITS value;
  (finding 3) ctx_core is immutable — no extension selection can disable
              parent-specificity — and EVERY core key flip is staleness-inducing.
"""

from __future__ import annotations

import dataclasses

import pytest

from .model import (
    CTX_EXT_KEYS,
    Certificate,
    FreshnessContext,
    h_c,
    issue_certificate,
)


def _ctx(**overrides) -> FreshnessContext:
    base = dict(
        cvar_name="theta",
        tuned_parent_values=(("model", "m1"),),
        calibration_source_id="src",
        signal_spec_hash=h_c("sig_v1"),
        calibrator_id="cal_v1",
        calibrator_version="1",
        calibrator_params_hash=h_c({"budgets": [0.1, 0.2]}),
        dataset_hash="pool_v1",
        evidence_n=20,
        calibration_split="cal",
        eval_split="eval",
        target="tgt",
        extensions=(),
    )
    base.update(overrides)
    return FreshnessContext(**base)


CORE_FLIPS = [
    ("cvar_name", "theta2"),
    ("tuned_parent_values", (("model", "m2"),)),
    ("calibration_source_id", "src2"),
    ("signal_spec_hash", h_c("sig_v2")),
    ("calibrator_id", "cal_v2"),
    ("calibrator_version", "2"),
    ("calibrator_params_hash", h_c({"budgets": [0.3]})),
    ("dataset_hash", "pool_v2"),
    ("evidence_n", 21),
    ("calibration_split", "cal2"),
    ("eval_split", "eval2"),
    ("target", "tgt2"),
]


def test_valid_for_same_context():
    ctx = _ctx()
    cert = issue_certificate("theta", 0.5, ctx)
    assert cert.valid_for("theta", "float", 0.5, ctx)


@pytest.mark.parametrize("field_name,new_value", CORE_FLIPS)
def test_every_core_key_flip_is_staleness_inducing(field_name, new_value):
    """Flip each ctx_core key individually → certificate stale (P-claim from
    the plan: 'certificates become stale when any freshness-key input changes')."""
    ctx = _ctx()
    cert = issue_certificate("theta", 0.5, ctx)
    flipped = dataclasses.replace(ctx, **{field_name: new_value})
    assert not cert.valid_for("theta", "float", 0.5, flipped), field_name


def test_extension_key_flip_is_staleness_inducing_when_selected():
    ctx = _ctx(extensions=(("model_versions", "mv1"),))
    cert = issue_certificate("theta", 0.5, ctx)
    flipped = _ctx(extensions=(("model_versions", "mv2"),))
    assert not cert.valid_for("theta", "float", 0.5, flipped)


def test_subject_binds_cvar_name():
    """Finding 2: a certificate for theta is NOT valid for theta2, even with
    an identical context shape."""
    ctx = _ctx()
    cert = issue_certificate("theta", 0.5, ctx)
    ctx2 = _ctx(cvar_name="theta2")
    assert not cert.valid_for("theta2", "float", 0.5, ctx2)


def test_subject_binds_value():
    """Finding 2: a certificate for value 0.5 is NOT valid for value 0.6."""
    ctx = _ctx()
    cert = issue_certificate("theta", 0.5, ctx)
    assert not cert.valid_for("theta", "float", 0.6, ctx)


def test_non_certified_decision_is_never_valid():
    ctx = _ctx()
    cert = issue_certificate("theta", 0.5, ctx)
    for decision in ("NO_DECISION", "BEST_EFFORT_UNCERTIFIED"):
        downgraded = dataclasses.replace(cert, decision=decision)
        assert not downgraded.valid_for("theta", "float", 0.5, ctx)


def test_parent_specificity_cannot_be_disabled_by_extension_choice():
    """Finding 3: parent values are CORE — no extension selection makes a
    parent-changed context hash-equal. Enumerate every extension subset."""
    import itertools

    for r in range(len(CTX_EXT_KEYS) + 1):
        for subset in itertools.combinations(sorted(CTX_EXT_KEYS), r):
            ext = tuple((k, "v") for k in subset)
            ctx_m1 = _ctx(extensions=ext)
            ctx_m2 = _ctx(tuned_parent_values=(("model", "m2"),), extensions=ext)
            assert ctx_m1.freshness_hash() != ctx_m2.freshness_hash(), subset


def test_invalid_extension_key_rejected():
    ctx = _ctx(extensions=(("not_a_real_key", "v"),))
    with pytest.raises(ValueError, match="invalid_calibration_context"):
        ctx.freshness_hash()


def test_canonicalization_rules():
    """§3.5 H_c restrictions: NFC strings, -0.0 fold, non-finite rejection."""
    assert h_c("café") == h_c("cafe\u0301")  # NFC: composed == decomposed
    assert h_c({"x": -0.0}) == h_c({"x": 0.0})
    with pytest.raises(ValueError):
        h_c(float("nan"))
    with pytest.raises(ValueError):
        h_c(float("inf"))
    # key order independence
    assert h_c({"a": 1, "b": 2}) == h_c({"b": 2, "a": 1})


def test_subject_type_checked():
    """v3 (review round 2, new finding 1): wrong declared type => invalid."""
    ctx = _ctx()
    cert = issue_certificate("theta", 0.5, ctx, cvar_type="float")
    assert not cert.valid_for("theta", "int", 0.5, ctx)


def test_audit_copies_must_agree_with_live_context():
    """v3: a certificate cannot DISPLAY one context while HASHING another —
    tampered audit fields (target/evidence) invalidate even with a correct
    issued_hash."""
    ctx = _ctx()
    cert = issue_certificate("theta", 0.5, ctx)
    for field_name, bad in [
        ("target", "tgt_forged"),
        ("evidence_n", 999),
        ("evidence_pool_hash", "pool_forged"),
    ]:
        tampered = dataclasses.replace(cert, **{field_name: bad})
        assert not tampered.valid_for("theta", "float", 0.5, ctx), field_name


def test_forged_subject_cross_context_rejected():
    """v4 (review round 3): a certificate issued against CVAR B's context with
    a FORGED subject naming A must not validate A — the live context presented
    for A must itself name A (valid's first conjunct)."""
    ctx_b = _ctx(cvar_name="theta_b")
    forged = dataclasses.replace(
        issue_certificate("theta_b", 0.5, ctx_b), subject_cvar="theta_a"
    )
    # query A with B's live context: first conjunct ctx.cvar_name == cvar fails
    assert not forged.valid_for("theta_a", "float", 0.5, ctx_b)
    # query A with A's own live context: issued_hash (covering cvar_name) fails
    ctx_a = _ctx(cvar_name="theta_a")
    assert not forged.valid_for("theta_a", "float", 0.5, ctx_a)
