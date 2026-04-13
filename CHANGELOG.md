# Changelog

All notable changes to the TVL spec, schema, tools, and SDK will be documented in this file.

## [1.0.0] - 2026-02-01

### Added

#### Formal Semantics (Version 1.0)

- Complete formal mathematical foundations document
- Type soundness theorem with proof
- SMT encoding soundness with direction-aware rounding
- Three-layer promotion semantics (validity → acceptability → dominance)
- ε-Pareto dominance with statistical testing
- TOST equivalence testing for banded objectives
- Clopper-Pearson exact intervals for chance constraints

#### Multiple Testing Adjustment

- Benjamini-Hochberg FDR control (`adjust: BH`)
- Holm FWER control (`adjust: holm`)
- Bonferroni FWER control (`adjust: bonferroni`)

#### OOPSLA Paper

- Complete paper draft for OOPSLA 2026 submission
- 12 section files with modular LaTeX structure
- Comprehensive bibliography (35+ references)

#### Open Source Release Preparation

- Apache 2.0 license for tools (`tvl_tools/`)
- MIT license for language specification
- Updated CITATION.cff with proper metadata
- VS Code plugin version 1.0.0

### Changed

- Version bump from 0.9 to 1.0 across all artifacts
- Updated JSON Schema title to "TVL Module (1.0)"
- Development status upgraded to "Production/Stable"
- Repository URL updated to tvl-lang organization

### Fixed

- Consistent versioning across all components
- Added `__version__` to Python SDK for programmatic access

---

## [0.9.0] - 2025-01-26

### Added

#### Type System

- **Base types**: `bool`, `int`, `float` with explicit domains
- **Compound types**: `enum[str]`, `enum[int]`, `enum[float]` for finite discrete sets
- **Product types**: `tuple[T1, T2, ...]` with Cartesian product semantics
- **Callable types**: `callable[ProtoId]` for protocol-defined functions with lazy resolution

#### Domain Specifications

- Explicit enumeration: `domain: [val1, val2, ...]`
- Numeric ranges: `domain: { range: [min, max], resolution: step }`
- Set wrapper: `domain: { set: [...] }` for metadata attachment
- Registry references: `domain: { registry: name, filter: expr }` for dynamic resolution

#### Constraint Language

- **Structural constraints**: Typed DNF compiled to SAT (QF_LIA) / SMT (QF_LRA)
- Atoms: equality (`=`, `!=`), comparison (`<`, `<=`, `>`, `>=`), intervals, set membership (`in`)
- Logical connectives: `and`, `or`, `not`, implication (`=>`)
- TVAR-to-TVAR equality comparisons with type checking
- **Derived constraints**: Linear arithmetic over environment symbols (not TVARs)

#### Objectives

- Standard objectives with `direction: maximize | minimize`
- Optional `metric_ref` identifiers for binding objectives to evaluator metric contracts
- **Banded objectives**: Target ranges with TOST equivalence testing
  - Range form: `target: [low, high]`
  - Center/tolerance form: `target: { center: num, tol: num }`

#### Promotion Policy

- `epsilon_pareto` dominance relation
- Per-objective `min_effect` thresholds (formerly epsilon)
- Benjamini-Hochberg adjustment (`adjust: BH`)
- **Chance constraints**: Probabilistic bounds with confidence levels
- **Tie breakers**: `min`, `max`, `min_abs_deviation`, `custom`

#### Exploration

- Strategy types: `random`, `grid`, `tpe`, `cmaes`, `nsga2`, `custom`
- Budget controls: `max_trials`, `max_spend_usd`, `max_wallclock_s`
- Parallelism configuration
- Convergence criteria: `hypervolume_improvement` with window/threshold

#### CLI Tools

- `tvl-parse` — Parse YAML to JSON AST
- `tvl-lint` — Semantic lint checks with 40+ error codes
- `tvl-validate` — JSON Schema + normative lints combined
- `tvl-check-structural` — SAT satisfiability check with UNSAT core extraction
- `tvl-check-operational` — Operational feasibility verification
- `tvl-config-validate` — Validate configuration against module
- `tvl-measure-validate` — Validate measurement bundles
- `tvl-ci-gate` — CI promotion gate dry-run (paired tests with epsilon and BH)
- `tvl-compose` — Flatten overlay files into valid TVL 0.9 modules
- `tvl-microsim-bridge` — Simulation bridge for testing

#### Documentation

- Comprehensive error code catalog (40+ codes with remediation guidance)
- Language reference with type system specification
- Constraint language reference
- Getting started guide
- Example walkthroughs

#### Infrastructure

- JSON Schema: `tvl.schema.json`
- EBNF Grammar: `tvl.ebnf`
- Configuration schema: `tvl-configuration.schema.json`
- Measurement schema: `tvl-measurement.schema.json`
- GitHub Actions CI pipeline
- 69 unit tests covering type system, constraints, and promotion policy

### Fixed

- `exploration` section is now correctly optional (lint no longer requires it)

### Notes

- Spec targets TVL 0.9; expect minor refinements before 1.0
- Registry-backed domains are defined but linting support is limited
- `tvl-ci-gate` provides dry-run functionality; full implementation pending TVO integration
