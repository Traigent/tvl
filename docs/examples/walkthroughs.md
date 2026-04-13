# Example Walkthroughs

These examples are aligned to the current TVL schema and mirror the canonical modules under `spec/examples`.

## Suggested Walkthrough Order

### 1. RAG Support Bot

Source: [rag-support-bot.tvl.yml](https://github.com/Traigent/tvl/blob/main/spec/examples/rag-support-bot.tvl.yml)

Use this first. It is the best compact baseline for a real TVL module because it includes:

*   `environment` and `evaluation_set`
*   multiple typed TVARs
*   structural and derived constraints
*   multi-objective optimization
*   a promotion policy with chance constraints

### 2. Agent Router

Source: [agent-router.tvl.yml](https://github.com/Traigent/tvl/blob/main/spec/examples/agent-router.tvl.yml)

This example highlights routing trade-offs and operational governance:

*   routing-model implications
*   latency-oriented objectives
*   chance constraints for timeout SLOs
*   `nsga2` plus convergence hints

### 3. Tool-Use Agent

Source: [tool-use.yml](https://github.com/Traigent/tvl/blob/main/spec/examples/tool-use.yml)

Use this when you want the current statistical features:

*   banded objective with `TOST`
*   `adjust: holm`
*   fairness-oriented chance constraints
*   finite domains suitable for grid-style search

### 4. Text-to-SQL

Source: [text-to-sql.yml](https://github.com/Traigent/tvl/blob/main/spec/examples/text-to-sql.yml)

This is a good example of a tighter single-pipeline workload:

*   banded token-budget objective
*   standard quality objective
*   `tpe` exploration
*   explicit dataset anchoring

### 5. Multi-Tenant Router

Source: [multi-tenant-router.tvl.yml](https://github.com/Traigent/tvl/blob/main/spec/examples/multi-tenant-router.tvl.yml)

This example focuses on policy-style structural constraints:

*   tenant-tier gating
*   `in` membership constraints
*   conditional token ceilings
*   clear separation between business policy and optimization policy

### 6. Cost Optimization

Source: [cost-optimization.tvl.yml](https://github.com/Traigent/tvl/blob/main/spec/examples/cost-optimization.tvl.yml)

Use this to study trade-offs where cost pressure is primary:

*   cost-vs-quality objectives
*   chance constraints for rollout safety
*   budget-oriented environment assumptions

## Validation-Focused Fixtures

The `validation-phase*` examples are important if you are building tooling, CI, or editor support rather than just authoring one spec.

Useful starting points:

*   [validation-phase2/structural-sat.tvl.yml](https://github.com/Traigent/tvl/blob/main/spec/examples/validation-phase2/structural-sat.tvl.yml)
*   [validation-phase2/structural-unsat.tvl.yml](https://github.com/Traigent/tvl/blob/main/spec/examples/validation-phase2/structural-unsat.tvl.yml)
*   [validation-phase5/banded-objective-tost.tvl.yml](https://github.com/Traigent/tvl/blob/main/spec/examples/validation-phase5/banded-objective-tost.tvl.yml)
*   [validation-phase5/chance-constraint-valid.tvl.yml](https://github.com/Traigent/tvl/blob/main/spec/examples/validation-phase5/chance-constraint-valid.tvl.yml)
*   [validation-phase5/callable-registry-ref.tvl.yml](https://github.com/Traigent/tvl/blob/main/spec/examples/validation-phase5/callable-registry-ref.tvl.yml)

These fixtures exercise:

*   satisfiable vs. contradictory structural clauses
*   banded objective validation
*   chance-constraint policy validation
*   callable TVARs and registry-backed domains

## Recommended CLI Sequence

Run this sequence for each example you inspect:

```bash
tvl-parse <module>
tvl-lint <module>
tvl-validate <module>
tvl-check-structural <module> --json
tvl-check-operational <module> --json
```

If you are working with composed overlays or runtime artifacts, extend the flow with:

```bash
tvl-compose base.tvl.yml staging.overlay.yml > merged.tvl.yml
tvl-config-validate merged.tvl.yml config.yml
tvl-measure-validate merged.tvl.yml config.yml measurements.yml
```

## Rule of Thumb

Start with `rag-support-bot.tvl.yml` for the full module shape, move to `tool-use.yml` and `text-to-sql.yml` for richer policy/objective patterns, and use the `validation-phase*` fixtures whenever you need precise regression coverage for tooling.
