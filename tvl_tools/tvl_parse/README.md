# tvl-parse

Parses a TVL module YAML file and prints the raw AST (YAML → JSON).

```
tvl-parse spec/examples/rag-support-bot.tvl.yml --json
```

- Exit 0: YAML parsed with a mapping at the top level (schema validation is separate)
- Exit 2: unreadable input, malformed YAML, or a non-mapping top level
