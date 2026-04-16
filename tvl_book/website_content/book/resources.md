# Resources · Tools and Plug-ins

TVL ships with a modular toolchain so you can wire validation, linting, and promotion gates into CI/CD. Each
module lives under `tvl/tvl_tools/` and can be invoked directly or via the `tvl` wrapper command.

## Command Cheat Sheet

| Command | What it Checks |
|---------|----------------|
| `python -m tvl_tools.tvl_parse <spec>` | Fast schema parsing with line-level error reports. |
| `python -m tvl_tools.tvl_validate <spec>` | Full semantic validation: CEL constraints, units, override semantics. |
| `python -m tvl_tools.tvl_check_structural <spec>` | Lints inheritance graphs, duplicate IDs, and naming conventions. |
| `python -m tvl_tools.tvl_check_operational <spec>` | Reviews budgets, overlay narrowing, and deployment readiness. |
| `python -m tvl_tools.tvl_lint <spec>` | Formats YAML keys, ordering, and comments. |
| `python -m tvl_tools.tvl_ci_gate <spec>` | Bundled gate used by Triagent promotion pipelines. |
| `python -m tvl_tools.tvl_measure_validate <metrics.yml>` | Verifies metric definitions and unit annotations. |
| `python -m tvl_tools.tvl_config_validate --override <file>` | Checks environment overrides or CLI patch files before deployment. |
| `python -m tvl_tools.microsim_bridge <spec>` | Generates `microsim_presets.json` for the Orientation RAG interactive lab. |

!!! hint "Combine Modules"
    The plug-ins are composable. Many teams run `tvl_parse`, `tvl_validate`, and `tvl_check_structural` on every
    pull request, with `tvl_ci_gate` reserved for pre-deploy promotion proofs.

## Tooling Workflow

1. **Local Editing:** run `python -m tvl_tools.tvl_validate examples/ch2_hello_tvl.tvl.yml` while iterating.
2. **Pre-Commit Hooks:** add `tvl_lint` and `tvl_check_structural` to ensure formatting and inheritance hygiene.
3. **CI Pipeline:** execute `tvl_ci_gate` alongside simulation tests and DVL validation suites.
4. **Deployment:** Triagent consumes the validation reports and embeds them in the promotion manifest.

## Interpreting Validation Output

TVL plug-ins emit structured messages so you can quickly triage issues.

### Structural Checks

```bash
python -m tvl_tools.tvl_check_structural tvl_book/examples/ch4_environment_overlays.tvl.yml
```

Typical output:

```
[STRUCTURAL] ERROR env.production.configuration_space.max_tokens.range:
  override expands base range (base=128..1024, override=64..768)
[STRUCTURAL] WARNING metadata.tags: duplicate value "tv-book"
```

!!! info "How to read it"
    - **Prefix** (`[STRUCTURAL]`) identifies the plug-in.
    - **Severity** (`ERROR`, `WARNING`) determines the exit code (errors exit non-zero).
    - **Path** pinpoints the failing element in dotted notation.
    - **Message** provides the suggested fix.

### Operational Checks

```bash
python -m tvl_tools.tvl_check_operational tvl_book/examples/ch1_motivation_experiment.tvl.yml
```

Typical output:

```
[OPERATIONAL] ERROR optimization.budget.max_trials:
  value 5000 exceeds policy limit 500 (environment=finals_week)
[OPERATIONAL] WARNING evaluation_sets[policy_changes]:
  dataset dvl://faq/policy-2024 missing required drift suite "faq-topic-shift"
```

!!! info "Remediation steps"
    - Budget errors highlight overrides that violate guardrails—tighten the spec or update the policy repo.
    - Dataset warnings surface missing DVL suites—wire the evaluation set into an approved drift test before promotion.

### CI Gate Summary

`python -m tvl_tools.tvl_ci_gate <spec>` aggregates structural and operational checks:

```
[CI-GATE] structural: 0 errors, 1 warnings
[CI-GATE] operational: 1 errors, 0 warnings
[CI-GATE] FAILED
```

Use this in automated pipelines; the exit code mirrors the most severe finding.

### Exit Codes

- `0` – success or warnings only.
- `1` – validation failure.
- `2` – CLI usage error (missing files, bad arguments).

## Further Reading

- TVL Unification Design v2.0 — architecture and deterministic export strategy.
- CAIN Extended Abstract — motivation for TVars and governed optimization.
- DVL Drift Playbook — pairing configuration changes with dataset checks.
