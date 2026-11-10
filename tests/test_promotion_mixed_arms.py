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
        _stats_of(HIGH_INC),  # control: the same incumbent given as statistics
    ],
    ids=["samples-plus-n", "stats-control"],
)
def test_ci_gate_reads_a_sample_arm_with_stated_n_from_its_samples(tmp_path: Path, inc_quality: dict):
    # A samples arm that also states n kept mean 0.0 and promoted a regression (tvl#262).
    out, code = _gate(tmp_path, inc_quality)
    quality = out["evidence"]["per_objective"]["quality"]
    assert quality["mean_incumbent"] == pytest.approx(sum(HIGH_INC) / 6)
    assert quality["n_incumbent"] == 6
    assert out["decision"] == "Reject"
    assert code == 2


def test_ci_gate_stated_mean_contradicting_the_samples_is_no_decision(tmp_path: Path):
    # A stated mean that the samples do not produce (0.0 against samples averaging 0.955) must not
    # decide the objective: it promoted before the tvl#262 contradiction rule.
    out, code = _gate(tmp_path, {"samples": HIGH_INC, "mean": 0.0, "std": 1.0, "n": 6})
    quality = out["evidence"]["per_objective"]["quality"]
    assert quality["code"] == "missing_statistical_evidence"
    assert out["decision"] == "NoDecision"
    assert code != 0


def _gate_api(inc_quality: dict, cand_quality: dict):
    from tvl.promotion import epsilon_pareto_gate

    return epsilon_pareto_gate(
        {"objective_values": {"quality": inc_quality}},
        {"objective_values": {"quality": cand_quality}},
        {"alpha": 0.05, "min_effect": {"quality": 0.01}},
        [{"name": "quality", "direction": "maximize"}],
    )


def test_stated_mean_contradicting_the_samples_is_no_decision_in_a_mixed_pair():
    # The incumbent states mean 0.80 beside samples averaging 0.703. The contradiction leaves
    # the objective undecided, and the evidence reports the mean the samples give, not 0.80.
    inc = {"samples": INC_SAMPLES, "mean": 0.80, "std": 0.04, "n": 6}
    decision, evidence = _gate_api(inc, dict(CAND_STATS))

    quality = evidence["per_objective"]["quality"]
    assert decision == "NoDecision"
    assert quality["code"] == "missing_statistical_evidence"
    assert quality["mean_incumbent"] == pytest.approx(sum(INC_SAMPLES) / 6)
    assert quality["n_incumbent"] == 6


def test_original_262_repro_promotes_with_the_real_incumbent_n():
    decision, evidence = _gate_api({"samples": INC_SAMPLES}, dict(CAND_STATS))

    quality = evidence["per_objective"]["quality"]
    assert decision == "Promote"
    assert quality["n_incumbent"] == 6
    assert quality["mean_incumbent"] == pytest.approx(sum(INC_SAMPLES) / 6)


def test_samples_plus_n_only_derive_mean_and_std_from_the_samples():
    result = _test_objective(_spec(), {"samples": HIGH_INC, "n": 6}, dict(CAND_STATS))

    assert result.n_incumbent == 6
    assert result.mean_incumbent == pytest.approx(sum(HIGH_INC) / 6)
    expected_std = _stats_of(HIGH_INC)["std"]
    assert result.std_pooled == pytest.approx(math.sqrt((expected_std ** 2 + 0.04 ** 2) / 2), rel=1e-12)


def test_samples_plus_std_only_derive_n_and_mean_and_use_the_sample_std():
    # The samples are authoritative: the pooled std comes from the samples' ddof=1 std, and
    # a consistent stated std is only a cross-check, never the value the test uses.
    derived_std = _stats_of(HIGH_INC)["std"]
    stated_std = round(derived_std, 4)
    result = _test_objective(_spec(), {"samples": HIGH_INC, "std": stated_std}, dict(CAND_STATS))

    assert result.n_incumbent == 6
    assert result.mean_incumbent == pytest.approx(sum(HIGH_INC) / 6)
    assert result.std_pooled == pytest.approx(math.sqrt((derived_std ** 2 + 0.04 ** 2) / 2), rel=1e-12)


def test_empty_samples_with_full_stats_use_the_stated_stats_beside_a_sample_candidate():
    # An empty samples list is no samples: the incumbent's stated stats are used, not an n=0 arm.
    cand = [0.80, 0.83, 0.81, 0.82, 0.84, 0.82]
    decision, evidence = _gate_api({"samples": [], "mean": 0.70, "std": 0.01, "n": 6}, {"samples": cand})

    quality = evidence["per_objective"]["quality"]
    assert decision == "Promote"
    assert quality["n_incumbent"] == 6
    assert quality["mean_incumbent"] == pytest.approx(0.70)
    assert "code" not in quality


@pytest.mark.parametrize("inc_quality", [{}, {"samples": []}], ids=["no-samples-no-stats", "empty-samples-no-stats"])
def test_an_arm_with_no_samples_and_no_stats_is_missing_evidence_not_zero(inc_quality: dict):
    decision, evidence = _gate_api(inc_quality, dict(CAND_STATS))

    quality = evidence["per_objective"]["quality"]
    assert decision == "NoDecision"
    assert quality["code"] == "missing_statistical_evidence"
    assert quality["mean_incumbent"] is None


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


CAND8 = [0.80, 0.83, 0.81, 0.82, 0.84, 0.82, 0.81, 0.83]
LOW8 = [0.60, 0.63, 0.61, 0.62, 0.64, 0.62, 0.61, 0.63]


def _gate_cli(tmp_path: Path, inc_quality: dict, cand_quality: dict) -> tuple[dict, int]:
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
            "quality": cand_quality,
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


def test_stated_n_contradicting_the_samples_is_no_decision_through_ci_gate(tmp_path: Path):
    # tvl#262 follow-up: 8 samples with a stated n of 100000 promoted (exit 0) before the fix.
    out, code = _gate_cli(tmp_path, _stats_of(INC_SAMPLES), {"samples": CAND8, "n": 100000})
    quality = out["evidence"]["per_objective"]["quality"]
    assert out["decision"] == "NoDecision"
    assert quality["code"] == "missing_statistical_evidence"
    assert "disagree with the samples" in out["evidence"]["summary"]["decision_reason"]
    assert code != 0


@pytest.mark.parametrize(
    "contradiction",
    [{"n": 100000}, {"mean": 0.5}, {"std": 5.0}, {"n": 100000, "mean": 0.5}],
    ids=["n", "mean", "std", "n-and-mean"],
)
def test_conflict_evidence_reports_the_sample_arms_n_and_mean(contradiction: dict):
    # The conflict result must not show the stated, contradicting values as the arm's n and mean.
    decision, evidence = _gate_api(_stats_of(INC_SAMPLES), {"samples": CAND8, **contradiction})

    quality = evidence["per_objective"]["quality"]
    assert decision == "NoDecision"
    assert quality["code"] == "missing_statistical_evidence"
    assert quality["n_candidate"] == 8
    assert quality["mean_candidate"] == pytest.approx(sum(CAND8) / 8)
    assert quality["delta"] == pytest.approx(sum(CAND8) / 8 - _stats_of(INC_SAMPLES)["mean"])


@pytest.mark.parametrize("side", ["candidate", "incumbent"])
@pytest.mark.parametrize(
    "contradiction",
    [{"n": 100000}, {"mean": 0.5}, {"std": 5.0}],
    ids=["n", "mean", "std"],
)
def test_stated_statistics_contradicting_the_samples_are_no_decision(side: str, contradiction: dict):
    arm = {"samples": CAND8, **contradiction}
    if side == "candidate":
        decision, evidence = _gate_api(_stats_of(INC_SAMPLES), arm)
    else:
        decision, evidence = _gate_api(arm, dict(CAND_STATS))

    quality = evidence["per_objective"]["quality"]
    assert decision == "NoDecision"
    assert quality["code"] == "missing_statistical_evidence"
    assert quality["verdict"] == "inconclusive"
    assert "disagree with the samples" in evidence["summary"]["decision_reason"]


@pytest.mark.parametrize(
    "stated",
    [{"n": 8}, _stats_of(CAND8)],
    ids=["n-equal-to-samples", "full-stats-from-samples"],
)
def test_consistent_stated_statistics_still_promote(stated: dict):
    decision, evidence = _gate_api(_stats_of(INC_SAMPLES), {"samples": CAND8, **stated})

    quality = evidence["per_objective"]["quality"]
    assert decision == "Promote"
    assert "code" not in quality
    assert quality["n_candidate"] == 8


def test_consistent_stated_statistics_still_reject():
    decision, evidence = _gate_api(_stats_of(INC_SAMPLES), {"samples": LOW8, "n": 8})

    assert decision == "Reject"
    assert "code" not in evidence["per_objective"]["quality"]


# Mean 0.7032917 (sum 4.21975 over six samples).
SAMPLE_703 = [0.70, 0.71, 0.69, 0.70, 0.72, 0.69975]


def _sample_std(samples: list[float], ddof: int) -> float:
    n = len(samples)
    mean = sum(samples) / n
    return math.sqrt(sum((x - mean) ** 2 for x in samples) / (n - ddof))


@pytest.mark.parametrize(
    "stated",
    [
        {"n": 6, "mean": 0.703},  # mean written to three places; |diff| = 2.9e-4 <= 5e-4
        {"n": 6, "std": round(_sample_std(SAMPLE_703, 1), 4)},  # std written to four places
        {"n": 6, "mean": 0.703, "std": round(_sample_std(SAMPLE_703, 1), 4)},
    ],
    ids=["mean-3-places", "std-4-places", "mean-and-std"],
)
def test_consistent_written_precision_statistics_decide_as_the_samples_alone(stated: dict):
    # The stated values agree with the samples to the precision they are written with, so
    # they are accepted, and the test runs on the sample mean and std, not on the stated ones.
    result = _test_objective(_spec(), {"samples": SAMPLE_703, **stated}, dict(CAND_STATS))
    samples_only = _test_objective(_spec(), {"samples": SAMPLE_703}, dict(CAND_STATS))

    assert result.verdict == samples_only.verdict
    assert result.n_incumbent == 6
    assert result.mean_incumbent == pytest.approx(sum(SAMPLE_703) / 6, rel=1e-12)
    assert result.std_pooled == pytest.approx(samples_only.std_pooled, rel=1e-12)
    for field in ("t_statistic", "df", "p_value_noninf", "p_value_super", "p_value_inferior"):
        assert getattr(result, field) == pytest.approx(getattr(samples_only, field), rel=1e-12), field


def test_stated_population_std_is_accepted_and_the_sample_std_is_used():
    # A std written to four places that equals the ddof=0 population std is consistent. The test
    # still uses the ddof=1 std of the samples: the stated value does not reach the p-values.
    pop_std = round(_sample_std(SAMPLE_703, 0), 4)
    sample_std = _sample_std(SAMPLE_703, 1)
    assert pop_std != pytest.approx(sample_std, rel=1e-3)

    decision, evidence = _gate_api({"samples": SAMPLE_703, "std": pop_std, "n": 6}, dict(CAND_STATS))
    samples_only_decision, samples_only = _gate_api({"samples": SAMPLE_703}, dict(CAND_STATS))

    quality = evidence["per_objective"]["quality"]
    assert "code" not in quality
    assert decision == samples_only_decision
    assert quality["p_value_super"] == pytest.approx(samples_only["per_objective"]["quality"]["p_value_super"], rel=1e-12)
    assert quality["p_value_noninf"] == pytest.approx(
        samples_only["per_objective"]["quality"]["p_value_noninf"], rel=1e-12
    )
    assert quality["std_pooled"] == pytest.approx(
        math.sqrt((sample_std ** 2 + 0.04 ** 2) / 2), rel=1e-12
    )


@pytest.mark.parametrize(
    "contradiction",
    [
        {"mean": 0.80},  # about 14% away from the sample mean
        {"std": 2.0 * _sample_std(SAMPLE_703, 1)},  # twice the sample std
        {"n": 100000},
    ],
    ids=["mean-0.80", "std-doubled", "n-100000"],
)
def test_contradictions_against_rounded_samples_stay_no_decision(contradiction: dict):
    arm = {"samples": SAMPLE_703, **contradiction}
    decision, evidence = _gate_api(arm, dict(CAND_STATS))

    quality = evidence["per_objective"]["quality"]
    assert decision == "NoDecision"
    assert quality["code"] == "missing_statistical_evidence"
    assert "disagree with the samples" in evidence["summary"]["decision_reason"]


# The samples are authoritative. A stated mean, std or n on an arm with samples is a consistency
# cross-check only: it must agree with the samples to the precision it is written with, and the
# test never reads the stated value (tvl#262).

COST8 = [0.00120, 0.00125, 0.00123, 0.00124, 0.00122, 0.00123, 0.00124, 0.00127]  # mean 0.001235
COST_CAND = {"mean": 0.0010, "std": 0.00002, "n": 50}
C30 = [0.701 + 0.004 * ((i % 5) - 2) for i in range(30)]


def _gate_objective(inc_quality: dict, cand_quality: dict, direction: str, min_effect: float):
    from tvl.promotion import epsilon_pareto_gate

    return epsilon_pareto_gate(
        {"objective_values": {"quality": inc_quality}},
        {"objective_values": {"quality": cand_quality}},
        {"alpha": 0.05, "min_effect": {"quality": min_effect}},
        [{"name": "quality", "direction": direction}],
    )


def test_cost_mean_written_to_four_places_is_consistent_and_decides_as_the_samples_alone():
    # The sample mean is 0.001235. Stated 0.0012 is that mean written to four places:
    # |diff| = 3.5e-5 <= 0.5 * 10**-4. The result equals the one with no stated mean.
    stated_decision, stated_ev = _gate_objective({"samples": COST8, "mean": 0.0012}, COST_CAND, "minimize", 0.0)
    alone_decision, alone_ev = _gate_objective({"samples": COST8}, COST_CAND, "minimize", 0.0)
    quality = stated_ev["per_objective"]["quality"]
    alone = alone_ev["per_objective"]["quality"]

    assert "code" not in quality
    assert stated_decision == alone_decision
    assert quality["mean_incumbent"] == pytest.approx(0.001235, rel=1e-12)
    for field in ("t_statistic", "df", "std_pooled", "p_value_noninf", "p_value_super", "p_value_inferior"):
        assert quality[field] == pytest.approx(alone[field], rel=1e-12), field


def test_stated_mean_0_99_percent_off_the_sample_mean_is_no_decision():
    # 1.0099 times the sample mean is 0.99% away. Written in full, that is far finer than the
    # stated precision allows, so the stated mean contradicts the samples.
    s = _stats_of(C30)
    decision, evidence = _gate_api(
        {"mean": 0.70, "std": 0.01, "n": 30},
        {"samples": C30, "mean": s["mean"] * 1.0099},
    )

    quality = evidence["per_objective"]["quality"]
    assert decision == "NoDecision"
    assert quality["code"] == "missing_statistical_evidence"
    assert "disagree with the samples" in evidence["summary"]["decision_reason"]


def test_stated_mean_exactly_half_a_unit_away_is_consistent():
    # The samples [1.5, 1.6] have mean 1.55. The stated 1.5 is written to one place, so the
    # half unit is 0.05 and the difference is exactly that.
    _decision, evidence = _gate_api({"samples": [1.5, 1.6], "mean": 1.5}, dict(CAND_STATS))

    assert "code" not in evidence["per_objective"]["quality"]


def test_stated_mean_just_over_half_a_unit_away_is_no_decision():
    # The samples [1.5, 1.6002] have mean 1.5501. The difference from 1.5 is 0.0501, just over 0.05.
    decision, evidence = _gate_api({"samples": [1.5, 1.6002], "mean": 1.5}, dict(CAND_STATS))

    quality = evidence["per_objective"]["quality"]
    assert decision == "NoDecision"
    assert quality["code"] == "missing_statistical_evidence"


@pytest.mark.parametrize("stated_mean", [float("nan"), float("inf"), True], ids=["nan", "inf", "bool"])
def test_non_finite_or_boolean_stated_mean_is_no_decision(stated_mean):
    # A boolean is not a statistic. For the sample mean 1.0, True would otherwise read as 1.0.
    decision, evidence = _gate_api({"samples": [1.0, 1.1, 0.9], "mean": stated_mean}, dict(CAND_STATS))

    quality = evidence["per_objective"]["quality"]
    assert decision == "NoDecision"
    assert quality["code"] == "missing_statistical_evidence"


def test_stats_only_pair_is_tested_on_the_stated_values():
    # An arm without samples is unchanged: its stated mean, std and n are the inputs.
    inc = {"mean": 0.70, "std": 0.01, "n": 50}
    cand = {"mean": 0.82, "std": 0.04, "n": 200}
    result = _test_objective(_spec(), dict(inc), dict(cand))
    oracle = _test_from_stats(_spec(), dict(inc), dict(cand))

    assert result.n_incumbent == 50
    assert result.mean_incumbent == 0.70
    assert result.p_value_super == pytest.approx(oracle.p_value_super, rel=1e-12)
    assert result.p_value_noninf == pytest.approx(oracle.p_value_noninf, rel=1e-12)


# Written precision is read from the value as stated, not from a float's repr (tvl#262).


def test_float32_stated_mean_and_std_agree_with_the_samples():
    # numpy writes a float32 with its shortest repr (0.701), but float() of it has 16 digits.
    np = pytest.importorskip("numpy")
    stated = {
        "samples": SAMPLE_703,
        "mean": np.float32(0.703),
        "std": np.float32(round(_sample_std(SAMPLE_703, 1), 4)),
        "n": 6,
    }
    decision, evidence = _gate_api(stated, dict(CAND_STATS))
    samples_only_decision, _ = _gate_api({"samples": SAMPLE_703}, dict(CAND_STATS))

    assert "code" not in evidence["per_objective"]["quality"]
    assert decision == samples_only_decision


@pytest.mark.parametrize(
    ("samples", "agrees"),
    [([0.5, 0.6, 0.7], True), ([0.2, 0.3, 0.4], False)],
    ids=["int-1-vs-sample-mean-0.6", "int-1-vs-sample-mean-0.3"],
)
def test_integer_stated_mean_has_an_allowance_of_half_a_unit(samples: list[float], agrees: bool):
    # An integer has no decimal places, so its allowance is 0.5. Before this, float(1) was read as
    # 1.0 (one place) and the allowance was 0.05.
    decision, evidence = _gate_api({"samples": samples, "mean": 1, "n": 3}, dict(CAND_STATS))

    quality = evidence["per_objective"]["quality"]
    if agrees:
        assert "code" not in quality
    else:
        assert decision == "NoDecision"
        assert quality["code"] == "missing_statistical_evidence"


@pytest.mark.parametrize("scale", [1.5e5, 2.5e6], ids=["scale-1.5e5", "scale-2.5e6"])
def test_full_precision_numpy_statistics_on_large_values_agree(scale: float):
    # np.mean and np.std are pairwise sums; the gate sums in order. The two differ by an ulp, which
    # is far larger than 1e-12 at this magnitude. Such a stated value is still the same statistic.
    np = pytest.importorskip("numpy")
    for seed in range(20):
        rng = np.random.default_rng(seed)
        samples = [float(x) for x in rng.normal(scale, 0.1 * scale, 30)]
        stated = {
            "samples": samples,
            "mean": float(np.mean(samples)),
            "std": float(np.std(samples, ddof=1)),
            "n": 30,
        }
        decision, evidence = _gate_api(stated, dict(CAND_STATS))
        samples_only_decision, _ = _gate_api({"samples": samples}, dict(CAND_STATS))

        assert "code" not in evidence["per_objective"]["quality"], f"seed {seed}"
        assert decision == samples_only_decision, f"seed {seed}"


def test_stated_value_too_large_for_a_float_is_no_decision_not_an_exception():
    decision, evidence = _gate_api({"samples": [1.0, 2.0], "mean": 10 ** 400}, dict(CAND_STATS))

    quality = evidence["per_objective"]["quality"]
    assert decision == "NoDecision"
    assert quality["code"] == "missing_statistical_evidence"


# A float subclass whose text is not a number is unparseable: it never agrees, and no exception
# escapes. Each value equals the sample mean (1.0), so only the text decides (tvl#262).


class _NaNText(float):
    def __str__(self):
        return "NaN"


class _InfinityText(float):
    def __str__(self):
        return "Infinity"


class _NonStrText(float):
    def __str__(self):
        # Deliberate: __str__ returns a non-str to prove the gate does not crash on it.
        return 5  # noqa: PLE0307


@pytest.mark.parametrize(
    "stated_mean",
    [_NaNText(1.0), _InfinityText(1.0), _NonStrText(1.0)],
    ids=["text-NaN", "text-Infinity", "text-non-str"],
)
def test_stated_value_with_unparseable_text_is_no_decision_not_an_exception(stated_mean):
    decision, evidence = _gate_api(
        {"samples": [1.0, 1.1, 0.9], "mean": stated_mean}, dict(CAND_STATS)
    )

    quality = evidence["per_objective"]["quality"]
    assert decision == "NoDecision"
    assert quality["code"] == "missing_statistical_evidence"
