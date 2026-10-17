"""The book's runnable support-bot project (book/support-bot/): scenarios end in real gate decisions.

Every scenario writes an incumbent and a candidate evidence bundle from the
SIMULATED bot, validates both with tvl-measure-validate, and asks tvl-ci-gate for
a decision. These tests run the real command-line tools as separate processes,
on 5 seeds each, and assert the decision and the exit codes. Nothing here
measures a real bot: the data is synthetic by construction.

tvl-ci-gate exits 0 on Promote and 2 on Reject and on NoDecision (its README
says exit 0 for every decision; the code and these tests are the authority).

The slo-* scenarios run chapter 6's module, which adds one chance constraint
(at most 5% slow replies, at 95% confidence). The evaluator writes its
violation and trial counts in chance_outcomes, as the contract requires.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "book" / "support-bot"
sys.path.insert(0, str(PROJECT))

import bot  # noqa: E402
import confidence  # noqa: E402
import evaluate as ev  # noqa: E402
import make_tickets  # noqa: E402
import run_scenario as rs  # noqa: E402

SEEDS = [0, 1, 2, 3, 4]
GATE_EXIT = {"Promote": 0, "Reject": 2, "NoDecision": 2}
BUNDLE_TOP_LEVEL = {"bundle_id", "config_id", "module_id", "objective_values", "chance_outcomes", "summary"}


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_tickets_are_synthetic_and_reproducible() -> None:
    lines = (PROJECT / "tickets.jsonl").read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])["_meta"]
    assert header["synthetic"] is True and "SYNTHETIC" in header["note"]
    rows = [json.loads(line) for line in lines[1:]]
    assert len(rows) == 200
    assert all(r["synthetic"] is True for r in rows)
    assert {"id", "category", "difficulty", "needs_lookup", "split"} <= set(rows[0])
    assert make_tickets.render() == "\n".join(lines) + "\n", "tickets.jsonl differs from make_tickets.py"


def test_evaluation_split_is_separate_from_tuning() -> None:
    tuning = {t["id"] for t in ev.load_tickets(split="tuning")}
    evaluation = {t["id"] for t in ev.load_tickets(split="eval")}
    assert len(tuning) == 60 and len(evaluation) == 140
    assert not tuning & evaluation


def test_bot_is_deterministic_and_labelled_a_simulator() -> None:
    ticket = ev.load_tickets()[0]
    config = _yaml(PROJECT / "configs" / "incumbent.yml")["assignments"]
    assert bot.run_bot(config, ticket, 3) == bot.run_bot(config, ticket, 3)
    assert "simulator" in bot.__doc__.lower() and "SYNTHETIC" in bot.SIMULATOR_NOTE


def test_scenario_candidates_are_better_or_worse_by_the_simulators_own_formula() -> None:
    """The true (noise-free) rates back each story, so a decision is not luck."""
    tickets = ev.load_tickets()

    def rate(name: str) -> float:
        return bot.expected_resolution_rate(_yaml(PROJECT / "configs" / f"{name}.yml")["assignments"], tickets)

    assert rate("promote-candidate") - rate("incumbent") > 0.05
    assert rate("reject-candidate") - rate("incumbent") < -0.10
    assert 0.03 < rate("nodecision-candidate") - rate("nodecision-incumbent") < 0.10


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("name", list(rs.SCENARIOS))
def test_scenario_ends_in_the_expected_gate_decision(name: str, seed: int, tmp_path: Path) -> None:
    sc = rs.SCENARIOS[name]
    result = rs.run_scenario(name, seed, tmp_path, verbose=False)

    assert result["decision"] == sc["expect_gate"], result["reason"]
    assert result["gate_exit"] == GATE_EXIT[result["decision"]]
    assert result["validate"]["incumbent"]["exit"] == sc.get("expect_incumbent_validate", 0)
    assert result["validate"]["candidate"]["exit"] == sc["expect_candidate_validate"]
    # Both bundles passed the gate's promotion-readiness check: a decision was produced from valid inputs.
    assert all(v["promotion_ready"] for v in result["validate"].values())

    out = result["out"]
    for role in ("incumbent", "candidate"):
        bundle = _yaml(out / f"{role}.synthetic.measure.yml")
        assert set(bundle) <= BUNDLE_TOP_LEVEL
        assert bundle["module_id"] == "book.support_bot"
        assert bundle["summary"]["synthetic"] is True
        assert set(bundle["objective_values"]) == {"resolution_rate", "cost_per_ticket_usd", "reply_tokens"}
        n = bundle["summary"]["n_tickets"]
        assert all(len(o["samples"]) == n for o in bundle["objective_values"].values())

    if name == "band-fail":
        assert "reply_tokens" in result["reason"]
        assert result["evidence"]["per_objective"]["reply_tokens"]["verdict"] == "out_of_band"
    if name == "nodecision":
        assert result["evidence"]["per_objective"]["resolution_rate"]["n_candidate"] == 16

    chance = result["evidence"]["chance_constraints"]
    if rs.module_of(name) == rs.MODULE:
        assert chance == {}
        for role in ("incumbent", "candidate"):
            assert "chance_outcomes" not in _yaml(out / f"{role}.synthetic.measure.yml")
    else:
        c = chance["reply_latency_slo"]
        bundle = _yaml(out / "candidate.synthetic.measure.yml")
        n = bundle["summary"]["n_tickets"]
        # Exactly the contract's shape: violations and trials, one trial per ticket.
        assert bundle["chance_outcomes"] == {"reply_latency_slo": {"violations": c["violations"], "trials": n}}
        assert (c["threshold"], c["confidence"]) == (0.05, 0.95)
        if name == "slo-pass":
            assert n == 140 and c["verdict"] == "pass" and c["ci_upper"] <= 0.05
        if name == "slo-few":
            # Fewer than 59 trials: the bound stays above 5% even with no slow reply at all.
            assert n == 50 and c["verdict"] == "fail" and c["ci_upper"] > 0.05
            assert result["reason"] == "Chance constraints failed: reply_latency_slo"
            assert result["validate"]["candidate"]["chance"][0]["code"] == "chance_violation"


def test_slow_reply_counts_follow_the_evaluators_predicate() -> None:
    """chance_outcomes counts the simulator's own slow replies; nothing is invented."""
    module = _yaml(rs.MODULE_CH06)
    config = _yaml(PROJECT / "configs" / "promote-candidate.yml")
    tickets = ev.load_tickets()
    for seed in SEEDS:
        bundle = ev.evaluate_config(module, config, tickets, seed, "x", "eval")
        slow = sum(bot.run_bot(config["assignments"], t, seed).slow for t in tickets)
        assert bundle["chance_outcomes"]["reply_latency_slo"] == {"violations": slow, "trials": len(tickets)}


def test_slo_few_rejects_a_candidate_whose_true_slow_rate_is_low() -> None:
    """The slo-few Reject is a burden-of-proof result: the simulator's true rate is far below 5%."""
    config = _yaml(PROJECT / "configs" / "promote-candidate.yml")["assignments"]
    assert bot.expected_slow_rate(config, ev.load_tickets()) < 0.01


def test_evaluator_refuses_a_chance_constraint_it_cannot_count(tmp_path: Path) -> None:
    module = _yaml(rs.MODULE_CH06)
    module["promotion_policy"]["chance_constraints"].append({"name": "unknown_event", "threshold": 0.1, "confidence": 0.9})
    config = _yaml(PROJECT / "configs" / "incumbent.yml")
    with pytest.raises(SystemExit, match="unknown_event"):
        ev.evaluate_config(module, config, ev.load_tickets(), 0, "x", "eval")


def test_committed_seed0_bundles_match_a_fresh_run(tmp_path: Path) -> None:
    for name in rs.SCENARIOS:
        rs.write_bundles(name, 0, tmp_path / name)
        for role in ("incumbent", "candidate"):
            fresh = (tmp_path / name / f"{role}.synthetic.measure.yml").read_text(encoding="utf-8")
            kept = (PROJECT / "bundles" / name / "seed-0" / f"{role}.synthetic.measure.yml").read_text(encoding="utf-8")
            assert fresh == kept, f"{name}/{role}: committed bundle is stale; rerun run_scenario.py --out book/support-bot/bundles"


def test_coverage_figure_data_matches_a_fresh_simulation(tmp_path: Path) -> None:
    """Figure 6.1 draws website/client/src/book/data/coverage-studies.json; it must be the script's output."""
    out = tmp_path / "coverage.json"
    assert confidence.main(["coverage", "--json-out", str(out)]) == 0
    kept = ROOT / "website" / "client" / "src" / "book" / "data" / "coverage-studies.json"
    assert out.read_text(encoding="utf-8") == kept.read_text(encoding="utf-8"), (
        "coverage figure data is stale; rerun book/support-bot/confidence.py coverage --json-out ..."
    )
    data = json.loads(kept.read_text(encoding="utf-8"))
    assert data["covered"] == sum(s["covers"] for s in data["studies"])
    assert all(s["covers"] == (s["upper_bound"] >= data["true_rate"]) for s in data["studies"])


def test_zero_violations_need_at_least_59_trials_for_a_5_percent_bound() -> None:
    """The chapter's claim, from the gate's own bound: 0 of 58 is not enough, 0 of 59 is."""
    assert confidence.upper_bound(0, 58) > 0.05 >= confidence.upper_bound(0, 59)
    assert confidence.upper_bound(0, 50) > 0.05
    assert confidence.upper_bound(2, 140) <= 0.05 < confidence.upper_bound(3, 140)

