"""Compiler, privacy canary, and CLI tests for TVL 1.3 runtime extension (RFC 0003)."""


from __future__ import annotations


import json


from pathlib import Path


import pytest


from tvl.lints import lint_module


from tvl.runtime import (
    RuntimeClosedError,
    compile_runtime_document,
    compose_runtime_documents,
)


from tvl.yaml_safe import safe_load


from tvl_tools.tvl_compile_runtime.cli import run_cli as run_compile_cli


def test_privacy_canary_across_all_projection_rows() -> None:
    """Verify customer strings in module, names, states, selector ref, env, and checker labels never leak."""
    doc = {
        "tvl": {"module": "CANARY_CORP.CANARY_BOT"},
        "tvl_version": "1.3",
        "environment": {"snapshot_id": "2026-10-16T00:00:00Z"},
        "evaluation_set": {"dataset": "CANARY_DATASET_URI"},
        "tvars": [{"name": "CANARY_TVAR", "type": "enum[str]", "domain": ["CANARY_VAL1", "CANARY_VAL2"]}],
        "objectives": [{"name": "CANARY_OBJ", "direction": "maximize"}],
        "promotion_policy": {
            "dominance": "epsilon_pareto",
            "alpha": 0.05,
            "min_effect": {"CANARY_OBJ": 0.01},
        },
        "requirements": [
            {
                "name": "CANARY_REQ_RATE",
                "kind": "rate_bound",
                "unit": "invocation",
                "among": {"checker": "customer:CANARY_CHECKER", "label_in": ["CANARY_LABEL_A"]},
                "violation": {"checker": "customer:CANARY_CHECKER", "label_in": ["CANARY_LABEL_B"]},
                "max_rate": 0.02,
            },
            {
                "name": "CANARY_REQ_PROTO",
                "kind": "zero_tolerance",
                "unit": "invocation",
                "violation": {
                    "pattern": "protocol",
                    "alphabet": [
                        {"event": "authorization_granted", "ref": "CANARY_AUTH_REF"},
                        {"event": "tool_call", "tool": "payments.charge"},
                    ],
                    "states": ["CANARY_STATE_START", "CANARY_STATE_AUTH", "CANARY_STATE_DONE", "CANARY_STATE_BAD"],
                    "start": "CANARY_STATE_START",
                    "transitions": [
                        {
                            "from": "CANARY_STATE_START",
                            "when": {"event": "authorization_granted", "ref": "CANARY_AUTH_REF"},
                            "to": "CANARY_STATE_AUTH",
                        },
                        {
                            "from": "CANARY_STATE_AUTH",
                            "when": {"event": "tool_call", "tool": "payments.charge"},
                            "to": "CANARY_STATE_DONE",
                        },
                    ],
                    "accepting": ["CANARY_STATE_DONE"],
                    "rejecting": ["CANARY_STATE_BAD"],
                },
            },
        ],
        "monitors": [
            {
                "name": "CANARY_MON_RATE",
                "requirement": "CANARY_REQ_RATE",
                "phase": "runtime",
                "evidence": {
                    "source": "customer_side",
                    "deployment_environment": "CANARY_ENV_PROD",
                },
                "window": {"tumbling_hours": 6, "grace_minutes": 30},
                "decision": {
                    "method": "clopper_pearson_rational_v2",
                    "confidence": 0.95,
                    "false_alarm_budget": 0.05,
                    "horizon_days": 30,
                    "min_samples": 300,
                    "max_unresolved_fraction": 0.05,
                },
                "episode": {"closure_windows": 2, "closure_max_age_hours": 24},
            },
            {
                "name": "CANARY_MON_PROTO",
                "requirement": "CANARY_REQ_PROTO",
                "phase": "runtime",
                "evidence": {
                    "source": "customer_side",
                    "deployment_environment": "CANARY_ENV_PROD",
                },
                "window": {"tumbling_hours": 6, "grace_minutes": 30},
                "decision": {"method": "exact_count_v1"},
                "episode": {"closure_windows": 2, "closure_max_age_hours": 24},
                "limits": {"max_active_obligations": 32, "max_tracked_correlations": 128},
            },
        ],
        "responses": [
            {
                "name": "CANARY_RESP",
                "rules": [
                    {
                        "id": "CANARY_RULE",
                        "trigger": {"monitor": "CANARY_MON_PROTO", "event": "unit_violation"},
                        "do": "block_action",
                        "on_check_error": "block",
                    }
                ],
            }
        ],
    }

    token_map_doc = {
        "format": "tvl-token-map/1",
        "tokens": [
            {"namespace": "module", "local": "CANARY_CORP.CANARY_BOT", "hosted": "tok_mod"},
            {"namespace": "requirement", "local": "CANARY_REQ_RATE", "hosted": "tok_req_1"},
            {"namespace": "requirement", "local": "CANARY_REQ_PROTO", "hosted": "tok_req_2"},
            {"namespace": "monitor", "local": "CANARY_MON_RATE", "hosted": "tok_mon_1"},
            {"namespace": "monitor", "local": "CANARY_MON_PROTO", "hosted": "tok_mon_2"},
            {"namespace": "response", "local": "CANARY_RESP", "hosted": "tok_resp"},
            {"namespace": "rule", "local": "CANARY_RULE", "hosted": "tok_rule"},
            {"namespace": "environment", "local": "CANARY_ENV_PROD", "hosted": "tok_env"},
            {"namespace": "selector_ref", "local": "CANARY_AUTH_REF", "hosted": "tok_ref"},
            {"namespace": "state", "local": "CANARY_STATE_START", "hosted": "tok_s0"},
            {"namespace": "state", "local": "CANARY_STATE_AUTH", "hosted": "tok_s1"},
            {"namespace": "state", "local": "CANARY_STATE_DONE", "hosted": "tok_s2"},
            {"namespace": "state", "local": "CANARY_STATE_BAD", "hosted": "tok_s3"},
            {
                "namespace": "checker",
                "local": "customer:CANARY_CHECKER",
                "hosted": "customer:1111111111111111111111111111111111111111111111111111111111111111",
            },
        ],
    }
    checker_reg_doc = {
        "format": "tvl-checker-registry/1",
        "checkers": [
            {
                "checker": "customer:CANARY_CHECKER",
                "labels": ["CANARY_LABEL_A", "CANARY_LABEL_B"],
            }
        ],
    }

    contract, local_prog, _issues = compile_runtime_document(
        doc,
        token_map_doc=token_map_doc,
        checker_registry_doc=checker_reg_doc,
    )
    hosted_json = json.dumps(contract, sort_keys=True)
    assert "CANARY_" not in hosted_json
    assert "payments.charge" in hosted_json
    assert local_prog["customer_monitors"] == ["CANARY_MON_RATE", "CANARY_MON_PROTO"]


def test_tool_alias_not_code_ident_rejected_before_projection() -> None:
    """Verify a free-form customer tool alias in selector.tool is rejected by lints."""
    doc = {
        "tvl": {"module": "acme.bot"},
        "tvl_version": "1.3",
        "environment": {"snapshot_id": "2026-10-16T00:00:00Z"},
        "evaluation_set": {"dataset": "ds"},
        "tvars": [{"name": "m", "type": "enum[str]", "domain": ["a", "b"]}],
        "objectives": [{"name": "q", "direction": "maximize"}],
        "promotion_policy": {"dominance": "epsilon_pareto", "alpha": 0.05, "min_effect": {"q": 0.01}},
        "requirements": [
            {
                "name": "r1",
                "kind": "zero_tolerance",
                "unit": "invocation",
                "violation": {
                    "pattern": "absence",
                    "a": {"event": "tool_call", "tool": "CANARY tool alias with spaces!"},
                },
            }
        ],
        "monitors": [
            {
                "name": "m1",
                "requirement": "r1",
                "phase": "runtime",
                "evidence": {"source": "customer_side"},
                "window": {"tumbling_hours": 6, "grace_minutes": 30},
                "decision": {"method": "exact_count_v1"},
                "episode": {"closure_windows": 2, "closure_max_age_hours": 24},
            }
        ],
    }
    with pytest.raises(RuntimeClosedError) as exc_info:
        compile_runtime_document(doc, token_map_doc={"format": "tvl-token-map/1", "tokens": []})
    assert exc_info.value.code == "runtime_tool_not_code_identifier"
    assert "CANARY" not in str(exc_info.value)


def test_compile_cli_end_to_end(tmp_path: Path) -> None:
    """Compile a module with a pack and verify both public artifacts."""
    pack_yaml = """
tvl_version: "1.3"
pack: { module: acme.org_floors }
requirements:
  - name: latency_floor_2s
    kind: rate_bound
    unit: trace
    violation: { metric: wall_clock_latency_ms, exceeds: 2000 }
    max_rate: 0.10
  - name: latency_floor_live
    kind: evidence_liveness
    unit: window
    of: latency_floor_2s_prod
    max_stale_windows: 4
monitors:
  - name: latency_floor_2s_prod
    requirement: latency_floor_2s
    phase: runtime
    profile: backend_v1
    applies_to: tenant_floor
    evidence: { source: backend_trace_metadata, deployment_environment: production,
                attribution: agent_key_exact_v1, resolution: terminal_status_v1, sampling: unverified }
    window: { tumbling_hours: 6, grace_minutes: 30 }
    decision: { method: clopper_pearson_exact_v1, model: iid_bernoulli_within_window_v1, confidence: 0.95,
                false_alarm_budget: 0.05, horizon_days: 30, min_samples: 200, max_unresolved_fraction: 0.05 }
    episode: { closure_windows: 2, closure_max_age_hours: 24 }
  - name: latency_floor_live_check
    requirement: latency_floor_live
    phase: runtime
    applies_to: tenant_floor
    evidence: { source: windows }
    decision: { method: exact_count_v1 }
"""
    mod_yaml = """
tvl: { module: acme.support_bot }
tvl_version: "1.3"
environment: { snapshot_id: "2026-10-16T00:00:00Z" }
evaluation_set: { dataset: support_eval_v4 }
tvars: [ { name: model, type: "enum[str]", domain: [m_small, m_large] } ]
objectives: [ { name: quality, direction: maximize } ]
promotion_policy: { dominance: epsilon_pareto, alpha: 0.05, min_effect: { quality: 0.02 } }

requirements:
  - name: latency_2s
    kind: rate_bound
    unit: trace
    violation: { metric: wall_clock_latency_ms, exceeds: 2000 }
    max_rate: 0.05
monitors:
  - name: latency_2s_prod
    requirement: latency_2s
    phase: runtime
    profile: backend_v1
    applies_to: agent
    evidence: { source: backend_trace_metadata, deployment_environment: production }
    decision: { method: clopper_pearson_exact_v1 }
"""
    pack_path = tmp_path / "pack.yml"
    mod_path = tmp_path / "module.yml"
    tokens_path = tmp_path / "tokens.json"
    out_dir = tmp_path / "out"

    pack_path.write_text(pack_yaml, encoding="utf-8")
    mod_path.write_text(mod_yaml, encoding="utf-8")
    tokens_path.write_text(
        json.dumps(
            {
                "format": "tvl-token-map/1",
                "tokens": [
                    {"namespace": "module", "local": "acme.org_floors", "hosted": "tok_pack"},
                    {"namespace": "module", "local": "acme.support_bot", "hosted": "tok_mod"},
                    {"namespace": "requirement", "local": "latency_floor_2s", "hosted": "tok_req_fl"},
                    {"namespace": "requirement", "local": "latency_floor_live", "hosted": "tok_req_live"},
                    {"namespace": "requirement", "local": "latency_2s", "hosted": "tok_req_lat"},
                    {"namespace": "monitor", "local": "latency_floor_2s_prod", "hosted": "tok_mon_fl"},
                    {"namespace": "monitor", "local": "latency_floor_live_check", "hosted": "tok_mon_live"},
                    {"namespace": "monitor", "local": "latency_2s_prod", "hosted": "tok_mon_lat"},
                    {"namespace": "environment", "local": "production", "hosted": "tok_env"},
                ],
            }
        ),
        encoding="utf-8",
    )

    code, res = run_compile_cli(
        [
            str(mod_path),
            "--pack",
            str(pack_path),
            "--token-map",
            str(tokens_path),
            "--out-dir",
            str(out_dir),
            "--format",
            "json",
        ]
    )
    assert code == 0
    assert res["ok"] is True
    assert (out_dir / "runtime-contract.json").exists()
    assert (out_dir / "runtime-local.json").exists()




ROOT = Path(__file__).resolve().parents[1]


RUNTIME_CASES = ROOT / "conformance" / "cases" / "runtime"


def _must(cond: bool, msg: str = "check failed") -> None:
    """Assertion helper that stays active under `python -O`."""
    if not cond:
        raise AssertionError(msg)


def _load_fixture(rel_path: str) -> dict:
    return safe_load((RUNTIME_CASES / rel_path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("existing_pair", [False, True])
@pytest.mark.parametrize("failure", ["second_write", "second_replace"])
def test_compile_cli_failure_preserves_artifact_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing_pair: bool, failure: str,
) -> None:
    case = _load_fixture("projection/numbers-enums-and-methods.yml")
    module_path = tmp_path / "module.yml"
    tokens_path = tmp_path / "tokens.json"
    out_dir = tmp_path / "out"
    module_path.write_text(json.dumps(case["module"]), encoding="utf-8")
    tokens_path.write_text(json.dumps({"format": "tvl-token-map/1", "tokens": case["input"]["token_map"]}),
                           encoding="utf-8")
    args = [str(module_path), "--token-map", str(tokens_path), "--out-dir", str(out_dir), "--format", "json"]
    previous = {}
    if existing_pair:
        code, result = run_compile_cli(args)
        assert code == 0 and result["ok"]
        previous = {path.name: path.read_bytes() for path in out_dir.iterdir()}
        assert set(previous) == {"runtime-contract.json", "runtime-local.json"}
        case["module"]["requirements"][0]["max_rate"] = 0.04
        module_path.write_text(json.dumps(case["module"]), encoding="utf-8")

    write_text = Path.write_text
    replace = Path.replace
    failures = []

    def fail_second_write(path: Path, data: str, *args, **kwargs):
        if path.name == "runtime-local.json":
            failures.append(path)
            write_text(path, data[:10], *args, **kwargs)
            raise OSError("injected second artifact write failure")
        return write_text(path, data, *args, **kwargs)

    def fail_second_replace(path: Path, target: Path):
        if Path(target) == out_dir / "runtime-local.json":
            failures.append(path)
            raise OSError("injected second artifact replacement failure")
        return replace(path, target)

    if failure == "second_write":
        monkeypatch.setattr(Path, "write_text", fail_second_write)
    else:
        monkeypatch.setattr(Path, "replace", fail_second_replace)

    code, result = run_compile_cli(args)
    assert code == 2 and not result["ok"]
    assert result["contract_digest"] is None
    assert [issue["code"] for issue in result["issues"]] == ["schema_error"]
    assert len(failures) == 1
    assert {path.name: path.read_bytes() for path in out_dir.iterdir()} == previous


def test_compile_pack_preserves_composed_responses() -> None:
    """Compiling a module with --pack retains composed pack responses and rewritten references."""

    c = _load_fixture("composition/all-paired-preview-validates-without-provenance.yml")
    tokens = [
        {"namespace": "module", "local": "conformance.runtime", "hosted": "t0"},
        {"namespace": "module", "local": "test_pack", "hosted": "t1"},
        {"namespace": "environment", "local": "production", "hosted": "t2"},
        {"namespace": "requirement", "local": "agent_req", "hosted": "t3"},
        {"namespace": "requirement", "local": "agent_live", "hosted": "t4"},
        {"namespace": "requirement", "local": "floor_req", "hosted": "t5"},
        {"namespace": "requirement", "local": "floor_live", "hosted": "t6"},
        {"namespace": "monitor", "local": "agent_monitor", "hosted": "t7"},
        {"namespace": "monitor", "local": "agent_live_monitor", "hosted": "t8"},
        {"namespace": "monitor", "local": "floor_monitor", "hosted": "t9"},
        {"namespace": "monitor", "local": "floor_live_monitor", "hosted": "t10"},
        {"namespace": "response", "local": "pack_alerts", "hosted": "t11"},
        {"namespace": "rule", "local": "alert", "hosted": "t12"},
    ]
    contract, local, _ = compile_runtime_document(
        c["overlay"],
        packs=[c["base"]],
        token_map_doc={"format": "tvl-token-map/1", "tokens": tokens},
    )
    _must(len(local["declarations"]["responses"]) == 1)
    _must(local["declarations"]["responses"][0]["rules"][0]["trigger"]["monitor"] == "agent_monitor")
    _must(contract["declarations"]["responses"][0]["rules"][0]["trigger"]["monitor"] == "t7")


def test_unrecoverable_decimal_literal_rejected() -> None:
    """Unrecoverable decimal literals (e.g. 0.050000000000000001) are rejected by lint and compile."""

    p = RUNTIME_CASES / "projection" / "numbers-enums-and-methods.yml"
    c = safe_load(p.read_text(encoding="utf-8").replace("max_rate: 0.05", "max_rate: 0.050000000000000001"))
    issues = lint_module(c["module"])
    _must(any(i["code"] == "runtime_invalid_profile" for i in issues))
    try:
        compile_runtime_document(
            c["module"],
            token_map_doc={"format": "tvl-token-map/1", "tokens": []},
        )
        _must(False, "Expected RuntimeClosedError('runtime_invalid_profile')")
    except RuntimeClosedError as exc:
        _must(exc.code == "runtime_invalid_profile")


def test_compose_emits_schema_valid_numbers(tmp_path: Path) -> None:
    """Compose emits YAML numbers (not strings) and validates the exact written bytes."""
    from tvl.schema import validator

    c = _load_fixture("composition/compose-pack-output-validates-as-authored.yml")
    composed, _ = compose_runtime_documents(c["base"], c["overlay"], operation="overlay")
    _must(isinstance(composed["requirements"][0]["max_rate"], float))
    _must(not list(validator().iter_errors(composed)))


def test_runner_rejects_unknown_expected_keys() -> None:
    """Conformance runner rejects unknown expected keys."""
    import copy
    from tvl.runtime_conformance import ConformanceFailureError, run_runtime_conformance_case

    p = sorted((RUNTIME_CASES / "projection").glob("*.yml"))[0]
    c_mut = copy.deepcopy(safe_load(p.read_text(encoding="utf-8")))
    c_mut["expected"]["totally_unknown_key"] = 42
    rejected = False
    try:
        run_runtime_conformance_case(c_mut)
    except ConformanceFailureError:
        rejected = True
    _must(rejected, "Unknown expected key must be rejected")


def test_projection_validates_contract_schema_and_blocks_leaks() -> None:
    """Projection validates contract schema and rejects leaked local names."""
    import copy
    import tvl.runtime_conformance as R

    ConformanceFailureError = R.ConformanceFailureError
    run_runtime_conformance_case = R.run_runtime_conformance_case

    c = _load_fixture("projection/numbers-enums-and-methods.yml")
    orig = R.project_runtime_declarations

    def leak_proj(doc: dict, **k):
        loc, hosted, bp, toks = orig(doc, **k)
        hosted = copy.deepcopy(hosted)
        hosted["monitors"][0]["name"] = doc["monitors"][0]["name"]
        return loc, hosted, bp, toks

    R.project_runtime_declarations = leak_proj
    try:
        failed = False
        try:
            run_runtime_conformance_case(copy.deepcopy(c))
        except ConformanceFailureError:
            failed = True
        _must(failed, "Leaked monitor name in projection must fail")
    finally:
        R.project_runtime_declarations = orig


def test_float_power_lint_never_falls_back_to_rational(monkeypatch: pytest.MonkeyPatch) -> None:
    """Float power lint emits an explicit error diagnostic if scipy beta fails, never falling back to rational."""
    import scipy.stats

    c = _load_fixture("latency_roundtrip/latency-defaults.yml")
    monkeypatch.setattr(scipy.stats.beta, "ppf", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("scipy unavailable")))
    issues = lint_module(c["module"])
    _must(any(i["code"] == "runtime_invalid_profile" and i["severity"] == "error" for i in issues))


def test_pre13_check_operational_preserves_structured_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Invalid legacy modules retain the structured diagnostic and exit code 2."""
    import sys
    from tvl_tools.tvl_check_operational.cli import main as check_op_main

    bad_12 = tmp_path / "bad12.yml"
    bad_12.write_text("tvl: { module: bad.mod }\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["tvl-check-operational", str(bad_12), "--json"])
    with pytest.raises(SystemExit) as exc:
        check_op_main()
    _must(exc.value.code == 2)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    _must(payload["schemaVersion"] == "1.0")
    _must(payload["kind"] == "PhaseResult")
    _must(payload["phase"] == "operational")
    _must(payload["ok"] is False)
    _must(payload["status"] == "error")
    _must("'environment' is a required property" in payload["error"])
    _must("code" not in payload)
    _must("Traceback" not in captured.err)


def test_cli_utils_contains_no_test_harness() -> None:
    """tvl_tools/cli_utils.py ships no test harness."""
    import tvl_tools.cli_utils as cu

    _must(not hasattr(cu, "invoke_entrypoint_for_test"))


def test_production_conformance_has_no_test_imports(tmp_path: Path) -> None:
    import os
    import subprocess
    import sys

    script = '''
import importlib.abc
import sys
class NoTests(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "tests" or fullname.startswith("tests."):
            raise RuntimeError("production imported tests")
sys.meta_path.insert(0, NoTests())
from pathlib import Path
from tvl.runtime_conformance import run_runtime_conformance_case
from tvl.yaml_safe import safe_load
run_runtime_conformance_case(safe_load(Path(sys.argv[1]).read_text()))
'''
    # Select an existing v1.3 reader case that goes through the shared CLI harness.
    cases = [_load_fixture(str(p.relative_to(RUNTIME_CASES))) for p in (RUNTIME_CASES / "compatibility").glob("*.yml")]
    case_data = next(c for c in cases if c["input"].get("reader") == "v1_3")
    case = tmp_path / "case.json"
    case.write_text(json.dumps(case_data), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "python"), str(ROOT)]))
    result = subprocess.run([sys.executable, "-c", script, str(case)], cwd=tmp_path,
                            env=env, text=True, capture_output=True, check=False)
    _must(result.returncode == 0, result.stdout + result.stderr)
