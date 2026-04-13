# tvl-lint

Static checks for TVL modules. Reuses the normative lints (duplicate TVARs, band validation, promotion policy coverage, exploration sanity) without running the JSON Schema validator.

```
tvl-lint spec/examples/rag-support-bot.yml --json
```

- Exit 0: lints pass
- Exit 2: lint failures or parse errors
