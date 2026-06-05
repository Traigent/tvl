"""TVL 1.1 (RFC 0001) validators — cvars, policies, namespaces, calibration.

Two layers:
1. Fixture conformance: every module in spec/examples/validation-phase6-cvars
   produces EXACTLY its README-promised diagnostic through the real schema +
   lint pipeline (these fixtures are the executable acceptance bar produced
   by the model-checking packet).
2. Targeted lint/schema unit checks for the new diagnostics, P1 conservative
   extension, and the P5 SAT-exclusion lock.
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

FIXTURES = BASE / "spec" / "examples" / "validation-phase6-cvars"
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
# Layer 1 — fixture conformance (the packet-2 acceptance bar).
# ---------------------------------------------------------------------------

EXPECTED = {
    "cvar-policies-happy.tvl.yml": (set(), None),
    "cvar-calibrated-threshold.tvl.yml": (set(), None),
    "policy-cascade.tvl.yml": (set(), None),
    "cvar-shadows-tvar.tvl.yml": ({"cvar_shadows_tvar"}, None),
    "cvar-missing-parent-ref.tvl.yml": ({"missing_ref"}, None),
    "gate-threshold-not-cvar.tvl.yml": ({"missing_ref"}, None),
    "cascade-arity-violation.tvl.yml": ({"cascade_arity"}, None),
    "duplicate-stage.tvl.yml": ({"duplicate_stage"}, None),
    "cvar-in-structural-constraint.tvl.yml": ({"cvar_in_structural_constraint"}, None),
    "namespace-prefix-collision-error.tvl.yml": ({"namespace_prefix_collision"}, "error"),
    "namespace-prefix-collision-legacy-warning.tvl.yml": (
        {"namespace_prefix_collision"},
        "warning",
    ),
}


@pytest.mark.parametrize("name,expected", sorted(EXPECTED.items()))
def test_fixture_conformance(name, expected):
    expected_codes, expected_severity = expected
    doc = yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))

    # All phase-6 fixtures are schema-valid 1.1 documents.
    errors = _schema_errors(doc)
    assert not errors, f"{name}: schema errors {[e.message for e in errors[:3]]}"

    issues = [i for i in lint_module(doc) if isinstance(i, dict)]
    error_codes = {i["code"] for i in issues if i.get("severity") == "error"}

    if not expected_codes:
        assert not error_codes, f"{name}: unexpected errors {error_codes}"
        return

    if expected_severity == "warning":
        warning_codes = {i["code"] for i in issues if i.get("severity") == "warning"}
        assert expected_codes <= warning_codes, (name, warning_codes)
        # P1: the legacy module remains VALID — warning only, zero errors.
        assert not error_codes, f"{name}: legacy module must stay valid, got {error_codes}"
    else:
        # EXACT equality: the fixture exhibits its diagnostic and NOTHING
        # else — extra errors would be new-lint false positives.
        assert error_codes == expected_codes, (name, error_codes)


def test_cvar_in_structural_is_precise_not_generic():
    """The diagnostic names the CVAR situation, not undeclared_tvar."""
    doc = _load("cvar-in-structural-constraint.tvl.yml")
    codes = _codes(doc)
    assert "cvar_in_structural_constraint" in codes
    assert "undeclared_tvar" not in codes


def test_sat_exclusion_lock():
    """P5 executable lock: solver variables are exactly the tvar names even
    for a module declaring cvars/policies."""
    doc = _load("cvar-policies-happy.tvl.yml")
    compiled = compile_constraints(doc)
    assert set(compiled.domains) == {"model", "retriever.k"}
    assert "router.margin_threshold" not in compiled.domains


# ---------------------------------------------------------------------------
# Layer 2 — targeted unit checks.
# ---------------------------------------------------------------------------


def _happy() -> dict:
    return _load("cvar-policies-happy.tvl.yml")


def test_p1_all_existing_examples_unchanged():
    """Conservative extension: every pre-1.1 example module still schema-
    validates and produces no NEW error codes (the full corpus, excluding the
    forward phase-6 fixtures)."""
    new_error_codes = {
        "duplicate_cvar",
        "invalid_cvar_name",
        "unsupported_cvar_type",
        "cvar_missing_source",
        "invalid_cvar_governance",
        "invalid_cvars",
        "invalid_cvar_decl",
        "invalid_policies",
        "invalid_policy_decl",
        "invalid_policy_name",
        "invalid_policy_kind",
        "unknown_policy_strategy",
        "unknown_gate_kind",
        "cascade_arity",
        "duplicate_stage",
        "missing_ref",
        "cvar_shadows_tvar",
        "policy_name_conflict",
        "cvar_in_structural_constraint",
        "invalid_require_calibration",
        "invalid_calibration_context",
        "invalid_scope",
        "duplicate_policy",
        "namespace_prefix_collision",
    }
    checked = 0
    for path in sorted(EXAMPLES.rglob("*.yml")):
        if "validation-phase6-cvars" in str(path):
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or "tvars" not in doc:
            continue
        codes = {
            i["code"]
            for i in lint_module(doc)
            if isinstance(i, dict) and i.get("severity") == "error"
        }
        assert not (codes & new_error_codes), (path.name, codes & new_error_codes)
        checked += 1
    assert checked >= 20


def test_duplicate_cvar():
    doc = _happy()
    doc["cvars"].append(dict(doc["cvars"][0]))
    assert "duplicate_cvar" in _codes(doc, "error")


def test_policy_name_conflict_with_cvar():
    doc = _happy()
    doc["policies"][0]["name"] = doc["cvars"][0]["name"]
    assert "policy_name_conflict" in _codes(doc, "error")


def test_unknown_policy_strategy_and_kind():
    doc = _happy()
    doc["policies"][0]["strategy"] = "tournament"
    doc["policies"][0]["kind"] = "router"
    codes = _codes(doc, "error")
    assert {"unknown_policy_strategy", "invalid_policy_kind"} <= codes


def test_gate_kind_registry():
    doc = _happy()
    doc["policies"][0]["gates"][0]["kind"] = "cost_above"
    assert "unknown_gate_kind" in _codes(doc, "error")


def test_m1_cascade_without_gates_is_valid():
    doc = _happy()
    doc["policies"][0]["stages"] = ["only"]
    del doc["policies"][0]["gates"]
    assert "cascade_arity" not in _codes(doc, "error")


def test_depends_on_naming_cvar_is_missing_ref():
    """v1: CVAR->CVAR parents are deferred; refs must be TVARs."""
    doc = _happy()
    doc["cvars"].append(
        {
            "name": "second.theta",
            "type": "float",
            "calibration": {"source": "pool_b", "depends_on": ["router.margin_threshold"]},
        }
    )
    assert "missing_ref" in _codes(doc, "error")


def test_require_calibration_rejects_core_key():
    """The mandatory ctx_core is NOT module-configurable — naming a core key
    (e.g. tuned_parent_values) as an extension is an error."""
    doc = _happy()
    doc["promotion_policy"]["require_calibration"]["hash_covered_context"] = [
        "tuned_parent_values"
    ]
    assert "invalid_calibration_context" in _codes(doc, "error")


def test_require_calibration_empty_extensions_valid():
    """Core-only coverage (empty extension list) is valid by design."""
    doc = _happy()
    doc["promotion_policy"]["require_calibration"]["hash_covered_context"] = []
    assert "invalid_calibration_context" not in _codes(doc, "error")


def test_scope_prefix_mismatch_warning():
    doc = _happy()
    doc["cvars"][0]["scope"] = {"node": "planner"}  # name prefix is 'router'
    issues = [i for i in lint_module(doc) if isinstance(i, dict)]
    assert any(
        i["code"] == "scope_prefix_mismatch" and i["severity"] == "warning"
        for i in issues
    )


def test_invalid_scope_field():
    doc = _happy()
    doc["cvars"][0]["scope"] = {"tenant": "x"}
    assert "invalid_scope" in _codes(doc, "error")


def test_schema_rejects_unknown_cvar_fields():
    doc = _happy()
    doc["cvars"][0]["search"] = True
    assert _schema_errors(doc)


def test_schema_rejects_policy_without_stages():
    doc = _happy()
    del doc["policies"][0]["stages"]
    assert _schema_errors(doc)


def test_schema_accepts_scope_on_tvar():
    """The one 1.0-shape change: optional scope on TVarDecl (additive)."""
    doc = _happy()
    doc["tvars"][0]["scope"] = {"node": "model"}
    assert not _schema_errors(doc)


def test_cvar_on_rhs_of_tvar_equality_is_precise():
    """RFC §3.2/P5 (review finding): a CVAR referenced on the RHS of a TVAR
    equality gets the precise diagnostic too — for numeric, bool, AND enum
    left-hand sides."""
    doc = _happy()
    # int, enum, and bool LHS — the three live kinds in the happy fixture
    # (the reviewer manually verified float/tuple/callable behave identically)
    doc["tvars"].append({"name": "zero_shot", "type": "bool", "domain": [True, False]})
    for then in (
        "retriever.k = router.margin_threshold",   # int LHS
        "model = router.margin_threshold",          # enum LHS
        "zero_shot = router.margin_threshold",      # bool LHS
    ):
        doc["constraints"] = {
            "structural": [{"when": "retriever.k = 0", "then": then}]
        }
        codes = _codes(doc, "error")
        assert "cvar_in_structural_constraint" in codes, then
        assert "undeclared_tvar" not in codes, then


def test_presence_based_11_opt_in():
    """§3.7(5): an explicit EMPTY cvars list still opts into 1.1 severity —
    the prefix collision escalates to error."""
    doc = yaml.safe_load(
        (FIXTURES / "namespace-prefix-collision-legacy-warning.tvl.yml").read_text(
            encoding="utf-8"
        )
    )
    doc["cvars"] = []
    issues = [i for i in lint_module(doc) if isinstance(i, dict)]
    assert any(
        i["code"] == "namespace_prefix_collision" and i["severity"] == "error"
        for i in issues
    )


def test_p8_new_declaration_shapes_are_closed():
    """P8 schema canary (closes the recorded Phase-4 deferral): every TVL 1.1
    declaration shape is CLOSED — additionalProperties:false — so no open
    payload field exists to smuggle content. policy.parameters stays the one
    deliberate opaque object (explicitly OUT of the P8 guarantee, RFC §3.8)."""
    schema = json.loads(
        (BASE / "spec" / "grammar" / "tvl.schema.json").read_text(encoding="utf-8")
    )
    defs = schema["$defs"]
    for shape in ("CVarDecl", "PolicyDecl", "GateDecl", "Scope"):
        assert defs[shape].get("additionalProperties") is False, shape
    # the documented exception: parameters is an opaque object by design
    params = defs["PolicyDecl"]["properties"]["parameters"]
    assert params.get("type") == "object"
