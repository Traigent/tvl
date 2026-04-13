# Phase 1A Validation Examples

These examples exercise the new typed-surface checks implemented in Phase 1A. Run `tvl-lint` against each file to inspect the diagnostics.

| Example | Highlights |
| --- | --- |
| `structural-type-errors.tvl.yml` | Undeclared TVAR usage, enum literal outside its domain, boolean compared to an integer |
| `derived-violations.tvl.yml` | Derived constraint referencing TVAR symbols and using non-linear arithmetic |
| `float-equality-warning.tvl.yml` | Floating-point equality warning on structural constraints |

```bash
tvl-lint spec/examples/validation-phase1a/structural-type-errors.tvl.yml
```

All examples include the minimum viable module blocks (module, environment, evaluation_set, tvars, objectives, promotion_policy) so they pass schema validation and surface only the intended issues.
