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

### `duplicate_domain_value`
- **Severity**: error
- **Description**: An enumerated TVAR domain lists the same member more than once. Repeated members silently collapse into one choice, which inflates the apparent domain size and makes encoding ambiguous.
- **Example**: `domain: ["gpt-4o", "gpt-4o"]`
- **Remediation**: Remove the repeated value.

### `invalid_enum_domain`
- **Severity**: error
- **Description**: A TVAR declared `enum[str]`, `enum[int]` or `enum[float]` lists a domain member whose type does not match the element type. `enum[str]` accepts strings only; `enum[int]` accepts integers; `enum[float]` accepts integers and floats. Booleans are never numbers, and strings are never converted, so `"3"` is not an `int`. YAML `3.0` is a float, so it is rejected in `enum[int]`. The message names the TVAR and the offending values.
- **Example**: `type: enum[int]` with `domain: [three, 4]`
- **Remediation**: Change the member to the declared element type, or change the declared type.
- **Note**: The schema enforces member types for direct arrays and `domain.set`, so module loaders used by configuration and structural checks also reject mismatches. Registry references are unchanged. JSON Schema treats integral numbers such as `3.0` as integers; schema-only consumers accept this representation in `enum[int]`, while the lint rejects the Python float literal.

### `invalid_tuple_domain`
- **Severity**: error
- **Description**: A tuple TVAR domain uses the `components` form, but `components` is not a non-empty list.
- **Example**: `type: tuple[int, int]` with `domain: { components: [] }`
- **Remediation**: List at least one component domain under `components`.

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

### `malformed_structural_constraint`
- **Severity**: error
- **Description**: A `constraints.structural` entry does not have the required shape. Each entry must be an object holding either `when` and `then`, or a single `expr`. A non-object entry, an entry with only one of `when`/`then`, and an entry with unrecognised keys are rejected, because the constraint would otherwise be silently ignored. An entry that mixes an incomplete `when`/`then` with `expr` is rejected by the JSON Schema; the lint does not yet flag that form.
- **Example**: `structural: ["model = 'gpt-4o'"]` (a bare string) or `{ when: "zero_shot = true" }` (no `then`)
- **Remediation**: Write each entry as `{ when: ..., then: ... }` or `{ expr: ... }`.

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

### `derived_references_bindings`
- **Severity**: error
- **Description**: An operational precondition references `env.bindings.*`. Bindings are opaque deployment references (such as a region name or an index id), not numeric operational symbols.
- **Example**: `require: "env.bindings.llm_gateway <= 1"`
- **Remediation**: Put the numeric value under `environment.context` and reference it as `env.context.<name>`.

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

### `empty_objectives`
- **Severity**: error
- **Description**: The module declares no objectives. At least one objective is required.
- **Example**: `objectives: []`
- **Remediation**: Declare at least one objective with a `direction` (or a `band`).

### `duplicate_objective`
- **Severity**: error
- **Description**: Two objectives share the same `name`.
- **Example**: Two entries with `name: quality`
- **Remediation**: Give each objective a unique name.

### `invalid_direction`
- **Severity**: error
- **Description**: An objective without a `band` has a `direction` other than `maximize` or `minimize`.
- **Example**: `{ name: quality, direction: up }`
- **Remediation**: Use `direction: maximize` or `direction: minimize`.

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
- **Remediation**: Set confidence strictly between 0 and 1.
### `unknown_min_effect_objective`
- **Severity**: error
- **Description**: A key in `promotion_policy.min_effect` does not name a declared objective.
- **Example**: `min_effect: { latency: 0.1 }` when no objective is named `latency`
- **Remediation**: Rename the key to match a declared objective, or declare the objective.

### `invalid_chance_threshold`
- **Severity**: error
- **Description**: A chance constraint `threshold` is not a number in [0, 1].
- **Example**: `threshold: 1.5`
- **Remediation**: Set `threshold` to a violation-rate bound between 0 and 1.

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

## Calibrated Variable Errors (TVL 1.1)

These codes come from the `cvars` block introduced by RFC 0001 (`formalization/rfc-0001-knob-bindings-cvars-policies.md`). A calibrated variable (CVAR) is governed but never searched: it does not enter the configuration space or structural SAT.

### `invalid_cvars`
- **Severity**: error
- **Description**: `cvars` is present but is not a list of declarations.
- **Example**: `cvars: { name: router.margin_threshold }`
- **Remediation**: Declare `cvars` as a list of declaration objects.

### `invalid_cvar_decl`
- **Severity**: error
- **Description**: An entry in `cvars` is not an object.
- **Example**: `cvars: ["router.margin_threshold"]`
- **Remediation**: Replace the entry with an object that has `name`, `type`, and `calibration`.

### `invalid_cvar_name`
- **Severity**: error
- **Description**: A CVAR has a missing or invalid `name`. Names on the 1.1 surfaces are ASCII dotted identifiers: letters, digits and underscores, with no hyphens and no empty segments.
- **Example**: `name: "router margin"`
- **Remediation**: Use an identifier such as `router.margin_threshold`.

### `duplicate_cvar`
- **Severity**: error
- **Description**: A CVAR name is declared more than once.
- **Example**: Two `cvars` entries with `name: router.margin_threshold`
- **Remediation**: Remove the duplicate or rename one declaration.

### `cvar_shadows_tvar`
- **Severity**: error
- **Description**: A CVAR uses the same name as a TVAR. TVARs, CVARs, and policies share one declaration namespace.
- **Example**: A TVAR `model` and a CVAR `model`
- **Remediation**: Rename one of the two declarations.

### `unsupported_cvar_type`
- **Severity**: error
- **Description**: A CVAR `type` is not `bool`, `int`, `float`, or `enum[...]`. Tuple and callable CVARs are deferred.
- **Example**: `type: tuple[int, int]`
- **Remediation**: Use a supported scalar or enum type.

### `cvar_missing_source`
- **Severity**: error
- **Description**: A CVAR has no `calibration.source` string naming the evidence pool its value is fit from.
- **Example**: `calibration: { signal: vote_margin }`
- **Remediation**: Add `calibration.source`.

### `missing_ref`
- **Severity**: error
- **Description**: A namespace reference does not resolve to a declaration of the required kind. It is raised for a CVAR `calibration.depends_on` entry that is not a declared TVAR, for a policy gate `threshold` that is not a declared CVAR, and for a composite `threshold` or `cardinality` that does not resolve (see the composite section).
- **Example**: `calibration: { source: pool, depends_on: [no_such_tvar] }`
- **Remediation**: Declare the referenced name, fix the typo, or reference a declaration of the right kind.

### `invalid_cvar_governance`
- **Severity**: error
- **Description**: `governance.require_calibration` on a CVAR is not a boolean.
- **Example**: `governance: { require_calibration: "yes" }`
- **Remediation**: Use `true` or `false`.

### `cvar_in_structural_constraint`
- **Severity**: error
- **Description**: A structural constraint references a CVAR. CVARs are governed but not searched, so they cannot appear in the structural constraint set.
- **Example**: `expr: "router.margin_threshold <= 0.5"`
- **Remediation**: Constrain a TVAR instead, or substitute the CVAR's value as a constant.

---

## Operational Policy Errors (TVL 1.1)

These codes come from the `policies` block introduced by RFC 0001. Policies are operational declarations; the first supported strategy is `cascade`. Several of these codes are shared with composite cascades (see below).

### `invalid_policies`
- **Severity**: error
- **Description**: `policies` is present but is not a list of declarations.
- **Example**: `policies: { name: cheap_strong_cascade }`
- **Remediation**: Declare `policies` as a list of declaration objects.

### `invalid_policy_decl`
- **Severity**: error
- **Description**: An entry in `policies` is not an object.
- **Example**: `policies: ["cheap_strong_cascade"]`
- **Remediation**: Replace the entry with an object that has `name`, `kind`, `strategy`, `stages`, and `gates`.

### `invalid_policy_name`
- **Severity**: error
- **Description**: A policy has a missing or invalid `name` (see `invalid_cvar_name` for the identifier rule).
- **Example**: `name: "cheap strong"`
- **Remediation**: Use an identifier such as `cheap_strong_cascade`.

### `duplicate_policy`
- **Severity**: error
- **Description**: A policy name is declared more than once.
- **Example**: Two `policies` entries with `name: cheap_strong_cascade`
- **Remediation**: Remove the duplicate or rename one declaration.

### `policy_name_conflict`
- **Severity**: error
- **Description**: A policy uses a name that is also declared as a TVAR or a CVAR. TVARs, CVARs, and policies share one declaration namespace.
- **Example**: A policy and a CVAR both named `router.margin_threshold`
- **Remediation**: Rename the policy.

### `invalid_policy_kind`
- **Severity**: error
- **Description**: A policy `kind` is not the literal `policy`.
- **Example**: `kind: cvar`
- **Remediation**: Set `kind: policy`.

### `unknown_policy_strategy`
- **Severity**: error
- **Description**: A policy `strategy` is not in the v1 registry, which contains only `cascade`.
- **Example**: `strategy: ensemble`
- **Remediation**: Use `strategy: cascade`.

### `cascade_arity`
- **Severity**: error
- **Description**: A cascade has the wrong number of gates. A policy needs at least one stage and exactly one gate between consecutive stages, so `|gates| = |stages| - 1`. A composite cascade must satisfy `|gates| = |arms| - 1`.
- **Example**: A policy with `stages: [cheap, mid, strong]` and a single gate
- **Remediation**: Add or remove gates until the count is one less than the number of stages (or arms).

### `duplicate_stage`
- **Severity**: error
- **Description**: The same stage identifier appears more than once in a policy `stages` list, or more than once among the arms of a composite.
- **Example**: `stages: [cheap, cheap]`
- **Remediation**: Give each stage a unique identifier.

### `unknown_gate_kind`
- **Severity**: error
- **Description**: A gate `kind` is not in the registry. Policy gates must be `margin_below`. Composite cascade gates must be `margin_below` or `signal_below`.
- **Example**: A policy gate with `kind: signal_below`
- **Remediation**: Use a registered gate kind for the construct.

---

## Namespace and Scope Diagnostics (TVL 1.1)

RFC 0001 gives TVARs, CVARs, and policies one shared declaration namespace and an optional ownership `scope`.

### `invalid_scope`
- **Severity**: error
- **Description**: A declaration `scope` is not an object, has a field other than `node`, `agent`, or `workflow`, or has a value that is not a valid identifier.
- **Example**: `scope: { team: router }`
- **Remediation**: Use only `node`, `agent`, and `workflow`, each set to an identifier string.

### `scope_prefix_mismatch`
- **Severity**: warning
- **Description**: A dotted declaration name starts with a prefix that differs from its `scope.node`. The metadata is informational, but the mismatch usually signals a copy-and-paste error.
- **Example**: `name: router.margin_threshold` with `scope: { node: other }`
- **Remediation**: Make the name prefix and `scope.node` agree, or drop the redundant `scope`.

### `namespace_prefix_collision`
- **Severity**: error (warning in legacy modules)
- **Description**: A declared name is a strict dotted prefix of another declared name, which makes attribute-style access ambiguous. The diagnostic is an error when the module uses a 1.1 construct (`cvars`, `policies`, `promotion_policy.require_calibration`, or a TVAR `scope`) and a warning otherwise.
- **Example**: TVARs named `retriever` and `retriever.k`
- **Remediation**: Rename one of the declarations so that no name is a dotted prefix of another.

---

## Strict Calibration Errors (TVL 1.1)

These codes validate `promotion_policy.require_calibration`, the strict evidence mode defined by RFC 0001.

### `invalid_require_calibration`
- **Severity**: error
- **Description**: `promotion_policy.require_calibration` is not an object with a boolean `enabled` field.
- **Example**: `require_calibration: { enabled: "yes" }`
- **Remediation**: Set `enabled: true` or `enabled: false`.

### `invalid_calibration_context`
- **Severity**: error
- **Description**: `hash_covered_context` is not a list, names a key that is not a freshness-context extension key, or repeats a key. The mandatory core of the context is implicit and cannot be configured. The extension keys are `stage_versions`, `model_versions`, `budget_assumptions`, `cost_assumptions`, and `signal_inputs`.
- **Example**: `hash_covered_context: [dataset_version]`
- **Remediation**: List each extension key at most once, using only the keys above.

---

## Composite Knob Errors (TVL 1.2)

These codes come from the `composites` block introduced by RFC 0002 (`formalization/rfc-0002-composite-knobs.md`): named bundles of member knobs under a control-flow shape (`cascade`, `ensemble`, or `loop`). A composite is a namespace and expansion unit; it never binds a value. Codes shared with the 1.1 constructs (`missing_ref`, `cascade_arity`, `duplicate_stage`, `unknown_gate_kind`) are described above.

**Declarations and shape**

### `invalid_composites`
- **Severity**: error
- **Description**: `composites` is present but is not a list of declarations.
- **Example**: `composites: { name: answerer }`
- **Remediation**: Declare `composites` as a list of declaration objects.

### `invalid_composite_decl`
- **Severity**: error
- **Description**: An entry in `composites` is not an object.
- **Example**: `composites: ["answerer"]`
- **Remediation**: Replace the entry with an object that has `name`, `kind`, and the fields for that kind.

### `invalid_composite_name`
- **Severity**: error
- **Description**: A composite has a missing or invalid `name` (see `invalid_cvar_name` for the identifier rule).
- **Example**: `name: "my composite"`
- **Remediation**: Use an identifier such as `answerer`.

### `duplicate_composite`
- **Severity**: error
- **Description**: A composite name is declared more than once.
- **Example**: Two `composites` entries with `name: answerer`
- **Remediation**: Remove the duplicate or rename one declaration.

### `composite_shadows_name`
- **Severity**: error
- **Description**: A composite uses a name already declared as a TVAR, CVAR, or policy. All four share one namespace.
- **Example**: A composite named `temperature` when a TVAR `temperature` exists
- **Remediation**: Rename the composite.

### `unknown_composite_kind`
- **Severity**: error
- **Description**: A composite `kind` is not in the sealed v1 registry (`cascade`, `ensemble`, `loop`).
- **Example**: `kind: router`
- **Remediation**: Use one of the three registered kinds.

### `unknown_composite_field`
- **Severity**: error
- **Description**: A composite has a field that is unknown, or that belongs to a different kind. Composite shapes are closed.
- **Example**: A `cascade` composite with `max_iters: 3` (a loop field)
- **Remediation**: Remove the field, or change `kind` to the constructor that owns it.

### `composite_binds_value`
- **Severity**: error
- **Description**: A composite carries `value`, `default`, or `binding`. A composite never binds a value; it only groups other knobs.
- **Example**: `value: 1` on a composite
- **Remediation**: Remove the field and bind values on the member TVARs or CVARs.

### `composite_cycle`
- **Severity**: error
- **Description**: Composites nest each other cyclically, so expansion would not terminate.
- **Example**: Composite `a` has a `{ composite: b }` arm and `b` has a `{ composite: a }` arm
- **Remediation**: Break the cycle so that nesting is acyclic.

**Arms**

### `ambiguous_arm`
- **Severity**: error
- **Description**: A bare-identifier arm is always a stage, but its name is also a declared composite name.
- **Example**: An arm `voter` when a composite `voter` exists
- **Remediation**: Nest the composite with the tagged form `{ composite: voter }`, or rename the stage.

### `invalid_arm_shape`
- **Severity**: error
- **Description**: An arm is not one of the three allowed forms: a bare stage identifier, `{ stage, tuned_params? }`, or `{ composite }`. Mixing the stage and composite forms, adding unknown keys, or adding `tuned_params` to a composite-tagged arm is rejected.
- **Example**: `{ stage: s, composite: voter }`
- **Remediation**: Use exactly one of the allowed forms.

### `invalid_tuned_param`
- **Severity**: error
- **Description**: A `tuned_params` entry does not resolve to a declared TVAR. CVARs, policies, and composites are not tuned parents.
- **Example**: `tuned_params: [router.margin_threshold]` where that name is a CVAR
- **Remediation**: List only declared TVAR names.

### `missing_composite_ref`
- **Severity**: error
- **Description**: A `{ composite: name }` arm names a composite that is not declared.
- **Example**: `{ composite: ghost }`
- **Remediation**: Declare the composite or fix the name.

### `empty_arms`
- **Severity**: error
- **Description**: A cascade or ensemble declares no arms.
- **Example**: `arms: []`
- **Remediation**: Add at least one arm.

**Cascade gates and signals**

### `gate_kind_placement_mismatch`
- **Severity**: error
- **Description**: A gate kind is used under the wrong placement. `margin_below` is post-only; `signal_below` is pre-only. When `placement` is omitted it defaults to `post`.
- **Example**: A `margin_below` gate under `placement: pre`
- **Remediation**: Change the gate kind or the cascade `placement`.

### `gate_arm_incompatible`
- **Severity**: error
- **Description**: A `margin_below` gate reads vote statistics from an arm that does not produce them. The gated arm must be a stage or a `majority_vote` ensemble.
- **Example**: A `margin_below` gate whose gated arm is a `judge_max` ensemble
- **Remediation**: Gate a margin-bearing arm, or use a `signal_below` gate with a pre placement.

### `missing_gate_signal`
- **Severity**: error
- **Description**: A `signal_below` gate has no `signal` field.
- **Example**: `{ kind: signal_below, threshold: dispatch.route_threshold }`
- **Remediation**: Add `signal: { signal: <id> }`.

### `invalid_signal_use`
- **Severity**: error
- **Description**: A signal use is malformed. It must be an object `{ signal, inputs? }` where `signal` is a string and `inputs` is a list of identifiers.
- **Example**: `signal: { signal: vote_margin, inputs: draft }`
- **Remediation**: Use `signal: { signal: vote_margin, inputs: [draft] }`.

### `invalid_threshold_type`
- **Severity**: error
- **Description**: A gate, accept, or stop threshold CVAR is not `int` or `float` typed.
- **Example**: A threshold CVAR with `type: enum[str]`
- **Remediation**: Use a numeric CVAR as the threshold.

### `missing_calibration_signal`
- **Severity**: error
- **Description**: A composite uses a CVAR as a threshold, but the CVAR declares no `calibration.signal`. The composite obliges it to name the signal the construct measures.
- **Example**: A threshold CVAR with `calibration: { source: margin_eval_pool }`
- **Remediation**: Add `calibration.signal` with the signal the gate, accept, or stop reads.

### `signal_mismatch`
- **Severity**: error
- **Description**: A threshold CVAR is calibrated against a different signal than the one its construct measures, so its freshness check would be vacuous.
- **Example**: A `margin_below` gate whose threshold CVAR has `calibration.signal: other_signal` instead of `vote_margin`
- **Remediation**: Set `calibration.signal` to the signal the construct measures.

### `unbound_signal_inputs`
- **Severity**: error
- **Description**: A signal use declares `inputs`, but they are not freshness-bound. `promotion_policy.require_calibration.hash_covered_context` must include `signal_inputs`, and `promotion_policy.require_calibration.signal_inputs` must equal the use-site input list.
- **Example**: A stop signal with `inputs: [draft]` and `hash_covered_context: [model_versions]`
- **Remediation**: Add `signal_inputs` to `hash_covered_context` and set the matching `signal_inputs` list.

### `missing_composite_parent`
- **Severity**: error
- **Description**: A threshold CVAR's `calibration.depends_on` omits a TVAR that parameterizes the arm the gate observes, so the threshold would not go stale when that TVAR changes.
- **Example**: A post-cascade whose cheap arm is tuned by `cheap_model` and `temperature`, with a threshold CVAR that depends only on `cheap_model`
- **Remediation**: Add every TVAR that parameterizes the observed arm to `depends_on`.

**Ensembles**

### `cardinality_arity_mismatch`
- **Severity**: error
- **Description**: An ensemble's `cardinality` does not match its arm count. A sampling-form ensemble (exactly one arm) requires a `cardinality`; a committee-form ensemble (more than one arm) must not declare one.
- **Example**: An ensemble with one arm and no `cardinality`
- **Remediation**: Add `cardinality` to a one-arm ensemble, or remove it from a multi-arm ensemble.

### `invalid_cardinality_type`
- **Severity**: error
- **Description**: `cardinality` resolves to a declaration whose type is not `int`.
- **Example**: `cardinality: temperature` where `temperature` is a float TVAR
- **Remediation**: Reference an int-typed TVAR or CVAR.

### `unknown_aggregate_kind`
- **Severity**: error
- **Description**: An ensemble `aggregate.kind` is not `majority_vote` or `judge_max`, or an `accept.stat` is not `vote_margin` or `vote_agreement`.
- **Example**: `aggregate: { kind: weighted_vote }`
- **Remediation**: Use a registered aggregate kind and accept statistic.

### `missing_judge`
- **Severity**: error
- **Description**: A `judge_max` aggregate has no `judge` arm.
- **Example**: `aggregate: { kind: judge_max }`
- **Remediation**: Add a `judge` arm.

**Loops**

### `invalid_max_iters`
- **Severity**: error
- **Description**: A loop `max_iters` is not an integer greater than or equal to 1. A loop must be total, so it needs a finite iteration bound.
- **Example**: `max_iters: 0`
- **Remediation**: Set `max_iters` to an integer of at least 1.

### `unknown_stop_kind`
- **Severity**: error
- **Description**: A loop `stop.kind` is not in the registry (`signal_accept`, `external_accept`, `exhausted`).
- **Example**: `stop: { kind: converged }`
- **Remediation**: Use a registered stop kind.

### `missing_stop_threshold`
- **Severity**: error
- **Description**: A `signal_accept` stop has no `threshold`.
- **Example**: `stop: { kind: signal_accept, signal: { signal: draft_quality } }`
- **Remediation**: Add `threshold` naming a numeric CVAR.

### `missing_stop_signal`
- **Severity**: error
- **Description**: A `signal_accept` stop has no `signal`.
- **Example**: `stop: { kind: signal_accept, threshold: refine.stop_threshold }`
- **Remediation**: Add `signal: { signal: <id> }`.

### `missing_stop_predicate`
- **Severity**: error
- **Description**: An `external_accept` stop has no `predicate`.
- **Example**: `stop: { kind: external_accept }`
- **Remediation**: Add `predicate`.

### `stop_signal_outside_state`
- **Severity**: error
- **Description**: A stop signal reads input keys that are not declared in the loop's `state_keys`.
- **Example**: `state_keys: [draft]` with `signal: { signal: draft_quality, inputs: [other] }`
- **Remediation**: Declare each input in `state_keys`, or read only declared keys.

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

`cvars`, `policies` (RFC 0001), and `composites` (RFC 0002) are also outside the formally verified subset today: the Lean proof tree (`proofs/`) predates both RFCs and has not yet been extended to cover them. There is no lint warning for this gap yet (tracked as follow-up work); see `formalization/tvl-formal-semantics.md` §1.4 for the full disclosure.

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
- **Remediation**: Choose a precision factor that exactly aligns every declared decimal value and range step; the diagnostic reports one exact-alignment factor when it can derive one. Otherwise use an exact rational or index encoding. A factor based only on the smallest gap between values is not sufficient.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success under the tool's contract (see the 1.3 tool table below) |
| 2 | A reported issue, validation or parse failure, or an unsuccessful gate decision, as specified by the tool |

TVL tools use 0 and 2 for their documented results; exit 1 is not a defined diagnostic outcome.

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
| `duplicate_domain_value` | error | Domain | Repeated enum member |
| `invalid_enum_domain` | error | Domain | Enum member does not match `enum[T]` |
| `invalid_tuple_domain` | error | Domain | Bad tuple components |
| `malformed_structural_constraint` | error | Structural | Entry is not {when,then} or {expr} |
| `derived_references_bindings` | error | Derived | Bindings in derived |
| `empty_objectives` | error | Objective | No objectives |
| `duplicate_objective` | error | Objective | Duplicate objective name |
| `invalid_direction` | error | Objective | Bad direction |
| `unknown_min_effect_objective` | error | Policy | min_effect key not an objective |
| `invalid_chance_threshold` | error | Policy | Bad chance threshold |
| `invalid_cvars` | error | CVAR (1.1) | cvars not a list |
| `invalid_cvar_decl` | error | CVAR (1.1) | CVAR entry not an object |
| `invalid_cvar_name` | error | CVAR (1.1) | Bad CVAR name |
| `duplicate_cvar` | error | CVAR (1.1) | Duplicate CVAR |
| `cvar_shadows_tvar` | error | CVAR (1.1) | CVAR reuses a TVAR name |
| `unsupported_cvar_type` | error | CVAR (1.1) | Unsupported CVAR type |
| `cvar_missing_source` | error | CVAR (1.1) | No calibration.source |
| `missing_ref` | error | CVAR (1.1) | Reference does not resolve |
| `invalid_cvar_governance` | error | CVAR (1.1) | Bad governance flag |
| `cvar_in_structural_constraint` | error | CVAR (1.1) | CVAR in structural constraint |
| `invalid_policies` | error | Policy (1.1) | policies not a list |
| `invalid_policy_decl` | error | Policy (1.1) | Policy entry not an object |
| `invalid_policy_name` | error | Policy (1.1) | Bad policy name |
| `duplicate_policy` | error | Policy (1.1) | Duplicate policy |
| `policy_name_conflict` | error | Policy (1.1) | Policy reuses a TVAR/CVAR name |
| `invalid_policy_kind` | error | Policy (1.1) | kind is not `policy` |
| `unknown_policy_strategy` | error | Policy (1.1) | Unknown strategy |
| `cascade_arity` | error | Policy (1.1) | Wrong gate count |
| `duplicate_stage` | error | Policy (1.1) | Duplicate stage |
| `unknown_gate_kind` | error | Policy (1.1) | Unknown gate kind |
| `invalid_scope` | error | Namespace (1.1) | Bad scope |
| `scope_prefix_mismatch` | warning | Namespace (1.1) | Name prefix differs from scope.node |
| `namespace_prefix_collision` | error/warning | Namespace (1.1) | Name is a prefix of another |
| `invalid_require_calibration` | error | Calibration (1.1) | Bad require_calibration |
| `invalid_calibration_context` | error | Calibration (1.1) | Bad hash_covered_context |
| `invalid_composites` | error | Composite (1.2) | composites not a list |
| `invalid_composite_decl` | error | Composite (1.2) | Composite entry not an object |
| `invalid_composite_name` | error | Composite (1.2) | Bad composite name |
| `duplicate_composite` | error | Composite (1.2) | Duplicate composite |
| `composite_shadows_name` | error | Composite (1.2) | Composite reuses a name |
| `unknown_composite_kind` | error | Composite (1.2) | Unknown kind |
| `unknown_composite_field` | error | Composite (1.2) | Field not allowed for kind |
| `composite_binds_value` | error | Composite (1.2) | Composite binds a value |
| `composite_cycle` | error | Composite (1.2) | Cyclic nesting |
| `ambiguous_arm` | error | Composite (1.2) | Arm collides with composite |
| `invalid_arm_shape` | error | Composite (1.2) | Bad arm form |
| `invalid_tuned_param` | error | Composite (1.2) | tuned_params not a TVAR |
| `missing_composite_ref` | error | Composite (1.2) | Nested composite undeclared |
| `empty_arms` | error | Composite (1.2) | No arms |
| `gate_kind_placement_mismatch` | error | Composite (1.2) | Gate kind vs placement |
| `gate_arm_incompatible` | error | Composite (1.2) | Gated arm has no margin |
| `missing_gate_signal` | error | Composite (1.2) | signal_below without signal |
| `invalid_signal_use` | error | Composite (1.2) | Malformed signal use |
| `invalid_threshold_type` | error | Composite (1.2) | Non-numeric threshold CVAR |
| `missing_calibration_signal` | error | Composite (1.2) | Threshold CVAR has no signal |
| `signal_mismatch` | error | Composite (1.2) | Wrong calibration signal |
| `unbound_signal_inputs` | error | Composite (1.2) | Signal inputs not freshness-bound |
| `missing_composite_parent` | error | Composite (1.2) | depends_on omits arm TVAR |
| `cardinality_arity_mismatch` | error | Composite (1.2) | Cardinality vs arm count |
| `invalid_cardinality_type` | error | Composite (1.2) | Cardinality is not int |
| `unknown_aggregate_kind` | error | Composite (1.2) | Unknown aggregate/stat |
| `missing_judge` | error | Composite (1.2) | judge_max without judge |
| `invalid_max_iters` | error | Composite (1.2) | max_iters < 1 |
| `unknown_stop_kind` | error | Composite (1.2) | Unknown stop kind |
| `missing_stop_threshold` | error | Composite (1.2) | signal_accept without threshold |
| `missing_stop_signal` | error | Composite (1.2) | signal_accept without signal |
| `missing_stop_predicate` | error | Composite (1.2) | external_accept without predicate |
| `stop_signal_outside_state` | error | Composite (1.2) | Stop input not in state_keys |
| `schema_error` | error | Schema | JSON Schema violation |
| `unverifiable_registry_domain` | warning | Formal | Registry domain used |
| `unverifiable_callable_type` | warning | Formal | Callable type used |
| `inadequate_precision` | warning | Formal | Float precision too low |

---

## TVL 1.3 diagnostics

These codes belong to the TVL 1.3 requirements, monitors and responses (see the
[guide](../guides/requirements-monitors-responses.md) and the
[language reference](language.md#tvl-13-requirements-monitors-responses)). TVL 1.3 is a draft; codes can still change.

Every diagnostic has the same shape as the codes above: `{ code, message, path, severity }`. In text mode a line looks like
`[runtime_window_out_of_range] monitors.0.window.tumbling_hours: tumbling_hours 5 is outside its allowed domain`, and `path` points at the key to fix. Severity is
`error` unless marked `warning`. Warnings are reported but do not fail `tvl-validate` or `tvl-lint`: with warnings only, both print `ok: true` and exit 0.

**Reported by** says which tool in this repository can produce the code:

| Value | Tool |
|---|---|
| lint | `tvl-validate`, `tvl-lint` (and `tvl-ci-gate`, which lints every full module before deciding) |
| compose | `tvl-compose` with `--pack`, `--meet` or an overlay |
| compile | `tvl-compile-runtime` |
| gate | `tvl-measure-validate`, `tvl-ci-gate` |
| platform | defined by the draft for the platform that registers or evaluates your contract; no tool in this repository produces it |

!!! note "Message text"
    Some tools print only the code, for example `Error: requirement_weaker_than_floor`, with no path. The code, not the wording, is the stable part.

### Version and readers

| Code | Severity | Reported by | What it means | What to do |
|---|---|---|---|---|
| `unsupported_construct` | error | various tools | a tool met a 1.3 construct it does not implement (`requirements`, `monitors`, `responses`, `tvl_pack`, `monitor_outcomes`, `runtime_report`) and refused instead of ignoring it. The first construct found is named. | use a tool that supports the construct (for a pack: `tvl-validate`, `tvl-lint`, `tvl-compose`, `tvl-compile-runtime`), or remove the construct for that tool |
| `runtime_version_required` | error | lint | the document uses `requirements`, `monitors` or `responses`, or is a `tvl_pack`, and has no `tvl_version` | add `tvl_version: "1.3"` |
| `declared_version_below_constructs` | error | lint | `tvl_version` is present but is not the string `"1.3"`; an unquoted `1.3` is a number | write `tvl_version: "1.3"` with quotes |
| `runtime_unsupported_capability` | error | platform | the target platform has not enabled the monitor's kind, source, method or predicate class | change the declaration to something the platform supports, or ask the platform to enable it |
| `response_action_unsupported` | error | platform | the target platform cannot carry out a rule's action | remove the rule or pick an action the platform supports |

### Names and references

| Code | Severity | Reported by | What it means | What to do |
|---|---|---|---|---|
| `runtime_name_collision` | error | lint, compose | a duplicate name within the requirement, monitor or response namespace; a runtime name equal to a tvar, cvar, policy or composite name; or a pack name that clashes with a different module declaration | rename one of them |
| `response_rule_id_duplicate` | error | lint | two rules of one response share an `id` | give each rule a unique `id` |
| `runtime_missing_ref` | error | lint | `monitor.requirement`, `of` or `trigger.monitor` names nothing | fix the name or declare the missing item |
| `runtime_ref_kind_mismatch` | error | lint | a reference points at the wrong kind of thing: `recovery_time.of` at a monitor with no episode, `evidence_liveness.of` at a monitor with no windows, or a `trigger.event` the monitor never emits | point at the right monitor, or pick an event that monitor emits (guide, section 7) |
| `runtime_dependency_cycle` | error | lint | requirements and monitors refer to each other in a cycle | break the cycle: an obligation (`of`) must not depend on itself |

### Kinds, profiles and values

| Code | Severity | Reported by | What it means | What to do |
|---|---|---|---|---|
| `runtime_unknown_kind` | error | lint, compile | a value outside a sealed list: a requirement kind, unit, pattern, metric, event type, status, checker id or label, source, method, model, sampling mode, attribution or resolution rule, profile, phase, trigger event, `correlate_by`, `unlisted`, `mode`, approval, severity or `on_check_error`. Also an unbound customer checker or label at compile time. | use a value from the reference table; check the spelling |
| `response_unknown_action` | error | lint | `do` is not one of the nine actions; `record` is implicit and cannot be declared | use `notify`, `open_next_step`, `optimize`, `rollback`, `throttle`, `degrade`, `suspend`, `block_action` or `halt_unit` |
| `runtime_invalid_profile` | error | lint, compile | the combination of kind, source, phase and method is not allowed; a field is missing or forbidden for the monitor's role; a key of another variant is present; sampling is not allowed for the source; a stateful pattern has no `limits`; a selector field is on the wrong event; or a number cannot be read exactly | compare the monitor to the role table in the reference; the message names the role |
| `runtime_legacy_profile_override` | error | lint | under `profile: backend_v1`, a field or value other than the frozen ones | remove the field, or drop `profile: backend_v1` and declare the monitor in full |
| `runtime_rate_out_of_range` | error | lint | `max_rate` is not strictly between 0 and 1 | use a value such as `0.05` |
| `runtime_confidence_out_of_range` | error | lint | `confidence` is not strictly between 0 and 1; under `backend_v1` it is not 0.90, 0.95 or 0.99 | pick an allowed value |
| `runtime_window_out_of_range` | error | lint | `tumbling_hours` does not divide 24; under `backend_v1` it is not 1, 3, 6, 12 or 24 | use 1, 2, 3, 4, 6, 8, 12 or 24 |
| `runtime_grace_out_of_range` | error | lint | `grace_minutes` is outside 0 to 360 | use 0 to 360 |
| `runtime_min_samples_out_of_range` | error | lint | `min_samples` is outside 1 to 10,000,000 | use a value in range |
| `runtime_unresolved_fraction_out_of_range` | error | lint | `max_unresolved_fraction` is outside 0 to 0.5 | use a value in range |
| `runtime_false_alarm_budget_out_of_range` | error | lint | `false_alarm_budget` is not above 0 and at most 0.5 | use a value such as `0.05` |
| `runtime_horizon_out_of_range` | error | lint | `horizon_days` is outside 1 to 365 | use a value in range |
| `runtime_closure_windows_out_of_range` | error | lint | `closure_windows` is outside 1 to 24 | use a value in range |
| `runtime_closure_age_out_of_range` | error | lint | `closure_max_age_hours` is outside 1 to 720 | use a value in range |
| `runtime_exceeds_out_of_range` | error | lint | `exceeds` is outside its metric's domain: an integer >= 1 for latency, tokens and tool calls (1 to 600,000 under `backend_v1`), a decimal > 0 for cost | use a valid number |
| `runtime_sampling_rate_out_of_range` | error | lint | a sampling `rate` is not strictly between 0 and 1 | use a value such as `0.1` |
| `runtime_rate_floor_out_of_range` | error | lint | `rate_floor` is not strictly between 0 and 1 | use a value such as `0.5` |
| `runtime_within_hours_out_of_range` | error | lint | `within_hours` is below 1 | use an integer >= 1 |
| `runtime_max_stale_windows_out_of_range` | error | lint | `max_stale_windows` is below 1 | use an integer >= 1 |
| `runtime_within_ms_out_of_range` | error | lint | `within_ms` is below 1 | use an integer >= 1 |
| `runtime_max_count_out_of_range` | error | lint | `max_count` is below 0 | use an integer >= 0 |
| `runtime_trigger_hours_out_of_range` | error | lint | `trigger.hours` is below 1 | use an integer >= 1 |
| `runtime_repeat_after_hours_out_of_range` | error | lint | `repeat_after_hours` is below 1 | use an integer >= 1 |
| `runtime_max_repeats_out_of_range` | error | lint | `max_repeats` is below 1 | use an integer >= 1 |
| `runtime_max_active_obligations_out_of_range` | error | lint | `limits.max_active_obligations` is below 1 | use an integer >= 1 |
| `runtime_max_tracked_correlations_out_of_range` | error | lint | `limits.max_tracked_correlations` is below 1 | use an integer >= 1 |
| `runtime_burn_out_of_range` | error | lint | a burn monitor with `threshold_factor` <= 1, or with b times `max_rate` >= 1, or that can never breach at `min_samples` | choose b > 1 with b times `max_rate` < 1 and a `min_samples` that can breach |
| `runtime_zero_tolerance_inexact` | error | lint | a `zero_tolerance` violation that is a metric or a checker rather than an exact pattern | use an exact pattern, or switch to `rate_bound` |
| `runtime_zero_tolerance_incomplete` | error | lint | a `zero_tolerance` monitor declares `sampling`; a sampled window can never be complete, so `MET` would be unreachable | remove `sampling` |
| `runtime_protocol_nondeterministic` | error | lint | a protocol has two transitions for one (state, event), an event matching two alphabet entries, an undeclared state or selector, or overlapping accepting and rejecting states | make the state machine deterministic and declare every state |
| `runtime_tool_not_code_identifier` | error | lint | a selector `tool` is not a plain function or qualified name (a wildcard, a list item, a space) | name exactly one tool, such as `payments.charge` |
| `runtime_content_on_backend_source` | error | lint | a checker predicate on `backend_trace_metadata`, or a content check assigned to hosted execution | run checkers on `customer_side` or `evaluation_set` evidence |

A value of the wrong JSON type, for example a string where an integer is required, is `schema_error`, not an out-of-range code.

### Statistics and power

| Code | Severity | Reported by | What it means | What to do |
|---|---|---|---|---|
| `runtime_met_unreachable_at_min_samples` | error (warning under `backend_v1`) | lint | even with zero bad units, a window of `min_samples` units can never be `MET` at this `max_rate` and `confidence`, so no window of that size can close an episode | raise `min_samples` to at least the size in the guide's table (299 for `max_rate` 0.01 at 0.95), loosen `max_rate`, or lower `confidence` |
| `runtime_breach_unreachable_at_min_samples` | warning | lint | even with every unit bad, a window of `min_samples` units can never be `BREACHED` | raise `min_samples` |
| `chance_constraint_shadowed` | warning | lint | a promotion monitor and a 1.2 `chance_constraints` entry share a name, so the chance constraint's `Reject` still wins | remove one of them |
| `runtime_liveness_missing` | warning | lint | a primary monitor has no `evidence_liveness` requirement watching it | add an `evidence_liveness` requirement and a `source: windows` monitor for it |

### Composition and schedule

| Code | Severity | Reported by | What it means | What to do |
|---|---|---|---|---|
| `closure_unreachable` | error | lint, compose | `closure_max_age_hours * 60` is less than `closure_windows * tumbling_hours * 60 + grace_minutes + 60`, so clean windows can never be fresh enough to close an episode (also checked on the composed result) | raise `closure_max_age_hours`, or shorten the window, grace or `closure_windows` |
| `evaluation_schedule_mismatch` | error | compose | a module monitor and its floor, an overlay and its base, or two meet inputs differ in window length, grace, horizon or false-alarm budget | make the schedules identical |
| `requirement_weaker_than_floor` | error | compose | the module's monitor or obligation bound is weaker than the pack floor on a composed field (higher `max_rate`, lower `confidence`, ...) | tighten your numbers to the floor or better |
| `runtime_duplicate_key` | error | lint | two monitors have the same effective key (same predicate, source, environment, attribution, method and `threshold_factor`), or two monitors serve one obligation | keep one, or change what they measure; use a burn monitor for a second tier |
| `recovery_deadline_impossible` | error | lint, compose | `within_hours` is less than `closure_windows * tumbling_hours`, so an episode could never close in time (equal is fine; also checked on the composed result) | raise `within_hours` or shorten the window or `closure_windows` |
| `tenant_floor_outside_pack` | error | lint | a module monitor declares `applies_to: tenant_floor`, which only a pack may do | remove `applies_to`, or move the monitor into a `tvl_pack` |
| `runtime_incompatible_replacement` | error | compose | an overlay, pack or meet changed an immutable part: predicate, population, source, environment, method, sampling, `threshold_factor`, `single_producer` or `limits` | change only tightenable numbers, or declare a new requirement |
| `runtime_overlay_weakens` | error | compose | an overlay drops a base declaration or rule, loosens a number, lowers a notification severity, weakens an approval, or widens a repeat bound; the same for a module response against a same-named pack response | keep every base item and only tighten |

### Projection and compile

| Code | Severity | Reported by | What it means | What to do |
|---|---|---|---|---|
| `runtime_unresolved_alias` | error | compile | a name has no entry in the token map, the token map is missing, unreadable or malformed, or an entry breaks the one-to-one rule. The message does not say which entry. | check that the map covers every module, requirement, monitor, response, rule, environment (including the default `production`), selector `ref`, protocol state and customer checker you use |
| `runtime_unsafe_egress` | error | compile | the compiled hosted contract failed its own closed-schema self-check, or does not correspond to your module through the token map (for example a crossed or malformed reference) | check the token map entries; if the map is right, treat it as a toolchain bug. Nothing is written. |
| `schema_error` | error | lint, compile | a document fails its JSON Schema: an unknown key, a wrong type, or a missing always-required key | see the message path; for a rule written with `on:` rename it `trigger` |

### Responses

| Code | Severity | Reported by | What it means | What to do |
|---|---|---|---|---|
| `runtime_invalid_ladder` | error | lint | an action parameter is missing, not allowed for the action or ill-typed (`target` only on `rollback`, `fallback` only on `suspend` and `degrade`, `rate_floor` only on `throttle`, `severity` only on `notify`, `on_check_error` only on the guards, `max_repeats` without `repeat_after_hours`, a fingerprint that is not 64 lowercase hex characters); `trigger.hours` present without `episode_open_for`, or missing with it; an approval the action does not allow; or a remote service action on a terminal-scope event or `unit_violation` | compare the rule with the action and trigger tables in the reference; terminal events can notify, but cannot authorize a remote service action |
| `response_suspend_without_human` | error | lint | `suspend` without an explicit `approval: human`, including an omitted approval | write `approval: human` explicitly |
| `response_suspend_unconfirmed` | error | lint | `suspend` triggered by an event other than `episode_continued`, `episode_open_for` or `recovery_overdue` | trigger on one of those three events |
| `response_irreversible_without_approval` | error | lint | `optimize`, `rollback`, `throttle` or `degrade` with `approval: none` | use `standing` or `human` |
| `response_rollback_target_uncertified` | error | platform | a rollback `target` or degrade `fallback` fingerprint has no valid configuration-attributed certificate | use `last_certified` or a fingerprint that is certified |
| `response_guard_not_enforceable` | error | lint | `block_action` or `halt_unit` on a monitor whose violation is not fixed by a prefix (`bounded_response`, metric, checker), whose source is not `customer_side`, or triggered by an event other than `unit_violation` | use a guard only on `absence`, `bounded_existence`, `precedence` or `protocol`, on `unit_violation` |
| `response_on_check_error_missing` | error | lint | a guard without `on_check_error` | choose `block` (fail closed) or `allow` |
| `response_rule_repeat_unbounded` | error | lint | an action other than `notify` repeats without `max_repeats` | add `max_repeats` |

### Measurement and reports

| Code | Severity | Reported by | What it means | What to do |
|---|---|---|---|---|
| `missing_monitor_counts` | readiness issue (exit 2) | gate | a promotion monitor has no `monitor_outcomes.<monitor name>` in the candidate bundle, or its `k` is greater than `n` | supply `{ n, k }` (and `complete: true` for a zero-tolerance monitor) |
| `runtime_report_conservation` | error | platform | a window report breaks count conservation, or does not match its contract, the window grid or the sampling commitment | fix the producer of the report; the error repeats no input |

### Exit codes of the 1.3 tools

| Tool | 0 | 2 |
|---|---|---|
| `tvl-validate`, `tvl-lint` | no error (warnings allowed) | any error |
| `tvl-compose` | composed; with `--validate`, no error (warnings allowed) | any composition error, unreadable input, or a `--validate` error |
| `tvl-compile-runtime` | both files written, or token-map template printed (warnings allowed) | any error |
| `tvl-ci-gate module incumbent candidate` | `Promote` | `Reject`, `NoDecision`, not ready, or any error |
