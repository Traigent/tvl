# Schema Reference

Machine-readable schemas:

- `spec/grammar/tvl.schema.json` — TVL module definitions
- `spec/grammar/tvl-configuration.schema.json` — configuration assignments
- `spec/grammar/tvl-measurement.schema.json` — measurement bundles

Use `tvl-validate` for modules, `tvl-config-validate` for configurations, and `tvl-measure-validate` for measurement bundles.

Environment note for TVL modules:

- `environment.bindings` pins opaque deployment references such as retriever indexes, gateway regions, or catalog versions.
- `environment.context` carries numeric environment facts that operational preconditions may check through `env.context.*`.
- `environment` contains `snapshot_id`, optional `bindings`, and optional `context`.

Objective note for TVL modules:

- `objectives[*].metric_ref` is an optional stable metric identifier resolved by the evaluation harness.
- Prefer declarative IDs such as `metrics.answer_accuracy.v1`, not implementation-specific function pointers.

For the verifier model behind SAT/UNSAT, structural vs operational checks, and promotion-evidence tooling, see:

- [Semantics and Verification Reference](/specification/verification-reference)
- [Constraint Language Reference](/specification/constraint-language)
