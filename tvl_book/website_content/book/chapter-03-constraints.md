# Chapter 3 · Constraints and Safety Nets

TVL uses a **typed Disjunctive Normal Form (DNF)** constraint language. Tools can hand these formulas to a
SAT/SMT solver (a program that decides whether a set of logical formulas can all be true at once) to check that
the constraints are satisfiable, that is, that at least one configuration meets them. This chapter shows how to
write structural and derived constraints, and how to test them before an optimizer (such as TVO, the TVL
Optimizer in the Traigent platform) spends trials on configurations the constraints rule out.

## Two Kinds of Constraints

TVL separates constraints into two categories:

| Category | Evaluated When | Purpose |
|----------|---------------|---------|
| **Structural** | Before trials run (static) | Rules over TVARs (tuned variables) that define the valid configuration space |
| **Operational Preconditions** | Before trials run (static), against the declared environment snapshot | Feasibility checks over environment symbols such as provider price, baseline latency, and request headroom |

```yaml
# Fragment: constraints section only (embed in full TVL module)
constraints:
  structural:
    # Checked statically - compiles to SAT/SMT
    - expr: "temperature <= 0.8"
    - when: model = "gpt-4o"
      then: max_tokens >= 1000

  derived:
    # Checked statically against the declared environment snapshot (env.context)
    - require: env.context.gateway_baseline_latency_ms <= 250
    - require: env.context.provider_input_price_usd_per_1k_tokens <= 0.05
    - require: env.context.rpm_limit - env.context.rpm_current_load >= 50
```

## Structural Constraint Syntax

Structural constraints use typed DNF formulas over TVARs (the tuned variables declared in `tvars`). The canonical
syntax, from the [grammar](../../../spec/grammar/tvl.ebnf), differs from general-purpose languages:

| Canonical TVL | Meaning | Avoid |
|----------------|---------|----------|
| `model = "gpt-4o"` | Equality | `model == "gpt-4o"` (accepted by the reference parser, but not canonical) |
| `temperature <= 0.5` | Comparison, using the declared TVAR name | `params.temperature <= 0.5` (unless a TVAR is declared with that dotted name) |
| `A and B` | Conjunction | `A && B` |
| `A or B` | Disjunction | `A \|\| B` |
| `not A` | Negation | `!A` |
| `x in {"a", "b"}` | Set membership | `x in ["a", "b"]` (accepted by the reference parser, but not canonical) |

The reference parser rejects `&&`, `||`, and `!`.

### Expression Form vs Implication Form

```yaml
# Fragment: structural constraints only
constraints:
  structural:
    # Expression form - always enforced
    - expr: "temperature <= 1.0"

    # Implication form - when/then (sugar for: not(when) or then)
    - when: model = "gpt-4o"
      then: temperature <= 0.5
```

### Structural Constraint Fragment

```yaml
# Fragment: structural constraints showcasing all syntax forms
constraints:
  structural:
    # Safety bound on temperature
    - expr: "0.0 <= temperature <= 1.0"

    # Premium models need lower temperature for consistency
    - when: model = "gpt-4o"
      then: temperature <= 0.5

    # Deep retrieval requires more tokens
    - when: retrieval_depth >= 5
      then: max_tokens >= 512

    # Forbidden combination (use negation)
    - expr: "not (temperature > 0.9 and max_tokens < 256)"

    # Set membership
    - when: use_caching = true
      then: model in {"gpt-4o-mini", "claude-3-haiku"}
```

!!! reliability "Debugging Constraint Failures"
    Run `tvl-check-structural spec.yml` to see which constraints are unsatisfiable.
    The tool reports an UNSAT core when available: a subset of constraints that conflict with each other.
    The core may be approximate and is not necessarily minimal.
    Use `--json` for machine-readable output.

## Operational Preconditions

Operational preconditions are linear comparisons (inequalities or equalities) over **environment symbols** (not
TVARs). They are checked statically, before any trial, against the environment snapshot declared in the module
(`environment.context`). Run `tvl-check-operational spec.yml` to check them.

```yaml
# Fragment: derived constraints over environment symbols
constraints:
  derived:
    # Provider price guard
    - require: env.context.provider_input_price_usd_per_1k_tokens <= 0.05

    # Baseline gateway latency guard
    - require: env.context.gateway_baseline_latency_ms <= 250

    # Request headroom guard
    - require: env.context.rpm_limit - env.context.rpm_current_load >= 50
```

**Supported operations:** `+`, `-`, scalar multiplication, and comparisons (`<=`, `>=`, `=`, `<`, `>`).

**Not supported:** Multiplication between symbols (`a * b`), division, exponentiation.

## Analog Circuit Drill · Watch Constraints React

Load the Orientation RAG lab (Latency Spike preset) to see constraint feedback the moment a slider moves.

<iframe src="../microsims/orientation-rag-circuit/main.html#latency-spike" height="640px" scrolling="no" style="width: 100%; border: none;"></iframe>

The lab shows three warnings. Only the rerank rule has the shape of a TVL structural constraint (an implication over
knobs). The latency and cost warnings check simulated outcomes; in TVL, limits on measured outcomes belong in
`objectives` or promotion-policy chance constraints (caps on a violation rate, checked against evaluation results at a
stated confidence; see [formal semantics Definition 9.8](../../../formalization/tvl-formal-semantics.md)), not in
structural constraints:

- **Latency under 800 ms** — raises amber/red when the simulated configuration breaches the ceiling.
- **Cost under $0.12** — highlights the response-token capacitor if the API budget slips.
- **Rerank weight ≥ 0.3** — conditional guard for `retriever_top_k >= 40` to prevent noisy answers.

Challenge yourself to bring all three back to green without dropping quality below 75.

## Testing Constraints

Use `tvl-check-structural` to verify your constraints are satisfiable:

```bash
# Check if constraints have at least one valid solution
tvl-check-structural my-spec.tvl.yml

# JSON output for CI pipelines
tvl-check-structural my-spec.tvl.yml --json
```

For unit testing in Python, use the TVL SDK:

```python
from tvl import load, validate_configuration
from tvl.structural_sat import check_structural

def test_constraints_satisfiable():
    """Verify the spec has at least one valid configuration."""
    module = load("my-spec.tvl.yml")
    result = check_structural(module)
    assert result.ok, f"UNSAT or undecided: {result.unsat_core}"

def test_specific_config_valid():
    """Verify a specific configuration passes domains and constraints."""
    module = load("my-spec.tvl.yml")
    config = {"assignments": {"model": "gpt-4o-mini", "temperature": 0.3, "max_tokens": 512}}
    report = validate_configuration(module, config)
    assert report["ok"], f"Violations: {report['domains'] + report['constraints']}"
```

`validate_configuration` expects a value for every TVAR. Its constraint evaluator is narrower than
`tvl-check-structural`: in TVL 1.5 it reports `not`, interval forms such as `0.0 <= temperature <= 1.0`, and
`in {...}` membership as unsupported, and fails closed. Use `check_structural` for those forms.

Run the tests:

```bash
pytest test_constraints.py -v
```

## Checklist Before Promotion

1. All structural constraints pass `tvl-check-structural` (satisfiable).
2. Constraint formulas use TVL syntax (`=`, `and`, `or`, `not`), not other languages.
3. Operational preconditions (`constraints.derived`) only reference environment symbols, not TVARs.
4. Unit tests cover both valid and invalid configurations.
