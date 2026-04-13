# tvl-config-validate

Validates a configuration assignment against a TVL module (schema + structural constraints).

```
tvl-config-validate spec/examples/rag-support-bot.yml spec/configurations/rag-support-bot.config.yml --json
```

- Exit 0: configuration satisfies domains and structural constraints
- Exit 2: invalid configuration (schema/domain/constraint failure)
