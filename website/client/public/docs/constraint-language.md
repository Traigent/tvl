# TVL Constraint Language Reference

TVL uses a **typed Disjunctive Normal Form (DNF)** constraint language for structural constraints. This document provides a complete reference for writing and understanding TVL constraints.

## Overview

TVL constraints are divided into two categories:

1. **Structural Constraints**: Boolean formulas over TVARs that express rules over the configuration space, checked by the structural verifier before search or promotion
2. **Operational Preconditions** (`constraints.derived`): Linear arithmetic over `env.context.*` symbols that express required operating conditions relative to the current environment snapshot, checked by the operational verifier against that snapshot

Operational preconditions are not additional knobs to tune. They are checks over the declared `env.context.*`
symbols that help decide whether the study or rollout is feasible under the module's environment snapshot.

Structural constraints are the part that lead to the familiar **SAT/UNSAT** vocabulary:

*   **SAT**: at least one legal TVAR assignment satisfies all structural clauses
*   **UNSAT**: no legal TVAR assignment exists, so the feasible search space is empty

In the reference implementation, `tvl-check-structural` is the tool that answers that question. Operational
preconditions are handled separately by `tvl-check-operational`.

## Structural Constraints

Structural constraints define rules over the configuration space. Collectively, they must admit at least one assignment for the module to be structurally valid.

### Basic Syntax

Structural constraints can be expressed in two forms:

```yaml
constraints:
  structural:
    # Expression form - standalone constraint
    - expr: "temperature <= 1.0"

    # Implication form - conditional constraint
    - when: "use_cot = true"
      then: "temperature <= 0.5"
```

### Atom Types

Atoms are the primitive predicates in constraint formulas.

#### Equality Atoms
Compare a TVAR to a literal value:
```yaml
- expr: "model = 'gpt-4'"           # enum equality
- expr: "use_examples = true"        # boolean equality
- expr: "max_calls = 5"              # integer equality
```

#### Comparison Atoms
Compare numeric TVARs to numeric literals:
```yaml
- expr: "temperature >= 0.3"         # greater-than-or-equal
- expr: "max_tokens <= 1000"         # less-than-or-equal
```

#### Interval Atoms
Bound a numeric TVAR to a range:
```yaml
- expr: "0.0 <= temperature <= 1.0"  # closed interval
- expr: "100 <= max_tokens <= 4000"  # integer interval
```

#### Membership Atoms
Check if a TVAR value is in a set:
```yaml
- expr: "model in {'gpt-4', 'gpt-4-turbo'}"
- expr: "retriever_k in {3, 5, 7, 10}"
```

#### TVAR Equality Atoms
Compare two TVARs of compatible types:
```yaml
- expr: "primary_model = fallback_model"
```

### Logical Operators

Combine atoms using standard logical operators:

```yaml
# Conjunction (AND)
- expr: "temperature <= 0.7 and max_tokens >= 500"

# Disjunction (OR)
- expr: "model = 'gpt-4' or model = 'gpt-4-turbo'"

# Negation (NOT)
- expr: "not (use_cot = true and temperature > 0.8)"

# Implication (=>)
- when: "use_cot = true"
  then: "max_tokens >= 1000"
# Equivalent to: "not (use_cot = true) or max_tokens >= 1000"

# Parentheses for grouping
- expr: "(model = 'gpt-4' or model = 'gpt-4-turbo') and temperature <= 0.5"
```

### Operator Precedence

1. `not` (highest)
2. `and`
3. `or`
4. `=>` (lowest)

Use parentheses to override precedence.

### Type Checking Rules

All constraints are type-checked against the declared TVARs:

| TVAR Type | Allowed Operators | Allowed Comparands |
|-----------|-------------------|-------------------|
| `bool` | `=`, `!=` | `true`, `false` |
| `int` | `=`, `!=`, `<`, `<=`, `>`, `>=`, `in` | integers |
| `float` | `=`, `!=`, `<`, `<=`, `>`, `>=`, `in` | numbers |
| `enum[T]` | `=`, `!=`, `in` | literals from domain |
| `tuple[...]` | `=`, `!=`, `in` | tuples from domain |
| `callable[P]` | `=`, `!=`, `in` | identifiers from registry |

**Important**: Float equality (`=`) generates a warning because floating-point comparison may be unstable. Consider using range constraints instead.

**Note**: Ordering comparisons between TVARs (e.g., `a >= b`) are not supported. TVAR-to-TVAR checks are supported for equality/inequality (e.g., `a = b`).

## Operational Preconditions (`constraints.derived`)

Operational preconditions are linear arithmetic expressions over numeric `env.context.*` symbols (not TVARs). They are
evaluated against the current environment snapshot and are written under the `constraints.derived` key.

### Syntax

```yaml
constraints:
  derived:
    - require: "env.context.provider_input_price_usd_per_1k_tokens <= 0.05"
    - require: "env.context.gateway_baseline_latency_ms <= 250"
    - require: "env.context.rpm_limit - env.context.rpm_current_load >= 50"
```

### Supported Operations

- Addition: `a + b`
- Subtraction: `a - b`
- Scalar multiplication: `2.5 * symbol`
- Comparison: `<=`, `>=`, `=`, `<`, `>`

**Not Supported** (non-linear operations):
- Multiplication between symbols: `a * b`
- Division: `a / b`
- Exponentiation: `a ^ 2`

### Environment Symbol References

Operational preconditions reference numeric symbols from `environment.context`. `environment.bindings` is for opaque
deployment references and must not appear in arithmetic.

```yaml
environment:
  snapshot_id: "2025-01-15T12:00:00Z"
  bindings:
    retriever_index: faq-v3
    llm_gateway: us-east-1
  context:
    provider_input_price_usd_per_1k_tokens: 0.03
    gateway_baseline_latency_ms: 180
    rpm_limit: 600
    rpm_current_load: 420
```

In operational preconditions:
```yaml
constraints:
  derived:
    - require: "env.context.provider_input_price_usd_per_1k_tokens <= 0.05"
    - require: "env.context.rpm_limit - env.context.rpm_current_load >= 50"
```

## Common Patterns

### Safety Bounds
```yaml
constraints:
  structural:
    - expr: "0.0 <= temperature <= 2.0"
    - expr: "max_tokens >= 100 and max_tokens <= 4000"
```

### Conditional Requirements
```yaml
constraints:
  structural:
    # If using chain-of-thought, require lower temperature
    - when: "use_cot = true"
      then: "temperature <= 0.5"

    # Premium models require higher token limits
    - when: "model in {'gpt-4', 'claude-3-opus'}"
      then: "max_tokens >= 2000"
```

### Forbidden Combinations
```yaml
constraints:
  structural:
    # Prevent high temperature with streaming
    - expr: "not (temperature > 1.0 and streaming = true)"

    # Never use legacy model with new features
    - when: "model = 'gpt-3.5-turbo'"
      then: "not (use_tools = true)"
```

### Environment Feasibility Guards (Operational Preconditions)
```yaml
constraints:
  derived:
    # Require a cheap enough provider snapshot
    - require: "env.context.provider_input_price_usd_per_1k_tokens <= 0.05"

    # Require enough gateway headroom before running the study
    - require: "env.context.rpm_limit - env.context.rpm_current_load >= 50"
```

## Compilation to SMT

Structural constraints compile to SMT/SAT-style solver inputs in the reference implementation:

1. **Boolean TVARs**: Direct propositional encoding
2. **Integer TVARs**: QF_LIA (quantifier-free linear integer arithmetic)
3. **Float TVARs**: Scaled to integers for QF_LIA (default precision: 1000)
4. **Enum TVARs**: Encoded as bounded integers
5. **DNF formulas**: Direct SMT encoding

### Example Compilation

TVL constraint:
```yaml
- when: "use_cot = true"
  then: "temperature <= 0.5"
```

SMT-LIB output (temperature scaled by 1000):
```smt
(declare-const use_cot Bool)
(declare-const temperature Int)
(assert (and (>= temperature 0) (<= temperature 2000)))
(assert (or (not use_cot) (<= temperature 500)))
(check-sat)
```

If the solver returns `sat`, the verifier can emit a witness assignment. If it returns `unsat`, the verifier can report an UNSAT core or the conflicting expressions that made the search space empty.

## Which Tool Checks What

Use the CLI according to the semantic layer you are trying to validate:

```bash
# Syntax, schema, and lint checks
tvl-validate module.tvl.yml

# Structural SAT/UNSAT over TVAR domains
tvl-check-structural module.tvl.yml --json

# Environment-scoped operational preconditions and budgets
tvl-check-operational module.tvl.yml --json
```

`tvl-check-operational` is not the statistical promotion gate. Promotion evidence is checked later with `tvl-measure-validate` and `tvl-ci-gate`.

## Best Practices

1. **Use ranges over equality for floats**: Prefer `0.4 <= temperature <= 0.6` over `temperature = 0.5`

2. **Keep constraints simple**: Complex nested expressions are harder to debug and may slow SAT solving

3. **Separate concerns**: Use structural constraints for TVAR relationships, operational preconditions (`constraints.derived`) for numeric `env.context.*` feasibility checks, and chance constraints for measured rollout gates

4. **Test constraints**: Write unit tests for your constraints using the test harness pattern from `ch3_constraint_tests.py`

5. **Document intent**: Add comments explaining why constraints exist, not just what they do

6. **Version constraints**: When requirements change, update constraints in version control with clear commit messages

## Error Codes Reference

See [error-codes.md](./error-codes.md) for a complete list of constraint-related error codes:

- `undeclared_tvar`: Unknown TVAR in constraint
- `constraint_value_out_of_domain`: Literal outside domain
- `constraint_type_mismatch`: Type incompatibility
- `non_linear_structural`: Non-linear operators used
- `derived_references_tvar`: TVAR used inside an operational precondition
- `derived_invalid_symbol_reference`: Operational precondition referenced something other than `env.context.*`
- `derived_references_bindings`: `environment.bindings` referenced inside an operational precondition
- `float_equality` (warning): Float equality comparison

## Grammar (EBNF)

```ebnf
formula       = disjunction ;
disjunction   = conjunction , { "or" , conjunction } ;
conjunction   = unary , { "and" , unary } ;
unary         = [ "not" ] , ( atom | "(" , formula , ")" | implication ) ;
implication   = formula , "=>" , formula ;

atom          = equality_atom | comparison_atom | interval_atom | tvar_eq_atom | membership_atom ;
equality_atom = ident , "=" , value ;
comparison_atom = ( ident , ">=" , scalar ) | ( ident , "<=" , scalar ) ;
interval_atom = number , "<=" , ident , "<=" , number ;
tvar_eq_atom  = ident , "=" , ident ;
membership_atom = ident , "in" , set_literal ;

set_literal   = "{" , value , { "," , value } , "}" ;
scalar        = number | ident ;
```

See `tvl/spec/grammar/tvl.ebnf` for the complete grammar specification.
