"""All shipped console entry points fail cleanly on unreadable YAML input."""

import importlib
import json
import sys
import tomllib
from pathlib import Path

import pytest

from tvl_tools.tvl_check_structural import cli as structural

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
ARGS = {
    "tvl-parse": [], "tvl-lint": [], "tvl-validate": [],
    "tvl-ci-gate": ["unused-incumbent.yml", "unused-candidate.yml"],
    "tvl-config-validate": ["unused-config.yml"],
    "tvl-measure-validate": ["unused-config.yml", "unused-measurement.yml"],
    "tvl-check-structural": [], "tvl-check-operational": [], "tvl-compose": [],
    "tvl-microsim-bridge": ["--dry-run"], "tvl-compile-runtime": ["--emit-token-map-template"],
}


def test_input_error_table_covers_all_console_scripts():
    assert ARGS.keys() == SCRIPTS.keys()


@pytest.mark.parametrize("script", sorted(SCRIPTS))
@pytest.mark.parametrize("defect", ["missing", "malformed"])
def test_console_input_error_is_defined_exit_without_traceback(script, defect, tmp_path, monkeypatch, capsys):
    path = tmp_path / "input.yml"
    if defect == "malformed":
        path.write_text("key: [1\n")
    module, function = SCRIPTS[script].split(":")
    monkeypatch.setattr(sys, "argv", [script, str(path), *ARGS[script]])
    with pytest.raises(SystemExit) as exc:
        getattr(importlib.import_module(module), function)()
    assert exc.value.code == (5 if script == "tvl-config-validate" else 2)
    output = capsys.readouterr()
    assert output.out or output.err
    assert "Traceback" not in output.out + output.err


@pytest.mark.parametrize("defect", ["missing-candidate", "malformed-candidate", "nonmapping-candidate", "missing-module"])
@pytest.mark.parametrize("json_mode", [False, True], ids=["text", "json"])
def test_structural_candidate_input_errors(defect, json_mode, tmp_path, monkeypatch, capsys):
    module = ROOT / "conformance/cases/satisfiable/minimal.yml"
    candidate = tmp_path / "candidate.json"
    if defect == "malformed-candidate":
        candidate.write_text("{bad")
    elif defect == "nonmapping-candidate":
        candidate.write_text("[]")
    elif defect == "missing-module":
        module = tmp_path / "missing.yml"
        candidate.write_text('{"edits": []}')
    args = ["tvl-check-structural", str(module), "--candidate-file", str(candidate)]
    monkeypatch.setattr(sys, "argv", args + (["--json"] if json_mode else []))
    with pytest.raises(SystemExit) as exc:
        structural.main()
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert "Traceback" not in output.out + output.err
    if json_mode:
        payload = json.loads(output.out)
        assert payload["ok"] is False and payload["kind"] == "PhaseResult"
        assert payload["status"] == "error" and payload["phase"] == "structural"
    else:
        assert "Error loading" in output.err
