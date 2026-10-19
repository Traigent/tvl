# tvl-ci-gate

Offline dry-run for the TVL promotion gate. Evaluates Clopper-Pearson bounds, TOST bands, and false discovery rate (FDR) control for paired metrics.

```
tvl-ci-gate spec/examples/rag-support-bot.tvl.yml \
  spec/measurements/rag-support-bot.incumbent.measure.yml \
  spec/measurements/rag-support-bot.candidate.measure.yml --json
```

- Canonical input bundles use `objective_values` with `samples` or `mean/std/n`, and
  `chance_outcomes` with `violations` and `trials`.
- `--policy` is kept only as a deprecated fallback for standalone dry-runs.

- Exit 0: decision is `Promote`
- Exit 2: decision is `Reject` or `NoDecision`, or input validation fails
