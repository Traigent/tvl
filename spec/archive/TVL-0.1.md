# TVL 0.1 — Normative Specification (Outline)

This document is the normative specification for TVL (Tuned Variables Language) version 0.1. Non-normative explanations may be included but are identified as such.

## Front matter

- Scope and non-goals (language definition, not implementation)
- Conformance terms (MUST/SHOULD/MAY)
- Versioning (TVL module version, schema version)

## 1. Core objects and notation

- Environment snapshot (E_τ), evaluation set (I_τ)
- TVAR set (T); domains D_{t_i}(E_τ); joint space X(E_τ)
- Structural feasibility C^{str}{E_τ} and operational feasibility F_{op}

## 2. Syntax

- Abstract syntax (AST): types, TVAR declarations, constraints, objectives, policy, exploration
- Concrete YAML schema: top-level blocks (`tvl`, `environment`, `evaluation_set`, `tvars`, `constraints`, `objectives`, `promotion_policy`, `exploration`) with list-based TVAR/objective declarations. Machine-readable schema lives in `spec/grammar/tvl.schema.json`.

## 3. Static semantics

- Typing rules for atoms and formulas; well-formed domains; band definitions
- DNF constraint language; compilation target (QF_LIA/LRA) and diagnosable errors

## 4. Denotational semantics

- Objective functionals (means, quantiles) and orientation vector (σ)
- Banded targets: hard chance-constraint vs soft distance-to-band (TOST)
- Stochastic ε-Pareto dominance at level α with Benjamini–Hochberg control; paired tests; decisions: Promote / Reject / NoDecision

## 5. Execution semantics for TVAR reads

- Atomic per-invocation reads; async boundaries; isolation across trials (MUST)

## 6. Exploration sub-language

- Strategies (random, grid, TPE, CMA-ES, NSGA-II), feasible prior over F_{op}
- Budgets & stop rules (hypervolume improvement)

## 7. CI gate and artifacts

- Gate algorithm; multiplicity handling; promotion manifest fields (dataset checksum, seeds, price snapshot id/hash, p-values, ε)

## 8. Conformance requirements

- Loader MUST parse & type-check; compile constraints; specialize domains from E_τ; materialize policy; evaluate only F_{op}. Provide unsat core when available.

## 9. Configurations

- A **configuration** is a total assignment `γ : T → Value` respecting the domain of each TVAR at environment snapshot E_τ.
- Configurations are serialized as YAML objects conforming to `spec/grammar/tvl-configuration.schema.json`.
- Structural validity: `γ` MUST satisfy all declarative structural constraints (DNF, implications) when interpreted with operator semantics defined in §3.
- Operational metadata MAY accompany a configuration (trial counts, seeds, dataset hashes) but MUST NOT alter structural validity.
  - Optional fields: `config_id`, `module_id`, `module_version`, `trace` (opaque map).

## 10. Measurement bundles

- A **measurement bundle** captures observed metrics for a configuration; schema defined in `spec/grammar/tvl-measurement.schema.json`.
- Each objective `o` MUST provide an observed statistic (`mean`, `quantile`, or `estimate`) and, when applicable, an effect size (`delta`) and hypothesis test `p_value`.
- Chance/SLO checks:
  - Hard SLO (threshold) objectives MUST provide observed statistic verifying the inequality.
  - Banded objectives MUST supply an observed statistic compared against `[low, high]`.
  - Promotion policy parameters (`α`, `ε`) determine acceptance criteria for `p_value` and `delta` fields.

## 11. Validation semantics

- **Structural**: verifying `γ ⊨ C^{str}` via SMT/CP-SAT compilation of DNF constraints.
- **Operational**: verifying observed metrics satisfy SLOs, bands, and `ε`-Pareto thresholds relative to incumbents.
- **Chance**: verifying statistical evidence (p-values, confidence intervals) respect promotion policy defaults and multiple testing control (Benjamini–Hochberg).
- Validators MUST emit machine-readable diagnostics (`--json`) distinguishing structural vs operational vs chance failures.

## Appendices (normative as needed)

- Typing/satisfaction rules
- Statistical defaults (estimators, tests, TOST; BH)
- Examples cross-referencing files in `spec/examples/`
- Configuration and measurement schemas with field-level constraints
