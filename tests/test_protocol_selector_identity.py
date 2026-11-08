"""Issue #229: a protocol whose selectors use different fields must lint, not crash.

The duplicate-requirement identity sorted selector tuples that hold ``None`` for absent
fields next to strings, which raised ``TypeError`` for a schema-valid module.
"""

import copy
import json
import sys
from pathlib import Path

import yaml
from tvl.lints import lint_module

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "spec/examples/runtime-1.3/22-forbidden-tool-set-via-protocol.tvl.yml"


def _mixed_selector_module():
    doc = yaml.safe_load(EXAMPLE.read_text())
    violation = doc["requirements"][0]["violation"]
    replaced = 0
    for idx, sel in enumerate(violation["alphabet"]):
        if sel.get("tool") == "warehouse.run_ddl":
            violation["alphabet"][idx] = {"event": "tool_call", "status": "error"}
            replaced += 1
    for transition in violation["transitions"]:
        if transition.get("when", {}).get("tool") == "warehouse.run_ddl":
            transition["when"] = {"event": "tool_call", "status": "error"}
            replaced += 1
    assert replaced >= 2, "fixture no longer has the warehouse.run_ddl selector"
    return doc


def test_mixed_tool_and_status_selectors_lint_without_crash():
    issues = lint_module(_mixed_selector_module())
    assert all(isinstance(issue, dict) and "code" in issue for issue in issues)


def test_duplicate_mixed_selector_protocols_are_still_detected():
    doc = _mixed_selector_module()
    assert "runtime_duplicate_key" not in {i["code"] for i in lint_module(doc)}
    twin = copy.deepcopy(doc["requirements"][0])
    twin["name"] = "no_write_tools_twin"
    # Same selectors in a different order must still be the same requirement.
    twin["violation"]["alphabet"].reverse()
    twin["violation"]["transitions"].reverse()
    doc["requirements"].append(twin)
    twin_monitor = copy.deepcopy(doc["monitors"][0])
    twin_monitor["name"] = "no_write_tools_twin_prod"
    twin_monitor["requirement"] = "no_write_tools_twin"
    doc["monitors"].append(twin_monitor)
    codes = {i["code"] for i in lint_module(doc)}
    assert "runtime_duplicate_key" in codes, codes


def test_tvl_validate_reports_issues_not_a_python_error(tmp_path, monkeypatch, capsys):
    from tvl_tools.tvl_validate import cli

    module = tmp_path / "mixed.tvl.yml"
    module.write_text(yaml.safe_dump(_mixed_selector_module(), sort_keys=False))
    monkeypatch.setattr(sys, "argv", ["tvl-validate", str(module), "--json"])
    try:
        cli.main()
    except SystemExit:
        pass
    payload = json.loads(capsys.readouterr().out)
    assert "error" not in payload, payload
    assert "issues" in payload
