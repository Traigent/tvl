# tvl-measure-validate

Validates a configuration together with a measurement bundle against a TVL module (structural, operational, chance checks).

```
tvl-measure-validate spec/examples/rag-support-bot.tvl.yml \
  spec/configurations/rag-support-bot.config.yml \
  spec/measurements/rag-support-bot.measure.yml --json
```

- Canonical measurement bundles use `objective_values` with `samples` or `mean/std/n`,
  plus `chance_outcomes` with `violations` and `trials`.
- Legacy top-level `objectives` and `chance` fields are still parsed with deprecation warnings.

- Exit 0: all checks pass
- Exit 2: structural/operational/chance violation or schema failure
