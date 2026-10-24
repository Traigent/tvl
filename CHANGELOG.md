# Changelog

All notable changes to the TVL spec, schema, tools, and SDK will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Info diagnostic `outside_proved_subset`: emitted once per construct family present (`cvars`, `policies`, `composites`) that the Lean proofs do not model. Diagnostics with the new `info` severity are printed and included in JSON output but never affect `ok` or the exit status of `tvl-validate`, `tvl-lint` or `tvl-compose --validate`.
- `tools/claim_audit`: a paragraph-level audit of the claims in the published documentation.
- Error `structural_undecided_without_solver`: without OR-Tools, the fallback structural search no longer reports an UNSAT it has not shown. It reports SAT when it finds a witness, UNSAT only when it tried every value of every domain, and otherwise this error (`tvl-check-structural` exits 2, JSON `status: "undecided"`).
- Gate decision `Error` with code `zero_trials`: a chance constraint with zero trials or no trial count makes its check undefined (Definition 9.8), so the gate returns `Error` before any other branch, instead of `Reject`. When the gate returns it, `tvl-ci-gate` prints `Decision: Error` and exits 2 (canonical `chance_outcomes` with `trials` 0 or missing are a schema error at load, exit 2; a deprecated `chance` summary with `summary.trials: 0` reaches the gate and gives `Error`).
- Error `duplicate_key`: a YAML mapping that repeats a key is rejected at parse time (RFC 0001 §3.5(4)); the message names the key, line and column. A key that overrides one inherited through `<<` is not a duplicate.
- `tvl-check-structural` JSON field `exact_assignment` (and `StructuralResult.exact_assignment`): the witness with every numeric value as an exact decimal or `"p/q"` string, tuple components included. The existing `assignment` field keeps plain binary64 numbers for compatibility and can merge distinct grid points. The text output prints the exact witness.
- Undecided results of `tvl-check-structural` (exit 2, JSON `status: "undecided"`), each with its own error code: `structural_encoding_overflow`, `structural_solver_inconclusive`, `structural_witness_unverified`, `structural_witness_too_large`, `structural_ill_typed_atom`, `structural_non_finite_domain`, `structural_unresolved_domain`, `structural_pair_table_too_large`, `structural_expansion_too_large` and `structural_value_too_large`. The checker reports one of these instead of a SAT or UNSAT it cannot show.
- Lint error `non_finite_domain_value`: NaN or an infinity in a TVAR domain.
- Parse-time error `complex_mapping_key`: a YAML mapping key that is a mapping or a sequence is rejected.
- YAML loading limits: merge keys (`<<`) may copy at most 100,000 key/value pairs in total, a float literal may have at most 400 digits and an exponent within ±400, and a document nested too deeply to parse is rejected. Each is a YAML parse error.

### Changed

- Specification page corrections: version compatibility table, scoped overlay narrowing, budget-check responsibilities, assurance-scope table, a decision table for `chance_constraints` versus a promotion monitor, and the authority section.
- Publication review corrections across the documentation, including the error code catalog (new entries for operational-check, calibration-readiness and document-shape codes, and a statement of which tool codes it does not list yet).
- Formal semantics: derived constraints admit strict `<` and `>`, matching the grammar and the reference checker; a strict atom is false at equality.
- `exploration.budgets.max_spend_usd: 0` is valid and means no paid spending is allowed; `tvl-check-operational` accepts it and reports `invalid_budget_max_spend` only for a negative value.
- A repository-wide source authority rule: the formal semantics governs meaning, the grammar and schemas govern syntax, accepted RFCs govern where the semantics is silent, the Python implementation is reference behaviour, not normative, and the docs are informative (language reference and `GOVERNANCE.md`).
- `SECURITY.md` supported versions: 1.5.x supported, 1.3.x–1.4.x best effort, below 1.3 not supported.
- Formal semantics diagnostic tables now list the codes the implementation emits (for example `unknown_derived_symbol` in place of `derived_env_undefined`, and the `outside_proved_subset` info diagnostic).
- Formal semantics: a range `resolution` is optional, matching the grammar; the default step is 1 for an `int` range and 0.001 for a float range (§2.4). The language reference and the book now say the same; a float range inside a tuple component still needs a `resolution` in the schema.
- RFC 0001 errata: the certificate field `target` (`TargetProperty`) is a closed, opaque identifier string with no nested fields (RFC 0001 §11).
- RFC 0002 errata: definitions of the telemetry measures `vote_margin`, `vote_agreement` and `gate_margin_pass_rate`, taken from the reference runtime (RFC 0002 §11).
- Publication review corrections to the website pages and book chapters.
- Formal roadmap (`formalization/tvl-formal-roadmap.md`) rewritten as a status page: it records which core results exist on paper and in Lean, with their scope, and lists the remaining work without dates.
- Formal semantics §11.1 lists the core results already proved in Lean and the areas that remain; the proof of Theorem 7.1 counts the size of set and tuple atoms instead of treating every atom as constant time.
- Float range TVARs are encoded by exact grid index (Definition 3.6) instead of being scaled by a precision of 1000. Only legacy `min`/`max`/`precision` float domains keep the precision scaling.
- Ordering comparisons (`<`, `<=`, `>`, `>=`) and intervals are allowed on enums whose values are all numbers (T-Cmp, T-Interval); string enums still reject them.
- The domain model (`tvl.model`) gives a float range inside a tuple component the default step 0.001 when it has no `resolution`, instead of raising an error. The JSON Schema still requires the `resolution` there, so such a module is still a schema error.
- Repeated enum members are treated as one set member by `tvl-check-structural`; `tvl-validate` still reports `duplicate_domain_value`.
- `tvl-ci-gate --help` no longer describes the tool as a dry run.

### Fixed

Entries marked **(1.5.0)** fix defects that are also present in the 1.5.0 release. The structural soundness fixes among them can change a reported result, so re-run `tvl-check-structural` on modules checked with 1.5.0.

- **(1.5.0)** False UNSAT on strict float comparisons: the strict bound was applied twice, so a satisfiable module such as `t > 0.5`, `t < 0.7` on `{range: [0, 1], resolution: 0.1}` was reported UNSAT. Strict and non-strict bounds are now computed exactly on the grid.
- **(1.5.0)** False SAT from a resolution that does not divide the range: the checker searched a finer grid than the declared one, so `{range: [0, 1], resolution: 0.3}` with `t >= 0.95` was reported SAT with `t = 1.0`, which is not on the grid `{0, 0.3, 0.6, 0.9}`. Witnesses could also be off-grid when the range did not start at 0.
- **(1.5.0)** Every CP-SAT status other than a solution was treated as UNSAT. Only `INFEASIBLE` now proves UNSAT; any other status is `structural_solver_inconclusive`.
- **(1.5.0)** Without OR-Tools, the fallback search could report UNSAT for a satisfiable module (for example `x > 0.3`, `x < 0.31` on a float range). It now reports UNSAT only after trying every value, and otherwise `structural_undecided_without_solver`.
- **(1.5.0)** Range endpoints and numeric literals were compared as binary64 floats. So `e = 0.100000000000000001` was reported SAT for an enum holding only `0.1`, and `n > 1.5`, `n <= 2` on an `int` range was reported UNSAT. Both are now read exactly from their source text and decided exactly.
- **(1.5.0)** Tuple grids were built by rounding to 12 decimals and by rounding the step count, which could add a point past the upper bound. Tuple grids now follow Definition 3.6 exactly, and the 10,000-value product limit is checked before any axis is built.
- **(1.5.0)** Denial of service on loading: merge keys (`<<`) that double at each level, and float literals with a huge exponent such as `1.0e-99999999`, made every tool hang. Both are now rejected quickly by the loading limits above.
- **(1.5.0)** Duplicate YAML mapping keys were accepted silently (the last value won). They are now rejected as `duplicate_key`, including keys repeated inside a mapping used as a merge source.
- **(1.5.0)** Very small resolutions could raise `OverflowError`, and `in` sets and negated intervals could expand without a limit; the expansion is now bounded (`structural_expansion_too_large`).
- **(1.5.0)** Negated strict intervals dropped their endpoints: `not (0 < x < 1)` on `{range: [0, 1], resolution: 0.5}` was reported UNSAT, though `x = 0` and `x = 1` satisfy it.
- **(1.5.0)** `tvl-compile-runtime`: the local artefact carried every token-map entry, not only the entries the contract uses (`token_map_digest` still covers the whole map), and inputs were read before the schema and lint checks ran (RFC 0003 §11.4.4, §11.4.6, §11.5).
- **(1.5.0)** A gate check with zero trials returned `Reject`; it now returns `Error` with `zero_trials` (see Added).
- **(1.5.0)** `tvl-check-operational` rejected `max_spend_usd: 0` (see Changed).
- Tuple equality between TVARs now checks arity and component types (formal semantics §4.7).
- **(1.5.0)** `tvl-check-structural` read a reversed range such as `{range: [5, 1]}` as an empty domain and reported UNSAT. The range is malformed (§2.4) and is now refused; `tvl-validate` reports it as `invalid_range_domain`, as before.
- **(1.5.0)** Equality between two TVARs now follows T-TVarEq exactly: both sides need the same element type, with no numeric widening. `tvl-validate` now rejects `int_var = float_var` and `enum[str]` against `enum[int]` as `constraint_type_mismatch`, and accepts `int_var = enum_int_var`, which it used to reject. Tuple TVARs need the same component types (T-TupleVarEq). `tvl-check-structural` still decides `int_var = float_var` (`docs/reference/error-codes.md`, `structural_ill_typed_atom`).
- **(1.5.0)** `inadequate_precision` follows Definition 8.6: it warns when some value `v` of a float domain has `v·P` not an integer, read from the exact decimal written. It used to warn only when two values collided after rounding, or when a range resolution was misaligned, so an aligned-looking set such as `[0.0005, 0.5]` with P = 1000 is now reported.
- **(1.5.0)** Banded objectives with zero variance: with `std = 0` the TOST statistics are taken as +∞ or −∞, so a mean strictly inside the band passes and a mean exactly on a band edge is `inconclusive`. Before, every zero-variance result was `inconclusive` (formal semantics Definition 9.6).
- **(1.5.0)** Banded objectives with fewer than 2 observations: a single observation outside the band is `out_of_band` and the gate returns `Reject`, as for any point estimate outside the band (formal semantics §9.5). Before, it was `inconclusive`. An in-band single observation, or none, is still `inconclusive` (`spec/promotion-gate-io.md` §3.4).
- **(1.5.0)** The `runtime_invalid_profile` diagnostic for a `clopper_pearson_exact_v1` monitor whose power bounds `scipy.stats.beta` cannot evaluate no longer repeats the monitor name in its message; the path locates the monitor (RFC 0003 §5.10).

## [1.5.0] - 2026-10-23

TVL 1.5 (RFC 0005, breach persistence and census aggregates) and formal semantics §14 are accepted. Package, citation, `tvl.__version__` and the compiler's default toolchain version report 1.5.0; authored modules using the new constructs declare `tvl_version: "1.5"`. Not published to a package registry.

### Added

- RFC 0005 (TVL 1.5): breach persistence (k-of-n finalized windows) on notification rules, and census aggregates (`sum`, `mean`) as `aggregate_bound` requirements. Includes schemas, lints, conformance cases and Lean persistence proofs.
- New projected constructs select contract/local format `/3` and aggregate report format `report/2`; count reports stay `/1`.

### Changed

- The default `toolchain.version` is `"1.5.0"`. A 1.4 module compiled by 1.5.0 differs from 1.4.0 output only in `toolchain.version` and the derived digests; explicitly pinning `toolchain_version="1.4.0"` preserves historical bytes and digests. Consumers pinning toolchain versions must add `"1.5.0"`.

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

## [1.3.0] - 2026-10-21

TVL 1.3 (RFC 0003, runtime requirements, monitors and responses) is accepted. Package, citation and `tvl.__version__` report 1.3.0; authored modules keep `tvl_version: "1.3"` and document format tags are unchanged. Not published to a package registry.

### Language (acceptance revision)

- `among` admits only a checker predicate; a metric or exact predicate there is the new lint `runtime_among_not_checker` (RFC 0003 §16.3 question 20). Membership was defined only for checker labels, and the two readings of an exact predicate select opposite populations.
- RFC 0003 states the `u = pl = 0` condition on question 15, the deliberate exclusion of recovery triggers for `deploy`, and the reference limits the environment-label rule to `backend_v1`.

### Security

- Cleared the open dependency and code-scanning findings: the website PDF build server now checks path containment with `path.relative` (a sibling directory such as `dist/public-evil` no longer passes), the website deploy checkout no longer persists credentials, the support-bot evaluator raises an explicit error instead of using `assert`, and the older locked `numpy` releases (2.2.6, 2.4.6) are gone with the Python 3.12 minimum below.

### Fixed

- `tvl-ci-gate` now refuses promotion (`calibration_evidence_unsupported`, exit 2) under every strict-mode calibration trigger of RFC 0001 section 3.6 and RFC 0002 section 5 that the module records, not only an explicit `require_calibration`. The operational-profile trigger of RFC 0001 section 3.6 is not checked, because the gate does not receive the operational profile.
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
- Before TVL 1.3 was accepted, package, citation, and `tvl.__version__` metadata were raised to language version 1.2.0 (the 1.1 and 1.2 extensions below were already in the schema, validators, and examples); this release reports 1.3.0.
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

- Version bump from 0.9 to 1.0 across all language-versioned artifacts (the VS Code extension keeps its own version)
- Development status upgraded to "Production/Stable"
- Repository URL updated to the Traigent organization (`https://github.com/Traigent/tvl`)

### Fixed

- Consistent versioning across all language-versioned components
- Added `__version__` to Python SDK for programmatic access

---

## [0.9.0] - 2025-01-26

> This entry predates the public repository (its first commit is dated 2026-04-13). The release date and the test count below come from the earlier private history and cannot be checked against this repository.

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

- **Structural constraints**: Typed DNF compiled to quantifier-free linear integer arithmetic (QF_LIA), with float domains scaled to integers
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
