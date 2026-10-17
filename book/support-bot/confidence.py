#!/usr/bin/env python3
"""What a 95% upper confidence bound promises, shown by simulation (SIMULATED studies).

Two views of the one-sided Clopper-Pearson upper bound that tvl-ci-gate uses for
chance constraints. Both call the gate's own function,
tvl.promotion.evaluate_chance_constraint, so the numbers are the gate's numbers.

    python book/support-bot/confidence.py bounds --violations 0 --trials 10 30 50 59 140
    python book/support-bot/confidence.py coverage

`bounds` prints the upper bound for a violation count over several trial counts.

`coverage` runs many simulated studies of a process whose true violation rate
is known (TRUE_RATE). Each study draws N_TRIALS independent trials, counts the
violations and computes the 95% upper bound. "Coverage" is the share of studies
whose bound lands at or above the true rate. Confidence is that long-run share
over repeated studies; it is not a probability about any one study.

With --json-out it also writes the first FIGURE_STUDIES studies for the
book's coverage figure (chapter 6). Everything here is simulated.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from tvl.promotion import evaluate_chance_constraint

TRUE_RATE = 0.035  # the simulated process's true violation rate
N_TRIALS = 140  # trials per study, as many as the book's evaluation split has tickets
CONFIDENCE = 0.95
FIGURE_STUDIES = 60
MANY_STUDIES = 10_000
SEED = "book-coverage-2026-10-17"


def upper_bound(violations: int, trials: int, confidence: float = CONFIDENCE) -> float:
    """The gate's one-sided upper confidence bound on the violation rate."""
    # The threshold does not affect the bound; it only decides pass/fail.
    result = evaluate_chance_constraint("bound", {"violations": violations, "trials": trials}, 1.0, confidence)
    return float(result.ci_upper)


def study(index: int) -> dict:
    rng = random.Random(f"{SEED}:{index}")
    k = sum(1 for _ in range(N_TRIALS) if rng.random() < TRUE_RATE)
    bound = upper_bound(k, N_TRIALS)
    return {"study": index + 1, "violations": k, "trials": N_TRIALS,
            "upper_bound": round(bound, 5), "covers": bound >= TRUE_RATE}


def cmd_bounds(args: argparse.Namespace) -> int:
    print(f"95% upper bound on the violation rate with {args.violations} violation(s) observed")
    print(f"{'trials':>7}  {'upper bound':>11}")
    for n in args.trials:
        print(f"{n:>7}  {upper_bound(args.violations, n):>11.4f}")
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    shown = [study(i) for i in range(FIGURE_STUDIES)]
    covered_shown = sum(s["covers"] for s in shown)
    # A bound depends only on the count, so the many-study run tallies counts.
    covered_many = sum(1 for i in range(MANY_STUDIES) if study(i)["covers"])
    print(f"SIMULATED studies: true violation rate {TRUE_RATE}, {N_TRIALS} trials each, "
          f"{CONFIDENCE:.0%} upper bound")
    print(f"first {FIGURE_STUDIES} studies: the bound covers the true rate in {covered_shown}")
    misses = [f"study {s['study']} ({s['violations']} violation{'' if s['violations'] == 1 else 's'}, "
              f"bound {s['upper_bound']:.4f})"
              for s in shown if not s["covers"]]
    print("misses: " + (", ".join(misses) if misses else "none"))
    print(f"{MANY_STUDIES} studies: the bound covers the true rate in {covered_many} "
          f"({covered_many / MANY_STUDIES:.1%})")
    if args.json_out:
        data = {
            "_note": "SIMULATED studies, written by book/support-bot/confidence.py coverage --json-out. "
                     "Not measurements.",
            "true_rate": TRUE_RATE, "trials": N_TRIALS, "confidence": CONFIDENCE,
            "covered": covered_shown, "studies": shown,
            "many_studies": MANY_STUDIES, "many_covered": covered_many,
        }
        args.json_out.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bounds", help="upper bounds for one violation count over several trial counts")
    b.add_argument("--violations", type=int, default=0)
    b.add_argument("--trials", type=int, nargs="+", required=True)
    c = sub.add_parser("coverage", help="repeated simulated studies of a known true rate")
    c.add_argument("--json-out", type=Path, help="write the figure data here")
    args = ap.parse_args(argv)
    return cmd_bounds(args) if args.cmd == "bounds" else cmd_coverage(args)


if __name__ == "__main__":
    sys.exit(main())
