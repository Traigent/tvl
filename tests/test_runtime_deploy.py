"""`optimize.deploy` (RFC 0003 §7.6): schema, lint, composition and compiler checks."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict

import pytest

from tvl.runtime import RuntimeClosedError, compile_runtime_document, compose_runtime_documents
from tvl.runtime_compiler import _check_deploy_gates
from tvl.runtime_conformance import _build_synthetic_tokens_for_docs
from tvl.schema import runtime_contract_validator, validator as module_validator
from tvl.yaml_safe import safe_load

CASES = Path(__file__).resolve().parents[1] / "conformance/cases/runtime"


def _case(rel: str) -> Dict[str, Any]:
    return safe_load((CASES / rel).read_text())


def _module() -> Dict[str, Any]:
    return copy.deepcopy(_case("lints/deploy-if-promoted-with-promotion-monitor.yml")["module"])


def _tokens(*docs: Dict[str, Any]) -> Dict[str, Any]:
    return {"format": "tvl-token-map/1", "tokens": _build_synthetic_tokens_for_docs(list(docs))}


def _opt_rule(contract: Dict[str, Any], index: int = 1) -> Dict[str, Any]:
    return contract["declarations"]["responses"][0]["rules"][index]


def test_authored_schema_admits_deploy_and_checks_only_its_type() -> None:
    doc = _module()
    assert not list(module_validator().iter_errors(doc))
    doc["responses"][0]["rules"][1]["deploy"] = 1
    assert list(module_validator().iter_errors(doc))


def test_compile_carries_deploy_and_fills_the_never_default() -> None:
    doc = _module()
    doc["responses"][0]["rules"].append(
        {"id": "opt_default", "trigger": {"monitor": "monitor_main", "event": "episode_continued"},
         "do": "optimize", "approval": "standing"}
    )
    contract, local, _ = compile_runtime_document(doc, token_map_doc=_tokens(doc))
    assert _opt_rule(contract)["deploy"] == "if_promoted"
    assert _opt_rule(contract, 2)["deploy"] == "never"
    assert "deploy" not in _opt_rule(contract, 0)  # open_next_step carries no deploy coordinate
    assert local["declarations"]["responses"][0]["rules"][1]["deploy"] == "if_promoted"
    assert "monitor_gate" in local["harness_monitors"]


def test_deploy_changes_the_contract_digest() -> None:
    doc = _module()
    never = copy.deepcopy(doc)
    never["responses"][0]["rules"][1]["deploy"] = "never"
    a, _, _ = compile_runtime_document(doc, token_map_doc=_tokens(doc))
    b, _, _ = compile_runtime_document(never, token_map_doc=_tokens(never))
    from tvl.canonical import canonical_json_digest

    assert canonical_json_digest(a) != canonical_json_digest(b)


def test_contract_schema_requires_deploy_on_optimize_and_forbids_it_elsewhere() -> None:
    doc = _module()
    contract, _, _ = compile_runtime_document(doc, token_map_doc=_tokens(doc))
    assert not list(runtime_contract_validator().iter_errors(contract))
    missing = copy.deepcopy(contract)
    del _opt_rule(missing)["deploy"]
    assert list(runtime_contract_validator().iter_errors(missing))
    misplaced = copy.deepcopy(contract)
    _opt_rule(misplaced, 0)["deploy"] = "never"
    assert list(runtime_contract_validator().iter_errors(misplaced))
    unknown = copy.deepcopy(contract)
    _opt_rule(unknown)["deploy"] = "always"
    assert list(runtime_contract_validator().iter_errors(unknown))


def test_compile_refuses_deploy_without_promotion_monitor_with_closed_code() -> None:
    doc = _module()
    doc["monitors"] = [m for m in doc["monitors"] if m["phase"] != "promotion"]
    with pytest.raises(RuntimeClosedError) as err:
        compile_runtime_document(doc, token_map_doc=_tokens(doc))
    assert err.value.code == "response_deploy_without_promotion_monitor"
    assert err.value.path == ["responses", 0, "rules", 1, "deploy"]
    assert "monitor_main" not in err.value.message


def test_post_composition_gate_check_fails_closed() -> None:
    doc = _module()
    _check_deploy_gates(doc)
    doc["monitors"] = [m for m in doc["monitors"] if m["phase"] != "promotion"]
    with pytest.raises(RuntimeClosedError) as err:
        _check_deploy_gates(doc)
    assert err.value.code == "response_deploy_without_promotion_monitor"
    misplaced = _module()
    misplaced["responses"][0]["rules"][0]["deploy"] = "if_promoted"
    with pytest.raises(RuntimeClosedError) as err:
        _check_deploy_gates(misplaced)
    assert err.value.code == "runtime_invalid_ladder"


def test_module_cannot_widen_a_pack_optimize_rule_to_deploy() -> None:
    case = _case("composition/compile-pack-keeps-composed-responses.yml")
    pack, module = copy.deepcopy(case["base"]), copy.deepcopy(case["overlay"])
    pack["responses"][0]["rules"].append(
        {"id": "opt", "trigger": {"monitor": "floor_monitor", "event": "episode_opened"},
         "do": "optimize", "approval": "human"}
    )
    module["monitors"].append(
        {"name": "agent_gate", "requirement": "agent_req", "phase": "promotion",
         "evidence": {"source": "evaluation_set"},
         "decision": {"method": "clopper_pearson_rational_v2", "confidence": 0.95, "false_alarm_budget": 0.05}}
    )
    module["responses"] = copy.deepcopy(pack["responses"])
    for rule in module["responses"][0]["rules"]:
        rule["trigger"]["monitor"] = "agent_monitor"
    composed, _ = compose_runtime_documents(pack, module, operation="overlay")
    assert composed["responses"][0]["rules"][1].get("deploy", "never") == "never"
    module["responses"][0]["rules"][1]["deploy"] = "if_promoted"
    with pytest.raises(RuntimeClosedError) as err:
        compose_runtime_documents(pack, module, operation="overlay")
    assert err.value.code == "runtime_overlay_weakens"
    assert err.value.path[-1] == "deploy"


def test_promotion_monitor_on_another_requirement_does_not_gate_the_deploy() -> None:
    doc = _case("lints/deploy-promotion-monitor-on-other-requirement.yml")["module"]
    from tvl.lints import lint_module

    assert "response_deploy_without_promotion_monitor" in {i["code"] for i in lint_module(doc)}
    with pytest.raises(RuntimeClosedError) as err:
        compile_runtime_document(doc, token_map_doc=_tokens(doc))
    assert err.value.code == "response_deploy_without_promotion_monitor"
    with pytest.raises(RuntimeClosedError) as err:
        _check_deploy_gates(doc)
    assert err.value.code == "response_deploy_without_promotion_monitor"


def _pack_with_deploy() -> tuple[Dict[str, Any], Dict[str, Any]]:
    case = _case("composition/pack-deploy-cannot-borrow-module-gate.yml")
    return copy.deepcopy(case["base"]), copy.deepcopy(case["overlay"])


@pytest.mark.parametrize("operation", ["overlay", "meet"])
def test_pack_deploy_cannot_borrow_the_module_gate(operation: str) -> None:
    pack, module = _pack_with_deploy()
    with pytest.raises(RuntimeClosedError) as err:
        compose_runtime_documents(pack, module, operation=operation)
    assert err.value.code == "response_deploy_without_promotion_monitor"
    assert err.value.path == ["responses", 0, "rules", 1, "deploy"]
    pack["responses"][0]["rules"][1]["deploy"] = "never"
    compose_runtime_documents(pack, module, operation=operation)


@pytest.mark.parametrize("flag", ["--pack", "--meet"])
def test_compose_cli_validate_refuses_pack_deploy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                  capsys: pytest.CaptureFixture, flag: str) -> None:
    import json
    import sys

    import yaml

    from tvl_tools.tvl_compose.cli import main

    pack, module = _pack_with_deploy()
    module_path, pack_path = tmp_path / "module.yml", tmp_path / "pack.yml"
    module_path.write_text(yaml.safe_dump(module))
    pack_path.write_text(yaml.safe_dump(pack))
    monkeypatch.setattr(sys, "argv", ["tvl-compose", str(module_path), "--json", "--validate", flag, str(pack_path)])
    try:
        main()
    except SystemExit as exc:
        assert exc.code not in (0, None)
    result = json.loads(capsys.readouterr().out)
    assert not result["ok"]
    assert "response_deploy_without_promotion_monitor" in json.dumps(result)
