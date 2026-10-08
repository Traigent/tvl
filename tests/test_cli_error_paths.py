"""Regression tests for CLI validation/error behavior.

Covers:
- #54: `tvl-compose --validate` must actually validate (and fail non-zero on
  an invalid composed module) even when no `-o/--output` is given.
- #56: `tvl-config-validate` must emit text (not raw JSON) on a TVLError in
  text mode, consistent with its success path and cli_utils.handle_error.
- #20: `tvl-check-structural` and `tvl-check-operational` must exit 2 (not 1)
  and emit a structured diagnostic (JSON under --json, text on stderr
  otherwise) on a missing/malformed module file, never a raw traceback.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tvl_tools.tvl_compose import cli as compose_cli
from tvl_tools.tvl_config_validate import cli as config_validate_cli
from tvl_tools.tvl_ci_gate import cli as ci_gate_cli
from tvl_tools.tvl_check_structural import cli as check_structural_cli
from tvl_tools.tvl_check_operational import cli as check_operational_cli


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_ci_gate_fails_closed_when_strict_calibration_evidence_is_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "spec"
        / "examples"
        / "validation-phase6-cvars"
        / "cvar-policies-happy.tvl.yml"
    )
    incumbent_path = tmp_path / "incumbent.yml"
    candidate_path = tmp_path / "candidate.yml"
    for path, mean in ((incumbent_path, 0.80), (candidate_path, 0.90)):
        _write_yaml(
            path,
            {
                "module_id": "corp.validation.cvars_happy",
                "objective_values": {
                    "quality": {"mean": mean, "std": 0.04, "n": 100},
                },
            },
        )

    monkeypatch.setattr(
        "sys.argv",
        [
            "tvl-ci-gate",
            str(module_path),
            str(incumbent_path),
            str(candidate_path),
            "--json",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        ci_gate_cli.main()

    assert excinfo.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "calibration_evidence_unsupported" in {
        issue["code"] for issue in payload["readiness_issues"]
    }


def test_compose_validate_without_output_fails_on_invalid_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """#54: `--validate` (no -o) validates and exits non-zero on an invalid spec."""
    base_path = tmp_path / "base.tvl.yml"
    overlay_path = tmp_path / "staging.overlay.yml"

    # Base is missing required TVL structure (no `tvl`/`tvars`/etc.) so the
    # composed module fails schema/lint validation.
    _write_yaml(base_path, {"not_a_real_field": True})
    _write_yaml(
        overlay_path,
        {
            "_tvl_overlay": {"extends": "base.tvl.yml"},
            "overrides": {},
        },
    )

    monkeypatch.setattr(
        "sys.argv",
        ["tvl-compose", str(overlay_path), "--no-validate", "--validate"],
    )

    with pytest.raises(SystemExit) as excinfo:
        compose_cli.main()

    # Validation ran and surfaced a failure with a non-zero exit code even
    # though no -o/--output was provided.
    assert excinfo.value.code != 0
    err = capsys.readouterr().err
    assert "Validation failed" in err


def test_compose_validate_without_output_passes_on_valid_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#54: a valid composed module still exits 0 under `--validate` without -o."""
    base_path = tmp_path / "base.tvl.yml"
    overlay_path = tmp_path / "prod.overlay.yml"

    _write_yaml(
        base_path,
        {
            "tvl": {"module": "demo.compose"},
            "environment": {"snapshot_id": "2025-01-20T00:00:00Z"},
            "evaluation_set": {"dataset": "s3://datasets/demo.jsonl"},
            "tvars": [
                {
                    "name": "temperature",
                    "type": "float",
                    "domain": {"range": [0.0, 1.0], "resolution": 0.05},
                }
            ],
            "constraints": {"structural": [], "derived": []},
            "objectives": [{"name": "quality", "direction": "maximize"}],
            "promotion_policy": {
                "dominance": "epsilon_pareto",
                "alpha": 0.05,
                "min_effect": {"quality": 0.01},
            },
        },
    )
    _write_yaml(
        overlay_path,
        {"_tvl_overlay": {"extends": "base.tvl.yml"}, "overrides": {}},
    )

    monkeypatch.setattr(
        "sys.argv", ["tvl-compose", str(overlay_path), "--validate"]
    )

    # Valid module: main() completes without raising SystemExit(non-zero).
    compose_cli.main()


def test_config_validate_tvlerror_text_mode_is_not_raw_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """#56: a TVLError in text mode prints `Error: ...` to stderr, not JSON."""
    # A nonexistent/invalid module path triggers a TVLError from the loader.
    missing_module = tmp_path / "does_not_exist.tvl.yml"
    config_file = tmp_path / "config.yml"
    _write_yaml(config_file, {"assignments": {}})

    monkeypatch.setattr(
        "sys.argv",
        ["tvl-config-validate", str(missing_module), str(config_file)],
    )

    with pytest.raises(SystemExit) as excinfo:
        config_validate_cli.main()

    assert excinfo.value.code == 5
    captured = capsys.readouterr()
    # Text mode: error goes to stderr as plain text, not raw JSON on stdout.
    assert captured.out.strip() == ""
    assert captured.err.startswith("Error:")
    with pytest.raises(json.JSONDecodeError):
        json.loads(captured.err.strip())


@pytest.mark.parametrize(
    "cli_module",
    [check_structural_cli, check_operational_cli],
    ids=["tvl-check-structural", "tvl-check-operational"],
)
def test_check_cli_missing_file_json_exits_2_with_structured_payload(
    cli_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """#20: a missing module file exits 2 with a JSON error payload, never a
    raw traceback / exit 1 (regression: tvl-check-operational had zero
    exception handling around `load()`)."""
    missing = tmp_path / "does_not_exist.tvl.yml"

    monkeypatch.setattr("sys.argv", [cli_module.__name__, str(missing), "--json"])

    with pytest.raises(SystemExit) as excinfo:
        cli_module.main()

    assert excinfo.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "No such file" in payload["error"] or "not exist" in payload["error"].lower()


@pytest.mark.parametrize(
    "cli_module",
    [check_structural_cli, check_operational_cli],
    ids=["tvl-check-structural", "tvl-check-operational"],
)
def test_check_cli_malformed_yaml_exits_2_no_traceback(
    cli_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """#20: malformed YAML exits 2 with a text error on stderr, not a raw
    traceback, when --json is not passed."""
    malformed = tmp_path / "malformed.tvl.yml"
    malformed.write_text("a: [1,2\n", encoding="utf-8")

    monkeypatch.setattr("sys.argv", [cli_module.__name__, str(malformed)])

    with pytest.raises(SystemExit) as excinfo:
        cli_module.main()

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("Error")
    assert "Traceback" not in captured.err
