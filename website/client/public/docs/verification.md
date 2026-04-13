# Semantics and Verification Reference

This page explains the verifier model behind the TVL CLI and the SAT/UNSAT terminology that appears in the specification and example fixtures.

For the full mathematical treatment, see `tvl/formalization/tvl-formal-semantics.md`. This page is the user-facing implementation guide.

## The Three Layers

TVL has three different decision layers:

1. **Structural validity**
   Does the module admit at least one configuration assignment over the declared TVAR domains?
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

Typical structural verifier outputs are:

*   **SAT** + a witness assignment such as `model = "gpt-4o", retriever.k = 5`
*   **UNSAT** + an UNSAT core or conflicting expression set showing which clauses cannot all hold together

## Structural Verifier

Tool:

```bash
tvl-check-structural module.tvl.yml --json
```

Purpose:

*   load declared TVAR domains
*   parse `constraints.structural`
*   decide whether the constraint set is satisfiable
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

*   CLI entry point: `tvl-check-structural` in `tvl/pyproject.toml`
*   implementation: `tvl/tvl_tools/tvl_check_structural/cli.py`
*   solver/model logic: `tvl/python/tvl/structural_sat.py`

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

*   positive and well-formed exploration budgets
*   operational precondition expressions over numeric `env.context.*` symbols
*   rejection of unsupported environment-field usage and rejection of binding references inside operational preconditions

What it does **not** check:

*   structural SAT/UNSAT
*   incumbent vs candidate promotion logic
*   statistical acceptability of measurements

Repository locations:

*   CLI entry point: `tvl-check-operational` in `tvl/pyproject.toml`
*   implementation: `tvl/tvl_tools/tvl_check_operational/cli.py`
*   checking logic: `tvl/python/tvl/operational.py`

## Promotion-Evidence Checks

The structural and operational verifiers are both **pre-evaluation** checks. They do not decide whether a candidate should ship.

That later stage uses:

```bash
tvl-measure-validate module.tvl.yml config.yml measurements.yml
tvl-ci-gate module.tvl.yml incumbent.measure.yml candidate.measure.yml --json
```

These tools work with measured evidence, chance constraints, and the `promotion_policy` comparison rule.

## Where Users Should Start

If you are authoring TVL modules:

1. Run `tvl-validate`
2. Run `tvl-check-structural`
3. Run `tvl-check-operational`
4. Only after collecting measurements, run `tvl-measure-validate` and `tvl-ci-gate`

If you are trying to understand constraint syntax, read:

*   [Constraint Language Reference](/specification/constraint-language)

If you want the full semantics, read:

*   `tvl/formalization/tvl-formal-semantics.md`

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

The public contract is the semantic behavior, not the exact solver brand. You may use CP-SAT, SMT, brute-force enumeration for small domains, or another decision procedure, as long as SAT/UNSAT results and diagnostics remain faithful to the language semantics.
