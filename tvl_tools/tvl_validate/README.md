# tvl-validate

Schema validation plus normative lints for TVL modules. Runs the JSON Schema checker and applies targeted checks (duplicate TVARs, non-linear constraints, band targets (the acceptable `[low, high]` range of a banded objective), promotion policy coverage, exploration budgets). A TVAR is a tuned variable: a controllable setting that a module declares.

```
tvl-validate spec/examples/rag-support-bot.tvl.yml --format json
```

- Exit 0: schema and lints pass
- Exit 2: schema failure, any lint issue except severity `info`, or a parse error
