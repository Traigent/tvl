# The support bot, runnable (SYNTHETIC data and a SIMULATED bot)

A small project that runs the whole chain of chapters 2 to 6 of the book on your machine:

```
module  ->  candidate configuration  ->  evaluation  ->  evidence bundle  ->  tvl-ci-gate decision
```

The module is the chapter 5 file `spec/examples/book/ch05/support-bot.tvl.yml` (four knobs; objectives
`resolution_rate`, `cost_per_ticket_usd` and the banded `reply_tokens`; margins in `promotion_policy`).
The two `slo-*` scenarios use chapter 6's `spec/examples/book/ch06/support-bot.tvl.yml`, the same module
plus `adjust: holm` and one chance constraint, `reply_latency_slo` (at most 5% slow replies, shown at 95%
confidence). Nothing is copied: the scenarios use those files as they are.

## What is simulated, and why

**Everything here is synthetic. No number below is a measurement of a real bot, model or customer.**

| Part | What it is |
|---|---|
| `tickets.jsonl` | 200 tickets invented by `make_tickets.py` (seeded). Fields: `id`, `category`, `difficulty`, `needs_lookup`, `split`. No text, no real data. 60 are the `tuning` split, 140 the `eval` split. The first line is a header that says "SYNTHETIC". |
| `bot.py` | A deterministic **simulator** that stands in for an agent. The formulas are in its docstring: bigger models resolve more and cost more, tool calls help tickets that need a lookup, retrieval makes replies longer, tool calls and retrieval make replies slower, and so on. They are invented for teaching and do not model any real LLM. No network, no LLM calls. |
| `evaluate.py` | Runs one configuration over a split and writes an evidence bundle in the format of `spec/promotion-evidence-contract.md`. Every bundle has `summary.synthetic: true` (the contract's `summary` field is where extra metadata may go), a comment header, and the file name contains `.synthetic.`. |

Why simulate: so that every reader gets the same bundles and the same gate decisions, offline, in seconds,
and so that a scenario can be built to end in each of the three decisions on purpose. The price is that the
decisions show how the gate **reasons**, not how any real agent **performs**.

Two details that follow from the design:

- **Paired comparison.** The simulator's randomness depends only on `(seed, ticket)`, never on the configuration,
  so the incumbent and a candidate see the same luck on the same tickets. The bundles therefore carry
  `paired: true` and the gate runs a paired test. A real agent re-run on the same tickets is correlated in the
  same way, but only if you evaluate the same tickets for both configurations in the same order.
- **Separate splits.** `evaluate.py` defaults to the `eval` split. Tune on `tuning`, decide on `eval`.

- **Chance outcomes.** The chapter 5 module declares no chance constraints, so its bundles have no
  `chance_outcomes`. Under the chapter 6 module, `evaluate.py` writes
  `chance_outcomes.reply_latency_slo: {violations, trials}`: one trial per ticket, and a violation is a
  reply whose simulated latency is above `bot.SLO_MS` (10,000 ms). That predicate is the evaluator's, not
  TVL's: the module names the event and caps its rate. For any other chance-constraint name `evaluate.py`
  stops instead of inventing violation counts.

## Run it (from the repository root)

Python 3.11+ with the `tvl-spec` package installed (`pip install -e .` in this repository), or run with
`PYTHONPATH=python:.` as the tests do. Check the tickets are what the generator makes:

```bash
python book/support-bot/make_tickets.py --check
```

### Scenarios

Each scenario writes an incumbent bundle and a candidate bundle under `book/support-bot/out/<scenario>/seed-<n>/`
(git-ignored), runs `tvl-measure-validate` on each, then `tvl-ci-gate`. The configurations are in
`book/support-bot/configs/`. The decision does not depend on the seed (see the robustness table below).

| Scenario | Incumbent | Candidate | The point |
|---|---|---|---|
| `promote` | large, 1 tool call, T=0.7, no retrieval | medium, 2 tool calls, T=0.2, retrieval | better beyond the margins, 140 tickets |
| `reject` | same | medium, 0 tool calls, T=0.7, no retrieval | much cheaper, but resolves far fewer tickets |
| `nodecision` | medium, 1 tool call, T=0.5, no retrieval | medium, 1 tool call, T=0.3, retrieval | truly a little better, judged on 16 tickets |
| `band-fail` | large, 1 tool call, T=0.7, no retrieval | large, 2 tool calls, T=0.2, retrieval | resolves more, but replies average above 250 tokens |
| `slo-pass` | as `promote`, chapter 6 module | as `promote` | 0 slow replies in 140 (seed 0): the 95% upper bound 0.0212 is below 5% |
| `slo-few` | as `promote`, chapter 6 module, 50 tickets | as `promote` | 0 slow replies in 50 (seed 0), but the bound 0.0582 is above 5%: `Reject` |

The simulator's own noise-free resolution rates on the 140 evaluation tickets, from `bot.expected_resolution_rate`
(so you can see that "better" and "worse" are true in the simulator, not luck):

```
incumbent              0.5527
promote-candidate      0.6601
reject-candidate       0.3207
nodecision-incumbent   0.4647
nodecision-candidate   0.5167
band-fail-candidate    0.7601
```

The promote candidate's noise-free rate of slow replies (above 10,000 ms), from `bot.expected_slow_rate`, is
0.0038: far below the 5% limit. So the `slo-few` Reject below is about too little evidence, not a slow bot.

Run one scenario:

```bash
python book/support-bot/run_scenario.py promote --seed 0
```

```
$ tvl-measure-validate spec/examples/book/ch05/support-bot.tvl.yml book/support-bot/configs/incumbent.yml book/support-bot/out/promote/seed-0/incumbent.synthetic.measure.yml --json
  exit 0  ok=True  promotion_ready=True
$ tvl-measure-validate spec/examples/book/ch05/support-bot.tvl.yml book/support-bot/configs/promote-candidate.yml book/support-bot/out/promote/seed-0/candidate.synthetic.measure.yml --json
  exit 0  ok=True  promotion_ready=True
$ tvl-ci-gate spec/examples/book/ch05/support-bot.tvl.yml book/support-bot/out/promote/seed-0/incumbent.synthetic.measure.yml book/support-bot/out/promote/seed-0/candidate.synthetic.measure.yml --json
  exit 0  decision=Promote
  reason: All non-inferiority tests pass; superior on: resolution_rate, cost_per_ticket_usd
  resolution_rate      incumbent=0.5786 candidate=0.6714 delta=+0.0929 (margin 0.02, n=140) -> superior
  cost_per_ticket_usd  incumbent=0.0241 candidate=0.0097 delta=-0.0144 (margin 0.001, n=140) -> superior
  reply_tokens         mean=200.7 band=[80, 250] -> in_band
  (SYNTHETIC: simulator output, not a measurement of a real bot)
```

`tvl-ci-gate` exits 0 on Promote and 2 on Reject and NoDecision. (The tool's own README says exit 0 for every
decision; the code returns 2 for both of the others, and the tests assert the code.)

```bash
python book/support-bot/run_scenario.py reject --seed 0
```

```
$ tvl-measure-validate spec/examples/book/ch05/support-bot.tvl.yml book/support-bot/configs/incumbent.yml book/support-bot/out/reject/seed-0/incumbent.synthetic.measure.yml --json
  exit 0  ok=True  promotion_ready=True
$ tvl-measure-validate spec/examples/book/ch05/support-bot.tvl.yml book/support-bot/configs/reject-candidate.yml book/support-bot/out/reject/seed-0/candidate.synthetic.measure.yml --json
  exit 0  ok=True  promotion_ready=True
$ tvl-ci-gate spec/examples/book/ch05/support-bot.tvl.yml book/support-bot/out/reject/seed-0/incumbent.synthetic.measure.yml book/support-bot/out/reject/seed-0/candidate.synthetic.measure.yml --json
  exit 2  decision=Reject
  reason: Regression beyond the allowed margin demonstrated on: resolution_rate
  resolution_rate      incumbent=0.5786 candidate=0.3429 delta=-0.2357 (margin 0.02, n=140) -> inferior
  cost_per_ticket_usd  incumbent=0.0241 candidate=0.0090 delta=-0.0151 (margin 0.001, n=140) -> superior
  reply_tokens         mean=134.3 band=[80, 250] -> in_band
  (SYNTHETIC: simulator output, not a measurement of a real bot)
```

```bash
python book/support-bot/run_scenario.py nodecision --seed 0
```

```
$ tvl-measure-validate spec/examples/book/ch05/support-bot.tvl.yml book/support-bot/configs/nodecision-incumbent.yml book/support-bot/out/nodecision/seed-0/incumbent.synthetic.measure.yml --json
  exit 0  ok=True  promotion_ready=True
$ tvl-measure-validate spec/examples/book/ch05/support-bot.tvl.yml book/support-bot/configs/nodecision-candidate.yml book/support-bot/out/nodecision/seed-0/candidate.synthetic.measure.yml --json
  exit 0  ok=True  promotion_ready=True
$ tvl-ci-gate spec/examples/book/ch05/support-bot.tvl.yml book/support-bot/out/nodecision/seed-0/incumbent.synthetic.measure.yml book/support-bot/out/nodecision/seed-0/candidate.synthetic.measure.yml --json
  exit 2  decision=NoDecision
  reason: Non-inferiority not established on: resolution_rate
  resolution_rate      incumbent=0.2500 candidate=0.2500 delta=+0.0000 (margin 0.02, n=16) -> inconclusive
  cost_per_ticket_usd  incumbent=0.0092 candidate=0.0095 delta=+0.0003 (margin 0.001, n=16) -> noninferior
  reply_tokens         mean=195.9 band=[80, 250] -> in_band
  (SYNTHETIC: simulator output, not a measurement of a real bot)
```

On the sixteen tickets this seed drew, each bot resolved four. The bundle cannot tell a bot that is
a little better from one that is the same, so the gate says `NoDecision` instead of guessing.

```bash
python book/support-bot/run_scenario.py band-fail --seed 0
```

```
$ tvl-measure-validate spec/examples/book/ch05/support-bot.tvl.yml book/support-bot/configs/incumbent.yml book/support-bot/out/band-fail/seed-0/incumbent.synthetic.measure.yml --json
  exit 0  ok=True  promotion_ready=True
$ tvl-measure-validate spec/examples/book/ch05/support-bot.tvl.yml book/support-bot/configs/band-fail-candidate.yml book/support-bot/out/band-fail/seed-0/candidate.synthetic.measure.yml --json
  exit 2  ok=False  promotion_ready=True  operational=[{'objective': 'reply_tokens', 'code': 'band_violation', 'message': 'Value 260.68857142857144 outside band [80, 250]'}]
$ tvl-ci-gate spec/examples/book/ch05/support-bot.tvl.yml book/support-bot/out/band-fail/seed-0/incumbent.synthetic.measure.yml book/support-bot/out/band-fail/seed-0/candidate.synthetic.measure.yml --json
  exit 2  decision=Reject
  reason: Banded objectives outside declared band: reply_tokens
  resolution_rate      incumbent=0.5786 candidate=0.7786 delta=+0.2000 (margin 0.02, n=140) -> superior
  cost_per_ticket_usd  incumbent=0.0241 candidate=0.0246 delta=+0.0005 (margin 0.001, n=140) -> noninferior
  reply_tokens         mean=260.7 band=[80, 250] -> out_of_band
  (SYNTHETIC: simulator output, not a measurement of a real bot)
```

Here `tvl-measure-validate` also exits 2 on the candidate (`band_violation`): the mean reply length is outside the
declared band. The gate checks acceptability (bands, chance constraints) before it looks at dominance, so a
candidate that resolves 20 points more still gets `Reject`.

```bash
python book/support-bot/run_scenario.py slo-few --seed 0
```

```
$ tvl-measure-validate spec/examples/book/ch06/support-bot.tvl.yml book/support-bot/configs/incumbent.yml book/support-bot/out/slo-few/seed-0/incumbent.synthetic.measure.yml --json
  exit 2  ok=False  promotion_ready=True  chance=[{'constraint': 'reply_latency_slo', 'code': 'chance_violation', 'message': 'ci_upper (0.0582) > threshold (0.05)'}]
$ tvl-measure-validate spec/examples/book/ch06/support-bot.tvl.yml book/support-bot/configs/promote-candidate.yml book/support-bot/out/slo-few/seed-0/candidate.synthetic.measure.yml --json
  exit 2  ok=False  promotion_ready=True  chance=[{'constraint': 'reply_latency_slo', 'code': 'chance_violation', 'message': 'ci_upper (0.0582) > threshold (0.05)'}]
$ tvl-ci-gate spec/examples/book/ch06/support-bot.tvl.yml book/support-bot/out/slo-few/seed-0/incumbent.synthetic.measure.yml book/support-bot/out/slo-few/seed-0/candidate.synthetic.measure.yml --json
  exit 2  decision=Reject
  reason: Chance constraints failed: reply_latency_slo
  resolution_rate      incumbent=0.5600 candidate=0.6600 delta=+0.1000 (margin 0.02, n=50) -> superior
  cost_per_ticket_usd  incumbent=0.0242 candidate=0.0097 delta=-0.0145 (margin 0.001, n=50) -> superior
  reply_tokens         mean=203.8 band=[80, 250] -> in_band
  reply_latency_slo    violations=0/50 upper bound=0.0582 (threshold 0.05, confidence 0.95) -> fail
  (SYNTHETIC: simulator output, not a measurement of a real bot)
```

No slow reply in 50, but with fewer than 59 trials even zero violations cannot bring the 95% upper bound to 5%
or below. A chance constraint that is not shown to hold rejects the candidate (formal semantics §9.6–9.7);
an objective that is not shown non-inferior gives `NoDecision` instead.

### The same chain by hand

`run_scenario.py` only wires these steps together; each is a public command:

```bash
python book/support-bot/evaluate.py --module spec/examples/book/ch05/support-bot.tvl.yml \
    --config book/support-bot/configs/incumbent.yml --split eval --seed 0 \
    --bundle-id support-bot.incumbent --out /tmp/incumbent.synthetic.measure.yml
python book/support-bot/evaluate.py --module spec/examples/book/ch05/support-bot.tvl.yml \
    --config book/support-bot/configs/promote-candidate.yml --split eval --seed 0 \
    --bundle-id support-bot.promote-candidate --out /tmp/candidate.synthetic.measure.yml

tvl-measure-validate spec/examples/book/ch05/support-bot.tvl.yml \
    book/support-bot/configs/promote-candidate.yml /tmp/candidate.synthetic.measure.yml --json
tvl-ci-gate spec/examples/book/ch05/support-bot.tvl.yml \
    /tmp/incumbent.synthetic.measure.yml /tmp/candidate.synthetic.measure.yml --json
```

(Use `--json`: without it, the text mode of `tvl-ci-gate` prints an empty `Reason:` line for this module;
the reason is in `evidence.summary.decision_reason`.) A bundle looks like this (shortened):

```yaml
bundle_id: support-bot.promote.candidate
config_id: support-bot.promote-candidate
module_id: book.support_bot
objective_values:
  resolution_rate:
    samples: [1.0, 0.0, 1.0, ...]        # one value per ticket; 140 of them
    paired: true
  cost_per_ticket_usd: {samples: [...], paired: true}
  reply_tokens: {samples: [...], paired: true}
summary: {synthetic: true, seed: 0, split: eval, n_tickets: 140, ...}
```

Committed reference copies of the seed-0 bundles, gate output and validation output are in
`book/support-bot/bundles/`; a test checks that a fresh run reproduces the bundles byte for byte.

## Robustness: does the decision depend on the seed?

The five seeds, through the real command-line tools (`python book/support-bot/run_scenario.py all --seeds 0 1 2 3 4`):

```
Robustness table: gate decision per seed (SYNTHETIC data)
scenario    seed 0     seed 1     seed 2     seed 3     seed 4     expected
promote     Promote    Promote    Promote    Promote    Promote    Promote
reject      Reject     Reject     Reject     Reject     Reject     Reject
nodecision  NoDecision NoDecision NoDecision NoDecision NoDecision NoDecision
band-fail   Reject     Reject     Reject     Reject     Reject     Reject
slo-pass    Promote    Promote    Promote    Promote    Promote    Promote
slo-few     Reject     Reject     Reject     Reject     Reject     Reject
```

Slow replies per seed for the promote candidate: `slo-pass` 0, 0, 1, 0, 0 of 140; `slo-few` 0, 0, 1, 0, 0 of 50.

A wider check with the gate's library function (same code the command calls), 400 seeds, via
`PYTHONPATH=python:. python book/support-bot/robustness.py --seeds 400`:

```
Gate decisions over seeds 0..399 (SYNTHETIC data)
A flip is a seed where the decision differs from the expected one.
promote      expected Promote    Promote: 400
reject       expected Reject     Reject: 400
nodecision   expected NoDecision NoDecision: 399, Promote: 1
band-fail    expected Reject     Reject: 400
slo-pass     expected Promote    Promote: 392, Reject: 8
slo-few      expected Reject     Reject: 400
```

So the outcomes are robust, but not perfectly: with only 16 tickets, a lucky draw sometimes shows a
true improvement well enough to promote it (1 seed of 400 here). That is what a small sample is: a coin the
data can occasionally tip. On 8 seeds of 400, `slo-pass` draws three or more slow replies in 140 and the
bound rises above 5%: strict acceptability occasionally rejects a good candidate. The five reference seeds
do not flip.

## What a confidence bound promises

`confidence.py` uses the gate's own bound function (`tvl.promotion.evaluate_chance_constraint`):

```bash
python book/support-bot/confidence.py bounds --violations 0 --trials 10 30 50 59 140
python book/support-bot/confidence.py coverage
```

`coverage` simulates many studies of a process with a known true violation rate (3.5%, 140 trials each) and
counts how often the 95% upper bound lands at or above it: 58 of the first 60, and 95.8% of 10,000. With
`--json-out` it writes the data of the book's Figure 6.1 (`website/client/src/book/data/coverage-studies.json`);
a test checks that file against a fresh run.

## Replace the simulator with your own agent

1. Write your configuration files like those in `configs/` (a `config_id`, the `module_id`, and an
   `assignments` value for every knob the module declares).
2. In `evaluate.py`, `evaluate_config` calls `bot.run_bot(assignments, ticket, seed)`. Replace that one call with
   a call to your agent that returns the same things for a ticket: resolved (yes/no), cost in dollars,
   reply length in tokens and, for the chapter 6 module, the reply latency. Keep the loop over the **same tickets, in the same order,** for incumbent and
   candidate, and keep the bundle's `paired: true` only if you did.
3. Use your own tickets (an evaluation set with the fields your agent needs) instead of `tickets.jsonl`, and drop
   `"synthetic": true` from `summary` only for bundles your real agent produced.
4. For a module with `chance_constraints`, add `chance_outcomes.<name>: {violations, trials}` to the bundle,
   counted on the evaluation set.
5. Run `tvl-measure-validate` on each bundle with its configuration, then `tvl-ci-gate`. The number of
   tickets you can afford decides how small a difference the gate can see; `nodecision` is what too few looks like.

## Files

| File | Purpose |
|---|---|
| `make_tickets.py`, `tickets.jsonl` | the synthetic tickets and their generator |
| `bot.py` | the simulator |
| `evaluate.py` | configuration + tickets -> evidence bundle |
| `run_scenario.py` | a scenario end to end; `all --seeds ...` prints the robustness table |
| `robustness.py` | the same scenarios over many seeds, in process |
| `confidence.py` | upper bounds for a count, and the coverage simulation behind Figure 6.1 |
| `configs/` | the incumbent and candidate configurations |
| `bundles/` | reference output of seed 0 (bundles, validation reports, gate reports) |
| `ci-example.yml` | chapter 13's example GitHub Actions workflow (not a workflow of this repository); the tests run its steps |

Tests: `tests/test_book_support_bot.py`.
