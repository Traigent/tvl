#!/usr/bin/env python3
"""Run one configuration over a split of the synthetic tickets and write an evidence bundle.

The bundle has exactly the shape of spec/promotion-evidence-contract.md:
bundle_id, config_id, module_id, objective_values.<name>.samples (one value per
ticket) and, if the module declares chance constraints, chance_outcomes.<name>
with the violation and trial counts.
Because the bundle comes from the simulator in bot.py, `summary.synthetic` is
true and the default file name contains ".synthetic.": the numbers are not
measurements of a real bot.

    python book/support-bot/evaluate.py \
        --module spec/examples/book/ch05/support-bot.tvl.yml \
        --config book/support-bot/configs/incumbent.yml \
        --split eval --seed 0 --bundle-id support-bot.incumbent \
        --out /tmp/incumbent.synthetic.measure.yml

Replace the call to `bot.run_bot` in `evaluate_config` with a call to your own
agent to produce a real bundle; see the README.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bot  # noqa: E402

DEFAULT_TICKETS = HERE / "tickets.jsonl"

# Objective name in the module -> how to read one sample from a BotResult.
SAMPLE_OF = {
    "resolution_rate": lambda r: 1.0 if r.resolved else 0.0,
    "cost_per_ticket_usd": lambda r: round(r.cost_usd, 6),
    "reply_tokens": lambda r: round(r.reply_tokens, 1),
}

# Chance-constraint name in the module -> the evaluator's violation predicate on a BotResult.
# TVL caps the rate; deciding what counts as one violation is the evaluator's job.
VIOLATION_OF = {
    "reply_latency_slo": lambda r: r.slow,  # latency above bot.SLO_MS
}


def load_tickets(path: Path = DEFAULT_TICKETS, split: str = "eval") -> list[dict]:
    tickets = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if "_meta" in row:
            assert row["_meta"]["synthetic"] is True
            continue
        if split == "all" or row["split"] == split:
            tickets.append(row)
    return tickets


def select_tickets(tickets: list[dict], n: int | None, seed: int) -> list[dict]:
    """All tickets, or a seeded random subset of n (the same subset for every configuration)."""
    if n is None or n >= len(tickets):
        return list(tickets)
    chosen = random.Random(f"ticket-subset:{seed}").sample(tickets, n)
    return sorted(chosen, key=lambda t: t["id"])


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def evaluate_config(module: dict, config: dict, tickets: list[dict], seed: int,
                    bundle_id: str, split: str) -> dict:
    """Return the evidence bundle (a dict in the contract's shape) for one configuration."""
    chance_names = [c["name"] for c in (module.get("promotion_policy") or {}).get("chance_constraints") or []]
    no_predicate = [n for n in chance_names if n not in VIOLATION_OF]
    if no_predicate:
        raise SystemExit(
            f"this module declares chance constraints {no_predicate}; the simulator has no "
            "violation predicate for them, so no honest chance_outcomes can be written"
        )
    names = [o["name"] for o in module["objectives"]]
    unknown = [n for n in names if n not in SAMPLE_OF]
    if unknown:
        raise SystemExit(f"no sample extractor for objectives: {unknown}")
    assignments = config["assignments"]
    results = [bot.run_bot(assignments, t, seed) for t in tickets]  # <- swap in your agent here
    ids = [t["id"] for t in tickets]
    objective_values = {name: {"samples": [SAMPLE_OF[name](r) for r in results]} for name in names}
    # The comparison is paired: both bundles ran the same tickets, in the same order.
    for name in names:
        objective_values[name]["paired"] = True
    bundle = {
        "bundle_id": bundle_id,
        "config_id": config["config_id"],
        "module_id": module["tvl"]["module"],
        "objective_values": objective_values,
    }
    if chance_names:
        # One trial per ticket; a violation is a ticket whose reply breaks the predicate.
        bundle["chance_outcomes"] = {
            name: {"violations": sum(1 for r in results if VIOLATION_OF[name](r)), "trials": len(results)}
            for name in chance_names
        }
    bundle["summary"] = {
        "synthetic": True,
        "note": bot.SIMULATOR_NOTE,
        "seed": seed,
        "split": split,
        "n_tickets": len(tickets),
        "ticket_ids_sha256": hashlib.sha256(",".join(ids).encode()).hexdigest()[:16],
    }
    return bundle


def dump_bundle(bundle: dict) -> str:
    header = (
        "# SYNTHETIC evidence bundle, written by book/support-bot/evaluate.py from the\n"
        "# simulator in bot.py. Not a measurement of any real bot or model.\n"
    )
    return header + yaml.safe_dump(bundle, sort_keys=False, default_flow_style=None, width=100)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--module", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--split", choices=["tuning", "eval"], default="eval")
    ap.add_argument("--n-tickets", type=int, default=None, help="random subset size (default: the whole split)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--bundle-id", required=True)
    ap.add_argument("--tickets", type=Path, default=DEFAULT_TICKETS)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    module = _load_yaml(args.module)
    config = _load_yaml(args.config)
    tickets = select_tickets(load_tickets(args.tickets, args.split), args.n_tickets, args.seed)
    bundle = evaluate_config(module, config, tickets, args.seed, args.bundle_id, args.split)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(dump_bundle(bundle), encoding="utf-8")
    print(f"wrote {args.out}  ({len(tickets)} {args.split} tickets, seed {args.seed}, SYNTHETIC)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
