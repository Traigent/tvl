#!/usr/bin/env python3
"""Run a scenario: two evidence bundles, two validations, one gate decision.

    python book/support-bot/run_scenario.py promote --seed 0
    python book/support-bot/run_scenario.py all --seeds 0 1 2 3 4     # the robustness table

For a scenario this script
  1. writes an incumbent bundle and a candidate bundle (evaluate.py; SYNTHETIC),
  2. runs `tvl-measure-validate` on each bundle with its configuration,
  3. runs `tvl-ci-gate <module> <incumbent> <candidate> --json` and reports its decision.

The tools are run as separate processes, exactly as a reader would run them.
Run it from the repository root.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import evaluate as ev  # noqa: E402

MODULE = REPO / "spec" / "examples" / "book" / "ch05" / "support-bot.tvl.yml"
# Chapter 6's module: the chapter 5 module plus one chance constraint on slow replies.
MODULE_CH06 = REPO / "spec" / "examples" / "book" / "ch06" / "support-bot.tvl.yml"
CONFIGS = HERE / "configs"
DEFAULT_OUT = HERE / "out"
TOOL_TIMEOUT_S = 120

# expect_gate: the decision the gate must return, on every seed.
# expect_candidate_validate: exit code of tvl-measure-validate on the candidate bundle.
# expect_incumbent_validate: the same for the incumbent bundle (default 0).
# module: the module the scenario runs under (default: chapter 5's).
SCENARIOS = {
    "promote": {
        "incumbent": "incumbent",
        "candidate": "promote-candidate",
        "n_tickets": None,  # the whole evaluation split (140 tickets)
        "expect_gate": "Promote",
        "expect_candidate_validate": 0,
        "story": "A medium model with two tool calls and retrieval resolves more tickets than the "
                 "large incumbent at a fraction of its cost, with enough tickets to show it.",
    },
    "reject": {
        "incumbent": "incumbent",
        "candidate": "reject-candidate",
        "n_tickets": None,
        "expect_gate": "Reject",
        "expect_candidate_validate": 0,
        "story": "A medium model with no tool calls is much cheaper but resolves far fewer tickets: "
                 "a regression beyond the margin on resolution_rate, which no saving can buy back.",
    },
    "nodecision": {
        "incumbent": "nodecision-incumbent",
        "candidate": "nodecision-candidate",
        "n_tickets": 16,  # too few tickets to show a modest true improvement
        "expect_gate": "NoDecision",
        "expect_candidate_validate": 0,
        "story": "A candidate that is truly a little better, judged on only 16 tickets: not enough "
                 "evidence to promote it, and no evidence against it either.",
    },
    "band-fail": {
        "incumbent": "incumbent",
        "candidate": "band-fail-candidate",
        "n_tickets": None,
        "expect_gate": "Reject",
        "expect_candidate_validate": 2,  # tvl-measure-validate also reports the band violation
        "story": "A candidate that resolves more tickets but whose replies average above 250 tokens: "
                 "the band on reply_tokens is checked before dominance, so the gate rejects it.",
    },
    "slo-pass": {
        "module": MODULE_CH06,
        "incumbent": "incumbent",
        "candidate": "promote-candidate",
        "n_tickets": None,
        "expect_gate": "Promote",
        "expect_candidate_validate": 0,
        "story": "Chapter 6's module adds a chance constraint: at most 5% slow replies, at 95% "
                 "confidence. On 140 tickets the promote candidate's upper bound is below 5%.",
    },
    "slo-few": {
        "module": MODULE_CH06,
        "incumbent": "incumbent",
        "candidate": "promote-candidate",
        "n_tickets": 50,  # fewer than 59 trials: even zero slow replies cannot show a rate <= 5%
        "expect_gate": "Reject",
        "expect_candidate_validate": 2,  # tvl-measure-validate reports chance_violation
        "expect_incumbent_validate": 2,  # 50 tickets cannot show the incumbent's rate either
        "story": "The same candidate on only 50 tickets. Even with no slow reply, the 95% upper "
                 "bound on the slow-reply rate stays above 5%, and a chance constraint that is "
                 "not shown to hold rejects the candidate.",
    },
}


def module_of(name: str) -> Path:
    return SCENARIOS[name].get("module", MODULE)


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO / "python"), str(REPO)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    return env


def _run(module_name: str, args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module_name, *map(str, args)],
        cwd=REPO, env=_env(), capture_output=True, text=True, timeout=TOOL_TIMEOUT_S,
    )


def write_bundles(name: str, seed: int, out: Path) -> tuple[Path, Path, Path, Path]:
    """Write incumbent and candidate bundles; return (inc_cfg, cand_cfg, inc_bundle, cand_bundle)."""
    sc = SCENARIOS[name]
    module = ev._load_yaml(module_of(name))
    tickets = ev.select_tickets(ev.load_tickets(split="eval"), sc["n_tickets"], seed)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for role in ("incumbent", "candidate"):
        cfg_path = CONFIGS / f"{sc[role]}.yml"
        bundle = ev.evaluate_config(module, ev._load_yaml(cfg_path), tickets, seed,
                                    f"support-bot.{name}.{role}", "eval")
        bundle_path = out / f"{role}.synthetic.measure.yml"
        bundle_path.write_text(ev.dump_bundle(bundle), encoding="utf-8")
        paths.append((cfg_path, bundle_path))
    return paths[0][0], paths[1][0], paths[0][1], paths[1][1]


def run_scenario(name: str, seed: int, out_root: Path = DEFAULT_OUT, verbose: bool = True) -> dict:
    sc = SCENARIOS[name]
    out = out_root / name / f"seed-{seed}"
    inc_cfg, cand_cfg, inc_b, cand_b = write_bundles(name, seed, out)
    rel = lambda p: os.path.relpath(p, REPO)  # noqa: E731
    result = {"scenario": name, "seed": seed, "out": out, "validate": {}}

    module_path = module_of(name)
    for role, cfg, bundle in (("incumbent", inc_cfg, inc_b), ("candidate", cand_cfg, cand_b)):
        proc = _run("tvl_tools.tvl_measure_validate.cli", [rel(module_path), rel(cfg), rel(bundle), "--json"])
        report = json.loads(proc.stdout)
        (out / f"{role}.measure-validate.json").write_text(proc.stdout, encoding="utf-8")
        result["validate"][role] = {"exit": proc.returncode, "ok": report.get("ok"),
                                    "promotion_ready": report.get("promotion_ready"),
                                    "operational": report.get("operational"), "chance": report.get("chance")}
        if verbose:
            print(f"$ tvl-measure-validate {rel(module_path)} {rel(cfg)} {rel(bundle)} --json")
            print(f"  exit {proc.returncode}  ok={report.get('ok')}  promotion_ready={report.get('promotion_ready')}"
                  + (f"  operational={report.get('operational')}" if report.get("operational") else "")
                  + (f"  chance={report.get('chance')}" if report.get("chance") else ""))

    proc = _run("tvl_tools.tvl_ci_gate.cli", [rel(module_path), rel(inc_b), rel(cand_b), "--json"])
    gate = json.loads(proc.stdout)
    (out / "gate.json").write_text(proc.stdout, encoding="utf-8")
    summary = gate["evidence"]["summary"]
    result.update(gate_exit=proc.returncode, decision=gate["decision"],
                  reason=summary["decision_reason"], evidence=gate["evidence"])
    if verbose:
        print(f"$ tvl-ci-gate {rel(module_path)} {rel(inc_b)} {rel(cand_b)} --json")
        print(f"  exit {proc.returncode}  decision={gate['decision']}")
        print(f"  reason: {summary['decision_reason']}")
        for oname, o in gate["evidence"]["per_objective"].items():
            if o["test_type"] == "tost":
                print(f"  {oname:<20} mean={o['mean']:.1f} band=[{o['band_lower']:g}, {o['band_upper']:g}] -> {o['verdict']}")
            else:
                print(f"  {oname:<20} incumbent={o['mean_incumbent']:.4f} candidate={o['mean_candidate']:.4f} "
                      f"delta={o['delta']:+.4f} (margin {o['epsilon']:g}, n={o['n_candidate']}) -> {o['verdict']}")
        for cname, c in gate["evidence"]["chance_constraints"].items():
            print(f"  {cname:<20} violations={c['violations']}/{c['trials']} upper bound={c['ci_upper']:.4f} "
                  f"(threshold {c['threshold']:g}, confidence {c['confidence']:g}) -> {c['verdict']}")
        print("  (SYNTHETIC: simulator output, not a measurement of a real bot)")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("scenario", choices=[*SCENARIOS, "all"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--seeds", type=int, nargs="+", help="several seeds; prints a robustness table")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    seeds = args.seeds or [args.seed]
    verbose = len(names) * len(seeds) == 1
    table: dict[str, dict[int, str]] = {n: {} for n in names}
    failures = 0
    for name in names:
        if not verbose:
            print(f"[{name}] {SCENARIOS[name]['story']}")
        for seed in seeds:
            r = run_scenario(name, seed, args.out, verbose=verbose)
            table[name][seed] = r["decision"]
            if r["decision"] != SCENARIOS[name]["expect_gate"]:
                failures += 1

    if not verbose:
        print()
        print("Robustness table: gate decision per seed (SYNTHETIC data)")
        print(f"{'scenario':<12}" + "".join(f"seed {s:<6}" for s in seeds) + "expected")
        for name in names:
            print(f"{name:<12}" + "".join(f"{table[name][s]:<11}" for s in seeds) + SCENARIOS[name]["expect_gate"])
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
