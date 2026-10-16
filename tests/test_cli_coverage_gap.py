"""CLI-level exit-code/--json/error-path coverage for the shipped console
scripts that had none (#22).

Before this file, of the 10 `[project.scripts]` entries, `tvl-parse`,
`tvl-validate`, `tvl-measure-validate`, `tvl-microsim-bridge`, and
`tvl-check-operational` had zero tests exercising the CLI entry point itself
(argparse wiring, exit code, `--json`/`--format json` payload shape, error
path) — only their underlying library functions were unit-tested elsewhere,
or not at all. (`tvl-check-operational`'s only prior coverage,
`tests/test_operational.py`, calls the `check_operational()` library
function directly and never goes through `tvl_tools/tvl_check_operational/cli.py`.)
The other five (`tvl-lint`, `tvl-ci-gate`, `tvl-config-validate`,
`tvl-compose`, `tvl-check-structural`) already have CLI-level tests in
`test_cli_error_paths.py`, `test_lint_non_mapping.py`, `test_tvl_compose.py`,
`test_constraints_parser_fixes.py`, and `test_parser_dos_guards.py`.

This file closes the gap for the remaining five, at a smoke level: one
success path (exit 0, well-shaped `--json`/`--format json` output) and one
error path per CLI, documenting the exit code each actually returns today.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tvl_tools.tvl_parse import cli as parse_cli
from tvl_tools.tvl_validate import cli as validate_cli
from tvl_tools.tvl_measure_validate import cli as measure_validate_cli
from tvl_tools.microsim_bridge import cli as microsim_bridge_cli
from tvl_tools.tvl_check_operational import cli as check_operational_cli

REPO_ROOT = Path(__file__).resolve().parents[1]
MINIMAL_MODULE = REPO_ROOT / "conformance" / "cases" / "satisfiable" / "minimal.yml"
RAG_MODULE = REPO_ROOT / "spec" / "examples" / "rag-support-bot.tvl.yml"
RAG_CONFIG = REPO_ROOT / "spec" / "configurations" / "rag-support-bot.config.yml"
RAG_MEASUREMENT = REPO_ROOT / "spec" / "measurements" / "rag-support-bot.measure.yml"
OPERATIONAL_BUDGET_OK = (
    REPO_ROOT / "spec" / "examples" / "validation-phase3" / "budget-default.tvl.yml"
)
OPERATIONAL_DERIVED_VIOLATION = (
    REPO_ROOT / "spec" / "examples" / "validation-phase3" / "derived-violation.tvl.yml"
)


# --- tvl-parse --------------------------------------------------------------


def test_parse_cli_success_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr("sys.argv", ["tvl-parse", str(MINIMAL_MODULE), "--format", "json"])
    parse_cli.main()  # exits 0 implicitly (no SystemExit raised)
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "ast" in payload


def test_parse_cli_missing_file_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr("sys.argv", ["tvl-parse", "/tmp/does-not-exist-tvl-22.yml", "--format", "json"])
    with pytest.raises(SystemExit) as excinfo:
        parse_cli.main()
    assert excinfo.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "File not found" in payload["error"]


# --- tvl-validate -------------------------------------------------------------


def test_validate_cli_success_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr("sys.argv", ["tvl-validate", str(MINIMAL_MODULE), "--format", "json"])
    validate_cli.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["issues"] == []


def test_validate_cli_missing_file_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr("sys.argv", ["tvl-validate", "/tmp/does-not-exist-tvl-22.yml", "--format", "json"])
    with pytest.raises(SystemExit) as excinfo:
        validate_cli.main()
    assert excinfo.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False


# --- tvl-measure-validate ------------------------------------------------------


def test_measure_validate_cli_success_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "tvl-measure-validate",
            str(RAG_MODULE),
            str(RAG_CONFIG),
            str(RAG_MEASUREMENT),
            "--json",
        ],
    )
    measure_validate_cli.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["promotion_ready"] is True


def test_measure_validate_cli_missing_module_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "tvl-measure-validate",
            "/tmp/does-not-exist-tvl-22.yml",
            str(RAG_CONFIG),
            str(RAG_MEASUREMENT),
            "--json",
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        measure_validate_cli.main()
    assert excinfo.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False


# --- tvl-microsim-bridge --------------------------------------------------------


def test_microsim_bridge_cli_dry_run_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr("sys.argv", ["tvl-microsim-bridge", str(MINIMAL_MODULE), "--dry-run"])
    microsim_bridge_cli.main()  # returns None; no SystemExit on success
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == "1.0.0"
    assert "presets" in payload


def test_microsim_bridge_cli_missing_spec_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Documents current behaviour: unlike the other CLIs, tvl-microsim-bridge
    has no error handling around the spec load and lets FileNotFoundError
    propagate (uncaught-exception exit code 1) rather than exiting 2 with a
    diagnostic. Tracked as a follow-up, not fixed here (out of #22's scope,
    which is coverage, not CLI error-contract parity)."""
    monkeypatch.setattr(
        "sys.argv", ["tvl-microsim-bridge", "/tmp/does-not-exist-tvl-22.yml", "--dry-run"]
    )
    with pytest.raises(FileNotFoundError):
        microsim_bridge_cli.main()


# --- tvl-check-operational ----------------------------------------------------


def test_check_operational_cli_success_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(
        "sys.argv", ["tvl-check-operational", str(OPERATIONAL_BUDGET_OK), "--json"]
    )
    with pytest.raises(SystemExit) as excinfo:
        check_operational_cli.main()
    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["issues"] == []


def test_check_operational_cli_derived_violation_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["tvl-check-operational", str(OPERATIONAL_DERIVED_VIOLATION), "--json"],
    )
    with pytest.raises(SystemExit) as excinfo:
        check_operational_cli.main()
    assert excinfo.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    codes = {issue["code"] for issue in payload["issues"]}
    assert "derived_constraint_violation" in codes
