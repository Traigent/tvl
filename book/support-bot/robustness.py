#!/usr/bin/env python3
"""How often does each scenario's decision change with the seed? (SYNTHETIC data.)

The README's 5-seed table runs the real CLIs. This script repeats the same
scenarios over many seeds faster, by calling the gate's library function
(`tvl.promotion.epsilon_pareto_gate`) in-process, the same code the CLI calls.

    python book/support-bot/robustness.py --seeds 200
"""

from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import evaluate as ev  # noqa: E402
import run_scenario as rs  # noqa: E402
from tvl.loader import load  # noqa: E402
from tvl.measurement import prepare_measurement_bundle  # noqa: E402
from tvl.promotion import epsilon_pareto_gate  # noqa: E402


def decide(modules: dict, name: str, seed: int) -> str:
    sc = rs.SCENARIOS[name]
    module = modules[rs.module_of(name)]
    tickets = ev.select_tickets(ev.load_tickets(split="eval"), sc["n_tickets"], seed)
    bundles = []
    for role in ("incumbent", "candidate"):
        config = ev._load_yaml(rs.CONFIGS / f"{sc[role]}.yml")
        raw = ev.evaluate_config(module, config, tickets, seed, f"{name}.{role}", "eval")
        bundles.append(prepare_measurement_bundle(module, raw, role=role)[0])
    decision, _ = epsilon_pareto_gate(
        bundles[0], bundles[1], module["promotion_policy"], module["objectives"]
    )
    return decision


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, default=200, help="seeds 0..N-1")
    args = ap.parse_args()
    modules = {rs.module_of(n): load(rs.module_of(n)) for n in rs.SCENARIOS}
    print(f"Gate decisions over seeds 0..{args.seeds - 1} (SYNTHETIC data)")
    print("A flip is a seed where the decision differs from the expected one.")
    for name, sc in rs.SCENARIOS.items():
        counts = collections.Counter(decide(modules, name, s) for s in range(args.seeds))
        print(f"{name:<12} expected {sc['expect_gate']:<10} " + ", ".join(f"{d}: {c}" for d, c in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
