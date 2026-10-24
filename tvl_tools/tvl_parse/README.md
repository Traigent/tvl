# tvl-parse

Parses a TVL module YAML file and prints the raw AST (YAML → JSON).

```
tvl-parse spec/examples/rag-support-bot.tvl.yml --format json
```

- Exit 0: parse succeeded
- Exit 2: the file is missing or is not valid YAML. `tvl-parse` does not check the TVL schema; use `tvl-validate` for that.
