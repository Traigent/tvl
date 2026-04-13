# TVL Promotion Evidence Contract

This note locks the current pre-submission contract for promotion evidence and chance semantics.

## Canonical semantics

- A chance constraint with threshold `theta` and confidence `gamma` is a bound on the **violation rate**.
- Let `k` be the observed number of violations in `n` trials.
- TVL computes the one-sided Clopper-Pearson upper confidence bound on the violation rate and passes iff that upper bound is `<= theta`.

## Canonical measurement bundle

Use one bundle shape for both `tvl-measure-validate` and `tvl-ci-gate`.

```yaml
bundle_id: example.candidate
config_id: example.default
module_id: corp.example
objective_values:
  quality:
    mean: 0.82
    std: 0.04
    n: 200
  latency_p95_ms:
    samples: [1300, 1280, 1310]
chance_outcomes:
  latency_slo:
    violations: 2
    trials: 200
```

Canonical rules:

- `objective_values.<name>` must provide either `samples` or `mean/std/n`.
- `chance_outcomes.<name>` must provide `violations` and `trials`.
- Quantile metrics use batch-level quantile observations, not raw per-request latencies.

## CLI contract

Primary gate workflow:

```bash
tvl-ci-gate <module> <incumbent-bundle> <candidate-bundle> --json
```

- The module is the source of `objectives` and `promotion_policy`.
- `--policy` remains only as a deprecated fallback for standalone dry-runs.

## Compatibility shims

Temporary compatibility remains for:

- top-level legacy `objectives` summaries,
- top-level legacy `chance` summaries,
- bare derived environment symbols such as `cost_usd <= 5`.

Compatibility behavior:

- legacy inputs emit deprecation warnings,
- legacy chance summaries are converted to canonical counts only when `violations` can be reconstructed exactly,
- summary-only objective bundles are not considered promotion-ready,
- canonical `env.<symbol>` references are preferred; bare symbols remain a migration-only alias.
