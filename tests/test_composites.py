"""TVL 1.2 (RFC 0002) validators — the composite-knob algebra.

Two layers, mirroring the RFC 0001 (phase-6) conformance suite:

1. Fixture conformance: every module in spec/examples/validation-phase7-composites
   produces EXACTLY its README-promised diagnostic through the real schema +
   lint pipeline. These fixtures are the executable acceptance bar for the
   validators packet (one happy + one rejecting fixture per §3.11 code, plus the
   degenerate-acceptance and §4 subsumption fixtures from RFC §9 criterion 3).
2. Targeted lint/schema checks for P1 conservative extension, the two intended
   composite-only ratchets (§4), and the composite-use-site-only signal binding.
"""

from __future__ import annotations

import json
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parents[1]
PKG_ROOT = BASE / "python"
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

import pytest  # noqa: E402
import yaml  # noqa: E402

from tvl.constraints import compile_constraints  # noqa: E402
from tvl.lints import lint_module  # noqa: E402
from tvl.schema import validator  # noqa: E402

FIXTURES = BASE / "spec" / "examples" / "validation-phase7-composites"
EXAMPLES = BASE / "spec" / "examples"


def _load(name: str) -> dict:
    return yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))


def _schema_errors(doc: dict) -> list:
    return list(validator().iter_errors(doc))


def _codes(doc: dict, severity: str | None = None) -> set:
    return {
        i["code"]
        for i in lint_module(doc)
        if isinstance(i, dict) and (severity is None or i.get("severity") == severity)
    }


# ---------------------------------------------------------------------------
# Layer 1 — fixture conformance (the validators-packet acceptance bar).
#
# Each value is the EXACT set of ERROR codes the fixture must exhibit (and
# nothing else). Positives map to the empty set. The single resolution-time
# code, invalid_cardinality_value (R9), is verified by the resolver /
# model-checking suite (tests/model_checking, R9_INVALID_CARDINALITY_VALUE) —
# its static-well-formed companion fixture asserts NO static error here.
# ---------------------------------------------------------------------------

EXPECTED: dict[str, set[str]] = {
    # --- happy / positive ---
    "composite-knobs-happy.tvl.yml": set(),
    "composite-knobs-happy-pre-cascade.tvl.yml": set(),
    "composite-knobs-happy-m1-cascade.tvl.yml": set(),
    "composite-knobs-happy-sampling-k1-ensemble.tvl.yml": set(),
    "composite-knobs-happy-committee-majority.tvl.yml": set(),
    "composite-knobs-happy-loop-max-iters-one.tvl.yml": set(),
    "composite-knobs-happy-tagged-nesting-under-judge.tvl.yml": set(),
    "composite-cascade-subsumes-policy.tvl.yml": set(),
    "legacy-policy-cascade-unchanged.tvl.yml": set(),
    "legacy-cvar-missing-signal-remains-valid.tvl.yml": set(),
    "invalid_cardinality_value-zero-resolved-k.tvl.yml": set(),  # R9 is resolution-time
    # --- rejecting: one per §3.11 code ---
    "unknown_composite_kind-fourth-kind.tvl.yml": {"unknown_composite_kind"},
    "unknown_composite_field-cross-kind-field.tvl.yml": {"unknown_composite_field"},
    "cascade_arity-no-gate-for-two-arms.tvl.yml": {"cascade_arity"},
    "unknown_gate_kind-unregistered-gate.tvl.yml": {"unknown_gate_kind"},
    "composite_binds_value-value-field.tvl.yml": {"composite_binds_value"},
    "composite_shadows_name-tvar-collision.tvl.yml": {"composite_shadows_name"},
    "duplicate_composite-same-name.tvl.yml": {"duplicate_composite"},
    "empty_arms-cascade-no-arms.tvl.yml": {"empty_arms"},
    "ambiguous_arm-bare-collides-composite.tvl.yml": {"ambiguous_arm"},
    "missing_composite_ref-tagged-nesting-ghost.tvl.yml": {"missing_composite_ref"},
    "composite_cycle-two-node-cycle.tvl.yml": {"composite_cycle"},
    "gate_arm_incompatible-margin-on-judge-max.tvl.yml": {"gate_arm_incompatible"},
    "gate_kind_placement_mismatch-signal-below-post.tvl.yml": {"gate_kind_placement_mismatch"},
    "missing_gate_signal-signal-below-no-signal.tvl.yml": {"missing_gate_signal"},
    "duplicate_stage-stage-repeat.tvl.yml": {"duplicate_stage"},
    "cardinality_arity_mismatch-committee-has-cardinality.tvl.yml": {"cardinality_arity_mismatch"},
    "invalid_cardinality_type-float-cardinality.tvl.yml": {"invalid_cardinality_type"},
    "missing_judge-judge-max-without-judge.tvl.yml": {"missing_judge"},
    "unknown_aggregate_kind-weighted-vote.tvl.yml": {"unknown_aggregate_kind"},
    "unknown_stop_kind-unregistered.tvl.yml": {"unknown_stop_kind"},
    "missing_stop_threshold-signal-accept-no-threshold.tvl.yml": {"missing_stop_threshold"},
    "missing_stop_signal-signal-accept-no-signal.tvl.yml": {"missing_stop_signal"},
    "missing_stop_predicate-external-accept-no-predicate.tvl.yml": {"missing_stop_predicate"},
    "stop_signal_outside_state-undeclared-key.tvl.yml": {"stop_signal_outside_state"},
    "invalid_max_iters-zero.tvl.yml": {"invalid_max_iters"},
    "invalid_tuned_param-cvar-parent.tvl.yml": {"invalid_tuned_param"},
    "invalid_threshold_type-enum-cvar.tvl.yml": {"invalid_threshold_type"},
    "missing_calibration_signal-no-signal.tvl.yml": {"missing_calibration_signal"},
    "signal_mismatch-wrong-signal.tvl.yml": {"signal_mismatch"},
    "unbound_signal_inputs-not-covered.tvl.yml": {"unbound_signal_inputs"},
    "missing_composite_parent-post-gate-omits-arm-tvar.tvl.yml": {"missing_composite_parent"},
    "invalid_arm_shape-unknown-arm-key.tvl.yml": {"invalid_arm_shape"},
    "invalid_arm_shape-composite-with-tuned-params.tvl.yml": {"invalid_arm_shape"},
    "invalid_signal_use-non-ident-inputs.tvl.yml": {"invalid_signal_use"},
    "invalid_signal_use-nonlist-inputs.tvl.yml": {"invalid_signal_use"},
    # --- reused RFC 0001 missing_ref family ---
    "missing_ref-threshold-unknown-cvar.tvl.yml": {"missing_ref"},
    "missing_ref-threshold-tvar-kind-mismatch.tvl.yml": {"missing_ref"},
}


def test_every_fixture_has_an_expectation():
    """No phase-7 fixture may be added without an exact expectation (and vice
    versa) — the suite must enumerate the whole directory."""
    on_disk = {p.name for p in FIXTURES.glob("*.tvl.yml")}
    assert on_disk == set(EXPECTED), {
        "missing_expectation": sorted(on_disk - set(EXPECTED)),
        "missing_fixture": sorted(set(EXPECTED) - on_disk),
    }


@pytest.mark.parametrize("name,expected_codes", sorted(EXPECTED.items()))
def test_fixture_conformance(name, expected_codes):
    doc = _load(name)

    # All phase-7 fixtures are schema-valid 1.2 documents: the §3.11 codes are
    # NORMATIVE LINTS, not schema_errors (the shape-vs-registry layering).
    errors = _schema_errors(doc)
    assert not errors, f"{name}: schema errors {[e.message for e in errors[:3]]}"

    error_codes = _codes(doc, "error")
    # EXACT equality: the fixture exhibits its diagnostic and NOTHING else —
    # extra errors would be new-lint false positives.
    assert error_codes == expected_codes, (name, error_codes)


# ---------------------------------------------------------------------------
# Layer 2 — targeted checks (P1, the two ratchets, use-site-only binding).
# ---------------------------------------------------------------------------


def test_p1_no_composites_block_is_byte_identical_lint():
    """Conservative extension: removing the composites block from a 1.2 module
    leaves a 1.1 module whose lint output gains no composite error code."""
    doc = _load("composite-knobs-happy.tvl.yml")
    before = _codes(doc, "error")
    assert not before
    doc.pop("composites")
    after = _codes(doc, "error")
    assert not after


def test_legacy_policy_cascade_does_not_get_composite_ratchets():
    """§4 / P1: the two composite-only ratchets — empty-tuned_params parent
    coverage and the signal/threshold binding — NEVER fire on a legacy
    policies: cascade, even when its threshold CVAR omits calibration.signal."""
    doc = _load("legacy-policy-cascade-unchanged.tvl.yml")
    codes = _codes(doc, "error")
    ratchet_codes = {
        "missing_calibration_signal",
        "signal_mismatch",
        "unbound_signal_inputs",
        "missing_composite_parent",
    }
    assert not (codes & ratchet_codes), codes


def test_signal_binding_is_composite_use_site_only():
    """§3.2 item 11: a CVAR whose calibration.signal is absent is well-formed in
    isolation — the binding lints fire ONLY at a composite use site."""
    doc = _load("legacy-cvar-missing-signal-remains-valid.tvl.yml")
    codes = _codes(doc, "error")
    assert "missing_calibration_signal" not in codes
    assert "signal_mismatch" not in codes
    assert "unbound_signal_inputs" not in codes


def test_subsumption_pair_lints_identically_modulo_ratchets():
    """RFC §9 criterion 3: the policies cascade and its composite form have
    identical execution semantics and both validate clean — the composite form
    only ADDS the two ratchet obligations (which it satisfies here)."""
    policy_doc = _load("legacy-policy-cascade-unchanged.tvl.yml")
    composite_doc = _load("composite-cascade-subsumes-policy.tvl.yml")
    assert not _codes(policy_doc, "error")
    assert not _codes(composite_doc, "error")


def test_composites_are_excluded_from_sat_encoding():
    """P2/P5: composites are invisible to search — they never enter Γ or the SAT
    encoding (only the member TVARs do)."""
    doc = _load("composite-knobs-happy.tvl.yml")
    compiled = compile_constraints(doc)
    assert set(compiled.domains) == {
        "cheap_model",
        "temperature",
        "strong_model",
        "k_samples",
    }
    # no composite/cvar name leaks into the solver variables
    for leaked in ("answerer", "voter", "refiner", "router.margin_threshold"):
        assert leaked not in compiled.domains


def test_loop_over_composite_accrues_nested_leaf_tvars():
    """§3.5 note: a signal_accept loop whose body is a COMPOSITE arm accrues the
    whole nested subtree's tuned TVARs into its stop-threshold obligation."""
    doc = _load("composite-knobs-happy.tvl.yml")
    # Re-point the loop body at the answerer composite (whose arms tune
    # cheap_model/temperature/strong_model) without covering them in depends_on.
    loop = next(c for c in doc["composites"] if c["name"] == "refiner")
    loop["body"] = {"composite": "answerer"}
    codes = _codes(doc, "error")
    assert "missing_composite_parent" in codes


def test_schema_keeps_signal_inputs_extension_key():
    """The §3.2 item-11 freshness extension key is admissible AND the new
    declaration sub-shapes that ARE closed stay closed (P8 discipline)."""
    schema = json.loads((BASE / "spec" / "grammar" / "tvl.schema.json").read_text())
    rc = schema["properties"]["promotion_policy"]["properties"]["require_calibration"]
    enum = rc["properties"]["hash_covered_context"]["items"]["enum"]
    assert "signal_inputs" in enum
    assert "signal_inputs" in rc["properties"]
    # The composite gate/aggregate/accept/stop sub-shapes stay CLOSED; only the
    # Composite envelope and the arm/signal surfaces are open (lints own those).
    for shape in ("CompositeGateDecl", "AggregateDecl", "AcceptDecl", "StopDecl"):
        assert schema["$defs"][shape].get("additionalProperties") is False, shape
