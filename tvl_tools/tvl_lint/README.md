# tvl-lint

Static checks for TVL modules. Reuses the normative lints (duplicate TVARs, band validation, promotion policy coverage, exploration sanity) without running the JSON Schema validator.

```
tvl-lint spec/examples/rag-support-bot.tvl.yml --json
```

- Exit 0: no error-severity lint issues
- Exit 2: lint failures or parse errors

Warning-only results exit 0 with `ok: true`; warnings remain in the output. An issue without a severity is treated as an error.
