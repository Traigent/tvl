# TVL Error Code Catalog

This document provides a normative catalog of all diagnostic codes emitted by TVL tooling. Each code follows the pattern `{category}_{description}` and includes severity level, explanation, and remediation guidance.

## Error Severity Levels

| Severity | Meaning | Effect |
|----------|---------|--------|
| `error` | Fatal validation failure | Blocks execution; module is rejected |
| `warning` | Suspicious but valid pattern | Module accepted; user should review |

---

## Declaration Errors (TVARs)

### `duplicate_tvar`
- **Severity**: error
- **Description**: A TVAR name is declared multiple times in the `tvars` array.
- **Example**: Two entries with `name: temperature`
- **Remediation**: Remove duplicate declarations or use distinct names.

### `invalid_tvar_name`
- **Severity**: error
- **Description**: TVAR declaration has missing or empty `name` field.
- **Example**: `{ type: int, domain: [1,2,3] }` (missing name)
- **Remediation**: Add a valid identifier as `name`.

### `missing_tvar_type`
- **Severity**: error
- **Description**: TVAR declaration lacks a `type` field.
- **Example**: `{ name: x, domain: [1,2,3] }` (missing type)
- **Remediation**: Add `type: int|float|bool|enum[str]|tuple[...]|callable[ProtoId]`.

### `unsupported_tvar_type`
- **Severity**: error
- **Description**: TVAR uses an unrecognized type string.
- **Example**: `type: string` (should be `enum[str]`)
- **Remediation**: Use a supported type: `bool`, `int`, `float`, `enum[T]`, `tuple[T*]`, `callable[ProtoId]`.

---

## Domain Errors

### `empty_domain`
- **Severity**: error
- **Description**: TVAR domain resolves to an empty set after specialization.
- **Example**: `domain: []` for an enum TVAR
- **Remediation**: Ensure domain contains at least one valid value.

### `missing_domain`
- **Severity**: error
- **Description**: TVAR lacks required domain specification.
- **Example**: `{ name: x, type: int }` (missing domain)
- **Remediation**: Add `domain: [values]` or `domain: { range: [min, max] }`.

### `invalid_bool_domain`
- **Severity**: error
- **Description**: Boolean TVAR domain contains non-boolean values.
- **Example**: `domain: [true, "yes"]`
- **Remediation**: Use only `true` and/or `false`.

### `invalid_numeric_domain`
- **Severity**: error
- **Description**: Numeric TVAR domain contains non-numeric values.
- **Example**: `domain: [1, 2, "three"]` for `type: int`
- **Remediation**: Ensure all domain values are valid numbers for the declared type.

### `invalid_range_domain`
- **Severity**: error
- **Description**: Range domain has invalid format or bounds.
- **Example**: `domain: { range: [5, 1] }` (min > max)
- **Remediation**: Specify `range: [min, max]` where `min <= max` with numeric bounds.

### `unsupported_domain_registry`
- **Severity**: error
- **Description**: Registry-backed domain used but not yet supported by linter.
- **Example**: `domain: { registry: model_catalog }`
- **Remediation**: Use explicit enumeration until registry support is available.

---

## Structural Constraint Errors

### `undeclared_tvar`
- **Severity**: error
- **Description**: Structural constraint references a TVAR not declared in `tvars`.
- **Example**: `expr: "unknown_var = true"` when `unknown_var` is not declared
- **Remediation**: Declare the TVAR or fix the typo in the constraint.

### `constraint_value_out_of_domain`
- **Severity**: error
- **Description**: Constraint literal is outside the TVAR's declared domain.
- **Example**: `expr: "agent = 'enterprise'"` when domain is `["mini", "pro"]`
- **Remediation**: Use a value within the declared domain.

### `constraint_type_mismatch`
- **Severity**: error
- **Description**: Constraint compares incompatible types.
- **Example**: `expr: "use_examples = 42"` when `use_examples` is boolean
- **Remediation**: Match the literal type to the TVAR's declared type.

### `constraint_operator_type_mismatch`
- **Severity**: error
- **Description**: Operator is invalid for the TVAR's type.
- **Example**: `expr: "agent >= 'mini'"` (comparison on enum)
- **Remediation**: Use equality for enums; comparisons only for numeric types.

### `invalid_structural_expression`
- **Severity**: error
- **Description**: Structural constraint expression cannot be parsed.
- **Example**: `expr: "x ==="` (malformed syntax)
- **Remediation**: Fix the expression syntax per DNF grammar.

### `invalid_constraint_expression`
- **Severity**: error
- **Description**: Constraint expression is not a string.
- **Example**: `expr: 123` (should be string)
- **Remediation**: Wrap expression in quotes.

### `non_linear_structural`
- **Severity**: error
- **Description**: Structural constraint contains non-linear operators.
- **Example**: `expr: "x * y = 10"` (multiplication not allowed)
- **Remediation**: Remove `*`, `/`, `^` operators; use only linear arithmetic.

### `unsupported_structural_literal`
- **Severity**: error
- **Description**: Constraint literal uses unsupported syntax.
- **Example**: Complex nested expressions not in DNF form
- **Remediation**: Simplify to supported atom forms (equality, comparison, range, membership).

### `invalid_interval`
- **Severity**: error
- **Description**: Interval bounds are not valid numbers.
- **Example**: `expr: "'a' <= x <= 'b'"`
- **Remediation**: Use numeric bounds for intervals.

### `unsupported_strict_interval`
- **Severity**: error
- **Description**: Strict inequality (`<`) used in interval for integer TVAR.
- **Example**: `expr: "1 < int_var <= 5"` (use `>=` for integers)
- **Remediation**: Use non-strict bounds (`<=`, `>=`) for integer TVARs.

### `float_equality`
- **Severity**: warning
- **Description**: Floating-point equality comparison may be unstable.
- **Example**: `expr: "temperature = 0.5"` where temperature is float
- **Remediation**: Consider using range constraints instead of exact equality.

---

## Derived Constraint Errors

### `derived_references_tvar`
- **Severity**: error
- **Description**: Derived constraint references a TVAR (should use environment symbols only).
- **Example**: `require: "max_calls <= 2"` when `max_calls` is a TVAR
- **Remediation**: Move TVAR constraints to `structural`; use only environment symbols in `derived`.

### `non_linear_derived`
- **Severity**: error
- **Description**: Derived constraint contains non-linear operators.
- **Example**: `require: "cost * quantity <= 100"`
- **Remediation**: Use only linear arithmetic (affine expressions).

### `derived_invalid_symbol_reference`
- **Severity**: error
- **Description**: Operational precondition references something other than `env.context.*`.
- **Example**: `require: "daily_budget_remaining >= 10"` or `require: "env.context.service_price_usd <= 1.5"`
- **Remediation**: Put numeric operational symbols under `environment.context` and reference them as `env.context.<name>`.

---

## Objective Errors

### `legacy_objective_epsilon`
- **Severity**: warning
- **Description**: Objective uses deprecated `epsilon` field.
- **Example**: `{ name: quality, metric_ref: metrics.quality.v1, direction: maximize, epsilon: 0.01 }`
- **Remediation**: Move epsilon to `promotion_policy.min_effect.quality`.

### `invalid_band_target`
- **Severity**: error
- **Description**: Banded objective target has invalid format.
- **Example**: `band: { target: [1, "high"] }`
- **Remediation**: Use `target: [low, high]` with numeric values or `{ center: num, tol: num }`.

### `invalid_band_bounds`
- **Severity**: error
- **Description**: Banded objective has low >= high.
- **Example**: `band: { target: [10, 5] }`
- **Remediation**: Ensure low < high.

### `invalid_band_center_tol`
- **Severity**: error
- **Description**: Banded objective center/tol are not numbers.
- **Example**: `band: { target: { center: "middle", tol: 5 } }`
- **Remediation**: Use numeric values for center and tol.

### `invalid_band_tolerance`
- **Severity**: error
- **Description**: Banded objective tolerance is not positive.
- **Example**: `band: { target: { center: 100, tol: 0 } }`
- **Remediation**: Set tol > 0.

### `missing_band_target`
- **Severity**: error
- **Description**: Banded objective lacks target specification.
- **Example**: `{ name: length, band: { test: TOST, alpha: 0.05 } }`
- **Remediation**: Add `target: [low, high]` or `target: { center: num, tol: num }`.

### `invalid_band_alpha`
- **Severity**: error
- **Description**: Banded objective alpha is not in valid range.
- **Example**: `band: { alpha: 1.5 }`
- **Remediation**: Set alpha in (0, 1].

### `invalid_band_test`
- **Severity**: error
- **Description**: Banded objective uses unsupported test.
- **Example**: `band: { test: "t-test" }`
- **Remediation**: Use `test: TOST` (only supported test).

---

## Promotion Policy Errors

### `invalid_alpha`
- **Severity**: error
- **Description**: Policy alpha is not a positive number.
- **Example**: `alpha: -0.05` or `alpha: "five percent"`
- **Remediation**: Set alpha to a positive number (typically 0.05).

### `invalid_dominance`
- **Severity**: error
- **Description**: Unsupported dominance relation specified.
- **Example**: `dominance: "pareto"` (should be `epsilon_pareto`)
- **Remediation**: Use `dominance: epsilon_pareto`.

### `missing_min_effect`
- **Severity**: error
- **Description**: Objective lacks entry in `min_effect` map.
- **Example**: `min_effect: { quality: 0.01 }` when `latency` objective exists
- **Remediation**: Add epsilon entry for every declared objective.

### `invalid_min_effect`
- **Severity**: error
- **Description**: Epsilon value is not a non-negative number.
- **Example**: `min_effect: { quality: -0.01 }`
- **Remediation**: Set epsilon >= 0.

### `duplicate_chance_constraint`
- **Severity**: error
- **Description**: Chance constraint name appears multiple times.
- **Example**: Two entries with `name: safety_rate`
- **Remediation**: Use unique names for each chance constraint.

### `invalid_chance_confidence`
- **Severity**: error
- **Description**: Chance constraint confidence not in valid range.
- **Example**: `confidence: 1.5` or `confidence: 0`
- **Remediation**: Set confidence in (0, 1].

---

## Exploration Errors

### `missing_strategy`
- **Severity**: error
- **Description**: Exploration lacks `strategy.type` field.
- **Example**: `exploration: { budgets: { max_trials: 100 } }`
- **Remediation**: Add `strategy: { type: random|grid|tpe|cmaes|nsga2 }`.

### `invalid_max_trials`
- **Severity**: error
- **Description**: max_trials is not a positive integer.
- **Example**: `budgets: { max_trials: 0 }` or `max_trials: "hundred"`
- **Remediation**: Set max_trials to a positive integer.

### `invalid_parallelism`
- **Severity**: error
- **Description**: max_parallel_trials is not a positive integer.
- **Example**: `parallelism: { max_parallel_trials: -1 }`
- **Remediation**: Set max_parallel_trials to a positive integer.

### `invalid_convergence_threshold`
- **Severity**: error
- **Description**: Hypervolume convergence threshold is not positive.
- **Example**: `convergence: { metric: hypervolume_improvement, threshold: 0 }`
- **Remediation**: Set threshold > 0.

### `invalid_convergence_window`
- **Severity**: error
- **Description**: Convergence window is not a positive integer.
- **Example**: `convergence: { metric: hypervolume_improvement, window: 0 }`
- **Remediation**: Set window to a positive integer.

---

## Schema Validation Errors

### `schema_error`
- **Severity**: error
- **Description**: Module fails JSON Schema validation.
- **Example**: Missing required field `tvl.module`
- **Remediation**: Ensure module conforms to `tvl.schema.json`.

---

## Formal Verification Warnings

These warnings indicate that the module uses features outside the formally verified TVL subset. The module may still be valid and functional, but the formal soundness guarantees (Theorem 8.1, etc.) do not apply.

### `unverifiable_registry_domain`
- **Severity**: warning
- **Code**: W6001
- **Description**: Module uses a registry domain, which is outside the formally verified subset.
- **Example**: `domain: { registry: model_catalog, filter: "version >= 2.0" }`
- **Impact**: SMT encoding soundness (Theorem 8.1) does not apply to this module.
- **Formal Property**: Registry domains have undefined `resolve(E_τ, R)` semantics.
- **Remediation**: For formal guarantees, resolve the registry to an explicit enum domain before validation.

### `unverifiable_callable_type`
- **Severity**: warning
- **Code**: W6002
- **Description**: Module uses a callable type, which is outside the formally verified subset.
- **Example**: `type: callable[Scorer]`
- **Impact**: Type safety theorems do not apply to callable-typed TVARs.
- **Formal Property**: "Implements protocol" is not formally defined.
- **Remediation**: For formal guarantees, replace with enum type listing known implementations.

### `inadequate_precision`
- **Severity**: warning
- **Code**: W6003
- **Description**: Float domain has values that collide under the current precision factor.
- **Example**: `domain: { range: [0.0001, 0.001], resolution: 0.0001 }` with precision P=1000
- **Impact**: SMT encoding soundness (Theorem 8.1) does not hold; constraint checking may be incorrect.
- **Formal Property**: Domain is not precision-aligned per Definition 8.5.
- **Remediation**: Increase precision factor (--precision=N) or use coarser resolution.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (no errors) |
| 1 | Runtime/internal error |
| 2 | Validation errors or parse failures |

---

## Quick Reference Table

| Code | Severity | Category | Summary |
|------|----------|----------|---------|
| `duplicate_tvar` | error | Declaration | Duplicate TVAR name |
| `invalid_tvar_name` | error | Declaration | Missing TVAR name |
| `missing_tvar_type` | error | Declaration | Missing type |
| `unsupported_tvar_type` | error | Declaration | Unknown type |
| `empty_domain` | error | Domain | Empty domain |
| `missing_domain` | error | Domain | Missing domain |
| `invalid_bool_domain` | error | Domain | Bad boolean domain |
| `invalid_numeric_domain` | error | Domain | Bad numeric domain |
| `invalid_range_domain` | error | Domain | Bad range format |
| `unsupported_domain_registry` | error | Domain | Registry unsupported |
| `undeclared_tvar` | error | Structural | Unknown TVAR |
| `constraint_value_out_of_domain` | error | Structural | Value outside domain |
| `constraint_type_mismatch` | error | Structural | Type mismatch |
| `constraint_operator_type_mismatch` | error | Structural | Wrong operator |
| `invalid_structural_expression` | error | Structural | Parse error |
| `invalid_constraint_expression` | error | Structural | Non-string expr |
| `non_linear_structural` | error | Structural | Non-linear expr |
| `unsupported_structural_literal` | error | Structural | Unsupported literal |
| `invalid_interval` | error | Structural | Bad interval |
| `unsupported_strict_interval` | error | Structural | Strict bound on int |
| `float_equality` | warning | Structural | Float equality |
| `derived_references_tvar` | error | Derived | TVAR in derived |
| `non_linear_derived` | error | Derived | Non-linear derived |
| `legacy_objective_epsilon` | warning | Objective | Deprecated epsilon |
| `invalid_band_target` | error | Objective | Bad band target |
| `invalid_band_bounds` | error | Objective | Bad band bounds |
| `invalid_band_center_tol` | error | Objective | Bad center/tol |
| `invalid_band_tolerance` | error | Objective | Non-positive tol |
| `missing_band_target` | error | Objective | Missing band target |
| `invalid_band_alpha` | error | Objective | Bad band alpha |
| `invalid_band_test` | error | Objective | Unsupported test |
| `invalid_alpha` | error | Policy | Bad policy alpha |
| `invalid_dominance` | error | Policy | Bad dominance |
| `missing_min_effect` | error | Policy | Missing epsilon |
| `invalid_min_effect` | error | Policy | Bad epsilon value |
| `duplicate_chance_constraint` | error | Policy | Duplicate name |
| `invalid_chance_confidence` | error | Policy | Bad confidence |
| `missing_strategy` | error | Exploration | No strategy type |
| `invalid_max_trials` | error | Exploration | Bad max_trials |
| `invalid_parallelism` | error | Exploration | Bad parallelism |
| `invalid_convergence_threshold` | error | Exploration | Bad threshold |
| `invalid_convergence_window` | error | Exploration | Bad window |
| `schema_error` | error | Schema | JSON Schema violation |
| `unverifiable_registry_domain` | warning | Formal | Registry domain used |
| `unverifiable_callable_type` | warning | Formal | Callable type used |
| `inadequate_precision` | warning | Formal | Float precision too low |
