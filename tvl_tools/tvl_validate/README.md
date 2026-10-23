# tvl-validate

Schema validation plus normative lints for TVL modules. Runs the JSON Schema checker and applies targeted checks (duplicate TVARs, non-linear constraints, band targets, promotion policy coverage, exploration budgets).

```
tvl-validate spec/examples/rag-support-bot.tvl.yml --json
```

- Exit 0: schema passes and no error-severity lint issues
- Exit 2: schema or lint failure

Warning-only results exit 0 with `ok: true`; warnings remain in the output. An issue without a severity is treated as an error.
