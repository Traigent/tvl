"""tvl-ci-gate refuses promotion under every strict-mode calibration trigger.

RFC 0001 section 3.6 defines the strict evidence mode; RFC 0002 section 5
extends it to calibrated composite members. The tools cannot validate
calibration certificates, so a module that needs them must be refused
(exit 2, ``calibration_evidence_unsupported``), never promoted.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from tvl.lints import lint_module
from tvl.measurement import _strict_calibration_triggers

from tvl_tools.tvl_ci_gate import cli as ci_gate_cli

ROOT = Path(__file__).resolve().parents[1]
BOOK = ROOT / "spec" / "examples" / "book"
BUNDLES = ROOT / "book" / "support-bot" / "bundles" / "slo-pass" / "seed-0"
INCUMBENT = BUNDLES / "incumbent.synthetic.measure.yml"
CANDIDATE = BUNDLES / "candidate.synthetic.measure.yml"
CODE = "calibration_evidence_unsupported"


def _load(relative: str) -> dict[str, Any]:
    return yaml.safe_load((BOOK / relative).read_text(encoding="utf-8"))


def _gate(
    module: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> tuple[int, dict[str, Any]]:
    module_path = tmp_path / "module.tvl.yml"
    module_path.write_text(yaml.safe_dump(module, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        ["tvl-ci-gate", str(module_path), str(INCUMBENT), str(CANDIDATE), "--json"],
    )
    with pytest.raises(SystemExit) as excinfo:
        ci_gate_cli.main()
    payload = json.loads(capsys.readouterr().out)
    return int(excinfo.value.code), payload


def _refused(payload: dict[str, Any]) -> bool:
    return CODE in {issue["code"] for issue in payload.get("readiness_issues", [])}


def _drop_explicit_enforcement(module: dict[str, Any]) -> None:
    module["promotion_policy"].pop("require_calibration", None)
    for cvar in module.get("cvars") or []:
        cvar.pop("governance", None)


@pytest.mark.parametrize("stage", ["ch07/support-bot.tvl.yml", "ch08/support-bot.tvl.yml"])
def test_chance_constraint_with_calibrated_cvar_is_refused_without_explicit_flag(
    stage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    module = _load(stage)
    _drop_explicit_enforcement(module)
    assert module["promotion_policy"]["chance_constraints"]

    code, payload = _gate(module, tmp_path, monkeypatch, capsys)

    assert code == 2
    assert _refused(payload)
    assert "chance_constraints" in _strict_calibration_triggers(module)


def test_composite_with_calibrated_members_is_refused_without_chance_or_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    module = _load("ch08/support-bot.tvl.yml")
    _drop_explicit_enforcement(module)
    module["promotion_policy"].pop("chance_constraints")
    # This used to `module.pop("cvars")` to leave the composite's gate threshold
    # as the only trigger. Issue #156 makes tvl-ci-gate lint every full module,
    # and a module without its cvars is lint-dirty (`missing_ref`), so the gate
    # now refuses it before the calibration check runs -- gate-level isolation
    # is no longer available. Keep the module lint-clean and pin the composite's
    # contribution differentially below instead.
    assert not [issue for issue in lint_module(module) if issue.get("severity") == "error"]

    code, payload = _gate(module, tmp_path, monkeypatch, capsys)

    assert code == 2
    assert _refused(payload)
    assert "composite_calibrated_member" in _strict_calibration_triggers(module)

    # The refusal above is over-determined: `certificate_backed_cvar` fires too,
    # and test_calibrated_cvar_alone_is_refused already covers that one. Without
    # this control the test would still pass if the composite rule were deleted.
    without_composites = copy.deepcopy(module)
    without_composites.pop("composites")
    assert not [
        issue for issue in lint_module(without_composites) if issue.get("severity") == "error"
    ]
    assert "composite_calibrated_member" not in _strict_calibration_triggers(without_composites)


def test_calibrated_cvar_alone_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    module = _load("ch07/support-bot.tvl.yml")
    _drop_explicit_enforcement(module)
    module["promotion_policy"].pop("chance_constraints")

    code, payload = _gate(module, tmp_path, monkeypatch, capsys)

    assert code == 2
    assert _refused(payload)
    assert "certificate_backed_cvar" in _strict_calibration_triggers(module)


def test_cvar_governance_flag_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    module = _load("ch07/support-bot.tvl.yml")
    _drop_explicit_enforcement(module)
    module["cvars"][0]["governance"] = {"require_calibration": True}

    code, payload = _gate(module, tmp_path, monkeypatch, capsys)

    assert code == 2
    assert _refused(payload)
    assert "cvar_governance" in _strict_calibration_triggers(module)


def test_explicit_policy_flag_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    module = _load("ch06/support-bot.tvl.yml")
    module["promotion_policy"]["require_calibration"] = {"enabled": True}

    code, payload = _gate(module, tmp_path, monkeypatch, capsys)

    assert code == 2
    assert _refused(payload)
    assert "require_calibration_enabled" in _strict_calibration_triggers(module)


def test_module_without_a_trigger_still_gets_a_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Control: chapter 6 has chance constraints but nothing to certify."""
    module = _load("ch06/support-bot.tvl.yml")
    assert module["promotion_policy"]["chance_constraints"]

    code, payload = _gate(module, tmp_path, monkeypatch, capsys)

    assert code == 0
    assert payload["decision"] == "Promote"
    assert not _refused(payload)
    assert not _strict_calibration_triggers(module)


def _no_cvar_module() -> dict[str, Any]:
    module = _load("ch06/support-bot.tvl.yml")
    module["composites"] = []
    return module


def test_judge_ensemble_without_calibrated_members_still_gets_a_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    module = _no_cvar_module()
    module["composites"] = [
        {
            "name": "panel",
            "kind": "ensemble",
            "arms": ["a", "b"],
            "aggregate": {"kind": "judge_max", "judge": "j"},
        }
    ]

    code, payload = _gate(module, tmp_path, monkeypatch, capsys)

    assert code == 0
    assert payload["decision"] == "Promote"
    assert not _strict_calibration_triggers(module)


def test_judge_referencing_a_gated_composite_is_refused() -> None:
    module = _load("ch08/support-bot.tvl.yml")
    module["composites"].append(
        {
            "name": "panel",
            "kind": "ensemble",
            "arms": ["a", "b"],
            "aggregate": {"kind": "judge_max", "judge": {"composite": "answerer"}},
        }
    )
    assert "composite_calibrated_member" in _strict_calibration_triggers(module)


def test_opaque_parameters_and_empty_gates_do_not_trigger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    module = _no_cvar_module()
    module["composites"] = [
        {
            "name": "single",
            "kind": "cascade",
            "arms": ["a"],
            "gates": [],
            "parameters": {"gates": ["routing"], "stop": {"kind": "signal_accept"}},
        }
    ]

    code, payload = _gate(module, tmp_path, monkeypatch, capsys)

    assert code == 0
    assert payload["decision"] == "Promote"
    assert not _strict_calibration_triggers(module)
