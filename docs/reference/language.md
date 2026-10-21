# TVL Language Reference for AI Agent Requirements

This page is a friendly guide to TVL.

TVL specifies the allowed design space and desired properties of an AI agent. It does not prescribe the build process or search algorithm used to produce a candidate. Instead of treating TVL as a bag of keywords, this reference teaches the language by following one concrete agent all
the way through: a simple campus FAQ RAG system. As you read, the example gives each TVL block a job, so the later
rules feel grounded instead of abstract.

If you are new to TVL, start with the example below and read it top to bottom once before diving into the rest of the
sections.

!!! note "Language version"
    This reference describes the core constructs of TVL, which is currently at version **1.3**. TVL 1.1 added calibrated variables (`cvars`), operational `policies`, and `promotion_policy.require_calibration` (RFC 0001); TVL 1.2 added `composites` (RFC 0002); TVL 1.3 added runtime `requirements`, `monitors`, `responses` and `tvl_pack` (RFC 0003, described below). All are conservative extensions, so a module that uses none of them (nor TVAR ownership `scope`, also added in 1.1) is also a valid 1.0 module. The RFCs live in `formalization/`, and every diagnostic is listed in the [error code catalog](https://github.com/Traigent/tvl/blob/main/docs/reference/error-codes.md).

## A Small RAG Agent

The following example shows a simple RAG question-answering agent for a campus FAQ system. The agent retrieves a few
passages, sends them to a small model, and answers student questions. We want TVL to experiment with only a few tuned
variables: which model to use, how many passages to retrieve, and how much randomness to allow in the final answer.
Whether a chosen configuration is acceptable is judged separately by the declared rules, operational checks, and
promotion policy.

This is the right size for learning the language: it is small enough to read end-to-end, but concrete enough that
every field has an obvious job.

To follow along, download the example and keep it in your working directory as `hello_tvl.yml`.

Full file:

*   [`/examples/hello_tvl.yml`](/examples/hello_tvl.yml)

```yaml
tvl:
  module: book.quickstart.simple_rag_qa

environment:
  snapshot_id: "2025-01-20T00:00:00Z"
  bindings:
    retriever_index: campus-faq-v1
    llm_gateway: us-east-1

evaluation_set:
  dataset: s3://datasets/campus-rag/dev.jsonl
  seed: 2025

tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4o-mini", "claude-3-haiku"]

  - name: retriever.k
    type: int
    domain:
      set: [3, 5, 8]

  - name: temperature
    type: float
    domain:
      range: [0.0, 0.6]
      resolution: 0.1

constraints:
  structural:
    - when: "retriever.k = 8"
      then: "temperature <= 0.3"

objectives:
  - name: answer_accuracy
    metric_ref: metrics.answer_accuracy.v1
    direction: maximize
  - name: latency_p95_ms
    metric_ref: metrics.latency_p95_ms.v1
    direction: minimize

promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  adjust: holm
  min_effect:
    answer_accuracy: 0.01
    latency_p95_ms: 50

exploration:
  strategy:
    type: grid
  budgets:
    max_trials: 24
    max_wallclock_s: 900
```

One distinction will help for the rest of the page. TVL operates on three different levels:

*   **Design space**: `tvars` plus `constraints.structural` describe the configurations TVL is allowed to explore.
*   **Operating assumptions**: `environment.bindings`, `environment.context`, and `constraints.derived` describe what infrastructure is pinned and which numeric operating assumptions must hold before the study runs.
*   **Measured outcomes**: `objectives`, `promotion_policy`, and `chance_constraints` describe what happened after evaluation and what is good enough to ship.

How to read it:

*   `environment` tells you which environment snapshot this agent was evaluated against: which retriever index and gateway were active while this study ran.
*   `evaluation_set` tells you which question set supplies the evidence. This is the shared evaluation set used to compare candidate settings fairly.
*   `tvars` lists the knobs TVL is allowed to tune. In this example, TVL can choose the model, retrieval depth, and answer randomness.
*   `constraints.structural` encodes constraints between design choices. If we retrieve a lot of passages (`retriever.k = 8`), we force lower temperature so the answer stays grounded.
*   This first example stops at structural rules. Operational preconditions come later, once the basic module shape is already clear.
*   `objectives` say what we are trying to improve: answer quality goes up, latency goes down.
*   `promotion_policy` says when an apparent improvement is strong enough to trust before rollout.

Useful first commands:

```bash
tvl-validate hello_tvl.yml
tvl-check-structural hello_tvl.yml --json
tvl-check-operational hello_tvl.yml --json
```

On this starter file, `tvl-check-operational` should succeed without much drama. That is intentional: the example is
teaching the core module shape first, not operational-precondition design.

<details>
<summary>Open a quick map of the top-level TVL blocks</summary>

A TVL module is usually organized as:

*   **Agent requirements**: which design choices may vary and which combinations are admissible
*   **Evaluation contract**: which evaluation set and metrics define observed properties
*   **Acceptance contract**: which evidence is required before a candidate can be accepted or promoted

*   `tvl`
*   `environment`
*   `evaluation_set`
*   `tvars`
*   `constraints`
*   `objectives`
*   `promotion_policy`
*   optional `exploration`

At minimum, the schema requires `tvl`, `environment`, `evaluation_set`, `tvars`, `objectives`, and `promotion_policy`.
</details>

## Module Header

The header tells tooling what this module is.

### `tvl`

The `tvl` block identifies the module itself.

Key field:

*   `module`: stable module identifier such as `corp.support.rag_bot`

Example:

```yaml
tvl:
  module: corp.support.rag_bot
```

## Environment

`environment` records the environment snapshot that the module was evaluated against. It has two different jobs:

*   `bindings` pin the concrete artifacts or services this study used.
*   `context` supplies the numeric operating assumptions that operational preconditions may read.

That separation matters because TVL is operating at different levels. A retriever index ID is something you pin for
reproducibility. A provider price or baseline gateway latency is a numeric operating assumption. Neither of those is a
tuned variable, and neither is a measured outcome.

Key fields:

*   `snapshot_id`: required RFC3339 timestamp or equivalent stable snapshot label
*   optional `bindings`: opaque deployment references such as retriever indexes, gateway regions, or catalog versions
*   optional `context`: numeric environment facts used by operational preconditions

Example:

```yaml
environment:
  snapshot_id: "2025-01-15T00:00:00Z"
  bindings:
    retriever: bm25-v3
    llm_gateway: us-east-1
  context:
    gateway_baseline_latency_ms: 180
    provider_input_price_usd_per_1k_tokens: 0.03
```

Rules that matter:

*   Put **operational facts** here, not optimization knobs. If the runtime is allowed to tune it, it belongs in `tvars`.
*   Use `bindings` for opaque references you want to pin for reproducibility. These are not tuned, and they are not valid numeric symbols in operational preconditions.
*   Use `context` for numeric environment facts that operational preconditions may check through `env.context.*`.
*   Update the environment snapshot when operational assumptions change in ways that affect feasibility or interpretation of results.

Why `bindings` exist:

*   They pin the concrete artifacts or service endpoints the study actually used.
*   They make evaluation results interpretable later: if quality shifts, you can tell whether the retriever index or gateway changed.
*   They prevent hidden infrastructure drift from being confused with tuning progress.
*   They keep those opaque references out of operational arithmetic, which should be reserved for numeric environment facts.

## Evaluation Set

`evaluation_set` defines the shared evaluation set used to compare candidates fairly. It tells the runtime which dataset or benchmark slice supplies the evidence for objective measurements and promotion decisions.

Key fields:

*   `dataset`: required canonical identifier or URI for the evaluation corpus
*   `seed`: optional integer seed for reproducible sampling, ordering, or stochastic execution

Example:

```yaml
evaluation_set:
  dataset: s3://datasets/support-tickets/dev.jsonl
  seed: 2025
```

Rules that matter:

*   Keep the evaluation set fixed while comparing candidate configurations in the same study.
*   If you switch datasets, slices, or benchmark protocols, treat that as new evidence rather than a continuation of the same comparison.
*   Store the evaluation-set reference here, not measured outcomes. Observed metrics belong in measurement artifacts, not in the module.
*   Keep `dataset` explicit even for internal or generated benchmarks so promotion decisions remain auditable.

## What The Verifiers Are Checking

As soon as you start running TVL tools, you will see words like `SAT`, `operational`, and `promotion`. These are
three different questions about the same module.

1. **Structural question**: does this spec describe at least one legal configuration?
2. **Operational question**: given the declared environment snapshot, do the operational requirements and budgets still hold?
3. **Promotion question**: after evaluation, is the candidate strong enough to ship?

For the RAG example:

*   the **structural** check asks whether there is at least one valid combination of `model`, `retriever.k`, and `temperature`
*   the **operational** check asks whether the environment snapshot still satisfies the declared operational requirements and runtime assumptions
*   the **promotion** step happens later, once measurements have been collected

When TVL says **SAT**, it means the answer to the structural question is yes. There is at least one legal assignment of
the tuned variables. When TVL says **UNSAT**, it means the structural rules contradict each other, so the search space
is empty and optimization should not begin.

<details>
<summary>Open the tool-by-tool verifier split</summary>

The user-facing verifier split is:

*   `tvl-check-structural`: checks structural satisfiability and may return a witness assignment or UNSAT core
*   `tvl-check-operational`: checks operational preconditions (`constraints.derived`) and budget feasibility against the current environment snapshot
*   `tvl-measure-validate` and `tvl-ci-gate`: validate measured evidence and promotion readiness after evaluations have run

More detailed references:

*   [Semantics and Verification Reference](/specification/verification-reference)
*   [Constraint Language Reference](/specification/constraint-language)
</details>

## TVAR Declarations

Each TVAR declares:

*   `name`
*   `type`
*   `domain`

### Supported Types

| Type | Notes | Example |
| :--- | :--- | :--- |
| `bool` | Boolean choice | `[true, false]` |
| `int` | Integer domain | `range: [1, 10]` |
| `float` | Numeric domain; a `range` should give a `resolution` (see below) | `range: [0.0, 1.0]`, `resolution: 0.1` |
| `enum[str]`, `enum[int]`, `enum[float]` | Finite enumerations | `["gpt-4o", "gpt-4o-mini"]` |
| `tuple[...]` | Structured tuple values | `tuple[int, float]` |
| `callable[ProtoId]` | Registry-backed executable choices | `callable[RerankerProto]` |

### Domain Shapes

TVL examples and schema support these common domain styles:

*   `set`: explicit discrete values
*   `range`: numeric interval
*   `resolution`: step size for numeric ranges

For a float `range`, the formal semantics (`formalization/tvl-formal-semantics.md`, section 2.4) requires a `resolution`; an `int` range defaults to a step of 1. The schema and the current tools do not yet enforce this: `tvl-validate` accepts a float range without a resolution. Always give one, as the examples in this documentation do. Enumerated float choices (`enum[float]` or a `set`) need no resolution, and the optional validity domain of a `cvar` is a closed interval that does not use one.
*   `registry`: lazy lookup for callable domains
*   `filter` and `version`: specialization-time filters for registry-backed domains

Example:

```yaml
tvars:
  - name: reranker
    type: callable[RerankerProto]
    domain:
      registry: corp.rerankers
      filter: "category = 'neural'"
      version: ">=1.0.0"

  - name: temperature
    type: float
    domain:
      range: [0.0, 1.0]
      resolution: 0.1
```

!!! note "Callable and registry-backed domains"
    These forms are supported by current TVL tooling, but the linter marks them as outside the formally verified subset. Expect warning-level diagnostics such as `unverifiable_callable_type` and `unverifiable_registry_domain`.

!!! note "cvars, policies, and composites (RFC 0001/0002)"
    The Lean proof tree (`proofs/`) predates RFC 0001 (`cvars`/`policies`) and RFC 0002 (`composites`) and has not yet been extended to cover them; formal soundness guarantees do not apply to modules using these constructs. There is no lint warning for this yet (tracked as follow-up work); see `formalization/tvl-formal-semantics.md` §1.4 for the disclosure.

## Constraints

TVL separates constraints into structural rules and operational preconditions (`constraints.derived`).

### Structural Constraints

Structural constraints are formulas over TVARs. They define the structurally feasible search space and are the part checked by SAT/SMT-based tooling.

Forms:

*   implication sugar: `when` + `then`
*   standalone formula: `expr`

Operators:

*   comparison: `=`, `!=`, `<`, `<=`, `>`, `>=`
*   logic: `and`, `or`, `not`
*   membership: `in`

Example:

```yaml
constraints:
  structural:
    - when: routing_model = "llm"
      then: max_hops <= 3
    - expr: fallback_threshold >= 0.5
```

### Operational Preconditions (`constraints.derived`)

Operational preconditions are **environment-only** linear predicates used in operational validation. Use them to
declare required numeric operating conditions the current environment snapshot should satisfy before a study proceeds.
They are not structural formulas over TVARs, and they are not a place to encode objective thresholds or measured
runtime outcomes.

Reference numeric environment symbols through `env.context.*`. `environment.bindings` is for opaque deployment
references and must not appear in operational arithmetic.

```yaml
constraints:
  derived:
    - require: env.context.gateway_baseline_latency_ms <= 250
    - require: env.context.provider_input_price_usd_per_1k_tokens <= 0.05
```

!!! note "Not CEL"
    Structural constraints use TVL's typed formula language, not CEL. Write `model = "gpt-4o"` rather than `params.model == "gpt-4o"`.

## Objectives

TVL supports two objective forms:

### Standard Objectives

Use `direction: maximize` or `direction: minimize`.

```yaml
objectives:
  - name: quality
    metric_ref: metrics.quality.v1
    direction: maximize
  - name: latency_p95_ms
    metric_ref: metrics.latency_p95_ms.v1
    direction: minimize
```

Optional field:

*   `metric_ref`: stable evaluator metric identifier such as `metrics.latency_p95_ms.v1`

Use `metric_ref` when you want the spec to say exactly which metric definition computes the objective. Keep it
declarative: point to a metric contract or registry key, not to a Python function path or shell command.

### Banded Objectives

Use `band` when success means staying within a target interval rather than strictly maximizing or minimizing. TVL uses `TOST` for these banded checks.

```yaml
objectives:
  - name: response_tokens
    metric_ref: metrics.response_tokens.v1
    band:
      target: [50, 200]
      test: TOST
      alpha: 0.05
```

## Promotion Policy

`promotion_policy` defines how a candidate is compared against an incumbent.

Key fields:

*   `dominance`: TVL requires `epsilon_pareto`
*   `alpha`: significance budget
*   `min_effect`: non-negative per-objective epsilon values
*   `adjust`: optional multiple-testing adjustment (`none`, `bonferroni`, `holm`, `BH`)
*   `chance_constraints`: optional hard confidence-based constraints

Example:

```yaml
promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  adjust: holm
  min_effect:
    quality: 0.01
    latency_p95_ms: 50
  chance_constraints:
    - name: latency_slo
      threshold: 0.05
      confidence: 0.95
```

Notes:

*   Standard objectives should have a `min_effect` entry.
*   Banded objectives do not need a `min_effect` entry.
*   Chance constraints are expressed as threshold + confidence pairs over named metrics.
*   `metric_ref` is optional, but recommended for production-facing specs because it links each objective to the metric contract that computes it.

## Legacy Implementation Hints (`exploration`)

`exploration` is retained for compatibility with existing modules. It contains non-semantic hints for a particular runtime about how to search the feasible space. It does not change which agent configurations are admissible or what evidence satisfies the requirements.

Portable requirement specifications should keep optimizer settings in an implementation profile or run plan. A runtime may ignore this block unless its declared profile says otherwise.

Common fields:

*   `strategy.type`: `random`, `grid`, `tpe`, `cmaes`, `nsga2`, `custom`
*   `initial_sampling`
*   `parallelism.max_parallel_trials`
*   `convergence`
*   `budgets`

Example:

```yaml
exploration:
  strategy:
    type: nsga2
  initial_sampling: latin_hypercube
  convergence:
    metric: hypervolume_improvement
    window: 5
    threshold: 0.01
  budgets:
    max_trials: 64
    max_spend_usd: 50.0
    max_wallclock_s: 3600
```

The CLI validates these legacy fields for shape and positivity. Their operational meaning and enforcement belong to the runtime executing the search; they are not part of TVL conformance or certification semantics.

## CLI Workflow

Core module validation:

```bash
tvl-parse path/to/module.yml
tvl-lint path/to/module.yml
tvl-validate path/to/module.yml
tvl-check-structural path/to/module.yml --json
tvl-check-operational path/to/module.yml --json
```

Artifact validation and composition:

```bash
tvl-compose staging.overlay.yml -o merged.tvl.yml
tvl-config-validate module.tvl.yml config.yml
tvl-measure-validate module.tvl.yml config.yml measurements.yml
```

`tvl-compose` takes **one** overlay file, which names its base via `_tvl_overlay.extends`.

#### Where `extends` may point

`_tvl_overlay.extends` is a **relative** path, resolved against the directory of the overlay file that contains it.
Absolute paths are refused. Every base in a chain must stay inside the **overlay root**: the directory of the overlay
file you pass to `tvl-compose`, and everything below it. The root is fixed by that first file and does not move as the
chain is followed, so an overlay in a subdirectory cannot reach back out through `..` to a base above the root. Paths
are resolved before the check, so a symlink that points outside the root is refused as well. A violation fails with
`Overlay 'extends' path must stay within the overlay root` (exit 2).

Place shared bases beside the overlay you compose from, or beneath its directory. If several entry overlays share a base, keep them in the same directory as that base:

```text
envs/
  base.yml              # shared base
  staging.overlay.yml   # extends: base.yml        -> run: tvl-compose envs/staging.overlay.yml
  team/
    prod.overlay.yml    # extends: ../base.yml     -> refused when run as envs/team/prod.overlay.yml
```

To compose the `team/` overlay, either move it up to `envs/` beside the base or keep a copy of the base inside `team/`.

### Overlays may only tighten

An overlay narrows a base module; it may never widen it. The composer enforces:

| Element | Rule |
|---|---|
| TVAR domains | enum values may be removed, never added; numeric ranges may shrink, never grow |
| TVARs | may not be added |
| `exploration.budgets` | may decrease, never increase |
| `promotion_policy.chance_constraints` | a named constraint may not be dropped; `threshold` may only **decrease**; `confidence` may only **increase** |
| `objectives` | may not be dropped; kind may not change (directional <-> banded); `direction` may not flip; a `band.target` may not be widened or removed (both `[low, high]` and `{center, tol}` forms); `band.alpha` may not be raised |
| `constraints.structural` / `constraints.derived` | clauses may not be dropped unless waived, or replaced by a strictly tighter bound on the same symbol |

`threshold` bounds a violation rate, so raising it permits more violations; lowering
`confidence` makes a weaker claim. Both are widenings even though the numbers move in
opposite directions.

Every edge of an overlay **chain** is validated, not just the outermost one — otherwise a
single pass-through overlay (`final` extends `weaken` extends `base`) would check `final`
against the already-weakened `weaken` and launder the whole change.

#### What this does NOT cover

The table above is the enforced set, not a guarantee that an overlay cannot loosen anything.
These remain unchecked and can still be changed freely, so review them by hand:

*   `promotion_policy.alpha`, `adjust`, and `min_effect`
*   `evaluation_set.dataset` and `seed` — an overlay may point at an easier evaluation set
*   `environment.bindings` and `environment.context` (beyond the derived-clause rules)
*   `objectives[].metric_ref` and `band.test`

`min_effect` is excluded deliberately: whether raising it tightens depends on the objective's
direction and which side of the comparison it lands on, so a rule here would reject valid
overlays as often as it caught bad ones. The others are unbounded by nature and would need a
policy decision about what "tighter" even means.

Note that `overrides` **replaces** a list rather than merging into it (`tvars` is the one
exception, merged by name). Every inherited clause you intend to keep must be restated in
the overlay — the retention rules above are what stop an accidental omission from silently
becoming a weakening.

### Tightening a bound is not dropping it

A derived clause replaced by a **strictly tighter bound on the same symbol** counts as
retained, not removed — `env.context.eval_samples >= 3000` becoming `>= 5990` is exactly what
a stricter profile should do, and restating the looser clause alongside it would be nonsense.

Direction matters and is handled: a lower bound (`>=`, `>`) tightens as the number **rises**,
an upper bound (`<=`, `<`) tightens as it **falls**. Only the simple
`<symbol> <op> <number>` shape is recognised; anything richer falls back to requiring exact
retention or a waiver, which is the safe default.

### Waiving an inherited clause

Narrowing a TVAR can make an inherited clause **vacuous**, and keeping it is then a hard
lint error. For example, narrowing `temperature` to `[0.0, 0.3]` makes an inherited
`when: temperature > 0.7` guard unsatisfiable, and `tvl-validate` rejects the composed
module with `constraint_value_out_of_domain`. The clause has to go — so removal needs to be
expressible without also permitting silent weakening.

Declare it:

```yaml
_tvl_overlay:
  extends: base.tvl.yml
  waives:
    - clause: "temperature > 0.7 => pii_redaction = true"
      reason: "vacuous: temperature narrowed to [0.0, 0.3]"
```

Clause syntax for a waiver: `expr` clauses are written verbatim; `when`/`then` clauses are
written `<when> => <then>`. Whitespace is normalised, so reformatting a clause does not
break the match.

`reason` is mandatory, and a waiver that matches no clause in the base is an error rather
than a no-op — a stale waiver usually means the clause text drifted, which would otherwise
silently re-open the hole it was covering.

A waiver records that **a human decided to drop the clause and why**. It deliberately does
*not* prove the clause is vacuous; verifying that would need the structural SAT solver, and
a waiver that quietly accepted a non-vacuous clause would be worse than having no mechanism
at all. The value is that a declared removal is distinguishable from a silent one in review.

Interpretation:

*   `tvl-validate` checks structure, schema, and lints, but it is not the satisfiability prover.
*   `tvl-check-structural` answers the SAT/UNSAT question for structural constraints.
*   `tvl-check-operational` answers whether environment-scoped feasibility checks and budgets currently pass.
*   `tvl-ci-gate` is the later promotion decision step once incumbent and candidate evidence bundles exist.

## Authoring Rules That Matter

*   Keep `environment.snapshot_id` and `evaluation_set.dataset` explicit for reproducibility.
*   Use structural constraints for TVAR logic and operational preconditions (`constraints.derived`) for `env.context.*` checks.
*   Mirror production-facing modules in `spec/examples` so docs, tests, and CI stay aligned.
*   Treat `promotion_policy` as mandatory governance, not optional metadata.

## Appendix

<details>
<summary>Open formal and repository references</summary>

This page is a teaching-oriented overview. The normative sources in this repository are:

*   `tvl/spec/grammar/tvl.ebnf`
*   `tvl/spec/grammar/tvl.schema.json`
*   `spec/examples/*.yml`

For the full formal treatment, the repository also includes:

*   `tvl/formalization/tvl-formal-semantics.md`
</details>

## TVL 1.3: requirements, monitors, responses

!!! note "TVL 1.3"
    TVL 1.3 was accepted on 2026-10-21. This section is a reference for the fields of the three new optional blocks, the `tvl_pack` document, and the
    values they accept. For a guided introduction read
    [Requirements, Monitors and Responses](../guides/requirements-monitors-responses.md). The normative source is
    `formalization/rfc-0003-runtime-requirements-monitors-responses.md`, and the machine-readable shape is
    `spec/grammar/tvl.schema.json` and `spec/grammar/tvl-pack.schema.json`.

TVL 1.3 is a conservative extension of 1.2: a module without these blocks is read exactly as before. TVL specifies and checks these
declarations; a runtime platform evaluates them and carries out responses. The release gate of `tvl-ci-gate` additionally
evaluates promotion monitors from fully resolved counts; its limits are listed below.

### Where each check runs

The JSON Schema checks only **shape**: closed key sets (an unknown key is a `schema_error`), JSON types (booleans are not numbers, integers are
JSON integers), the always-required keys, and the identifier pattern of runtime names. Everything else - sealed enums, which fields a
variant needs or forbids, numeric ranges, references between declarations, cross-field rules - is checked by the lints and reported with the
specific code listed in the [error code catalog](error-codes.md#tvl-13-diagnostics). `tvl-validate` runs the lints only when the schema
passes; `tvl-lint` runs no schema. Use `tvl-validate`.

### Module and pack placement

| Key | Where | Type | Notes |
|---|---|---|---|
| `tvl_version` | module root, pack root | string `"1.3"` | **required** as soon as `requirements`, `monitors` or `responses` appears (even empty) and in every pack. Absent: `runtime_version_required`. Any other value, including the number `1.3`: `declared_version_below_constructs`. The schema accepts a string or a number so the lint can give the specific code. |
| `requirements` | module root, pack root | list of requirement | optional in a module, required in a pack |
| `monitors` | module root, pack root | list of monitor | optional in a module, required in a pack |
| `responses` | module root, pack root | list of response | optional in both |
| `pack` | pack root only | `{ module: <name> }` | required in a pack; `module` is a TVL module identifier (dots allowed) |

A **pack root** has exactly the keys `tvl_version`, `pack`, `requirements`, `monitors`, `responses`. A root mapping with `pack` and without `tvl` is
treated as a pack. Pack monitors must declare `applies_to: tenant_floor` and `phase: runtime`.

### Names and namespaces

Requirement, monitor and response names, rule `id`s, protocol states, and selector `ref`s are *runtime identifiers*:
`^[A-Za-z_][A-Za-z0-9_]*$`, no dots. Requirements, monitors and responses are three separate namespaces; rule ids are scoped to their response. A
runtime name equal to a tvar, cvar, policy or composite name, or a duplicate within one namespace, is `runtime_name_collision`.
Because TVL loads YAML 1.1, an unquoted `yes`, `no`, `on`, `off`, `true` or `false` is a boolean and fails the string type.

### Value types and domains

Numbers mean the exact value of their decimal literal. A literal that cannot be recovered exactly from a floating-point number
(more than 15 significant digits is not guaranteed) is rejected with `runtime_invalid_profile`.

| Type | Values |
|---|---|
| `ident` | `^[A-Za-z_][A-Za-z0-9_]*$` |
| `code_ident` (selector `tool`) | `^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$`, at most 128 characters |
| `prob_open` (`max_rate`, sampling `rate`, `rate_floor`) | decimal x with 0 < x < 1 |
| `conf` (`confidence`) | decimal c with 0 < c < 1 |
| `prob` (`false_alarm_budget`) | decimal with 0 < x <= 0.5 |
| `frac` (`max_unresolved_fraction`) | decimal with 0 <= x <= 0.5 |
| `hours` (`tumbling_hours`) | a divisor of 24: 1, 2, 3, 4, 6, 8, 12, 24 |
| `grace_minutes` | integer 0 to 360 |
| `min_samples` | integer 1 to 10,000,000 |
| `horizon_days` | integer 1 to 365 |
| `closure_windows` | integer 1 to 24 |
| `closure_max_age_hours` | integer 1 to 720 |
| `exceeds` | for `wall_clock_latency_ms`, `total_tokens`, `tool_calls`: integer >= 1. For `cost_usd`: decimal > 0 |
| `threshold_factor` | decimal b with b > 1 and b times `max_rate` < 1 |
| `within_hours`, `max_stale_windows`, `within_ms`, `trigger.hours`, `repeat_after_hours`, `max_repeats`, `limits.*` | integer >= 1 |
| `max_count` | integer >= 0 |
| `fingerprint` | `^[0-9a-f]{64}$`: the fingerprint of a certified configuration |
| `label` | `^[A-Za-z_][A-Za-z0-9_]*$`; for a catalogue checker, a member of its label list |
| `env_label` | the environment label. Under `profile: backend_v1` it must be trimmed, lower-cased and 1 to 64 characters (RFC 0003 §4.2); customer-side labels are otherwise free strings resolved through the customer's token map |

An out-of-range value is the dedicated `runtime_*_out_of_range` code for that field. A value of the wrong JSON type (a string where an integer is
required) is a `schema_error`.

### `requirements`

Common keys: `name` (required, `ident`), `kind` (required), `unit` (required). `kind` is one of four sealed values:

| `kind` | `unit` | Keys | Meaning |
|---|---|---|---|
| `rate_bound` | `trace` or `invocation` | `violation` (required, any predicate), `max_rate` (required, `prob_open`), `among` (optional predicate) | at most `max_rate` of the units in scope may violate |
| `zero_tolerance` | `trace` or `invocation` | `violation` (required, an *exact* predicate), `among` (optional predicate) | no unit in scope may violate |
| `recovery_time` | `episode` | `of` (required: a runtime monitor that has an episode), `within_hours` (required) | after a breach the requirement must be met again within `within_hours` of window time |
| `evidence_liveness` | `window` | `of` (required: a runtime window monitor, primary or burn), `max_stale_windows` (required) | the monitor must keep producing usable evidence |

Keys that belong to another kind are `runtime_invalid_profile`. `among` is not allowed under `profile: backend_v1`.

A `trace` covers one request end to end, including its model calls, tool calls and handoffs across contributing
components. An `invocation` is one execution of the monitored agent itself; several invocations can belong to a
trace. Individual tool and model calls are events within a unit. Predicates describe the unit's complete history;
an evaluator profile outside TVL determines what partial evidence justifies reporting about it.

### Predicates (`violation`, `among`)

A predicate is exactly one of three families. Unknown keys are rejected. `among` takes only the checker family (`runtime_among_not_checker`); `violation` takes the families listed per kind.

| Family | Keys | Notes |
|---|---|---|
| metric | `metric`, `exceeds` | `metric` is `wall_clock_latency_ms`, `cost_usd`, `total_tokens` or `tool_calls`. A unit violates when the metric is strictly greater than `exceeds`. Only under `rate_bound`. |
| checker | `checker`, `label_in` | `checker` is a catalogue id (`traigent.refusal.v1`, labels `must_refuse`, `complied`) or `customer:<ident>`. `label_in` is a list of labels. As `violation`, only under `rate_bound`; as `among`, under `rate_bound` or `zero_tolerance`. Only for `customer_side` or `evaluation_set` evidence. |
| exact | `pattern` and its keys, below | allowed under `rate_bound` and `zero_tolerance` |

**Exact patterns**

| `pattern` | Required keys | Optional keys | Notes |
|---|---|---|---|
| `absence` | `a` | | any matching event violates |
| `bounded_existence` | `a`, `max_count` | | the (`max_count` + 1)-th matching event violates |
| `precedence` | `a`, `b` | `mode`, `correlate_by` | `mode`: `single_use` (default) or `reusable`. A `b` needs an earlier usable `a`. |
| `bounded_response` | `a`, `b`, `within_ms` | `correlate_by` | every `a` needs a `b` after it within `within_ms` ms (inclusive) |
| `protocol` | `alphabet`, `states`, `start`, `transitions`, `accepting`, `rejecting` | `unlisted` | deterministic state machine; `unlisted` is `reject` (default) or `ignore` |

`correlate_by` is `unit` (default), `correlation_id` or `tool_call_id`, only on `precedence` and `bounded_response`.
`bounded_existence` counts across the whole unit. Correlation matching needs the same non-missing key on both events.
`precedence` uses each `a` at most once unless `mode: reusable`; an `authorization_revoked` invalidates earlier
`authorization_granted` events with the same `ref` and correlation key, and never invalidates an `a` of another
event type. `bounded_response` matches one `b` to each `a`, one-to-one, after it in event order and within the
inclusive deadline.

A checker answers separately for each predicate position (`among` or `violation`), with one declared label or no
result. Its predicate holds iff that answer is in `label_in`; no result leaves the unit unresolved. The catalogue
checker has exactly the labels `must_refuse` and `complied`: the first is the positive answer to the `among`
question, the second to the `violation` question; the other label is negative in each position. The customer's
policy determines what must be refused. Checker accuracy is outside TVL's guarantees.

**Selector** (`a`, `b`, `alphabet` entries, `when`): `{ event, [tool], [status], [ref] }`.

| Key | Type | Allowed with |
|---|---|---|
| `event` (required) | `unit_start`, `unit_end`, `tool_call`, `tool_result`, `model_call`, `handoff`, `error`, `authorization_granted`, `authorization_revoked` | - |
| `tool` | `code_ident` | `tool_call`, `tool_result` |
| `status` | `running`, `completed`, `failed`, `rejected` | `unit_end`, `tool_result` |
| `ref` | `ident` | `authorization_granted`, `authorization_revoked` |

A selector field on the wrong event is `runtime_invalid_profile`. `{ event: error }` matches every error; the error class is not selectable.

Events are emitted by the agent's customer-side instrumentation (SDK, framework or own code). `ref` names an
authorization kind, not an individual grant. `correlation_id` identifies a logical transaction within the unit;
`tool_call_id` identifies one tool call and its result. Instrumentation supplies these event fields; selectors
test only the fields in the table above.

**Protocol transition**: `{ from: <state>, when: <selector>, to: <state> }`. Constraints: at most one transition per (state, alphabet entry);
no event may match two alphabet entries; every `when` is an alphabet entry; `start`, `accepting`, `rejecting` and every transition endpoint are declared
states; `accepting` and `rejecting` do not overlap (`runtime_protocol_nondeterministic`). The transition key is `when`, not `on` (YAML 1.1 reads `on` as a
boolean).

### `monitors`

| Key | Type | Required | Allowed values and notes |
|---|---|---|---|
| `name` | `ident` | yes | |
| `requirement` | `ident` | yes | the one requirement it checks (`runtime_missing_ref`) |
| `phase` | string | yes | `promotion` or `runtime` |
| `profile` | string | no | `backend_v1` |
| `applies_to` | string | no | `agent` (default in a module) or `tenant_floor` (only in a pack, and required there) |
| `evidence` | object | yes | see below |
| `window` | object | per role | `{ tumbling_hours, grace_minutes }` and nothing else |
| `decision` | object | yes | see below |
| `episode` | object | per role | `{ closure_windows, closure_max_age_hours }` |
| `limits` | object | per T13 | `{ max_active_obligations, max_tracked_correlations }`, integers >= 1 |
| `single_producer` | boolean | no | default `false`; only with an exact-pattern violation |

**`evidence`**

| Key | Allowed values |
|---|---|
| `source` (required) | `backend_trace_metadata`, `customer_side`, `evaluation_set`, `episodes`, `windows` |
| `deployment_environment` | an environment label; default `production`. Not allowed on promotion or obligation monitors. |
| `attribution` | `agent_key_exact_v1` (default) |
| `resolution` | `terminal_status_v1` (default) |
| `sampling` | the string `unverified`, or `{ mode, rate }` with `mode` = `head_sampled_declared` or `hash_bernoulli_committed_v1` and `rate` a `prob_open` |

**`decision`**

| Key | Allowed values |
|---|---|
| `method` (required) | `clopper_pearson_exact_v1`, `clopper_pearson_rational_v2`, `exact_count_v1` |
| `model` | `iid_bernoulli_within_window_v1` (default) |
| `confidence` | `conf` |
| `false_alarm_budget` | `prob` |
| `horizon_days` | `horizon_days` |
| `min_samples` | `min_samples` |
| `max_unresolved_fraction` | `frac` |
| `threshold_factor` | `threshold_factor`; marks a burn monitor |

**Compatible combinations.** Any other combination is `runtime_invalid_profile`.

| Requirement kind | Evidence source | Phase | Method |
|---|---|---|---|
| `rate_bound` | `backend_trace_metadata` (with `backend_v1`), `customer_side`, `evaluation_set` | `runtime`; `promotion` only with `evaluation_set` | `clopper_pearson_exact_v1` (only with `backend_v1`), `clopper_pearson_rational_v2` |
| `zero_tolerance` | `customer_side`, `evaluation_set` | `runtime`; `promotion` only with `evaluation_set` | `exact_count_v1` |
| `recovery_time` | `episodes` | `runtime` | `exact_count_v1` |
| `evidence_liveness` | `windows` | `runtime` | `exact_count_v1` |

**Monitor roles and their fields.** A *primary* monitor is a `runtime` `rate_bound` or `zero_tolerance` monitor without `threshold_factor`; a *burn*
monitor is a `runtime` `rate_bound` monitor with `threshold_factor`; a *promotion* monitor has `phase: promotion`; an *obligation* monitor checks a
`recovery_time` or `evidence_liveness` requirement. R = required, D = optional with the stated default, F = forbidden.

| Field | Primary `rate_bound` | Primary `zero_tolerance` | Burn | Promotion | Obligation |
|---|---|---|---|---|---|
| `evidence.deployment_environment` | D `production` | D `production` | D `production` | F | F |
| `evidence.attribution` | D | D | D | F | F |
| `evidence.resolution` | D | D | D | D | F |
| `evidence.sampling` | by source | F | by source | F | F |
| `window` | R | R | R | F | F |
| `decision.method` | R | R (`exact_count_v1`) | R (`clopper_pearson_rational_v2`) | R | R (`exact_count_v1`) |
| `decision.model` | D | F | D | F | F |
| `decision.confidence` | R | F | F | R for `rate_bound`, F for `zero_tolerance` | F |
| `decision.false_alarm_budget` | R | F | R | R for `rate_bound`, F for `zero_tolerance` | F |
| `decision.horizon_days` | R | F | R | F | F |
| `decision.min_samples` | R | D `1` | R | D `1` | F |
| `decision.max_unresolved_fraction` | R | F | R | D `0` for `rate_bound`, F for `zero_tolerance` | F |
| `decision.threshold_factor` | F | F | R | F | F |
| `episode` | R | R | F | F | F |
| `limits` | R for stateful patterns, otherwise D | as primary `rate_bound` | as primary `rate_bound` | as primary `rate_bound` | F |
| `single_producer` | D `false` | D `false` | D `false` | D `false` | F |

"Stateful patterns" means: a `customer_side` or `evaluation_set` monitor whose violation is `precedence`, `bounded_response` or `protocol` must declare
`limits`; other monitors may declare them. Outside the `backend_v1` profile and the defaults shown, no statistical field has a default; an omitted one is `runtime_invalid_profile`.

**Sampling by source.** `unverified` only with `backend_trace_metadata`. `head_sampled_declared` and `hash_bernoulli_committed_v1` only with
`customer_side` and `rate_bound`. `evaluation_set`, `episodes` and `windows` take no sampling. Omitted `sampling` on `customer_side` means a census.
`zero_tolerance` monitors declare no sampling.

**References.** `recovery_time.of` names a runtime monitor with an episode (a primary monitor). `evidence_liveness.of` names a runtime window monitor
(primary or burn). A cycle of requirement - `of` - monitor - `requirement` - requirement is `runtime_dependency_cycle`. Two monitors with the same
effective key (same requirement identity, source, environment, attribution, method and `threshold_factor`) are `runtime_duplicate_key`, even if their
requirements have different names or different bounds.

**Schedule rules.** `closure_max_age_hours * 60 >= closure_windows * tumbling_hours * 60 + grace_minutes + 60` or `closure_unreachable`.
`within_hours >= closure_windows * tumbling_hours` or `recovery_deadline_impossible`. A primary `rate_bound` monitor must be able to reach `MET` at
`min_samples` or `runtime_met_unreachable_at_min_samples` (a warning under `backend_v1`), and should be able to reach `BREACHED` or
`runtime_breach_unreachable_at_min_samples` warns. A primary monitor with no `evidence_liveness` requirement warns (`runtime_liveness_missing`).

### Profile `backend_v1`

`profile: backend_v1` freezes a monitor to the hosting platform's built-in latency requirement. It requires: `kind: rate_bound`, `unit: trace`,
`violation.metric: wall_clock_latency_ms`, `phase: runtime`, `evidence.source: backend_trace_metadata`, `decision.method: clopper_pearson_exact_v1`,
`sampling: unverified`, `attribution: agent_key_exact_v1`, `resolution: terminal_status_v1`, `model: iid_bernoulli_within_window_v1`. It forbids `among`,
`threshold_factor`, `limits` and `single_producer`. Any other field or value is `runtime_legacy_profile_override`. Omitted fields take the defaults below, and
`window` and `episode` may then be omitted whole.

| Field | Allowed | Default |
|---|---|---|
| `max_rate` | 0 < x < 1 | none |
| `violation.exceeds` (ms) | integer 1 to 600,000 | none |
| `deployment_environment` | trimmed, lower-cased, 1 to 64 characters | `production` |
| `confidence` | 0.90, 0.95, 0.99 | 0.95 |
| `tumbling_hours` | 1, 3, 6, 12, 24 | 6 |
| `grace_minutes` | 0 to 360 | 30 |
| `min_samples` | 1 to 10,000,000 | 200 |
| `max_unresolved_fraction` | 0 to 0.5 | 0.05 |
| `false_alarm_budget` | above 0, at most 0.5 | 0.05 |
| `horizon_days` | 1 to 365 | 30 |
| `closure_windows` | 1 to 24 | 2 |
| `closure_max_age_hours` | 1 to 720 | 24 |

### `responses`

A response is `{ name, rules }`. A rule is:

| Key | Type | Required | Notes |
|---|---|---|---|
| `id` | `ident` | yes | unique within its response (`response_rule_id_duplicate`) |
| `trigger` | `{ monitor, event, [hours] }` or (1.4) `{ rule, event }` | yes | `monitor` names a monitor of this document or of a composed pack. `event` must be one that monitor emits. `hours` is required for `episode_open_for` and `unknown_for`, and forbidden otherwise. |
| `do` | action | yes | the sealed action set below. `record` is implicit and cannot be declared (`response_unknown_action`). |
| `approval` | `none`, `standing`, `human` | yes for `suspend`, otherwise no | allowed values and defaults by action, below |
| `target` | `last_certified` or `fingerprint` | `rollback` only | |
| `severity` | `info`, `warning`, `critical` | `notify` only | default `critical` |
| `fallback` | `static_unavailable` or `route_to_human` for `suspend`; a `fingerprint` for `degrade` | `suspend`, `degrade` | |
| `rate_floor` | `prob_open` | `throttle` only | admission cap as a fraction of the unthrottled rate; smaller throttles harder |
| `repeat_after_hours` | integer >= 1 | no | re-fires while the scope is active |
| `max_repeats` | integer >= 1 | no | requires `repeat_after_hours`; required for every action except `notify` that repeats |
| `on_check_error` | `block`, `allow` | `block_action`, `halt_unit` only | no default |

A parameter that does not belong to the action, or is missing, is `runtime_invalid_ladder`.

**Actions**

| `do` | Approval allowed (default) | Extra fields | Trigger restriction |
|---|---|---|---|
| `notify` | `none` | `severity` | any event |
| `open_next_step` | `none` | none | active-scope events only (below); an open episode is needed for an effect |
| `optimize` | `standing`, `human` (`human`) | `deploy`: `never` (default) or `if_promoted` | active-scope events only (below); a next step must have been issued; `deploy: if_promoted` only on `episode_opened`, `episode_continued`, `episode_open_for` |
| `rollback` | `standing`, `human` (`human`) | `target` (required) | active-scope events only (below) |
| `throttle` | `standing`, `human` (`human`) | `rate_floor` (required) | active-scope events only (below) |
| `degrade` | `standing`, `human` (`human`) | `fallback` fingerprint (required) | active-scope events only (below) |
| `suspend` | explicit `human` required | `fallback` enum (required) | `episode_continued`, `episode_open_for` or `recovery_overdue` only (`response_suspend_unconfirmed`) |
| `block_action` | `none` | `on_check_error` (required) | `unit_violation` on a `customer_side` monitor whose pattern is fixed by a prefix (`absence`, `bounded_existence`, `precedence`, `protocol`) |
| `halt_unit` | `none` | `on_check_error` (required) | as `block_action` |

The lints reject a remote service action (`open_next_step`, `optimize`, `rollback`, `throttle`, `degrade`, `suspend`)
on `episode_resolved`, `episode_withdrawn`, `recovery_cancelled`, `recovery_recovered`, `live_again` or
`unit_violation` with `runtime_invalid_ladder`. These events cannot authorize a new remote effect. They can still
`notify`; `unit_violation` can also authorize local guards. A service effect still needs its action-specific
preconditions and a scope requiring intervention when it happens (RFC §7.4).

`optimize`, `rollback`, `throttle` and `degrade` with `approval: none` are `response_irreversible_without_approval`; `suspend` with an approval other
than `human`, or with `approval` omitted, is `response_suspend_without_human`. A standing grant (an owner-signed record, at most 30 days, outside TVL documents) never
authorizes `suspend`.

`optimize` with `deploy: if_promoted` also deploys the candidate it finds, as a separate service effect (RFC §7.6): it
needs its own human approval (or a standing grant that names the deploy), a still-open episode, a current contract, and
a `Promote` result of the promotion gate join for that candidate, which requires a promotion monitor on the trigger
monitor's requirement (`response_deploy_without_promotion_monitor` otherwise). A deploy never closes the episode;
only healthy production windows do. Overlays may change `if_promoted` to `never`, never the reverse.

`suspend` is latched: resolution or withdrawal makes human `resume` eligible, never automatic. An installed
`throttle` or `degrade` also remains until an authorized human `release`. Multiple throttles use the smallest
`rate_floor`. `open_next_step` records a recommendation for whoever maintains the agent; acting on it needs
separate authority and it changes no deployment by itself.

**Events by monitor role**

| Monitor role | Events |
|---|---|
| primary | `episode_opened`, `episode_continued`, `episode_open_for`, `episode_resolved`, `episode_withdrawn` |
| primary, `customer_side` | plus `unit_violation` |
| burn | `burn_breached` |
| `recovery_time` obligation | `recovery_overdue`, `recovery_cancelled`, `recovery_recovered` |
| `evidence_liveness` obligation | `stale`, `live_again` |
| promotion | none |

#### Reactive notifications (TVL 1.4, RFC 0004)

Declare `tvl_version: "1.4"` when a rule uses any of the following, including empty guard lists.
All require `do: notify` (`runtime_notify_only`). TVL 1.3 documents keep their diagnostics.

- `trigger: {rule: fix, event: optimize_no_candidate}` names another optimize rule in the same
  response. The closed outcome set is `optimize_no_candidate`, `optimize_failed`, `deploy_refused`,
  `deploy_failed`. Deploy outcomes require `deploy: if_promoted` on that optimize rule. Outcome
  triggers fire once per attempt; neither repeat field is allowed. Packs cannot declare them.
- `trigger: {monitor: latency, event: unknown_for, hours: 6}` requires a primary runtime monitor
  and hours at least its tumbling duration. It reports UNKNOWN windows with usable evidence, by
  window time, once per undecided run. Windows without usable evidence neither count nor end
  the run; MET, BREACHED or an effective-key change ends it. A single counted window can fire.
  Repeats are allowed. This differs from `stale`; both may fire on intermittent evidence.
- `only_while: [{monitor: errors, state: episode_open}]` is a conjunction;
  `unless: [{monitor: provider, state: episode_open}, {rule: fix, state: attempt_open}]` is a
  disjunction. These are the only guard forms. Monitor guards require primary runtime monitors;
  attempt guards require an optimize rule of the same response, and are forbidden in packs.

An attempt opens when optimize fires, including while approval is pending; it closes at its last
applicable outcome, successful repair/deploy, scope closure, response revision change before a
pending effect, or decline/expiry of the next effect's approval before that effect starts.
Waiting for approval or unreachable authority keeps it open with no outcome. Expiry after start
still allows that effect's outcome. Promote takes precedence over invalid evidence in another
candidate; without any Promote, invalid evidence gives `optimize_failed`, not NoDecision.
A deploy failure is terminal only after the evaluator profile's finite retry bound is exhausted.

Guards use strong Kleene logic (TRUE, FALSE, UNDECIDED). Deliver unless `only_while` is FALSE or
`unless` is TRUE; UNDECIDED never suppresses. Evaluate once per occurrence after all occurrences
fired by that evaluation, so a newly opened attempt is visible. Each repeat rechecks; a suppressed
occurrence is not delivered later when its guard changes. Use `episode_continued` or repeats to
recheck. Guards preserve trigger, scope and occurrence identity and grant no effect authority.

The unless graph adds an edge from each guarded notification's source monitor to every monitor
in its `unless`. For outcome rules, use the referenced optimize rule's trigger monitor. Cycles,
including self-loops, are `runtime_guard_cycle`; attempt guards add no edges. An `only_while` on
its own source is `runtime_guard_redundant` (warning). Conjunction guards may be symmetric.
Guard sets and outcome triggers are immutable under overlays and meets; list order/duplicates
are immaterial. Absorbed pack monitor aliases are rewritten in guards too. Hosted projection
uses closed enums and tokenized references; `backend_v1` is unchanged. Compiled contracts use `/1` for version 1.3 and `/2` for version 1.4, including the conservative
version exception for 1.4 declarations without new constructs (see Companion documents below and RFC 0004 §3).

### Verdicts, states and reasons

| Name | Values |
|---|---|
| runtime verdict | `MET`, `BREACHED`, `UNKNOWN(reason)` |
| window reasons | `late_evaluation`, `revision_gap`, `insufficient`, `unplaceable`, `unresolved`, `inconclusive`, `sampling_biased`, `incomplete` |
| recovery state | `RECOVERED` (MET), `OVERDUE` (BREACHED), `PENDING` (`UNKNOWN(pending)`), `CANCELLED` (`UNKNOWN(cancelled)`), `UNKNOWN(lifecycle_unavailable)` |
| liveness state | `LIVE` (MET), `STALE` (BREACHED), `UNKNOWN(insufficient)`, `UNKNOWN(awaiting)` |
| episode outcome | `resolved`, `withdrawn` |
| promotion mapping | `MET` passes, `BREACHED` is `Reject`, `UNKNOWN` is `NoDecision` |

`rate_bound` verdicts under `clopper_pearson_rational_v2` carry the declared false-alarm and confidence promises
under the statistical model; unresolved evidence cannot strengthen either claim. `zero_tolerance` means one
established violation breaches, while `MET` needs complete census coverage with at least `min_samples` units and
none violating. An empty complete window is `UNKNOWN(insufficient)`.
No guarantee is claimed for the floating-point method `clopper_pearson_exact_v1`: its verdicts are the hosting
platform's computation, matched against test vectors, not proved, and the probability theorems do not cover it.

Recovery uses the end of the closing window minus the end of the opening window. Wall-clock duration is reported
beside it. Freshness at evaluation can still prevent closure; missing lifecycle evidence alone is not `OVERDUE`.
Withdrawal before the obligation is decided gives `CANCELLED`; `RECOVERED`, `OVERDUE` and `CANCELLED` are terminal.

**Release gate.** The evaluation harness supplies `monitor_outcomes` in the candidate bundle: `n` resolved
units, `k` violating among them, optional `u` unresolved and `pl` unplaceable (both default 0). `tvl-ci-gate`
evaluates a monitor only with `u = pl = 0`; otherwise it returns `UNKNOWN(engine_required)` and maps it to
`NoDecision`. Zero tolerance also needs the harness's explicit `complete: true`, otherwise `UNKNOWN(incomplete)`.
That attestation means the evaluation set was fully covered; counts alone do not prove it. The gate joins these
results with the legacy result, `Reject` before `NoDecision` before `Promote`. A `rate_bound` promotion monitor
uses standard exact binomial tests; at matched confidence its `MET` test corresponds to a chance-constraint pass
(subject to floating-point ties in the legacy bound). A chance constraint rejects inconclusive evidence; a monitor
maps it to `NoDecision`. Legacy modules keep their previous gate behaviour.

### Companion documents

| Document | Format tag | Used for |
|---|---|---|
| token map | `tvl-token-map/1` | `{ format, tokens: [{ namespace, local, hosted }] }`. Customer side. Gives each name an opaque reference. `tvl-compile-runtime --token-map`. |
| checker registry | `tvl-checker-registry/1` | `{ format, checkers: [{ checker, labels }] }`. Customer side. Binds each `customer:<name>` to its closed, ordered label list. `tvl-compile-runtime --checkers`. |
| compiled contract | `tvl-runtime-contract/1`, `tvl-runtime-contract/2` | `runtime-contract.json`, written by `tvl-compile-runtime`; opaque references only. Schemas: `spec/grammar/tvl-runtime-contract.schema.json` (`/1`), `tvl-runtime-contract-v2.schema.json` (`/2`). |
| compiled local form | `tvl-runtime-local/1`, `tvl-runtime-local/2` | `runtime-local.json`, customer side. Schemas: `spec/grammar/tvl-runtime-local.schema.json` (`/1`), `tvl-runtime-local-v2.schema.json` (`/2`). |
| window report | `tvl-runtime-report/1` | produced by customer-side monitors. Schema: `spec/grammar/tvl-runtime-report.schema.json`. |
| measurement bundle | `monitor_outcomes` | `monitor_outcomes.<promotion monitor name>: { n, k, [u], [pl], [complete] }` (integers >= 0; `complete` boolean) in the bundle given to `tvl-measure-validate` and `tvl-ci-gate`. Schema: `spec/grammar/tvl-measurement.schema.json`. |

The `/1` contract and local schemas are frozen at TVL 1.3.0 and require `tvl_version: "1.3"`;
Previously accepted inputs other than authored `"1.4"` retain their canonical bytes for the same compiler inputs
and toolchain version; older or omitted declarations compile to version `"1.3"`, as in 1.3.0.
Outcome triggers, `unknown_for`, and projected `only_while`/`unless` guards use `/2`.
The conservative version exception is explicit: a `tvl_version: "1.4"` document with no new construct also uses `/2`,
because `/1` permits only version `"1.3"`. This overrides historical byte identity for `"1.4"` modules without
runtime blocks: 1.3.0 accepted those but emitted version `"1.3"` and `/1`. `/2` requires version `"1.4"`;
a 1.3 contract retagged `/2` is refused.
Validators dispatch by `format`; `/1` refuses every 1.4 field, and unknown format tags are refused.
An empty guard list is omitted during projection. See RFC 0004 §3 and §7.2; the RFC remains DRAFT.

Token-map `namespace` values are `module`, `requirement`, `monitor`, `response`, `rule`, `environment`, `selector_ref`, `checker`, `state`. In every
namespace except `checker` the `hosted` value matches `^[A-Za-z0-9_-]{1,128}$`; in `checker`, `local` is a customer checker id and `hosted` is
`customer:` followed by 64 lowercase hex characters. The map must be one-to-one within a namespace.

`tvl-compile-runtime DOCUMENT [--pack PACK.yml]... --emit-token-map-template` prints the required entries as
local-only JSON with empty `hosted` values, including default environments. It mints no tokens and writes no
compiled artefacts. Fill the placeholders before using the result with `--token-map`; template mode cannot be
combined with `--token-map` or `--out-dir`.

### Defaults at a glance

| Item | Default |
|---|---|
| `applies_to` (module monitor) | `agent` |
| `deployment_environment` | `production` |
| `attribution` / `resolution` / `model` | `agent_key_exact_v1` / `terminal_status_v1` / `iid_bernoulli_within_window_v1` |
| `sampling` on `customer_side` | census (every unit in scope) |
| `precedence.mode` / `correlate_by` / protocol `unlisted` | `single_use` / `unit` / `reject` |
| `notify.severity` | `critical` |
| `optimize.deploy` | `never` |
| `approval` | `none` for `notify`, `open_next_step`, `block_action`, `halt_unit`; `human` for `optimize`, `rollback`, `throttle`, `degrade`; explicit `human` required for `suspend` |
| `min_samples` (zero tolerance, promotion) | 1 |
| `max_unresolved_fraction` (promotion `rate_bound`) | 0 |
| `on_check_error` | none: you must choose |
| any other statistical field (outside `backend_v1`) | none: omission is `runtime_invalid_profile` |

### Version and compatibility

Documents without these blocks gain no new diagnostic. An old reader rejects a 1.3 module because the root schema is closed. A tool that meets a 1.3
construct it does not implement refuses with `unsupported_construct` and names the construct (`requirements`, `monitors`, `responses`, `tvl_pack`,
`monitor_outcomes` or `runtime_report`); it never ignores or strips it. `tvl-check-structural`, `tvl-check-operational` and `tvl-config-validate` erase the
three blocks from a module and check the rest; `tvl-ci-gate --policy` refuses any runtime block.
