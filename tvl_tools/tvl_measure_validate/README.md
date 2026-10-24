# tvl-measure-validate

Validates a configuration together with a measurement bundle against a TVL module (structural, operational, chance checks). Structural checks test the configuration against the module's domains and structural constraints. Operational checks test each observed objective value against its band or its SLO (service-level objective) `threshold`: a minimized objective fails above the threshold, a maximized one below it. Chance checks test whether the evidence bounds each chance constraint's violation rate.

```
tvl-measure-validate spec/examples/rag-support-bot.tvl.yml \
  spec/configurations/rag-support-bot.config.yml \
  spec/measurements/rag-support-bot.measure.yml --json
```

- Canonical measurement bundles use `objective_values` with `samples` or `mean`/`std`/`n` (mean, standard deviation and number of observations),
  plus `chance_outcomes` with `violations` and `trials`.
- Legacy top-level `objectives` and `chance` fields are still parsed with deprecation warnings.

- Exit 0: all checks pass
- Exit 2: structural/operational/chance violation, schema failure, or (for a module that uses requirements, monitors or responses) a bundle that is not promotion-ready (it lacks the evidence the promotion gate needs, such as enough observations; this says nothing about whether the candidate deserves promotion)
