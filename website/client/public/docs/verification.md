# Semantics and Verification Reference

TVL verification answers whether a candidate satisfies a declared AI agent requirements contract. A positive result is scoped to the module, candidate, evaluation set, evaluator, environment, and evidence used by the check; it is not a universal safety or correctness claim.

This page explains the verifier model behind the TVL CLI and the SAT/UNSAT terminology that appears in the specification and example fixtures. **SAT** (satisfiable) means at least one assignment of values meets every structural constraint; **UNSAT** (unsatisfiable) means none does.

For the full mathematical treatment, see `formalization/tvl-formal-semantics.md`. This page is the user-facing implementation guide.

## The Three Layers

TVL has three different decision layers:

1. **Structural validity**
   Does the module admit at least one configuration assignment over the domains of its declared TVARs (tuned variables)?
2. **Operational feasibility**
   Given the module's environment snapshot, do the declared operational checks still hold and are exploration budgets well-formed?
3. **Promotion evidence**
   After evaluations have run, is the candidate acceptable and strong enough to replace the incumbent under `promotion_policy`?

The key source of confusion is that only the first layer uses the SAT/UNSAT vocabulary directly.

Keep the roles separate:

*   TVARs are the controllable variables the tuner may change.
*   The environment snapshot records the operational context: `bindings` pin opaque deployment references, while numeric feasibility checks come from `env.context.*`.
*   Objectives express preferences over outcomes.
*   Safety or readiness is a judgment about a candidate configuration after the relevant checks and evidence pass.

## What SAT Means In TVL

When a TVL example is labeled **SAT**, it means the structural verifier found at least one assignment of TVAR values that satisfies all structural constraints.

When an example is labeled **UNSAT**, it means no such assignment exists. The configured search space is empty, so optimization should not begin.

The structural checker gives one of three results:

*   **SAT** + a witness assignment such as `model = "gpt-4o", retriever.k = 5`. The checker reports SAT only after it re-checks the witness with exact arithmetic: every value must be an exact member of its declared domain, and every constraint must hold. `tvl-check-structural` exits 0 and its JSON has `status: "passed"`.
*   **UNSAT** + an UNSAT core or conflicting expression set showing which clauses cannot all hold together. UNSAT comes only from OR-Tools CP-SAT returning `INFEASIBLE`, or from a fallback search that tried every value of every domain. The tool exits 2 with `status: "unsat"`.
*   **undecided** + an issue with a code. The module is neither reported SAT nor UNSAT. The tool exits 2 with `status: "undecided"` and an `issues` list.

The undecided cases are:

| Code | When |
|------|------|
| `structural_undecided_without_solver` | OR-Tools is not installed and the fallback search could not try every value |
| `structural_solver_inconclusive` | CP-SAT returned a status other than a solution or `INFEASIBLE` |
| `structural_encoding_overflow` | the exact integer encoding of a numeric TVAR is too large for the solver |
| `structural_witness_unverified` | the solver's witness failed the exact re-check |
| `structural_witness_too_large` | a witness value is too large to print exactly |
| `structural_ill_typed_atom` | an atom has no typed truth value (unknown TVAR, mismatched types, a bool compared with a number) |
| `structural_non_finite_domain` | a TVAR declaration contains NaN or an infinity |
| `structural_unresolved_domain` | an atom uses a registry domain that is not resolved |
| `structural_pair_table_too_large` | an equality between two enum TVARs needs more than 1,000,000 value pairs |
| `structural_expansion_too_large` | expanding an expression's `in` sets and negated intervals gives more than 10,000 clauses (a Boolean formula whose own `and`/`or` expansion exceeds that limit is instead reported as an invalid structural constraint, with `status: "error"`) |
| `structural_value_too_large` | enum members expand to more than 1,000,000 nested nodes or 100 levels |

The [error code catalog](./error-codes.md) describes each one.

OR-Tools is a required dependency. If it cannot be imported, the checker falls back to a search over candidate values: domain bounds, the literals that constraints compare against, with neighbours, and whole float grids of up to 2001 points when the total search stays small. A witness that the fallback finds is checked like any other. When it finds none, it reports UNSAT only if it tried every value of every domain. Otherwise the result is undecided with `structural_undecided_without_solver`. Install OR-Tools to decide such a module.

### Exact values

The checker compares numbers exactly, as rationals, never as binary64 floats:

*   A numeric literal is read from its source text. `0.1` means exactly one tenth, and `0.100000000000000001` is a different value.
*   A float range with a resolution is the grid `min + i * resolution` for whole numbers `i` from 0 up to the largest point not above `max` (formal semantics Definition 3.6). A resolution that does not divide the range is fine: `{range: [0, 1], resolution: 0.3}` is `{0, 0.3, 0.6, 0.9}`, so `t >= 0.95` is UNSAT.
*   Strict comparisons are exact: on that grid `t > 0.6` admits `0.9` and not `0.6`.
*   An `int` TVAR compared with a fractional literal is decided exactly: `n = 1.5` is false for every integer, `n > 1.5` means `n >= 2`, and `n != 1.5` is always true. (`tvl-validate` rejects such a literal for an `int` TVAR as `constraint_type_mismatch`; the structural checker still decides it exactly when run on its own.)
*   A `bool` TVAR equals only `true` or `false`. It never equals `1` or `0`; comparing it with a number is `structural_ill_typed_atom`.
*   NaN and infinities are not TVL values. A domain that contains one is rejected (`structural_non_finite_domain`; `tvl-validate` reports `non_finite_domain_value`).
*   An enum domain is a set. Repeated members collapse into one before the check; `tvl-validate` still reports them as `duplicate_domain_value`.
*   A reversed range such as `{range: [5, 1]}` is malformed (formal semantics §2.4) and is rejected, not treated as empty. `tvl-validate` reports it as `invalid_range_domain`.

### Witness fields in the JSON output

`tvl-check-structural --json` gives the witness twice:

*   `exact_assignment` is the exact witness. Each numeric value is a string: a terminating decimal such as `"0.3"` when one exists, else a fraction `"p/q"`. Tuple values are converted component by component. Non-numeric values (strings, booleans) are unchanged. Use this field when you need the exact value.
*   `assignment` is kept for compatibility. Its numbers are plain binary64 floats and ints, so it can lose precision: two different grid points can round to the same float.

Both fields are `null` when the result is not SAT. The text output prints the exact witness.

## Structural Verifier

Tool:

```bash
tvl-check-structural module.tvl.yml --json
```

Purpose:

*   load declared TVAR domains
*   parse `constraints.structural`
*   decide whether the constraint set is satisfiable, or report undecided with a code (see the table above)
*   emit a witness assignment when satisfiable
*   emit an UNSAT core or conflicting expressions when not satisfiable

What it checks:

*   relationships between TVARs
*   implication logic such as `when` / `then`
*   feasibility of the static search space

What it does **not** check:

*   runtime budgets
*   environment-scoped operational preconditions
*   measured outcomes
*   promotion statistics

Repository locations:

*   CLI entry point: `tvl-check-structural` in `pyproject.toml`
*   implementation: `tvl_tools/tvl_check_structural/cli.py`
*   solver/model logic: `python/tvl/structural_sat.py`

## Operational Verifier

Tool:

```bash
tvl-check-operational module.tvl.yml --json
```

Purpose:

*   validate `exploration.budgets`
*   validate operational preconditions (`constraints.derived`)
*   evaluate environment-scoped feasibility checks against the current module snapshot

What it checks today in the reference implementation:

*   well-formed exploration budgets: positive `max_trials` and `max_wallclock_s`, and `max_spend_usd` at least 0 (0 means no paid spending is allowed)
*   operational precondition expressions over numeric `env.context.*` symbols
*   rejection of unsupported environment-field usage and rejection of binding references inside operational preconditions

What it does **not** check:

*   structural SAT/UNSAT
*   incumbent vs candidate promotion logic
*   statistical acceptability of measurements

Repository locations:

*   CLI entry point: `tvl-check-operational` in `pyproject.toml`
*   implementation: `tvl_tools/tvl_check_operational/cli.py`
*   checking logic: `python/tvl/operational.py`

## Promotion-Evidence Checks

The structural and operational verifiers are both **pre-evaluation** checks. They do not decide whether a candidate should ship.

That later stage uses:

```bash
tvl-measure-validate module.tvl.yml config.yml measurements.yml
tvl-ci-gate module.tvl.yml incumbent.measure.yml candidate.measure.yml --json
```

These tools work with measured evidence, chance constraints, and the `promotion_policy` comparison rule.

**Keep the final evaluation independent of selection.** The gate compares one incumbent with one candidate. It cannot see how many candidates you tried or whether you chose the candidate on the same data. Choose on a tuning split, keep a separate evaluation set for the final comparison, and record how many candidates you tried. Repeated looks at the same evaluation set bias the result in the candidate's favour, and the formal semantics lists independent collection of the evidence among the assumptions behind a Promote (`formalization/tvl-formal-semantics.md`, section 9.8).

**Reading the exit status of `tvl-ci-gate`.** It exits 0 only for `Promote`. It exits 2 for `Reject`, for `NoDecision`, for `Error` (a check that is undefined, such as a chance constraint with no trials: `zero_trials`; canonical `chance_outcomes` with `trials` 0 or missing are refused earlier as a schema error, while a deprecated `chance` summary with `summary.trials: 0` reaches the gate and gives `Error`), and for inputs it cannot use (bundles that are not promotion-ready, unreadable files, any error). A nonzero status alone therefore does not tell you which. With `--json`, read `decision` when it is present (for `Error`, the `error` and `codes` fields say why); when it is absent, read the `error` and `readiness_issues` fields. The exit-code table is in the error-codes reference.

**Calibration.** The reference gate cannot validate calibration certificates. `tvl-ci-gate` refuses under every strict-mode trigger of RFC 0001 section 3.6 that is visible in the module, including the composite coverage fold of RFC 0002 section 3.6: `promotion_policy.require_calibration.enabled`; a `cvar` whose `governance.require_calibration` is set; any declared `cvar` (each one has a certificate); a chance constraint in a module that has a `cvar` or a calibrated composite member; and a composite with a gate threshold, a `signal_accept` stop, an aggregate accept threshold, a cvar-valued cardinality, or an aggregate judge that references a composite with a calibrated member. A module with a chance constraint and nothing to certify still gets a decision. The RFC 0001 trigger that comes from the operational profile (a selection target) is not covered: the gate does not receive the profile, so it cannot check it. For a module requiring calibration certificates `tvl-ci-gate` reports the readiness issue `calibration_evidence_unsupported` and exits 2 without a decision. This differs from `NoDecision`: no evidence comparison ran.

## Where Users Should Start

If you are authoring TVL modules:

1. Run `tvl-validate`
2. Run `tvl-check-structural`
3. Run `tvl-check-operational`
4. Only after collecting measurements, run `tvl-measure-validate` and `tvl-ci-gate`

If you are trying to understand constraint syntax, read:

*   [Constraint Language Reference](/specification/constraint-language)

If you want the full semantics, read:

*   `formalization/tvl-formal-semantics.md`

## What Implementers Need To Support

If you are implementing TVL support in another runtime or platform, the minimum useful surface is:

1. A loader/parser for TVL modules
2. Schema validation and linting for top-level shape and field contracts
3. A structural satisfiability checker over typed TVAR domains
4. An operational checker for operational preconditions (`constraints.derived`) and exploration budgets

If you want parity with the reference toolchain, also implement:

1. Configuration validation against the module domains
2. Measurement-bundle validation
3. Promotion-policy evaluation for incumbent vs candidate evidence
4. Overlay composition if you support preprocessed layered specs

The public contract is the semantic behavior, not the exact solver brand. You may use a CP-SAT solver (constraint programming with Boolean satisfiability techniques, as in OR-Tools, which the reference checker uses), an SMT solver (satisfiability modulo theories), brute-force enumeration for small domains, or another decision procedure, as long as SAT/UNSAT results and diagnostics remain faithful to the language semantics.
