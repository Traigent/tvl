# Phase 6 Validation Examples — RFC 0001 (cvars + policies)

Counterexample/conformance fixtures produced by the RFC 0001 model-checking
packet (`tests/model_checking/`). They are the **executable acceptance bar for
the validators packet**: the Phase 4 grammar/schema/lint changes are done when
every fixture below produces exactly its expected diagnostic.

> **Status note (forward fixtures).** The 1.1 surface (`cvars`, `policies`,
> `require_calibration`, `scope`) is not yet in `tvl.schema.json`, so fixtures
> using it intentionally FAIL schema validation today. The two
> `namespace-prefix-collision-*` fixtures and the lint/SAT-level properties are
> checkable now (the model suite does so at dict level, bypassing the schema).

| Example | Expected outcome after Phase 4 |
| --- | --- |
| `cvar-policies-happy.tvl.yml` | VALID — the conformance-positive 1.1 module (RFC §3.9) |
| `cvar-shadows-tvar.tvl.yml` | ERROR `cvar_shadows_tvar` (binding partition, §3.1) |
| `cvar-missing-parent-ref.tvl.yml` | ERROR `missing_ref` (`depends_on` → no TVAR, §3.7(4)) |
| `gate-threshold-not-cvar.tvl.yml` | ERROR `missing_ref` kind-mismatch (gate threshold must be a CVAR, §3.8) |
| `cascade-arity-violation.tvl.yml` | ERROR `cascade_arity` (\|gates\| ≠ \|stages\| − 1, §3.8) |
| `duplicate-stage.tvl.yml` | ERROR `duplicate_stage` (§3.8) |
| `cvar-in-structural-constraint.tvl.yml` | ERROR `cvar_in_structural_constraint` (precise, not `undeclared_tvar`); SAT encoding contains only TVARs (P5) |
| `namespace-prefix-collision-error.tvl.yml` | ERROR `namespace_prefix_collision` (module uses 1.1 constructs, §3.7(5)) |
| `namespace-prefix-collision-legacy-warning.tvl.yml` | WARNING only — pure-1.0 module stays VALID (P1, §3.7(5)) |

Dynamic semantics (resolver rejections R1–R8, certificate subject/freshness
validity, strict-promotion fail-closed, cascade execution) are not expressible
as static module fixtures; they are verified by the small-scope model suite in
`tests/model_checking/` and, for the runtime, by the SDK features
(`FR-SDK-KNOBS-CVARS-V1`, `FR-SDK-FAIL-CLOSED-PROMOTION-V1`).
