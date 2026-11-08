"""Regression: one arm as raw samples, the other as mean/std/n.

`_test_objective` took the sample path only when both arms carried samples and
otherwise read mean/std/n from each arm with defaults 0.0/0.0/0, so the arm
given as samples was read as an empty arm (n=0, mean=0.0). The objective was
always inconclusive and the evidence reported an incumbent that contradicted
the input. Spec 3.1: aggregated statistics are used when raw samples are not
available for both arms; the sample arm's n, mean and sample std are derived
from its samples.

See Traigent/tvl#262.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from tvl.promotion import ObjectiveSpec, _test_from_stats, _test_objective

REPO = Path(__file__).resolve().parents[1]

INC_SAMPLES = [0.70, 0.71, 0.69, 0.70, 0.72, 0.70]
CAND_STATS = {"mean": 0.82, "std": 0.04, "n": 200}


def _spec(direction: str = "maximize") -> ObjectiveSpec:
    return ObjectiveSpec(name="quality", direction=direction, epsilon=0.01)


def _stats_of(samples: list[float]) -> dict:
    n = len(samples)
    mean = sum(samples) / n
    std = math.sqrt(sum((x - mean) ** 2 for x in samples) / (n - 1))
    return {"mean": mean, "std": std, "n": n}


def test_sample_incumbent_with_stats_candidate_uses_the_samples():
    result = _test_objective(_spec(), {"samples": INC_SAMPLES}, dict(CAND_STATS))

    assert result.n_incumbent == 6
    assert result.mean_incumbent == pytest.approx(sum(INC_SAMPLES) / 6)
    assert result.delta == pytest.approx(0.82 - sum(INC_SAMPLES) / 6)
    assert result.df is not None
    assert result.p_value_super < 0.05


def test_stats_incumbent_with_sample_candidate_uses_the_samples():
    cand = [0.80, 0.83, 0.81, 0.82, 0.84, 0.82]
    result = _test_objective(_spec(), {"mean": 0.70, "std": 0.01, "n": 50}, {"samples": cand})

    assert result.n_candidate == 6
    assert result.mean_candidate == pytest.approx(sum(cand) / 6)
    assert result.df is not None


def test_mixed_arms_match_the_aggregated_stats_test_on_derived_stats():
    mixed = _test_objective(_spec("minimize"), {"samples": INC_SAMPLES}, dict(CAND_STATS))
    oracle = _test_from_stats(_spec("minimize"), _stats_of(INC_SAMPLES), dict(CAND_STATS))

    for field in ("n_incumbent", "n_candidate", "mean_incumbent", "mean_candidate", "delta",
                  "t_statistic", "df", "p_value_noninf", "p_value_super", "p_value_inferior"):
        assert getattr(mixed, field) == pytest.approx(getattr(oracle, field), rel=1e-12), field


def test_mixed_single_sample_arm_is_inconclusive_with_its_real_value():
    result = _test_objective(_spec(), {"samples": [0.7]}, dict(CAND_STATS))

    assert result.verdict == "inconclusive"
    assert result.n_incumbent == 1
    assert result.mean_incumbent == 0.7


def test_ci_gate_reports_the_sample_arm_from_its_samples(tmp_path: Path):
    """The issue's reproduction, end to end through tvl-ci-gate."""
    inc = {
        "module_id": "corp.support.rag_bot",
        "objective_values": {
            "quality": {"samples": INC_SAMPLES},
            "latency_p95_ms": {"samples": [1500, 1510, 1490, 1505, 1495, 1500]},
        },
        "chance_outcomes": {"latency_slo": {"violations": 0, "trials": 100}},
    }
    cand = {
        "module_id": "corp.support.rag_bot",
        "objective_values": {
            "quality": dict(CAND_STATS),
            "latency_p95_ms": {"mean": 1300, "std": 85, "n": 40},
        },
        "chance_outcomes": {"latency_slo": {"violations": 0, "trials": 100}},
    }
    (tmp_path / "inc.yml").write_text(yaml.safe_dump(inc), encoding="utf-8")
    (tmp_path / "cand.yml").write_text(yaml.safe_dump(cand), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "tvl_tools.tvl_ci_gate.cli",
         str(REPO / "spec/examples/rag-support-bot.tvl.yml"),
         str(tmp_path / "inc.yml"), str(tmp_path / "cand.yml"), "--json"],
        capture_output=True, text=True, cwd=REPO, check=False,
    )
    out = json.loads(proc.stdout)
    per = out["evidence"]["per_objective"]
    assert per["quality"]["n_incumbent"] == 6
    assert per["quality"]["mean_incumbent"] == pytest.approx(sum(INC_SAMPLES) / 6)
    assert per["latency_p95_ms"]["n_incumbent"] == 6
    assert per["latency_p95_ms"]["mean_incumbent"] == pytest.approx(1500.0)
    assert out["decision"] == "Promote"
    assert proc.returncode == 0


HIGH_INC = [0.95, 0.96, 0.95, 0.96, 0.95, 0.96]


def _gate(tmp_path: Path, inc_quality: dict) -> tuple[dict, int]:
    inc = {
        "module_id": "corp.support.rag_bot",
        "objective_values": {
            "quality": inc_quality,
            "latency_p95_ms": {"samples": [1500, 1510, 1490, 1505, 1495, 1500]},
        },
        "chance_outcomes": {"latency_slo": {"violations": 0, "trials": 100}},
    }
    cand = {
        "module_id": "corp.support.rag_bot",
        "objective_values": {
            "quality": dict(CAND_STATS),
            "latency_p95_ms": {"mean": 1300, "std": 85, "n": 40},
        },
        "chance_outcomes": {"latency_slo": {"violations": 0, "trials": 100}},
    }
    (tmp_path / "inc.yml").write_text(yaml.safe_dump(inc), encoding="utf-8")
    (tmp_path / "cand.yml").write_text(yaml.safe_dump(cand), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "tvl_tools.tvl_ci_gate.cli",
         str(REPO / "spec/examples/rag-support-bot.tvl.yml"),
         str(tmp_path / "inc.yml"), str(tmp_path / "cand.yml"), "--json"],
        capture_output=True, text=True, cwd=REPO, check=False,
    )
    return json.loads(proc.stdout), proc.returncode


@pytest.mark.parametrize(
    "inc_quality",
    [
        {"samples": HIGH_INC, "n": 6},
        {"samples": HIGH_INC, "mean": 0.0, "std": 1.0, "n": 6},
        _stats_of(HIGH_INC),  # control: the same incumbent given as statistics
    ],
    ids=["samples-plus-n", "samples-plus-contradicting-stats", "stats-control"],
)
def test_ci_gate_reads_a_sample_arm_with_stated_stats_from_its_samples(tmp_path: Path, inc_quality: dict):
    # A samples arm that also states n kept mean 0.0 and promoted a regression (tvl#262).
    out, code = _gate(tmp_path, inc_quality)
    quality = out["evidence"]["per_objective"]["quality"]
    assert quality["mean_incumbent"] == pytest.approx(sum(HIGH_INC) / 6)
    assert quality["n_incumbent"] == 6
    assert out["decision"] == "Reject"
    assert code == 2


@pytest.mark.parametrize("missing", ["mean", "std", "n"])
def test_an_arm_with_incomplete_stats_is_missing_evidence_not_zero(missing: str):
    from tvl.promotion import epsilon_pareto_gate

    inc_stats = {key: value for key, value in _stats_of(HIGH_INC).items() if key != missing}
    decision, evidence = epsilon_pareto_gate(
        {"objective_values": {"quality": inc_stats}},
        {"objective_values": {"quality": dict(CAND_STATS)}},
        {"alpha": 0.05, "min_effect": {"quality": 0.01}},
        [{"name": "quality", "direction": "maximize"}],
    )
    quality = evidence["per_objective"]["quality"]
    assert decision == "NoDecision"
    assert quality["verdict"] == "inconclusive"
    assert quality["code"] == "missing_statistical_evidence"
    if missing == "mean":
        assert quality["mean_incumbent"] is None
    assert evidence["summary"]["decision_reason"].startswith("missing_statistical_evidence")
