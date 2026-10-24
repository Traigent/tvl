"""Without OR-Tools the brute-force fallback must never claim UNSAT it did not prove."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvl import structural_sat  # noqa: E402
from tvl.structural_sat import check_structural  # noqa: E402
from tvl_tools.tvl_check_structural import cli  # noqa: E402

CODE = "structural_undecided_without_solver"


def _module(tvars, structural):
    return {"tvars": tvars, "constraints": {"structural": structural}}


FLOAT_SAT = _module(
    [{"name": "x", "type": "float", "domain": {"range": [0, 1], "resolution": 0.01}}],
    [{"expr": "x > 0.2"}, {"expr": "x < 0.3"}],
)
FINITE_UNSAT = _module(
    [{"name": "n", "type": "int", "domain": {"range": [0, 5]}}],
    [{"expr": "n >= 4"}, {"expr": "n = 3"}],
)
FINITE_SAT = _module(
    [{"name": "n", "type": "int", "domain": {"range": [0, 5]}}],
    [{"expr": "n = 3"}],
)
FLOAT_UNSAT = _module(
    [{"name": "x", "type": "float", "domain": {"range": [0, 1], "resolution": 0.01}}],
    [{"expr": "x > 0.5"}, {"expr": "x < 0.4"}],
)


@pytest.fixture(autouse=True)
def no_ortools(monkeypatch):
    monkeypatch.setattr(structural_sat, "cp_model", None)


def test_witness_found_is_sat():
    result = check_structural(FINITE_SAT)
    assert result.ok is True
    assert result.assignment == {"n": 3}
    assert not getattr(result, "undecided", False)


def test_finite_exhaustive_is_unsat():
    result = check_structural(FINITE_UNSAT)
    assert result.ok is False
    assert not getattr(result, "undecided", False)
    assert result.unsat_core


def test_float_non_exhaustive_is_undecided_not_unsat():
    # Satisfiable in reality (x = 0.22); the sampled search must not call it UNSAT.
    result = check_structural(FLOAT_SAT)
    assert result.ok is False
    assert result.undecided is True
    assert result.unsat_core is None
    assert [i["code"] for i in result.issues] == [CODE]
    assert result.issues[0]["severity"] == "error"
    assert "OR-Tools" in result.issues[0]["message"]


def test_float_domain_never_unsat_even_if_truly_unsat():
    result = check_structural(FLOAT_UNSAT)
    assert result.undecided is True
    assert result.unsat_core is None


def _run_cli(monkeypatch, capsys, tmp_path, module, as_json):
    import yaml

    path = tmp_path / "m.tvl.yml"
    path.write_text(yaml.safe_dump(module), encoding="utf-8")
    argv = ["tvl-check-structural", str(path)] + (["--json"] if as_json else [])
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(cli, "_load_module", lambda _p: module)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code, capsys.readouterr()


def test_cli_undecided_exits_error_json(monkeypatch, capsys, tmp_path):
    code, out = _run_cli(monkeypatch, capsys, tmp_path, FLOAT_SAT, True)
    assert code == 2
    payload = json.loads(out.out)
    assert payload["ok"] is False
    assert payload["status"] == "undecided"
    assert payload["issues"][0]["code"] == CODE


def test_cli_undecided_exits_error_text(monkeypatch, capsys, tmp_path):
    code, out = _run_cli(monkeypatch, capsys, tmp_path, FLOAT_SAT, False)
    assert code == 2
    assert CODE in out.err
    assert "UNSAT" not in out.out
