"""Declared enum element types apply at all existing module boundaries."""

import importlib
import json
import sys
from pathlib import Path

import pytest
import yaml
from tvl.lints import lint_module
from tvl.schema import validator

ROOT = Path(__file__).resolve().parents[1]


def _module(kind, values, wrapped):
    doc = yaml.safe_load((ROOT / "conformance/cases/satisfiable/minimal.yml").read_text())
    doc["tvars"] = [{"name": "choice", "type": f"enum[{kind}]", "domain": {"set": values} if wrapped else values}]
    return doc


def _invoke(tool, module, config, monkeypatch, capsys):
    args = [tool, str(module)]
    if tool == "tvl_config_validate":
        args += [str(config)]
    if tool in {"tvl_validate", "tvl_lint"}:
        args += ["--json"]
    monkeypatch.setattr(sys, "argv", args)
    status = 0
    try:
        importlib.import_module(f"tvl_tools.{tool}.cli").main()
    except SystemExit as exc:
        status = exc.code
    output = capsys.readouterr()
    return status, output.out + output.err


@pytest.mark.parametrize("wrapped", [False, True], ids=["array", "set"])
@pytest.mark.parametrize("kind,bad", [("int", "three"), ("int", True), ("float", "one"), ("float", True), ("str", 7), ("str", False)])
@pytest.mark.parametrize("tool", ["tvl_validate", "tvl_lint", "tvl_check_structural", "tvl_config_validate"])
def test_invalid_enum_members_reject_at_cli_boundary(kind, bad, wrapped, tool, tmp_path, monkeypatch, capsys):
    doc = _module(kind, [bad], wrapped)
    module = tmp_path / "module.yml"
    module.write_text(yaml.safe_dump(doc))
    config = tmp_path / "config.yml"
    config.write_text(yaml.safe_dump({"config_id": "test.choice", "module_id": doc["tvl"]["module"], "assignments": {"choice": bad}}))
    status, output = _invoke(tool, module, config, monkeypatch, capsys)
    assert status == (5 if tool == "tvl_config_validate" else 2), output
    assert "Traceback" not in output
    if tool in {"tvl_validate", "tvl_lint"}:
        payload = json.loads(output)
        assert payload["ok"] is False
        issues = [i for i in payload["issues"] if i["code"] == "invalid_enum_domain"]
        assert issues and "choice" in issues[0]["message"] and repr(bad) in issues[0]["message"]
        if tool == "tvl_validate":
            assert payload["schema_ok"] is False


@pytest.mark.parametrize("wrapped", [False, True], ids=["array", "set"])
@pytest.mark.parametrize("kind,values", [("int", [3, 4]), ("float", [1, 1.5]), ("str", ["small", "large"])])
@pytest.mark.parametrize("tool", ["tvl_validate", "tvl_lint", "tvl_check_structural", "tvl_config_validate"])
def test_valid_typed_enum_members_stay_usable(kind, values, wrapped, tool, tmp_path, monkeypatch, capsys):
    doc = _module(kind, values, wrapped)
    module = tmp_path / "module.yml"
    module.write_text(yaml.safe_dump(doc))
    config = tmp_path / "config.yml"
    config.write_text(yaml.safe_dump({"config_id": "test.choice", "module_id": doc["tvl"]["module"], "assignments": {"choice": values[0]}}))
    status, output = _invoke(tool, module, config, monkeypatch, capsys)
    assert status == 0, output


def test_integral_float_representation_has_explicit_schema_lint_boundary():
    doc = _module("int", [3.0, 4], False)
    assert not list(validator().iter_errors(doc))
    assert "invalid_enum_domain" in {i["code"] for i in lint_module(doc)}


@pytest.mark.parametrize("kind", ["int", "float", "str"])
def test_enum_registry_domains_remain_schema_valid(kind):
    doc = _module(kind, [], False)
    doc["tvars"][0]["domain"] = {"registry": "choices"}
    assert not list(validator().iter_errors(doc))
    assert "invalid_enum_domain" not in {i["code"] for i in lint_module(doc)}
