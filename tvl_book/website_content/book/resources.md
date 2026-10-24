# Resources · Tools and Plug-ins

TVL ships with a modular toolchain so you can wire validation, linting, and promotion gates into CI/CD. Each tool
lives under `tvl_tools/` in the repository and is installed as its own command (`tvl-validate`, `tvl-lint`, and so
on; see `[project.scripts]` in `pyproject.toml`). There is no single `tvl` wrapper command. Each command can also be
run as a Python module, for example `python -m tvl_tools.tvl_validate.cli <spec>`.

## Command Cheat Sheet

This sheet describes the TVL 1.5 toolchain.

| Command | What it Checks |
|---------|----------------|
| `tvl-parse <spec>` | Parses the YAML and prints it as JSON. |
| `tvl-validate <spec>` | JSON Schema validation, then the normative lints. It does not solve constraints. |
| `tvl-check-structural <spec>` | Satisfiability of the structural constraints: prints a satisfying assignment, or an UNSAT core. |
| `tvl-check-operational <spec>` | Derived preconditions against `environment.context`, and that declared `exploration.budgets` are positive. |
| `tvl-lint <spec>` | Normative lints (for example missing `min_effect` or duplicate TVARs). It reports diagnostics; it does not reformat YAML. |
| `tvl-ci-gate <module> <incumbent> <candidate>` | Offline promotion gate: compares incumbent and candidate measurement bundles under the module's promotion policy and prints `Promote`, `Reject`, `NoDecision` or `Error`. |
| `tvl-measure-validate <module> <config> <measurements>` | Checks a configuration and its measurement bundle against the module. |
| `tvl-config-validate <module> <config>` | Checks a configuration assignment against the module's domains and constraints. |
| `tvl-compose <overlay>` | Flattens an overlay chain into one module and checks the narrowing rules. |
| `tvl-compile-runtime <module>` | Compiles a module or pack into a version-tagged runtime contract and local artifacts. |
| `tvl-microsim-bridge <spec>` | Generates `microsim_presets.json` for the Orientation RAG interactive lab. It reads a legacy `configuration_space` block, not `tvars` (see the [lab page](../microsims/orientation-rag-circuit/index.md)). |

!!! hint "Combine Commands"
    One suggested setup: run `tvl-validate` and `tvl-check-structural` on every pull request, and run
    `tvl-ci-gate` before deployment on measurement bundles for the incumbent and the candidate. The gate's decision
    is a statistical test result: it is only as sound as the evidence in the bundles and the assumptions of the
    tests (see [formal semantics §9](../../../formalization/tvl-formal-semantics.md)).

## Tooling Workflow

1. **Local Editing:** run `tvl-validate tvl_book/examples/ch2_hello_tvl.tvl.yml` while iterating.
2. **Pre-Commit Hooks:** add `tvl-lint` (normative lints) and `tvl-check-structural` (constraint satisfiability).
3. **CI Pipeline:** run `tvl-ci-gate` alongside simulation tests and, if you use one, a dataset check such as DVL
   (a data-validation layer that is not part of TVL).
4. **Deployment:** an integration such as Traigent (whose optimizer, TVO, reads TVL; see
   [Chapter 5](chapter-05-integration.md)) can keep the validation reports with the promotion manifest.

## Interpreting Validation Output

### Structural Checks

```bash
tvl-check-structural spec.tvl.yml
```

Example output for a module whose constraints `temperature <= 0.2` and `temperature >= 0.6` conflict:

```
Structural constraints UNSAT.
- constraints.structural.0
    expression: temperature <= 0.2
      clause: temperature <= 0.2
- constraints.structural.1
    expression: temperature >= 0.6
      clause: temperature >= 0.6
```

!!! info "How to read it"
    - The first line is the result: satisfiable (followed by one satisfying assignment) or UNSAT.
    - For UNSAT, each entry is a constraint in the reported core, located by its path in the module. The core
      may be approximate and is not necessarily minimal.
    - The command exits 0 when the constraints are satisfiable and 2 otherwise (including when satisfiability
      is undecided). Use `--json` for machine-readable output.

### Operational Checks

```bash
tvl-check-operational tvl_book/examples/ch1_motivation_experiment.tvl.yml
```

Example output after raising `environment.context.gateway_baseline_latency_ms` to 400, which breaks the derived
precondition `env.context.gateway_baseline_latency_ms <= 250`:

```
Operational feasibility failed.
- derived_constraint_violation: [(1.0, 'env.context.gateway_baseline_latency_ms')]=400.0 violates constraint <= 250.0 (['constraints', 'derived', 0, 'require'])
```

!!! info "Remediation steps"
    - A derived-constraint violation means the declared environment does not meet a precondition: fix the
      environment values or the precondition.
    - A budget error means a declared `exploration.budgets` value is not positive. The check does not estimate
      cost and does not look at external policy limits or datasets.

### CI Gate Summary

`tvl-ci-gate <module> <incumbent> <candidate>` reads the module's objectives and promotion policy and two
measurement bundles. Text output starts with `Decision: <Promote|Reject|NoDecision|Error>` and a `Reason:` line,
followed by any warnings and an `== Evidence Summary ==` block. If a bundle is not promotion-ready, it prints the
readiness issues instead.

The exit code follows the decision: 0 for `Promote`, 2 for `Reject`, `NoDecision`, `Error`, a bundle that is not
promotion-ready, or any other error.

### Exit Codes

- `0` – success under the tool's contract (no issue, or only `info` issues; `Promote` for the gate).
- `2` – any reported `error` or `warning` issue, a validation or parse failure, or a gate decision other than
  `Promote`.
- `5` – `tvl-config-validate` only: the configuration fails validation or uses a construct it refuses.

Exit 1 is not a defined outcome. See the [error code reference](../../../docs/reference/error-codes.md#exit-codes).

## Further Reading

- TVL Unification Design v2.0 — architecture and deterministic export strategy.
- CAIN Extended Abstract — motivation for TVars and governed optimization.
- DVL Drift Playbook — pairing configuration changes with dataset checks.
