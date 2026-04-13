# tvl-parse

Parses a TVL module YAML file and prints the raw AST (YAML → JSON).

```
tvl-parse spec/examples/rag-support-bot.yml --json
```

- Exit 0: parse succeeded
- Exit 2: parse/schema error
