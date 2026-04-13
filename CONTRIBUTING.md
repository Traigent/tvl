# Contributing Guide

Thank you for your interest in improving TVL! This repo contains the normative spec, minimal tools, examples, and a Python SDK.

## Development Setup

1. Create a virtual environment.
2. From `tvl/`, install in editable mode:
   - `pip install -e .[dev]`

## Tools

- `tvl-parse <module.yml>` — parse and print AST (JSON)
- `tvl-lint <module.yml>` — normative lint checks (duplicate TVARs, bands, policy coverage, exploration budgets)
- `tvl-validate <module.yml>` — JSON Schema validation plus the same normative lints
- `tvl-config-validate <module.yml> <config.yml>` — ensure a configuration satisfies domain + structural constraints
- `tvl-measure-validate <module.yml> <config.yml> <measurement.yml>` — structural + operational + chance checks, plus promotion-readiness reporting
- `tvl-ci-gate <module.yml> <incumbent.yml> <candidate.yml>` — module-first promotion gate dry-run

Return codes: 0 on success; 2 for schema/type/lint errors; 3 reserved for future SAT/SMT unsat signals.

## Adding Examples

Place YAML files in `spec/examples/`. Keep them focused (15–40 lines). Run the tools locally before submitting a PR.

## Proposing Spec Changes

Open an issue with the proposed change, rationale, and any impacts on schema or tools. Keep normative statements precise.
