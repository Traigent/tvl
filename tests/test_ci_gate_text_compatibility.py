"""Legacy text stays stable while 1.3 explanations remain complete and closed."""

import json
import sys
from pathlib import Path

import pytest

from tvl_tools.tvl_ci_gate import cli


@pytest.mark.parametrize("module", [{"tvl_version": "1.2"}, {"tvl_version": "1.3"},
                                    {"tvl_version": "1.3", "requirements": []}])
@pytest.mark.parametrize("decision,reason,closed_reason", [
    ("Promote", "All non-inferiority tests pass; superior on: quality, accuracy",
     "All non-inferiority tests pass; at least one objective is superior"),
    ("Reject", "Promotion monitors breached: response_quality", "Promotion monitors breached"),
    ("NoDecision", "Promotion monitors inconclusive: latency_gate", "Promotion monitors inconclusive"),
    ("Reject", "Regression beyond the allowed margin demonstrated on: quality",
     "Regression beyond the allowed margin demonstrated"),
    ("NoDecision", "Non-inferiority not established on: quality", "Non-inferiority not established"),
    ("NoDecision", "All objectives non-inferior but no superiority demonstrated",
     "All objectives non-inferior but no superiority demonstrated"),
])
def test_reason_rendering_preserves_legacy_text_and_complete_13_explanation(
    monkeypatch, capsys, module, decision, reason, closed_reason,
):
    monkeypatch.setattr(sys, "argv", ["tvl-ci-gate", "module.yml", "incumbent.yml", "candidate.yml"])
    monkeypatch.setattr(cli, "_load_module_and_inputs", lambda *_: (module, {}, [], "incumbent.yml", "candidate.yml"))
    monkeypatch.setattr(cli, "lint_module", lambda _: [])
    monkeypatch.setattr(cli, "load_measurement", lambda _: {})
    monkeypatch.setattr(cli, "prepare_measurement_bundle", lambda *_, **__: ({}, [], []))
    summary = {"decision_reason": reason}
    monkeypatch.setattr(cli, "epsilon_pareto_gate", lambda **_: (decision, {"summary": summary}))
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == (0 if decision == "Promote" else 2)
    rendered_reason = closed_reason if "requirements" in module else reason
    assert capsys.readouterr().out == (
        f"Decision: {decision}\nReason: {rendered_reason}\n== Evidence Summary ==\n"
        + json.dumps(summary, indent=2) + "\n"
    )


def test_core_module_text_reason_comes_from_evidence_summary(monkeypatch, capsys):
    """Issue #138: a module without runtime blocks prints the summary's decision_reason."""
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(sys, "argv", [
        "tvl-ci-gate",
        str(root / "spec/examples/rag-support-bot.tvl.yml"),
        str(root / "spec/measurements/rag-support-bot.candidate.measure.yml"),
        str(root / "spec/measurements/rag-support-bot.incumbent.measure.yml"),
    ])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    out = capsys.readouterr().out
    reason_line = next(line for line in out.splitlines() if line.startswith("Reason:"))
    assert reason_line == (
        "Reason: Regression beyond the allowed margin demonstrated on: quality, latency_p95_ms"
    )
