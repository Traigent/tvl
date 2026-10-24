# tvl-config-validate

Validates a configuration assignment against a TVL module (schema + structural constraints: rules over the module's tuned variables that restrict which configurations are allowed).

```
tvl-config-validate spec/examples/rag-support-bot.tvl.yml spec/configurations/rag-support-bot.config.yml --json
```

- Exit 0: configuration satisfies domains and structural constraints
- Exit 5: invalid configuration (schema/domain/constraint failure), or a TVL error such as an unreadable module or configuration
