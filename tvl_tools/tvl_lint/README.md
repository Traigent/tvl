# tvl-lint

Static checks for TVL modules. Reuses the normative lints (duplicate TVARs, band validation, promotion policy coverage, exploration sanity) without running the JSON Schema validator. A TVAR is a tuned variable: a controllable setting that a module declares.

```
tvl-lint spec/examples/rag-support-bot.tvl.yml --format json
```

- Exit 0: lints pass
- Exit 2: any lint issue except severity `info`, or a parse error
