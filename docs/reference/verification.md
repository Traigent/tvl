# Semantics and Verification Reference

TVL verification answers whether a candidate satisfies a declared AI agent requirements contract. A positive result is scoped to the module, candidate, evaluation set, evaluator, environment, and evidence used by the check; it is not a universal safety or correctness claim.

This page explains the verifier model behind the TVL CLI and the SAT/UNSAT terminology that appears in the specification and example fixtures. **SAT** (satisfiable) means at least one assignment of values meets every structural constraint; **UNSAT** (unsatisfiable) means none does.

For the full mathematical treatment, see `formalization/tvl-formal-semantics.md`. This page is the user-facing implementation guide.

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

The solver result is exact when OR-Tools (a required dependency) is installed. If OR-Tools cannot be imported, the checker falls back to a search over sampled candidate values: domain bounds and the literals that constraints compare against, with neighbours. That fallback can miss a valid float assignment, so it can report UNSAT, with a core, for a satisfiable module. Treat a fallback UNSAT as unconfirmed.

## Structural Verifier

Tool:

```bash
tvl-check-structural module.tvl.yml --json
```

Purpose:

*   load declared TVAR domains
*   parse `constraints.structural`
*   decide whether the constraint set is satisfiable (exactly with OR-Tools; the fallback search described above can wrongly report UNSAT for float constraints)
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

**Reading the exit status of `tvl-ci-gate`.** It exits 0 only for `Promote`. It exits 2 for `Reject`, for `NoDecision`, and for inputs it cannot use (bundles that are not promotion-ready, unreadable files, any error). A nonzero status alone therefore does not tell you which. With `--json`, read `decision` when it is present; when it is absent, read the `error` and `readiness_issues` fields. The exit-code table is in the error-codes reference.

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
