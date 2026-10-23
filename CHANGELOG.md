# Changelog

All notable changes to the TVL spec, schema, tools, and SDK will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.0] - 2026-10-21

TVL 1.4 (RFC 0004, reactive outcomes and notification guards) and formal semantics §13 are accepted. Package, citation, `tvl.__version__` and the compiler's default toolchain version report 1.4.0; authored modules using the new constructs declare `tvl_version: "1.4"`. Projected constructs select `/1` or `/2` as described below. Not published to a package registry.

### Added

- RFC 0004 (TVL 1.4): notification-only repair outcome triggers, primary-monitor
  `unknown_for`, and three-valued `only_while`/`unless` guards. Includes response-local references,
  monitor inhibition cycle checks, immutable guard-set/outcome composition, hosted reference
  projection, schema/editor copies, conformance cases and Lean guard proofs. TVL 1.3 diagnostic codes
  and `backend_v1` are unchanged (some messages are reworded).
- Closed RFC 0004 §7.2 under owner ruling A: frozen 1.3.0 `/1` hosted/local schemas and separate `/2` schemas
  for projected 1.4 constructs, selected and validated by format tag, with identical editor copies. Only projected
  outcome triggers, `unknown_for`, or nonempty guards select `/2` and version `"1.4"`; all other declarations use
  `/1` and version `"1.3"`, including authored `"1.4"` declarations. Every input accepted by 1.3.0 retains byte-identical
  canonical artifacts for the same compiler inputs and toolchain version. The new default `toolchain.version`
  is `"1.4.0"`; compared with 1.3.0, only that hosted field, any checked packs' derived `pack_contract_digest`
  values, and local `contract_digest` change. Consumers pinning toolchain versions must add `"1.4.0"`;
  explicitly pinning `toolchain_version="1.3.0"` preserves historical bytes and digests.
  `/1` with 1.4 fields and `/2` without projected 1.4 constructs are refused.
  Success outcomes, pack guards over module monitors, and tracking manual deployment after `deploy: never`
  are recorded as limitations of 1.4.

### Security

- The website deployment settings check now passes its role secret through a step environment variable before testing the quoted value.

### Fixed

- `tvl-ci-gate` retains warning-severity lints in its output instead of discarding them; the refusal was already scoped to error severity and still is. The widened set of modules it lints is recorded under Compatibility below.
- `tvl-validate` keeps reporting the documented diagnostic code — `invalid_chance_threshold`, `missing_strategy`, `invalid_enum_domain` and the rest — for a bound the schema now also enforces, instead of downgrading it to the generic `schema_error`; `tvl-lint` and `tvl-ci-gate` already did. A `required` diagnostic's `path` points at the missing key rather than at the object missing it.
- Enum domains are checked in lints and in the module schema, so configuration and structural validators also reject mismatched members. Ordinary module validation reports `invalid_enum_domain` with the TVAR name and offending value; JSON Schema accepts integral numbers such as `3.0`, while lint also checks Python literal types.
- The book records warning expectations explicitly, and tool examples use the committed module filename.
- Tool documentation records configuration failures as exit 5 and gate success only for `Promote`.
- Structural candidate loading and MicroSim input handling now report diagnostic failures instead of tracebacks for unreadable, malformed or non-mapping input.
- The MicroSim bridge now exports numeric TVAR ranges with module identity, respects integer steps and range resolution, and warns about skipped variables and unmatched lab controls. Empty exports fail without writing.
- The VS Code extension derives a sibling linter by exact executable basename, preserving parent directories and Windows paths. Custom validator names require an explicit machine-scoped `tvl.lint.path`, and a configuration error clears stale diagnostics instead of leaving them in the gutter.
- Pull-request CI now compiles and tests the VS Code extension with the Python CLIs installed in the repository virtual environment; required CLI integration tests fail when the executable is absent.

### Compatibility

Five changes in this PR alter behaviour an existing script, pipeline or module
may depend on. They sit on top of 1.3.0, which carries more of its own — the
Python 3.12 minimum, the `Reject` -> `NoDecision` change in the `decision`
string a gate consumer parses, and a second unedited-module `Promote` ->
refused path through the strict-calibration triggers — so read 1.3.0's notes as
well if you are upgrading from 1.2.0. Releases 1.1.0 and 1.2.0 use this section
for the same purpose. The grammar is served at an unversioned `$id`, so a
consumer pinning that URL picks the tightened bounds up without opting in.

- `tvl-validate`, `tvl-lint` and `tvl-compose --validate` exit 0 with `ok: true` on a warning-only result, where they exited 2. Every diagnostic is still printed, in text as well as JSON, and an issue with no severity still counts as an error. A build step that gated on the exit code no longer fails on proof-coverage warnings. To keep that gate, test the payload: `tvl-validate m.tvl.yml --format json | jq -e '.ok and (.issues | length == 0)'`. The `.ok` term is load-bearing — an unreadable or unparsable module answers `{"ok": false, "error": …}` with no `issues` key, and `null | length` is `0`, so a check on `.issues` alone passes on a file that could not be read. (`jq` is not a dependency of this repository; use any JSON reader.)
- `tvl-ci-gate` lints every full module before deciding, where it linted only TVL 1.3 modules given in the canonical three-file form. A module that is schema-valid but has an error-severity lint is now refused with exit 2 instead of promoting. This is the point of the gate half of #156, and it is the change most likely to affect an existing pipeline: a module you have not edited can go from `Promote` to refused. A full module passed through `--policy` now gets the same schema validation as canonical input, for the same reason; the guard recognises a `tvl:` header or a `promotion_policy:` wrapper, so a wrapped standalone policy takes that path too (same exit code, different payload and deprecation warning).
- `tvl-parse` exits 2 on an empty, sequence or scalar document, where it exited 0 with `ok: true`. Schema validation stays `tvl-validate`'s job; a mapping with unknown fields still parses.
- `tvl-microsim-bridge` requires `-o/--output` unless `--dry-run` is given, where it defaulted to the bundled Orientation RAG presets file and overwrote it.
- The module schema tightens bounds that previously only the lint enforced: chance-constraint `threshold` to `[0, 1]` and `confidence` to `(0, 1)`, banded `tol` and `alpha` to `> 0`, `exploration.strategy` to required, and `convergence.window` and `threshold` to required under `metric: hypervolume_improvement` (`window`'s own `minimum: 1` is unchanged, and `threshold` additionally becomes `> 0`). Enum domains enforce their declared element type. For these bounds specifically, a module that was schema-valid and lint-invalid is now rejected by both — this is not a general property, and other lint rules such as `missing_min_effect` and the `composite_*` family remain lint-only, which JSON Schema cannot express. Measured by running `tvl-validate` over every committed module at both revisions, **none goes from passing to failing**; five go from failing to passing, and all five are warning-only modules moved by the exit-code change above. One consequence worth naming for anyone parsing the output: `schema_ok` now reports `false` where the grammar itself rejects one of these bounds, so a consumer using `schema_ok` to tell "grammar-invalid" from "lint-invalid" sees these move across that line. In the same vein, a `required` diagnostic's `path` now names the missing key rather than the object missing it, so for an object missing two or more keys the shape of that `path` changes. The exception is a `required` error that a lint at an ancestor path diagnoses instead: the lint's own path is used, because the lint owns it — a missing `cvars[0].calibration.source` is reported as `cvar_missing_source` at `["cvars", 0, "calibration"]`, with the field named in the message. The `code` field likewise changes value on committed files where the schema already enforced the bound at base, not only on the bounds moved here.

## [1.3.0] - 2026-10-21

TVL 1.3 (RFC 0003, runtime requirements, monitors and responses) is accepted. Package, citation and `tvl.__version__` report 1.3.0; authored modules keep `tvl_version: "1.3"` and document format tags are unchanged. Not published to a package registry.

### Language (acceptance revision)

- `among` admits only a checker predicate; a metric or exact predicate there is the new lint `runtime_among_not_checker` (RFC 0003 §16.3 question 20). Membership was defined only for checker labels, and the two readings of an exact predicate select opposite populations.
- RFC 0003 states the `u = pl = 0` condition on question 15, the deliberate exclusion of recovery triggers for `deploy`, and the reference limits the environment-label rule to `backend_v1`.

### Security

- Cleared the open dependency and code-scanning findings: the website PDF build server now checks path containment with `path.relative` (a sibling directory such as `dist/public-evil` no longer passes), the website deploy checkout no longer persists credentials, the support-bot evaluator raises an explicit error instead of using `assert`, and the older locked `numpy` releases (2.2.6, 2.4.6) are gone with the Python 3.12 minimum below.

### Fixed

- `tvl-ci-gate` now refuses promotion (`calibration_evidence_unsupported`, exit 2) under every strict-mode calibration trigger of RFC 0001 section 3.6 and RFC 0002 section 5, not only an explicit `require_calibration`.
- `tvl-lint` applies the documented default `promotion_policy.alpha` of 0.05 when it is omitted, instead of failing with `invalid_alpha`; explicit `null` or out-of-range values are still rejected.
- Runtime diagnostics printed by the CLI text renderers show their field location once instead of twice.

### Removed

- The website no longer ships the app builder's editor runtime or its source-location attributes, and the unused builder template leftovers (login dialog, maps component, OAuth helper) are gone.

### Added

- RFC 0003 (draft revision): an `optimize` response rule may declare `deploy: never | if_promoted` (default `never`). `if_promoted` declares deploying the candidate as a separate service effect with its own occurrence and approval, effect-time checks (open episode, current contract, `Promote` from the joined promotion gate), hold when unreachable, tighten-only composition, and no effect on episode closure. Lints `response_deploy_without_promotion_monitor` and `runtime_invalid_ladder`; schemas, compiler, conformance cases and the Lean rule model carry the new coordinate.

### Changed

- Python 3.12 or newer is required: `requires-python` is now `>=3.12`. Python 3.10 reached end of life in October 2026, and the fixed `numpy` releases need Python 3.12.
- Contributions are now accepted under the Developer Certificate of Origin sign-off (`DCO`, `Signed-off-by:` on every commit, checked in CI) instead of a contributor license agreement.
- The formal semantics now state that the omitted promotion `adjust` default is `holm`, matching the gate implementation and gate I/O specification.
- The formal semantics mark RFC 0001 as accepted and state that existing core results are preserved while the new constructs remain outside the mechanized proofs.
- The composition reference documents the directory boundary for overlay `extends`: relative paths, resolved against the containing overlay, must stay inside the directory of the overlay passed to `tvl-compose`, including across chained overlays and symlinks.
- RFC 0003 distinguishes `approval: none` event authority (`notify`) from the effect checks of remote service effects and the local guards of section 7.5, and limits the `min_samples` closure claim to windows of exactly that size.

- Revised the promotion decision contract so failure to establish non-inferiority returns `NoDecision`; `Reject` now requires demonstrated inferiority, a failed chance constraint, or an observed point estimate outside a hard band.
- Added `p_value_inferior`, `adjusted_p_inferior`, and `any_band_out_of_band` to promotion evidence.
- Made unsupported strict-calibration evidence and measurement/module identity mismatches promotion-readiness failures.
- Advanced the Promotion Gate I/O document to draft version 1.1 for review of these observable contract changes.
- Package, citation, and `tvl.__version__` metadata now report language version 1.2.0 (the 1.1 and 1.2 extensions below were already in the schema, validators, and examples).
- Documented every diagnostic emitted by `tvl.lints` in `docs/reference/error-codes.md`, including the codes for `cvars`, `policies`, `require_calibration`, and `composites`.
- Installation instructions now describe installing from a clone of this repository; the package is not published to a registry.

### Added

- The website has a short "TVL 1.3 (draft)" page (`/tvl-1-3`) linking RFC 0003, the guide and the runtime-1.3 examples; the home page book blurb now says 13 chapters.

- Community health files: a rewritten contributing guide, security policy and Contributor Covenant code of conduct, governance, maintainers and support documents, issue forms and a pull request template, an RFC process with an RFC template, code owners, Dependabot configuration, and a `NOTICE` file.
- README status badges and a short example that validates and lints a module.

### TVL 1.3

TVL 1.3 is a conservative extension of 1.2 (draft notes below; accepted in 1.3.0): a module without the new blocks is read exactly as before, and no 1.1 or 1.2 document gains a diagnostic.

TVL 1.3 adds language only. TVL defines what each requirement, monitor and response means and what each verdict promises, and its tools check, compose and compile these declarations. It evaluates no runtime evidence and executes no response: runtime verdicts come from an evaluator outside TVL (RFC 0003 §3.5). The only verdicts a TVL tool computes are those of the release gate, for promotion monitors whose counts contain no unresolved or unplaceable units.

#### Added

- Three optional module blocks, `requirements`, `monitors` and `responses`, and a separate `tvl_pack` document for organisation floors. A module that uses any of them, and every pack, declares `tvl_version: "1.3"` (a string).
- Four sealed requirement kinds: `rate_bound`, `zero_tolerance`, `recovery_time` and `evidence_liveness`.
- Seven unit predicates: numeric `metric`, `checker` labels, and the event patterns `absence`, `bounded_existence`, `precedence`, `bounded_response` and `protocol`.
- Monitors for promotion (before release, on the evaluation set) and runtime (production) evidence, with tumbling windows, `clopper_pearson_rational_v2` and `exact_count_v1` decisions, episodes, burn monitors, sampling modes, and the frozen `backend_v1` profile.
- Runtime verdicts `MET`, `BREACHED` and `UNKNOWN(reason)`; absence of evidence is never `MET`.
- A sealed response ladder: `notify`, `open_next_step`, `optimize`, `rollback`, `throttle`, `degrade`, `suspend`, `block_action` and `halt_unit`, with `none`, `standing` and `human` approvals.
- JSON Schemas: `tvl-pack.schema.json`, `tvl-runtime-contract.schema.json`, `tvl-runtime-local.schema.json` and `tvl-runtime-report.schema.json`; `tvl.schema.json` gains the three optional root properties; `tvl-measurement.schema.json` gains `monitor_outcomes`.
- A `tvl-compile-runtime` command that turns a module or pack, a token map and an optional checker registry into `runtime-contract.json` and `runtime-local.json`.
- `tvl-compose --pack` (organisation floors that can only be tightened) and `--meet`, and the same tighten-only rule for overlays over the three blocks.
- `tvl-ci-gate` joins promotion monitors with the existing promotion decision (`MET` passes, `BREACHED` is `Reject`, `UNKNOWN` is `NoDecision`) when a module declares them, and `tvl-measure-validate` reads `monitor_outcomes` from measurement bundles; a missing count is the new readiness issue `missing_monitor_counts`.
- TVL 1.3 lints and diagnostic codes (see the error code catalog), including `runtime_liveness_missing`, `runtime_met_unreachable_at_min_samples`, `closure_unreachable` and `recovery_deadline_impossible`.
- `unsupported_construct` for tools that meet a 1.3 construct they do not implement; they refuse instead of ignoring it.
- 23 example modules and packs in `spec/examples/runtime-1.3/`.
- Documentation: the guide *Requirements, Monitors and Responses*, a TVL 1.3 section in the language reference, TVL 1.3 entries in the error code catalog, and book chapter 6 *Requirements in Production*.

#### Changed

- `tvl-validate` and `tvl-lint` treat a root mapping with `pack` and without `tvl` as a `tvl_pack`.
- `tvl-check-structural`, `tvl-check-operational` and `tvl-config-validate` ignore the three runtime blocks in a module and refuse a pack with `unsupported_construct`; `tvl-ci-gate --policy` refuses any runtime block.

#### Not in 1.3

Sliding windows, anytime-valid sequential tests, per-user or cross-unit state, conditions on event arguments, boolean combinations of predicates, and routing of notifications. See *What TVL 1.3 cannot express* in the guide.

## [1.2.0] - 2026-06-06

Date is when RFC 0002 (`formalization/rfc-0002-composite-knobs.md`) and its validators landed on `main`.

### Added

- `composites` block: named, sealed composite knobs with three structural constructors (`cascade`, `ensemble`, `loop`), closed under nesting. A composite is a namespace and expansion unit; it never binds a value and never enters the configuration space or the dominance relation.
- Composite cascade gates (`margin_below`, `signal_below`), ensemble aggregation (`majority_vote`, `judge_max`) with optional acceptance on `vote_margin` or `vote_agreement`, and loop stop rules (`signal_accept`, `external_accept`, `exhausted`).
- A curated pattern catalog (`binary_cascade`, `n_cascade`, `self_consistency`, `best_of_n`, `self_debug`, `self_refine`) whose patterns expand deterministically into the algebra and carry closed, content-free provenance.
- `signal_inputs` as a freshness-context extension key for `promotion_policy.require_calibration`, so signal inputs used by composite gates and stops are bound into calibration freshness.
- Composite-specific lint codes (see `docs/reference/error-codes.md`), JSON Schema definitions, EBNF productions, example fixtures under `spec/examples/validation-phase7-composites/`, and a model-checking suite under `tests/model_checking/`.

### Compatibility

- Conservative extension of 1.1: a module with no `composites` block parses and validates exactly as it does under 1.1.

## [1.1.0] - 2026-06-05

Date is when RFC 0001 (`formalization/rfc-0001-knob-bindings-cvars-policies.md`) and its validators landed on `main`.

### Added

- The one-knob model: every configuration variable has exactly one typed binding (tuned, fixed, or calibrated).
- `cvars` block: calibrated variables that are governed but not searched. A CVAR declares its calibration source, signal, calibrator, and the TVARs it depends on, and never enters the optimizer search space or structural SAT.
- `policies` block: named operational policies; the first strategy is `cascade`, with `margin_below` gates whose thresholds reference CVARs.
- `promotion_policy.require_calibration`: a strict evidence mode in which certificate freshness is validated against a hash-covered calibration context.
- One shared declaration namespace for TVARs, CVARs, and policies, with prefix-collision diagnostics (a warning in modules that use no 1.1 construct, an error otherwise) and optional ownership `scope` (`node`, `agent`, `workflow`).
- New lint codes (see `docs/reference/error-codes.md`), JSON Schema definitions, EBNF productions, and example fixtures under `spec/examples/validation-phase6-cvars/`.

### Changed

- Clarified the claim scope of calibration certificates: they are per-variable procedural claims about the declared fit and its freshness, not configuration-level guarantees on metrics.

### Compatibility

- Conservative extension of 1.0: a module that uses none of `cvars`, `policies`, `require_calibration`, or `scope` validates as it did under 1.0.

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

#### Open Source Release Preparation

- Apache 2.0 license for code, schemas, validators, CLI tools, editor support, tests, and examples
- CC-BY-4.0 license for authored documentation and formalization notes (see `LICENSE-content`)
- Updated CITATION.cff with proper metadata
- VS Code extension (version 0.1.0 in `vscode-tvl/package.json`; it is not versioned with the language)

### Changed

- Version bump from 0.9 to 1.0 across all artifacts
- Development status upgraded to "Production/Stable"
- Repository URL updated to the Traigent organization (`https://github.com/Traigent/tvl`)

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
- `tvl-ci-gate` provides dry-run functionality; full implementation pending integration with an external optimizer
