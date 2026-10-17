"""Public declaration tooling and complete-evidence promotion contracts."""
import importlib
import json
from pathlib import Path

import pytest

from tvl.measurement import normalize_measurement_bundle, validate_measurement
from tvl.promotion import epsilon_pareto_gate
from tvl.promotion_monitor import evaluate_promotion_monitor
from tvl.canonical import RuntimeClosedError
from tvl.runtime_conformance import run_language_conformance_families
from tvl.yaml_safe import safe_load


ROOT = Path(__file__).resolve().parents[1]


def promotion_module(kind="rate_bound"):
    module = safe_load((ROOT / "spec/examples/runtime-1.3/14-release-gate-on-eval-set.tvl.yml").read_text())
    monitor = next(m for m in module["monitors"] if next(
        r for r in module["requirements"] if r["name"] == m["requirement"]
    )["kind"] == kind)
    requirement = next(r for r in module["requirements"] if r["name"] == monitor["requirement"])
    return module, requirement, monitor


@pytest.mark.parametrize("k,verdict", [(0, "MET"), (8, "UNKNOWN"), (30, "BREACHED")])
def test_complete_rate_evidence_uses_exact_binomial_tests(k, verdict):
    _, requirement, monitor = promotion_module()
    requirement = dict(requirement, max_rate=0.05)
    monitor = dict(monitor, decision={"method": "clopper_pearson_rational_v2", "confidence": 0.95,
                                     "false_alarm_budget": 0.05})
    result = evaluate_promotion_monitor(requirement, monitor, {"n": 100, "k": k, "u": 0, "pl": 0})
    assert result["verdict"] == verdict


@pytest.mark.parametrize("kind", ["rate_bound", "zero_tolerance"])
@pytest.mark.parametrize("k", [0, 100])
def test_unresolved_promotion_is_explicitly_deferred(kind, k):
    _, requirement, monitor = promotion_module(kind)
    result = evaluate_promotion_monitor(requirement, monitor, {"n": 100, "k": k, "u": 1, "pl": 0, "complete": True})
    assert (result["verdict"], result["mapped_decision"], result["reason"]) == (
        "UNKNOWN", "NoDecision", "engine_required",
    )


def test_zero_tolerance_requires_explicit_completeness_to_pass():
    _, requirement, monitor = promotion_module("zero_tolerance")
    for outcome in ({"n": 100, "k": 0}, {"n": 100, "k": 0, "complete": False}):
        assert evaluate_promotion_monitor(requirement, monitor, outcome)["mapped_decision"] == "NoDecision"
    assert evaluate_promotion_monitor(requirement, monitor, {"n": 100, "k": 0, "complete": True})["verdict"] == "MET"


def test_zero_tolerance_evaluation_requires_complete_evidence_even_for_positive_counts():
    _, requirement, monitor = promotion_module("zero_tolerance")
    result = evaluate_promotion_monitor(requirement, monitor, {"n": 100, "k": 1})
    assert (result["mapped_decision"], result["reason"]) == ("NoDecision", "incomplete")
    assert evaluate_promotion_monitor(requirement, monitor, {"n": 100, "k": 1, "complete": True})["verdict"] == "BREACHED"


def test_exact_equality_is_not_a_breach():
    result = evaluate_promotion_monitor(
        {"kind": "rate_bound", "max_rate": "0.1"},
        {"decision": {"confidence": "0.95", "false_alarm_budget": "0.001"}},
        {"n": 3, "k": 3},
    )
    assert (result["verdict"], result["reason"]) == ("UNKNOWN", "inconclusive")


def test_missing_violation_count_cannot_become_zero():
    _, requirement, monitor = promotion_module()
    with pytest.raises(RuntimeClosedError, match="^runtime_report_conservation$"):
        evaluate_promotion_monitor(requirement, monitor, {"n": 500})


def test_measurement_and_release_gate_share_the_public_boundary():
    module, _, monitor = promotion_module()
    outcomes = {m["name"]: {"n": 500, "k": 0, "complete": True} for m in module["monitors"]}
    outcomes[monitor["name"]]["u"] = 1
    candidate = {"objective_values": {obj["name"]: {"samples": [1, 2, 3]} for obj in module["objectives"]},
                 "monitor_outcomes": outcomes}
    incumbent = {"objective_values": {obj["name"]: {"samples": [0, 1, 2]} for obj in module["objectives"]}}
    normalized, _ = normalize_measurement_bundle(candidate)
    assert normalized["monitor_outcomes"][monitor["name"]]["u"] == 1
    report = validate_measurement(module, {"tvar_assignments": {}}, candidate)
    assert report["monitors"][monitor["name"]]["reason"] == "engine_required"
    decision, evidence = epsilon_pareto_gate(
        incumbent, candidate, module["promotion_policy"], module["objectives"],
        requirements=module["requirements"], monitors=module["monitors"],
    )
    assert decision == "NoDecision"
    assert evidence["promotion_monitors"][monitor["name"]]["reason"] == "engine_required"


def test_public_api_contains_declarations_only():
    runtime = importlib.import_module("tvl.runtime")
    assert not {name for name in vars(runtime) if name.startswith("_") and not name.startswith("__")}
    assert {name for name in vars(runtime) if not name.startswith("_")} == {
        "ALL_STATUSES", "APPROVAL_BY_RANK", "APPROVAL_ORDER", "EXACT_COUNT_METHOD",
        "FLOAT_METHOD", "RATIONAL_METHOD", "RuntimeClosedError", "SEVERITY_BY_RANK",
        "SEVERITY_ORDER", "TERMINAL_STATUSES", "canonical_json_bytes", "canonical_json_digest",
        "canonical_json_str", "minimal_decimal_str", "to_fraction", "erase_runtime_extensions",
        "from_backend_revision", "to_backend_profile", "join_promotion_decisions",
        "compile_runtime_document", "compose_runtime_documents", "project_runtime_declarations",
        "resolve_json_pointer", "validate_projected_contract",
    }
    assert callable(runtime.compile_runtime_document)


def test_public_registry_runs_without_enabling_any_capability():
    report = run_language_conformance_families()
    assert report["ok"], json.dumps(report)
    assert "enabled_monitors" not in report and "enabled_actions" not in report


def test_public_compiler_case_cannot_silently_ignore_a_behavior_assertion():
    from tvl.runtime_conformance import ConformanceFailureError, run_runtime_conformance_case

    paths = ROOT / "conformance/cases/runtime"
    case = next(
        c for path in paths.rglob("*.yml")
        if (c := safe_load(path.read_text()))["input"].get("entrypoint") == "tvl-compile-runtime"
    )
    case["expected"]["episode_state"] = "Open"
    with pytest.raises(ConformanceFailureError):
        run_runtime_conformance_case(case)
