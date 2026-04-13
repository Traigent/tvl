# Language Reference

This page is a friendly guide to TVL.

Instead of treating TVL as a bag of keywords, this reference teaches the language by following one concrete agent all
the way through: a simple campus FAQ RAG system. As you read, the example gives each TVL block a job, so the later
rules feel grounded instead of abstract.

If you are new to TVL, start with the example below and read it top to bottom once before diving into the rest of the
sections.

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
*   `evaluation_set` tells you which question set supplies the evidence. This is the shared workload used to compare candidate settings fairly.
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

`evaluation_set` defines the shared workload used to compare candidates fairly. It tells the runtime which dataset or benchmark slice supplies the evidence for objective measurements and promotion decisions.

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
*   Store the workload reference here, not measured outcomes. Observed metrics belong in measurement artifacts, not in the module.
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
| `float` | Numeric domain with optional resolution | `range: [0.0, 1.0]` |
| `enum[str]`, `enum[int]`, `enum[float]` | Finite enumerations | `["gpt-4o", "gpt-4o-mini"]` |
| `tuple[...]` | Structured tuple values | `tuple[int, float]` |
| `callable[ProtoId]` | Registry-backed executable choices | `callable[RerankerProto]` |

### Domain Shapes

TVL examples and schema support these common domain styles:

*   `set`: explicit discrete values
*   `range`: numeric interval
*   `resolution`: step size for numeric ranges
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

## Exploration

`exploration` describes how a runtime searches the feasible space.

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

Budgets are validated by the CLI for shape and positivity; actual enforcement is performed by the runtime executing the search.

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
tvl-compose base.tvl.yml staging.overlay.yml > merged.tvl.yml
tvl-config-validate module.tvl.yml config.yml
tvl-measure-validate module.tvl.yml config.yml measurements.yml
```

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
