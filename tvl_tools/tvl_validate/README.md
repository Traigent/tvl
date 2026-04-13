# tvl-validate

Schema validation plus normative lints for TVL modules. Runs the JSON Schema checker and applies targeted checks (duplicate TVARs, non-linear constraints, band targets, promotion policy coverage, exploration budgets).

```
tvl-validate spec/examples/rag-support-bot.yml --json
```

- Exit 0: schema and lints pass
- Exit 2: schema or lint failure
