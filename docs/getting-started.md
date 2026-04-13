# Getting Started with TVL

This guide walks through a small but valid TVL module and the core CLI checks you should run before using a spec in optimization or CI.

## Install the CLI

Use the published package:

```bash
python -m pip install tvl-spec
```

Or install directly from this repository while developing:

```bash
python -m pip install -e tvl/[dev]
```

That exposes the main CLI tools:

*   `tvl-parse`
*   `tvl-lint`
*   `tvl-validate`
*   `tvl-check-structural`
*   `tvl-check-operational`

## Write a first module

Create `support-bot.tvl.yml`:

```yaml title="support-bot.tvl.yml"
tvl:
  module: corp.support.bot

environment:
  snapshot_id: "2026-03-01T00:00:00Z"
  bindings:
    llm_gateway: us-east-1
  context:
    gateway_baseline_latency_ms: 1500

evaluation_set:
  dataset: s3://datasets/support-tickets/dev.jsonl
  seed: 2026

tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4o-mini", "gpt-4o", "llama-3-70b"]

  - name: temperature
    type: float
    domain:
      range: [0.0, 1.0]
      resolution: 0.1

  - name: retriever_k
    type: int
    domain:
      range: [0, 12]

constraints:
  structural:
    - when: model = "llama-3-70b"
      then: temperature <= 0.5
  derived:
    - require: env.context.gateway_baseline_latency_ms <= 1500

objectives:
  - name: quality_score
    metric_ref: metrics.quality_score.v1
    direction: maximize
  - name: latency_ms
    metric_ref: metrics.latency_ms.v1
    direction: minimize

promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  min_effect:
    quality_score: 0.01
    latency_ms: 50

exploration:
  strategy:
    type: random
  budgets:
    max_trials: 24
```

This module already contains the minimum pieces most production-facing TVL specs need:

*   a namespace under `tvl.module`
*   an explicit `environment.snapshot_id`
*   an `evaluation_set`
*   typed TVAR declarations
*   structural and optional derived checks
*   objectives plus a promotion policy
*   optional `metric_ref` identifiers so the evaluation harness knows which metric contract computes each objective

## Run the core checks

```bash
tvl-parse support-bot.tvl.yml
tvl-lint support-bot.tvl.yml
tvl-validate support-bot.tvl.yml
tvl-check-structural support-bot.tvl.yml --json
tvl-check-operational support-bot.tvl.yml --json
```

What each step does:

*   `tvl-parse` checks that the file is syntactically well-formed YAML with the expected TVL shape.
*   `tvl-lint` catches common policy and authoring issues.
*   `tvl-validate` runs schema and semantic validation.
*   `tvl-check-structural` checks the structural constraint set for satisfiability.
*   `tvl-check-operational` validates derived constraints and exploration budgets.

## Common first mistakes

*   Writing CEL-like expressions such as `params.model == "gpt-4o"` instead of TVL formulas like `model = "gpt-4o"`.
*   Using derived constraints for metric outputs. In TVL, derived constraints are over `env.context.*` symbols.
*   Treating `metric_ref` as executable code. It should be a stable metric ID such as `metrics.quality_score.v1`, resolved by your evaluator.
*   Forgetting `promotion_policy.min_effect` entries for standard objectives.
*   Omitting `evaluation_set.dataset`, which makes the spec non-reproducible.

## Next steps

*   Read the [Language Reference](reference/language.md) for the current TVL surface.
*   Work through the [Example Walkthroughs](examples/walkthroughs.md) to see RAG, routing, banded objectives, chance constraints, and overlay workflows.
*   Compare against the shipped examples in [`spec/examples`](https://github.com/Traigent/tvl/tree/main/spec/examples).
