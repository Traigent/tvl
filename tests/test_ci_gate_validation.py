"""Every full module gets schema and lint checks before a gate decision."""

import copy
import json
import sys
from pathlib import Path

import pytest
import yaml

from tvl_tools.tvl_ci_gate import cli

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "spec/examples/rag-support-bot.tvl.yml"
INCUMBENT = ROOT / "spec/measurements/rag-support-bot.incumbent.measure.yml"
CANDIDATE = ROOT / "spec/measurements/rag-support-bot.candidate.measure.yml"


def _gate(path, legacy, monkeypatch, capsys):
    args = ["tvl-ci-gate", str(INCUMBENT), str(CANDIDATE), "--policy", str(path)] if legacy else ["tvl-ci-gate", str(path), str(INCUMBENT), str(CANDIDATE)]
    monkeypatch.setattr(sys, "argv", [*args, "--json"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("legacy", [False, True], ids=["canonical", "legacy-module"])
@pytest.mark.parametrize("defect,expected", [("threshold", "invalid_chance_threshold"), ("min_effect", "missing_min_effect"), ("undeclared", "undeclared_tvar"), ("unknown_key", None), ("missing_policy", None)])
def test_gate_rejects_invalid_full_module(defect, expected, legacy, tmp_path, monkeypatch, capsys):
    doc = yaml.safe_load(MODULE.read_text())
    if defect == "threshold":
        doc["promotion_policy"]["chance_constraints"][0]["threshold"] = 5
    elif defect == "min_effect":
        doc["promotion_policy"]["min_effect"].pop("quality")
    elif defect == "undeclared":
        doc["constraints"]["structural"] = [{"expr": "unknown = 1"}]
    elif defect == "missing_policy":
        doc.pop("promotion_policy")
        doc["unknown_key"] = True
    else:
        doc["unknown_key"] = True
    path = tmp_path / "module.yml"
    path.write_text(yaml.safe_dump(doc))
    status, payload = _gate(path, legacy, monkeypatch, capsys)
    assert status == 2
    assert payload["ok"] is False and payload.get("decision") != "Promote"
    if expected:
        assert expected in {i["code"] for i in payload["issues"]}


@pytest.mark.parametrize("legacy", [False, True])
def test_valid_full_module_still_promotes(legacy, monkeypatch, capsys):
    status, payload = _gate(MODULE, legacy, monkeypatch, capsys)
    assert status == 0 and payload["decision"] == "Promote"


def test_standalone_policy_keeps_legacy_behavior(tmp_path, monkeypatch, capsys):
    policy = copy.deepcopy(yaml.safe_load(MODULE.read_text())["promotion_policy"])
    policy["objectives"] = yaml.safe_load(MODULE.read_text())["objectives"]
    path = tmp_path / "policy.yml"
    path.write_text(yaml.safe_dump(policy))
    status, payload = _gate(path, True, monkeypatch, capsys)
    assert status == 0 and payload["decision"] == "Promote"
