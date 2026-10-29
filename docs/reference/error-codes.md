# TVL Error Code Catalog

This document catalogs the diagnostic codes of the module and pack linter (`tvl.lints`, run by `tvl-lint`, `tvl-validate`, `tvl-compose --validate`, `tvl-ci-gate` and `tvl-compile-runtime`), the operational checker, the composition and compilation tools, and the gate readiness codes listed below. Each entry gives the severity, an explanation and remediation guidance. Not yet listed: the codes of `tvl-config-validate` and the configuration constraint evaluator (`tvl.constraints`, `tvl.configuration`), and most measurement-bundle and gate-evidence codes (`tvl.measurement`, `tvl-ci-gate`).

A pack (`tvl_pack`) is a separate document, introduced in TVL 1.3 and declaring `tvl_version` 1.3, 1.4 or 1.5, that carries organisation floors (requirements, monitors and optional responses) that modules can only tighten; see the [runtime guide](../guides/requirements-monitors-responses.md#9-organisation-floors-with-packs).

## Error Severity Levels

| Severity | Meaning | Effect |
|----------|---------|--------|
| `error` | Fatal validation failure | Blocks execution; module is rejected |
| `warning` | Suspicious but valid pattern | The module is not invalid, but `tvl-validate`, `tvl-lint` and `tvl-compose --validate` still report `ok: false` and exit 2; `tvl-compile-runtime` allows warnings |
| `info` | Information only | Included in JSON output, and printed in the text output of `tvl-validate` and `tvl-lint`; never affects `ok` or the exit status of `tvl-validate`, `tvl-lint` or `tvl-compose --validate` |

---

## Declaration Errors (TVARs)

A TVAR (tuned variable) is one entry of the `tvars` array: a choice the module lets vary, declared with a `name`, a `type` and a `domain` of allowed values.

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
- **Remediation**: Add one supported type, for example `type: int`. The choices are `int`, `float`, `bool`, `enum[T]` with `T` one of `str`, `int` or `float`, `tuple[...]` and `callable[ProtoId]`, where `ProtoId` is a protocol identifier such as `RerankerProto`.

### `unsupported_tvar_type`
- **Severity**: error
- **Description**: TVAR uses an unrecognized type string.
- **Example**: `type: string` (should be `enum[str]`)
- **Remediation**: Use a supported type: `bool`, `int`, `float`, `enum[T]` with `T` one of `str`, `int` or `float` (for example `enum[str]`), `tuple[T1, T2, ...]` with one or more component types (for example `tuple[enum[str], float]`), or `callable[ProtoId]` with a protocol identifier (for example `callable[RerankerProto]`). See formal semantics §2.3 for the type grammar.

---

## Domain Errors

### `empty_domain`
- **Severity**: error
- **Description**: TVAR domain resolves to an empty set after specialization (turning the declared domain, such as a list, set or range, into its finite set of values; formal semantics Definition 3.6). Registry domains are resolved outside TVL, so the linter does not check them for emptiness.
- **Example**: `domain: []` for an enum TVAR; `domain: {range: [1.2, 1.8]}` for an `int` TVAR (no integer lies in the range); `{set: []}` as a tuple component
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
- **Description**: A numeric (`int` or `float`) TVAR uses a registry-backed domain (`domain: { registry: ... }`, whose values come from a named external registry; formal semantics §2.4), which the linter does not support. Registry domains on `enum`, `tuple` and `callable` TVARs are accepted and resolved later, at specialization time.
- **Example**: `{ name: max_tokens, type: int, domain: { registry: model_catalog } }`
- **Remediation**: Give the numeric TVAR an explicit `range` or value list.

### `duplicate_domain_value`
- **Severity**: error
- **Description**: A TVAR domain lists the same member more than once: an enum or callable domain, a numeric `set` or bare list, or a tuple component. Without this error, repeated members would collapse into one choice, which inflates the apparent domain size and makes encoding ambiguous.
- **Example**: `domain: ["gpt-4o", "gpt-4o"]`
- **Remediation**: Remove the repeated value.
- **Note**: The domain is a set (formal semantics Definition 3.6). `tvl-check-structural` does not report this code: it removes repeated members and checks the remaining set.

### `non_finite_domain_value`
- **Severity**: error
- **Reported by**: `tvl-validate`, `tvl-lint`
- **Description**: A TVAR domain contains NaN (not a number) or an infinity. TVL numeric domains are rationals (formal semantics Definitions 3.1-3.2), so these values are not admitted. The message names the TVAR and the value, and the path points at it. `tvl-check-structural` reports the same input as `structural_non_finite_domain`.
- **Example**: `domain: { range: [0.0, .inf] }` gives `TVAR 't' domain contains inf; ...`
- **Remediation**: Use finite bounds and values.

### `invalid_tuple_domain`
- **Severity**: error
- **Description**: A tuple TVAR domain uses the `components` form, but `components` is not a non-empty list.
- **Example**: `type: tuple[int, int]` with `domain: { components: [] }`
- **Remediation**: List at least one component domain under `components`.

---

## Structural Constraint Errors

`tvl-check-structural` decides whether the structural constraints can all hold at once. SAT (satisfiable) means at least one configuration in the declared domains meets them all; the checker then returns one such configuration, called a witness (a satisfying assignment). UNSAT (unsatisfiable) means no configuration does. The checker uses CP-SAT, the constraint solver in Google's optional OR-Tools library, when it is installed, and otherwise searches the domains itself.

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
- **Remediation**: Fix the expression syntax; see the structural formula grammar in [`tvl.ebnf`](../../spec/grammar/tvl.ebnf).

### `invalid_constraint_expression`
- **Severity**: error
- **Description**: Constraint expression is not a string.
- **Example**: `expr: 123` (should be string)
- **Remediation**: Wrap expression in quotes.

### `non_linear_structural`
- **Severity**: error
- **Description**: Structural constraint contains non-linear operators.
- **Example**: `expr: "x * y = 10"` (multiplication not allowed)
- **Remediation**: Remove `*`, `/`, `^` operators. Structural constraints have no arithmetic: write them with equality, comparison with a number, interval and `in` membership atoms, combined with `and`, `or`, `not` and `=>`.

### `unsupported_structural_literal`
- **Severity**: error
- **Description**: A parsed literal could not be analysed. This is an internal fallback: the parser itself converts supported formulas, including nested `and`/`or`/`not`, to disjunctive normal form (DNF, an `or` of `and`-clauses), and a formula that does not parse is reported as `invalid_structural_expression`.
- **Example**: No well-formed input is known to reach it.
- **Remediation**: Rewrite the literal as one of the supported atom forms (equality, comparison, interval, membership); if the formula looks valid, report it as a toolchain bug.

### `invalid_interval`
- **Severity**: error
- **Description**: An interval bound token does not convert to a number. This is a defensive check: an interval must start with a number token, so a quoted or other non-numeric bound such as `"'a' <= x <= 'b'"` is reported as `invalid_structural_expression` instead.
- **Remediation**: Use numeric bounds for intervals.

### `unsupported_strict_interval`
- **Severity**: error
- **Description**: Strict lower bound (`<` before the TVAR) used in an interval for an integer TVAR. A strict upper bound does not trigger this code.
- **Example**: `expr: "1 < int_var <= 5"`
- **Remediation**: Use non-strict bounds for integer TVARs: write `"2 <= int_var <= 5"`, which admits the same integers.

### `float_equality`
- **Severity**: warning
- **Description**: Floating-point equality comparison may be unstable.
- **Example**: `expr: "temperature = 0.5"` where temperature is float
- **Remediation**: Consider using range constraints instead of exact equality.

### `malformed_structural_constraint`
- **Severity**: error
- **Description**: A `constraints.structural` entry does not have the required shape. Each entry must be an object holding either `when` and `then`, or a single `expr`. A non-object entry, an entry with only one of `when`/`then`, and an entry with unrecognised keys are rejected, because the constraint would otherwise be silently ignored. An entry that has both a complete `when`/`then` pair and `expr` is rejected. An entry that mixes `expr` with only one of `when` or `then` is not flagged today, by this lint or by the JSON Schema (its `oneOf` accepts the `expr` branch).
- **Example**: `structural: ["model = 'gpt-4o'"]` (a bare string) or `{ when: "zero_shot = true" }` (no `then`)
- **Remediation**: Write each entry as `{ when: ..., then: ... }` or `{ expr: ... }`.

### `structural_undecided_without_solver`
- **Severity**: error
- **Reported by**: `tvl-check-structural`
- **Description**: OR-Tools is not installed, and the fallback search neither found a satisfying assignment nor tried every value of every domain (for example, the module has a float TVAR). Satisfiability is undecided. The checker does not report this as UNSAT. It exits 2; with `--json` the result has `status: "undecided"` and an `issues` list holding this code.
- **Example**: a module whose structural constraints involve a float TVAR, checked without OR-Tools, where the sampled values find no witness
- **Remediation**: Install OR-Tools (`pip install ortools`) and run the check again.

### Other undecided results of `tvl-check-structural`

The codes below are also reported by `tvl-check-structural` when it cannot decide a module. Each one is severity `error`. The checker does not report the module as SAT or UNSAT. It exits 2; with `--json` the result has `status: "undecided"`, `ok: false`, `assignment` and `exact_assignment` set to `null`, and an `issues` list holding the code. Every message starts with `Structural satisfiability could not be decided:`.

### `structural_encoding_overflow`
- **Severity**: error
- **Reported by**: `tvl-check-structural`
- **Description**: The exact integer encoding of a numeric TVAR (its grid index range, or a coefficient times a bound) would leave the range the solver handles safely (about ±2^62). The message names the variable.
- **Example**: `{ name: t, type: float, domain: { range: [0.0, 1.0e+30], resolution: 1.0e-30 } }`
- **Remediation**: Narrow the range or use a coarser `resolution`.

### `structural_solver_inconclusive`
- **Severity**: error
- **Reported by**: `tvl-check-structural`
- **Description**: OR-Tools CP-SAT returned a status other than a solution or `INFEASIBLE` (for example `MODEL_INVALID` or `UNKNOWN`). Only `INFEASIBLE` proves UNSAT, so the result is undecided. The message names the status.
- **Example**: no small module is known to reach it; it guards against solver limits and encoding errors.
- **Remediation**: Simplify the constraints or narrow the domains and run the check again; if it persists on a small module, report it as a toolchain bug.

### `structural_witness_unverified`
- **Severity**: error
- **Reported by**: `tvl-check-structural`
- **Description**: The solver found an assignment, but the checker re-evaluates every witness exactly before it reports SAT, and this one failed: a value is not an exact member of its declared domain, or the assignment does not satisfy every constraint under exact evaluation.
- **Example**: no well-formed input is known to reach it; it is a final check on the encoding.
- **Remediation**: Report it as a toolchain bug, with the module.

### `structural_witness_too_large`
- **Severity**: error
- **Reported by**: `tvl-check-structural`
- **Description**: The witness has a value whose exact text would need more than 2000 digits in its numerator or denominator, so it cannot be reported exactly.
- **Example**: a float grid whose origin or step has very many digits
- **Remediation**: Use literals with fewer digits or smaller exponents.

### `structural_ill_typed_atom`
- **Severity**: error
- **Reported by**: `tvl-check-structural`
- **Description**: An atom has no well-defined truth value under the typing rules T-Eq, T-Neq, T-Cmp and T-TVarEq ([formal semantics §4.6](../../formalization/tvl-formal-semantics.md#46-scalar-atom-typing-rules)), so the checker does not decide the module. Cases: the identifier is not a declared TVAR; an unsupported operator; ordering (`<`, `<=`, `>`, `>=`) two TVARs; comparing TVARs of different element classes (numeric, `bool`, non-numeric enum); ordering a non-numeric operand; comparing a numeric TVAR with a non-numeric literal; comparing a `bool` TVAR with a non-bool literal. `tvl-validate` reports most of these first as `undeclared_tvar` or `constraint_type_mismatch`. The element-class check is coarser than T-TVarEq, which requires equal element types: the checker treats `int` and `float` as one numeric class, so `int_var = float_var` is decided here rather than reported (`tvl-validate` rejects it as `constraint_type_mismatch`), and it accepts any two enum-domain TVARs here, leaving tuple arity to the lint's `constraint_type_mismatch`.
- **Example**: `expr: "use_cot = 1"` where `use_cot` is `bool` (a bool never equals the number 1). The message is `atom 'use_cot == 1' in 'use_cot = 1' compares a bool TVAR with a non-bool literal (T-Eq/T-Neq).`
- **Remediation**: Fix the atom: declare the TVAR, or compare it with a literal of its own type (`use_cot = true`).

### `structural_non_finite_domain`
- **Severity**: error
- **Reported by**: `tvl-check-structural`
- **Description**: A TVAR declaration contains NaN or an infinity (`.nan`, `.inf`, `-.inf`). TVL numeric domains are rationals (formal semantics Definitions 3.1-3.2), so these values are not admitted. The message gives the path of the value. `tvl-validate` reports the same input as `non_finite_domain_value`.
- **Example**: `domain: { range: [0.0, .inf] }`
- **Remediation**: Use finite bounds and values.

### `structural_unresolved_domain`
- **Severity**: error
- **Reported by**: `tvl-check-structural`
- **Description**: An atom references a TVAR whose domain comes from a registry (or a tuple with a registry component). The registry is not resolved during the check, so the atom has no values to decide over.
- **Example**: `domain: { registry: model_catalog }` with `expr: "model = 'gpt-4o'"`
- **Remediation**: Resolve the registry to an explicit list of values before the structural check.

### `structural_pair_table_too_large`
- **Severity**: error
- **Reported by**: `tvl-check-structural`
- **Description**: An equality or inequality between two enum TVARs needs a table of equal-value pairs larger than 1,000,000 rows. Repeated members are removed first, so the table has at most as many rows as the smaller domain has members. The message names both TVARs and the row count.
- **Example**: `expr: "a = b"` where `a` and `b` are enum domains that share more than a million values
- **Remediation**: Narrow one or both domains.

### `structural_expansion_too_large`
- **Severity**: error
- **Reported by**: `tvl-check-structural`
- **Description**: Expanding one expression's `in` sets and negated intervals into clauses gives more than 10,000 clauses (the parser's DNF clause limit). Each `in` set multiplies the count. The message gives the path of the expression.
- **Example** (schematic; `...` stands for the omitted members and conjuncts, it is not valid syntax): `expr: "v0 in {0,...,9} and v1 in {0,...,9} and ... and v4 in {0,...,9}"`, that is five TVARs `v0` to `v4`, each tested against the ten values 0 to 9 (10^5 clauses)
- **Remediation**: Split the expression into several constraints or simplify it.

### `structural_value_too_large`
- **Severity**: error
- **Reported by**: `tvl-check-structural`
- **Description**: The members of one enum or tuple domain expand to more than 1,000,000 nested nodes in total, or nest deeper than 100 levels. YAML aliases can make a small file stand for a very large value; the checker counts the expanded size before it compares values.
- **Example**: a tuple member built by repeating an alias inside itself many times
- **Remediation**: Flatten or shrink the values.

---

## Derived Constraint Errors

### `derived_references_tvar`
- **Severity**: error
- **Description**: Derived constraint references a TVAR (should use environment symbols only).
- **Example**: `require: "max_calls <= 2"` when `max_calls` is a TVAR
- **Remediation**: Move TVAR constraints to `structural`; use only environment symbols in `derived`.

### `non_linear_derived`
- **Severity**: error
- **Description**: Derived constraint contains a non-linear operator: `/` or `^`. A product such as `cost * quantity` is not reported by this code: the lint reports bare names there as `derived_invalid_symbol_reference`, and `tvl-check-operational` reports a product of symbols as `unsupported_derived_expression`.
- **Example**: `require: "env.context.cost / env.context.quantity <= 100"`
- **Remediation**: Use only linear arithmetic (affine expressions).

### `derived_invalid_symbol_reference`
- **Severity**: error
- **Description**: Operational precondition references something other than `env.context.*`.
- **Example**: `require: "daily_budget_remaining >= 10"` (a bare name; `env.context.daily_budget_remaining` is the valid form, and an `env.context` name missing from the environment is `unknown_derived_symbol`)
- **Remediation**: Put numeric operational symbols under `environment.context` and reference them as `env.context.<name>`.

### `derived_references_bindings`
- **Severity**: error
- **Description**: An operational precondition references `env.bindings.*`. Bindings are opaque deployment references (such as a region name or an index id), not numeric operational symbols.
- **Example**: `require: "env.bindings.llm_gateway <= 1"`
- **Remediation**: Put the numeric value under `environment.context` and reference it as `env.context.<name>`.

---

## Operational Check Errors

`tvl-check-operational` reports these codes when it evaluates derived constraints against `environment.context` and checks exploration budgets. Each makes the check fail (exit 2). A budget error stops the check before derived constraints are evaluated.

### `invalid_budget_max_trials`
- **Severity**: error
- **Description**: `exploration.budgets.max_trials` is not positive.
- **Example**: `budgets: { max_trials: 0 }`
- **Remediation**: Set `max_trials` to a positive integer.

### `invalid_budget_max_spend`
- **Severity**: error
- **Description**: `exploration.budgets.max_spend_usd` is negative.
- **Example**: `budgets: { max_spend_usd: -1 }`
- **Remediation**: Set `max_spend_usd` to 0 or a positive number; 0 means no paid spending is allowed.

### `invalid_budget_max_wallclock`
- **Severity**: error
- **Description**: `exploration.budgets.max_wallclock_s` is not positive. (The schema separately requires a whole number of seconds, at least 1.)
- **Example**: `budgets: { max_wallclock_s: -1 }`
- **Remediation**: Set `max_wallclock_s` to a whole number of seconds, at least 1 (for example `3600`); fractions such as `0.5` are rejected.

### `unsupported_derived_expression`
- **Severity**: error
- **Description**: A derived constraint is not of the form `LinExpr OP Number`, where `LinExpr` is a sum or difference of terms such as `env.context.a` or `2 * env.context.b` (and plain numbers), and OP is `<=`, `>=`, `<`, `>` or `=`.
- **Example**: `require: "env.context.a"`
- **Remediation**: Write the constraint as a linear expression over `env.context.*` symbols compared with a number.

### `unknown_derived_symbol`
- **Severity**: error
- **Description**: A derived constraint references an `env.context` symbol that the environment does not define.
- **Example**: `require: "env.context.daily_budget_remaining >= 10"` with no `daily_budget_remaining` under `environment.context`
- **Remediation**: Add the symbol to `environment.context`, or fix its name.

### `non_numeric_derived_symbol`
- **Severity**: error
- **Description**: An `env.context` symbol used in a derived constraint does not have a numeric value.
- **Example**: `environment.context.region: eu` with `require: "env.context.region <= 1"`
- **Remediation**: Give the symbol a numeric value, or remove it from the constraint.

### `derived_constraint_violation`
- **Severity**: error
- **Description**: A derived constraint evaluates to false for the values in `environment.context`.
- **Example**: `require: "env.context.price_usd <= 1.5"` with `environment.context.price_usd: 2`
- **Remediation**: Change the environment values or the constraint bound.

---

## Objective Errors

### `legacy_objective_epsilon`
- **Severity**: warning
- **Description**: Objective uses deprecated `epsilon` field. Epsilon is the per-objective comparison tolerance (formal semantics §9.3); it now lives in `promotion_policy.min_effect`.
- **Example**: `{ name: quality, metric_ref: metrics.quality.v1, direction: maximize, epsilon: 0.01 }`
- **Remediation**: Move epsilon to `promotion_policy.min_effect.quality`.

### `invalid_band_target`
- **Severity**: error
- **Description**: Banded objective target has invalid format. A banded objective declares an acceptable range instead of a direction: `target: [low, high]`, or `{ center, tol }`, where `tol` is the tolerance radius around `center` and must be greater than 0.
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
- **Example**: `{ name: length, band: { test: TOST, alpha: 0.05 } }` (`TOST`, two one-sided tests, is the band test; `alpha` is its significance level; formal semantics §9.5)
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

The promotion policy compares a candidate with the incumbent. Under `dominance: epsilon_pareto` (formal semantics §9.3) the candidate must be no worse than the incumbent on every objective within that objective's tolerance in `min_effect`, and better on at least one by more than it. `chance_constraints` add limits on the rate of an undesirable event, each checked at a stated confidence (formal semantics Definition 9.8).

### `invalid_alpha`
- **Severity**: error
- **Description**: Policy alpha is not a number strictly between 0 and 1. An omitted alpha takes the default 0.05; an explicit `null` is rejected.
- **Example**: `alpha: -0.05`, `alpha: 1` or `alpha: "five percent"`
- **Remediation**: Set alpha to a number in (0, 1), typically 0.05.

### `invalid_dominance`
- **Severity**: error
- **Description**: Unsupported dominance relation specified.
- **Example**: `dominance: "pareto"` (should be `epsilon_pareto`)
- **Remediation**: Use `dominance: epsilon_pareto`.

### `missing_min_effect`
- **Severity**: error
- **Description**: A directional objective (one with `direction: maximize` or `minimize`) lacks an entry in the `min_effect` map. Banded objectives need no entry.
- **Example**: `min_effect: { quality: 0.01 }` when a `latency` objective with a direction exists
- **Remediation**: Add a `min_effect` entry for every directional objective.

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


### `zero_trials`
- **Severity**: error
- **Reported by**: `tvl-ci-gate`, the `chance` report of `tvl-measure-validate`, and the promotion gate (`epsilon_pareto_gate`) in the Python package
- **Description**: A chance constraint has `trials: 0`, or no trial count. The chance check is undefined without trials (precondition of Definition 9.8 in the formal semantics), so the gate returns the decision `Error`, which is neither `Reject` nor `NoDecision`. This is checked before any other decision branch. When the gate returns `Error`, `tvl-ci-gate` prints `Decision: Error` and exits 2; with `--json` it prints `{ "ok": false, "decision": "Error", "error": ..., "codes": ["zero_trials"], "warnings": ..., "evidence": ... }`. Which you see depends on the bundle form. With canonical `chance_outcomes`, a `trials` of 0 or a missing `trials` is a schema error when the file is loaded (exit 2, no `decision`). With the deprecated top-level `chance` summary, `summary.trials: 0` passes the schema and reaches the gate, which returns `Error` with `zero_trials` (exit 2). A bundle passed to the gate in Python, without the schema check, also gets `Error`.
- **Example**: the legacy bundle `{ "chance": { "safety": { "observed": 0.0 } }, "summary": { "trials": 0 } }`
- **Remediation**: Provide at least one trial for every chance constraint.

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
- **Description**: Hypervolume convergence threshold is not positive. Hypervolume measures how much of the objective space the current set of non-dominated results covers; with `metric: hypervolume_improvement`, `threshold` is the minimum improvement of that measure, over the sliding `window`, needed to continue exploring.
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

These codes come from the `policies` block introduced by RFC 0001. Policies are operational declarations; the first supported strategy is `cascade`: stages run in order, and a gate after each stage except the last decides whether to stop there or escalate to the next, so `m` stages have `m − 1` gates (RFC 0001 §3.8). Several of these codes are shared with composite cascades (see below).

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
- **Description**: A declaration `scope` is not an object, has a field other than `node`, `agent`, or `workflow`, or has a value that is not a valid identifier. A `scope: null` is treated as absent and gets no diagnostic.
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
- **Description**: `promotion_policy.require_calibration` is not an object with a boolean `enabled` field. A `null` value is treated as absent by the lint (the JSON Schema still requires an object).
- **Example**: `require_calibration: { enabled: "yes" }`
- **Remediation**: Set `enabled: true` or `enabled: false`.

### `invalid_calibration_context`
- **Severity**: error
- **Description**: `hash_covered_context` is present and not `null` but is not a list, names a key that is not a freshness-context extension key, or repeats a key. The freshness context is the set of inputs hashed into a calibration certificate, so that a change to any of them makes the certificate stale (RFC 0001 §3.5). Its mandatory core is always hashed and cannot be configured. The extension keys are `stage_versions`, `model_versions`, `budget_assumptions`, `cost_assumptions`, and `signal_inputs`.
- **Example**: `hash_covered_context: [dataset_version]`
- **Remediation**: List each extension key at most once, using only the keys above.

### `calibration_evidence_unsupported`
- **Severity**: readiness issue (exit 2)
- **Reported by**: `tvl-ci-gate` (and the promotion readiness report of `tvl-measure-validate`)
- **Description**: The module is in a strict calibration evidence mode (RFC 0001 §3.6, RFC 0002 §5), but the measurement bundle and the `tvl-ci-gate` contract cannot validate calibration certificates, so promotion is refused. The gate checks the triggers it can see in the module: `require_calibration.enabled`, a cvar with `governance.require_calibration`, any declared cvar, a calibrated composite member, and non-empty `chance_constraints` when there is a cvar or calibrated composite member to certify. The operational-profile trigger of RFC 0001 §3.6 is not checked, because the gate does not receive the operational profile.
- **Example**: `promotion_policy: { require_calibration: { enabled: true } }`
- **Remediation**: None within the current tools; this module cannot be promoted by `tvl-ci-gate` until calibration certificates are supported.

---

## Composite Knob Errors (TVL 1.2)

These codes come from the `composites` block introduced by RFC 0002 (`formalization/rfc-0002-composite-knobs.md`): named bundles of member knobs under a control-flow shape (`cascade`, `ensemble`, or `loop`). A composite is a namespace and expansion unit; it never binds a value. Codes shared with the 1.1 constructs (`missing_ref`, `cascade_arity`, `duplicate_stage`, `unknown_gate_kind`) are described above.

**Declarations and shape**

### `invalid_composites`
- **Severity**: error
- **Description**: `composites` is present, not `null`, and not a list of declarations. A `composites: null` is treated as absent.
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
- **Description**: A signal use of a composite-bound threshold declares non-empty `inputs`, but they are not freshness-bound (`inputs: []` needs no coverage). `promotion_policy.require_calibration.hash_covered_context` must include `signal_inputs`, and `promotion_policy.require_calibration.signal_inputs` must equal the use-site input list.
- **Example**: A stop signal with `inputs: [draft]` and `hash_covered_context: [model_versions]`
- **Remediation**: Add `signal_inputs` to `hash_covered_context` and set the matching `signal_inputs` list.

### `missing_composite_parent`
- **Severity**: error
- **Description**: A threshold CVAR's `calibration.depends_on` omits a TVAR its threshold depends on, so the threshold would not go stale when that TVAR changes. The required set (RFC 0002 §3.5) is: for a post-cascade gate, every TVAR of the observed arm and of all earlier arms; for a pre-cascade gate, the TVARs of the arm it admits; for an ensemble `accept` threshold, the TVARs of every arm, of the judge if present, and the ensemble's own cardinality if it is a TVAR; for a loop stop threshold, the TVARs of the body.
- **Example**: A post-cascade whose cheap arm is tuned by `cheap_model` and `temperature`, with a threshold CVAR that depends only on `cheap_model`
- **Remediation**: Add every TVAR of the required set to `depends_on`.

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

### `accept_over_judge_max`
- **Severity**: error
- **Description**: A `judge_max` aggregate carries an `accept` block. A `judge_max` ensemble takes no vote, so there is no vote statistic for `accept` to read. Added by an RFC 0002 errata (2026-10-25).
- **Example**: `aggregate: { kind: judge_max, judge: { stage: j }, accept: { kind: stat_at_least, stat: vote_margin, threshold: vote.accept_threshold } }`
- **Remediation**: Remove the `accept` block, or use `majority_vote`.

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

### `duplicate_key`
- **Severity**: error (at parse time)
- **Description**: A YAML mapping repeats a key (RFC 0001 §3.5(4)). The file is rejected as it is read, before any other check. The message names the key, its line and its column, for example `duplicate_key: duplicate mapping key 'tvl' (line 3, column 1)`. A key written explicitly next to a `<<` merge, overriding the key it would inherit, is not a duplicate.
- **Example**: a module with two top-level `tvars:` keys
- **Remediation**: Keep one copy of the key and merge the values into it.

### `complex_mapping_key`
- **Severity**: error (at parse time)
- **Description**: A YAML mapping key is itself a mapping or a sequence. TVL keys are scalars. Such a key is rejected rather than skipped, because a tagged collection key can construct to a plain string and silently replace an explicit key without tripping the duplicate-key check. The message names the kind of node and its line and column, for example `complex_mapping_key: a mapping key must be a scalar, found a sequence (line 2, column 3)`.
- **Example**: `? [a, b]` followed by `: 1`
- **Remediation**: Use a plain string key.

### YAML loading limits (`YAMLLimitError`)

Every TVL tool reads YAML through one hardened loader. A document that exceeds one of its limits is rejected as a YAML parse error before any other check. These failures have no diagnostic code: `tvl-validate` prints `Error: YAML syntax error: <message>` and exits 2, and `tvl-check-structural --json` returns `status: "error"` with the message in `error`.

| Limit | Message |
|-------|---------|
| Input larger than 5 MiB | `YAML input too large (<size> bytes > 5242880 byte limit)` |
| More than 5000 resolved aliases | `YAML alias-expansion budget exceeded (5000); possible entity-expansion DoS` |
| Merge keys (`<<`) copy more than 100,000 key/value pairs in total | `YAML merge-key expansion budget exceeded (100000 inherited key/value pairs, line <n>); possible merge-expansion DoS` |
| A float literal with more than 400 digits | `numeric literal has <n> digits (limit 400) (line <n>, column <n>)` |
| A float literal whose exponent is beyond ±400 | `numeric literal exponent exceeds +-400 (line <n>, column <n>)` |
| Nesting too deep for the parser | `YAML nesting too deep to parse safely` |

Every finite binary64 number (the IEEE 754 double-precision floating-point format) can be written within the literal limits. The merge budget is charged before each copy, so a document whose merges double at each level fails fast instead of hanging. Numeric literals inside structural constraint expressions have the same 400-digit limit; `tvl-check-structural` reports a longer one as `invalid structural constraint: numeric literal out of bounds: ...` and exits 2.

### `schema_error`
- **Severity**: error
- **Description**: Module fails JSON Schema validation.
- **Example**: Missing required field `tvl.module`
- **Remediation**: Ensure module conforms to `tvl.schema.json`.

### `invalid_document`
- **Severity**: error
- **Reported by**: `tvl-lint`
- **Description**: The file is not a mapping at the top level (for example a YAML list, a bare scalar or an empty file), so it is not a TVL module.
- **Example**: a file containing only `- a`
- **Remediation**: Write the module as a YAML mapping with `tvl`, `tvars` and the other top-level keys.

---

## Formal Verification Warnings

These diagnostics indicate that the module uses features outside the formally verified TVL subset. The module may still be valid and functional, but the proved results, such as Encoding Soundness ([formal semantics §8.8](../../formalization/tvl-formal-semantics.md#88-encoding-soundness), Theorem 8.1), do not cover those features.

`cvars`, `policies` (RFC 0001), and `composites` (RFC 0002) are also outside the formally verified subset today: the Lean proof tree (machine-checked proofs in the Lean 4 theorem prover, `proofs/`) does not model them. The info diagnostic `outside_proved_subset` below reports this; see `formalization/tvl-formal-semantics.md` §1.4 for the full disclosure.

### `outside_proved_subset`
- **Severity**: info
- **Description**: The module declares a construct family that the Lean proofs do not model. It is emitted once per family present: `cvars`, `policies`, `composites` (an empty or absent section emits nothing). Callable domains are reported by `unverifiable_callable_type` instead.
- **Example**: a module with a non-empty `cvars` list
- **Impact**: The proved results (type soundness, and soundness of the SMT (satisfiability modulo theories) encoding) do not cover this construct. Info diagnostics are included in JSON output and printed in the text output of `tvl-validate` and `tvl-lint` (a successful `tvl-compose --validate` prints only the composed module in text mode). They never affect `ok` or the exit status of `tvl-validate`, `tvl-lint` or `tvl-compose --validate`.
- **Remediation**: None required.

### `unverifiable_registry_domain`
- **Severity**: warning
- **Code**: W6001
- **Description**: Module uses a registry domain, which is outside the formally verified subset.
- **Example**: `domain: { registry: model_catalog, filter: "version >= 2.0" }`
- **Impact**: SMT encoding soundness (Theorem 8.1) does not apply to this module.
- **Formal Property**: The meaning of a registry domain is undefined in the formal semantics, because it depends on external state (the registry contents); see formal semantics Definition 3.6.
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
- **Description**: A float domain is not precision-aligned to the current precision factor P (Definition 8.6): some value `v` of the domain has `v·P` not an integer. A range has the values `a + k·r`, so it is checked through its lower bound `a` and its resolution `r` (0.001 when omitted); when two values also collide after scaling, the message names them.
- **Example**: `domain: { range: [0.0001, 0.001], resolution: 0.0001 }` with precision P=1000
- **Impact**: The preconditions of SMT encoding soundness (Theorem 8.1) are not met, so the theorem does not cover this module; constraint checking may be incorrect.
- **Formal Property**: Domain is not precision-aligned per Definition 8.6.
- **Remediation**: Choose a precision factor P for which every declared value has `v·P` an integer; for a range, both the lower bound `a` and the resolution `r` must scale to integers. When it can, the message ends with `Suggested exact-alignment precision: P=N.` (also in `suggested_precision`); otherwise it ends with `Use exact rational or index encoding because an aligned integer precision could not be established.` For a set domain the suggested P aligns every value. For a range it is derived from the misaligned resolution alone (or, when the resolution is aligned, from the lower bound alone), so it may still leave the other one misaligned: for `{range: [0.00001, 0.001], resolution: 0.0003}` with P=1000 the suggestion is P=10000, but `0.00001·10000 = 0.1`. Check the suggested P against both `a` and `r` and re-run `tvl-lint`, or use an exact rational or index encoding. A factor based only on the smallest gap between values is not sufficient.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success under the tool's contract (see the 1.3 tool table below) |
| 2 | A reported issue, validation or parse failure, or an unsuccessful gate decision, as specified by the tool |

TVL tools use 0 and 2 for their documented results, except `tvl-config-validate`, which exits 5 when validation fails or it refuses a construct. Exit 1 is not a defined diagnostic outcome. Diagnostics with severity `info` never change the exit status.

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
| `derived_invalid_symbol_reference` | error | Derived | Symbol other than `env.context.*` in derived |
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
| `invalid_budget_max_trials` | error | Operational | max_trials not positive |
| `invalid_budget_max_spend` | error | Operational | max_spend_usd negative |
| `invalid_budget_max_wallclock` | error | Operational | max_wallclock_s not positive |
| `unsupported_derived_expression` | error | Operational | Derived constraint not `LinExpr OP Number` (a linear expression compared with a number) |
| `unknown_derived_symbol` | error | Operational | env.context symbol not defined |
| `non_numeric_derived_symbol` | error | Operational | env.context symbol not numeric |
| `derived_constraint_violation` | error | Operational | Derived constraint false for the environment |
| `duplicate_domain_value` | error | Domain | Repeated domain member |
| `non_finite_domain_value` | error | Domain | NaN or infinity in a domain |
| `invalid_tuple_domain` | error | Domain | Bad tuple components |
| `malformed_structural_constraint` | error | Structural | Entry is not {when,then} or {expr} |
| `structural_undecided_without_solver` | error | Structural | No OR-Tools; fallback could not decide |
| `structural_encoding_overflow` | error | Structural | Exact encoding too large for the solver |
| `structural_solver_inconclusive` | error | Structural | Solver status not OPTIMAL, FEASIBLE or INFEASIBLE; undecided |
| `structural_witness_unverified` | error | Structural | Witness failed the exact re-check |
| `structural_witness_too_large` | error | Structural | Witness value too large to print exactly |
| `structural_ill_typed_atom` | error | Structural | Atom has no typed truth value |
| `structural_non_finite_domain` | error | Structural | NaN or infinity in a TVAR declaration |
| `structural_unresolved_domain` | error | Structural | Atom over an unresolved registry domain |
| `structural_pair_table_too_large` | error | Structural | TVAR equality table over 1,000,000 rows |
| `structural_expansion_too_large` | error | Structural | Expression expands past 10,000 clauses |
| `structural_value_too_large` | error | Structural | Enum members too large or too deep |
| `derived_references_bindings` | error | Derived | Bindings in derived |
| `empty_objectives` | error | Objective | No objectives |
| `duplicate_objective` | error | Objective | Duplicate objective name |
| `invalid_direction` | error | Objective | Bad direction |
| `unknown_min_effect_objective` | error | Policy | min_effect key not an objective |
| `invalid_chance_threshold` | error | Policy | Bad chance threshold |
| `zero_trials` | error | Policy | Chance constraint with no trials; gate decision Error |
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
| `calibration_evidence_unsupported` | readiness issue | Calibration (1.1) | Strict calibration mode; gate refuses promotion |
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
| `accept_over_judge_max` | error | Composite (1.2) | accept block on a judge_max aggregate |
| `invalid_max_iters` | error | Composite (1.2) | max_iters < 1 |
| `unknown_stop_kind` | error | Composite (1.2) | Unknown stop kind |
| `missing_stop_threshold` | error | Composite (1.2) | signal_accept without threshold |
| `missing_stop_signal` | error | Composite (1.2) | signal_accept without signal |
| `missing_stop_predicate` | error | Composite (1.2) | external_accept without predicate |
| `stop_signal_outside_state` | error | Composite (1.2) | Stop input not in state_keys |
| `duplicate_key` | error | Schema | Repeated YAML mapping key (parse time) |
| `complex_mapping_key` | error | Schema | Mapping or sequence used as a YAML key (parse time) |
| `schema_error` | error | Schema | JSON Schema violation |
| `invalid_document` | error | Schema | Top level is not a mapping |
| `unverifiable_registry_domain` | warning | Formal | Registry domain used |
| `unverifiable_callable_type` | warning | Formal | Callable type used |
| `outside_proved_subset` | info | Formal | cvars, policies or composites used (not in the Lean proofs) |
| `inadequate_precision` | warning | Formal | Float domain not aligned to precision P (Definition 8.6) |

---

## TVL 1.3 diagnostics

These codes belong to the TVL 1.3 requirements, monitors and responses (see the
[guide](../guides/requirements-monitors-responses.md) and the
[language reference](language.md#tvl-13-requirements-monitors-responses)). TVL 1.3 was accepted on 2026-10-21; a change to these codes is a language revision.

Every diagnostic has the same shape as the codes above: `{ code, message, path, severity }`. In text mode a line looks like
`[runtime_window_out_of_range] monitors.0.window.tumbling_hours: tumbling_hours is outside its allowed domain`, and `path` points at the key to fix. Severity is
`error` unless marked `warning`. Warnings still make `tvl-validate` and `tvl-lint` exit 2; `info` diagnostics never do.

**Reported by** says which tool in this repository can produce the code:

| Value | Tool |
|---|---|
| lint | `tvl-validate`, `tvl-lint`, `tvl-ci-gate` (which runs the runtime lints first) and `tvl-compile-runtime` (which runs the same lints before compiling and stops at the first lint error; lint warnings do not stop it). So `tvl-compile-runtime` can report every error code marked lint. |
| compose | `tvl-compose` with `--pack`, `--meet` or an overlay |
| compile | `tvl-compile-runtime`, from its own compile steps: customer checker bindings; the token map (a customer-side file that maps each customer-chosen name to its hosted reference); projection (rewriting the contract so only those hosted references leave the customer side); and the self-check. See [RFC 0003](../../formalization/rfc-0003-runtime-requirements-monitors-responses.md) §8.2, §11.4.6 and §11.5. A code marked `lint, compile` comes from both the lints and those steps. |
| gate | `tvl-measure-validate`, `tvl-ci-gate` |
| platform | defined by RFC 0003 for the platform that registers or evaluates your contract; no tool in this repository produces it |

!!! note "Message text"
    `tvl-compose` prints a composition error on one line as `Error: <code> at <path>: <message>`, for example `Error: requirement_weaker_than_floor at ...`. The code, not the wording, is the stable part.

### Version and readers

| Code | Severity | Reported by | What it means | What to do |
|---|---|---|---|---|
| `unsupported_construct` | error | various tools | a tool met a 1.3 construct it does not implement (`requirements`, `monitors`, `responses`, `tvl_pack`, `monitor_outcomes`, `runtime_report`) and refused instead of ignoring it. The first construct found is named. | use a tool that supports the construct (for a pack: `tvl-validate`, `tvl-lint`, `tvl-compose`, `tvl-compile-runtime`), or remove the construct for that tool |
| `runtime_version_required` | error | lint | the document uses `requirements`, `monitors` or `responses`, or is a `tvl_pack`, and has no `tvl_version` | add `tvl_version: "1.5"` for breach persistence or census aggregates ([RFC 0005](../../formalization/rfc-0005-persistence-and-census-aggregates.md)); at least "1.4" for reactive outcomes and notification guards ([RFC 0004](../../formalization/rfc-0004-reactive-outcomes-and-guards.md)); otherwise "1.3", "1.4" or "1.5" |
| `declared_version_below_constructs` | error | lint | `tvl_version` is not a supported quoted runtime version ("1.3", "1.4" or "1.5"; unquoted versions are numbers), reactive outcomes or guards use "1.3", or breach persistence or census aggregates use "1.3" or "1.4" | use "1.5" for RFC 0005 constructs, at least "1.4" for RFC 0004 constructs, otherwise "1.3", "1.4" or "1.5", quoted |
| `runtime_unsupported_capability` | error | platform | the target platform has not enabled the monitor's kind, source, method or predicate class | change the declaration to something the platform supports, or ask the platform to enable it |
| `response_action_unsupported` | error | platform | the target platform cannot carry out a rule's action | remove the rule or pick an action the platform supports |

### Names and references

| Code | Severity | Reported by | What it means | What to do |
|---|---|---|---|---|
| `runtime_name_collision` | error | lint, compose | a duplicate name within the requirement, monitor or response namespace; a runtime name equal to a tvar, cvar, policy or composite name; or a pack name that clashes with a different module declaration | rename one of them |
| `response_rule_id_duplicate` | error | lint | two rules of one response share an `id` | give each rule a unique `id` |
| `runtime_missing_ref` | error | lint | `monitor.requirement`, `of`, `trigger.monitor`, outcome `trigger.rule`, guard `monitor` or response-local guard `rule` names nothing | fix the name or declare the missing item |
| `runtime_ref_kind_mismatch` | error | lint | a reference points at the wrong kind of thing: `recovery_time.of` at a monitor with no episode, `evidence_liveness.of` at a monitor with no windows, a `trigger.event` the monitor never emits, an outcome naming itself or a non-optimize rule, or a guard naming a non-primary monitor or non-optimize rule | point at the right monitor, or pick an event that monitor emits (guide, section 7) |
| `runtime_dependency_cycle` | error | lint | requirements and monitors refer to each other in a cycle | break the cycle: an obligation (`of`) must not depend on itself |

### Kinds, profiles and values

| Code | Severity | Reported by | What it means | What to do |
|---|---|---|---|---|
| `runtime_unknown_kind` | error | lint, compile | a value outside a sealed list: a requirement kind, unit, pattern, metric, event type, status, checker id or label, source, method, model, sampling mode, attribution or resolution rule, profile, phase, trigger event, `correlate_by`, `unlisted`, `mode`, approval, severity, `on_check_error` or `deploy`. Also an unbound customer checker or label at compile time. | use a value from the reference table; check the spelling |
| `response_unknown_action` | error | lint | `do` is not one of the nine actions; `record` is implicit and cannot be declared | use `notify`, `open_next_step`, `optimize`, `rollback`, `throttle`, `degrade`, `suspend`, `block_action` or `halt_unit` |
| `runtime_invalid_profile` | error | lint, compile | the combination of kind, source, phase and method is not allowed; a field is missing or forbidden for the monitor's role; a key of another variant is present; sampling is not allowed for the source; a stateful pattern has no `limits`; a selector field is on the wrong event; or a number cannot be read exactly | compare the monitor to the role table in the reference; the message names the role |
| `runtime_legacy_profile_override` | error | lint | under `profile: backend_v1`, a field or value other than the frozen ones | remove the field, or drop `profile: backend_v1` and declare the monitor in full |
| `runtime_rate_out_of_range` | error | lint | `max_rate` is not strictly between 0 and 1 | use a value such as `0.05` |
| `runtime_confidence_out_of_range` | error | lint | `confidence` is not strictly between 0 and 1; under `backend_v1` it is not 0.90, 0.95 or 0.99 | pick an allowed value |
| `runtime_window_out_of_range` | error | lint | `tumbling_hours` does not divide 24; under `backend_v1` it is not 1, 3, 6, 12 or 24 | use 1, 2, 3, 4, 6, 8, 12 or 24 (under `backend_v1`: 1, 3, 6, 12 or 24) |
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
| `runtime_trigger_hours_out_of_range` | error | lint | `trigger.hours` is below 1, or unknown_for hours is below the monitor tumbling_hours | use an integer >= 1, and for `unknown_for` at least the monitor's `tumbling_hours` |
| `runtime_repeat_after_hours_out_of_range` | error | lint | `repeat_after_hours` is below 1 | use an integer >= 1 |
| `runtime_max_repeats_out_of_range` | error | lint | `max_repeats` is below 1 | use an integer >= 1 |
| `runtime_max_active_obligations_out_of_range` | error | lint | `limits.max_active_obligations` is below 1 | use an integer >= 1 |
| `runtime_max_tracked_correlations_out_of_range` | error | lint | `limits.max_tracked_correlations` is below 1 | use an integer >= 1 |
| `runtime_burn_out_of_range` | error | lint | a burn monitor whose `threshold_factor`, written b here, is <= 1, or with b times `max_rate` >= 1, or that can never breach at `min_samples` | choose b > 1 with b times `max_rate` < 1 and a `min_samples` that can breach |
| `runtime_zero_tolerance_inexact` | error | lint | a `zero_tolerance` violation that is a metric or a checker rather than an exact pattern | use an exact pattern, or switch to `rate_bound` |
| `runtime_among_not_checker` | error | lint | an `among` that is a metric or an exact pattern; 1.3 defines population membership only for checker labels | select the population with a checker, or drop `among` |
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
| `runtime_duplicate_key` | error | lint | two monitors have the same effective key (same requirement identity: kind, unit, population and predicate; and same source, environment, attribution, method and `threshold_factor`), or two monitors serve one obligation | keep one, or change what they measure; use a burn monitor for a second tier |
| `recovery_deadline_impossible` | error | lint, compose | `within_hours` is less than `closure_windows * tumbling_hours`, so an episode could never close in time (equal is fine; also checked on the composed result) | raise `within_hours` or shorten the window or `closure_windows` |
| `tenant_floor_outside_pack` | error | lint | a module monitor declares `applies_to: tenant_floor`, which only a pack may do; a composed module passes when it is validated with the floor provenance record of `tvl-compose --validate` | remove `applies_to`, or move the monitor into a `tvl_pack` |
| `runtime_incompatible_replacement` | error | compose | an overlay, pack or meet changed an immutable part: predicate, population, source, environment, method, sampling, `threshold_factor`, `single_producer`, `limits`, an outcome trigger, `only_while` set or `unless` set | change only tightenable numbers, or declare a new requirement |
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
| `runtime_invalid_ladder` | error | lint | a response rule breaks one of the ladder rules listed below this table | compare the rule with the action and trigger tables in the reference; terminal events can notify, but cannot authorize a remote service action |
| `response_suspend_without_human` | error | lint | `suspend` without an explicit `approval: human`, including an omitted approval | write `approval: human` explicitly |
| `response_suspend_unconfirmed` | error | lint | `suspend` triggered by an event other than `episode_continued`, `episode_open_for` or `recovery_overdue` | trigger on one of those three events |
| `response_irreversible_without_approval` | error | lint | `optimize`, `rollback`, `throttle` or `degrade` with `approval: none` | use `standing` or `human` |
| `response_rollback_target_uncertified` | error | platform | a rollback `target` or degrade `fallback` fingerprint has no valid configuration-attributed certificate | for rollback, use `last_certified` or a certified fingerprint; for degrade, use a certified fingerprint (64 lowercase hex characters; `last_certified` is not accepted there) |
| `response_guard_not_enforceable` | error | lint | `block_action` or `halt_unit` on a monitor whose violation is not fixed by a prefix (`bounded_response`, metric, checker), whose source is not `customer_side`, or triggered by an event other than `unit_violation` | use a guard only on `absence`, `bounded_existence`, `precedence` or `protocol`, on `unit_violation` |
| `response_on_check_error_missing` | error | lint | a guard without `on_check_error` | choose `block` (fail closed) or `allow` |
| `response_rule_repeat_unbounded` | error | lint | an action other than `notify` repeats without `max_repeats` | add `max_repeats` |
| `response_deploy_without_promotion_monitor` | error | lint, compile | an `optimize` rule with `deploy: if_promoted` whose trigger monitor's requirement has no promotion monitor (always the case in a `tvl_pack`) | add a `phase: promotion` monitor on that requirement, or use `deploy: never` |
| `runtime_notify_only` | error | lint | outcome trigger, unknown_for, only_while or unless on a non-notify rule | use do: notify |
| `runtime_guard_cycle` | error | lint | cycle (including self-loop) in the unless monitor graph, using the referenced optimize rule's source for outcome rules; attempts add no edge | remove mutual/self inhibition |
| `runtime_guard_redundant` | warning | lint | only_while names the rule's own source monitor | omit the redundant guard |

`runtime_invalid_ladder` is reported when a rule:

- has an action parameter that is missing, not allowed for the action, or ill-typed: `target` only on `rollback`; `fallback` only on `suspend` and `degrade`; `rate_floor` only on `throttle`; `severity` only on `notify`; `on_check_error` only on the guards; `deploy` only on `optimize`; `max_repeats` without `repeat_after_hours`; a fingerprint that is not 64 lowercase hex characters;
- has `trigger.hours` with an event other than `episode_open_for` or `unknown_for`, or lacks it with either;
- has `deploy: if_promoted` on an event other than `episode_opened`, `episode_continued` or `episode_open_for`;
- has an approval the action does not allow;
- authorizes a remote service action on a terminal-scope event or on `unit_violation`;
- (RFC 0004) has a deploy outcome trigger whose optimize rule lacks `deploy: if_promoted`, repeat coordinates on an outcome-triggered rule, an outcome trigger or `attempt_open` guard in a pack, or `unknown_for` on a non-primary monitor.

Reactive constructs require quoted `tvl_version` "1.4" or later ("1.5" is also accepted); using "1.3" yields
`declared_version_below_constructs`. Unknown outcome events/guard states use `runtime_unknown_kind`
(the compiled schemas reject them too). Guards have sealed reference/state shapes.

### Measurement and reports

| Code | Severity | Reported by | What it means | What to do |
|---|---|---|---|---|
| `missing_monitor_counts` | readiness issue (exit 2) | gate | a promotion monitor has no `monitor_outcomes.<monitor name>` in the candidate bundle, or its `k` is greater than `n` | supply `{ n, k }`, where `n` counts the resolved evaluation-set units in the monitor's population and `k` the violating ones (and `complete: true` for a zero-tolerance monitor) |
| `runtime_report_conservation` | error | platform | a window report breaks count conservation, or does not match its contract, the window grid or the sampling commitment | fix the producer of the report; the error repeats no input |

### Exit codes of the 1.3 tools

| Tool | 0 | 2 |
|---|---|---|
| `tvl-validate`, `tvl-lint` | no issue, or only `info` issues | any `error` or `warning` issue |
| `tvl-compose` | composed | any composition error or unreadable input |
| `tvl-compile-runtime` | both files written, or token-map template printed (warnings allowed) | any error |
| `tvl-ci-gate module incumbent candidate` | `Promote` | `Reject`, `NoDecision`, `Error` (an undefined check such as `zero_trials`), not ready, or any error |

## TVL 1.5 diagnostics

These diagnostics are specified by [RFC 0005 §2.6](../../formalization/rfc-0005-persistence-and-census-aggregates.md#26-schemas-and-diagnostics).
All rows below have severity error.
Old diagnostic meanings remain unchanged for documents without the new constructs.

| Code | Condition |
|---|---|
| `runtime_persistence_out_of_range` | with k = `persist.breached_in` and n = `persist.of_last`, the integers violate `1 ≤ k ≤ n ≤ 168` |
| `runtime_invalid_persistence` | ineligible source role/event, or either repeat coordinate with persistence |
| `runtime_aggregate_bound_out_of_range` | negative bound, or mean-score bound above 1 |
| `runtime_report_numeric` | malformed, noncanonical or out-of-domain aggregate report sum; nonzero sum for zero members; missing sum for complete nonempty evidence without `unknown_reason: "aggregate_precision_limit"` |
| `runtime_notify_only` (extended) | `persist` on an action other than `notify` |
| `runtime_invalid_profile` (extended) | missing/forbidden aggregate variant field, both/no bound directions, incompatible monitor tuple |
| `runtime_unknown_kind` (extended) | unknown aggregate kind, operator, metric or method |
| `runtime_missing_ref`, `runtime_ref_kind_mismatch` (reused) | missing or wrongly typed trigger/membership reference |
| `runtime_report_conservation` (extended) | aggregate count identities or window/source binding fail |
| `runtime_incompatible_replacement`, `evaluation_schedule_mismatch` (reused) | incompatible identity/persistence replacement, or changed schedule |
| `runtime_version_required`, `declared_version_below_constructs` (reused) | missing declaration, or incompatible declaration for a 1.5 construct |
| `schema_error`, `unsupported_construct` (reused) | invalid closed shape/type/tag, or an entrypoint refusing an unsupported construct |
| `response_deploy_without_promotion_monitor` (reused) | aggregate episode requests `deploy: if_promoted` without an eligible same-requirement promotion monitor |

Schemas check closed keys, primitive types and common required keys; lints check variant presence,
enums, numeric domains and references. Every nested record is closed. Malformed exchanged
summaries are refused; diagnostics echo no input.
The entire report sum string must match the minimal decimal encoding; trailing characters,
including a newline after `12.5`, are `runtime_report_numeric`. With zero members, only an absent
sum or `"0"` is valid. The aggregate window report format `tvl-runtime-report/2` ([RFC 0005 §2.5](../../formalization/rfc-0005-persistence-and-census-aggregates.md#25-composition-and-exchanged-documents)) permits optional `unknown_reason` with the closed, single-value
enum `aggregate_precision_limit`; omitting a complete nonempty sum with that reason yields
UNKNOWN(aggregate_precision_limit).

Verdict reasons are separate from error codes. TVL 1.5 adds `persistence_history_gap`
(missing, unavailable or incompatible history slot, including missing identity fields or absent
`available`), `aggregate_pending` (before due), and `aggregate_precision_limit`
(exact arithmetic exceeds declared limits). It reuses `inconclusive` for undecided persistence and
`insufficient` for complete empty aggregates, and extends `incomplete` to incomplete aggregates,
including invalid raw contributions. An invalid raw value is not a zero contribution.
Missing or null coverage, invalid membership (anything other than boolean `true`, boolean `false`
or the string `"unknown"`), and late units without coverage attesting completeness yield
UNKNOWN(incomplete). Check numeric encoding and precision/resource limits before exact rational
conversion; overlong otherwise valid numeric strings yield UNKNOWN(aggregate_precision_limit)
rather than a conversion failure.
