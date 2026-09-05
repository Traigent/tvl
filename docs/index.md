# TVL: AI agent requirements as a verifiable specification

## AI agents are under-specified

Teams still describe production AI systems with vague requests:

> *"Make it cheaper."*  
> *"Improve accuracy."*  
> *"Keep latency under control."*

Those requirements usually get translated into scattered prompt edits, hidden model switches, evaluation scripts, dashboards, and one-off runtime flags. TVL turns them into a single, typed, reviewable specification of the allowed agent designs and the properties a candidate must demonstrate.

**Tuned Variables Language (TVL)** is an AI agent requirements specification language. It defines what may vary, what must hold, how desired properties are measured, and what evidence is required for acceptance or promotion. It specifies an agent design space rather than a recipe for building one particular agent.

<div class="grid cards" markdown>

-   :material-tune-variant: **Specify the agent design space**

    Declare allowed models, prompts, routing policies, retrieval parameters, tool choices, memory, and orchestration as typed TVARs.

-   :material-shield-check: **State required properties**

    Express structural rules, operational assumptions, measurable objectives, acceptable ranges, and behavioral constraints.

-   :material-chart-scatter-plot: **Bind requirements to evidence**

    Pin the evaluation set and metric definitions used to decide whether a candidate satisfies the contract.

-   :material-file-document-check: **Support verifiable certification**

    Preserve the specification, candidate, evaluator, evidence, and governed decision as a scoped conformance claim.

</div>

## What TVL makes explicit

TVL is the contract boundary for governed adaptation in AI agents. A TVL module captures:

*   **Agent design space**: typed TVARs over primitive, enum, tuple, and callable domains
*   **Feasibility rules**: solver-friendly structural constraints over TVARs
*   **Operational assumptions**: environment snapshots with pinned bindings and numeric context for operational checks
*   **Desired properties**: maximize/minimize objectives and acceptable target bands
*   **Metric contract**: optional `metric_ref` pointers that tell the evaluator which metric definition computes each objective
*   **Acceptance governance**: `epsilon_pareto`, `min_effect`, `adjust`, and `chance_constraints`
The public language contract defines what these requirements mean. Search algorithms, candidate scheduling, sample allocation, and internal solver representations remain implementation choices.

## A Valid TVL Example

The example below mirrors the canonical `rag-support-bot.tvl.yml` module shipped in `spec/examples`:

```yaml title="rag-support-bot.tvl.yml"
tvl:
  module: corp.support.rag_bot

environment:
  snapshot_id: "2024-02-15T00:00:00Z"
  bindings:
    retriever: bm25-v3
    llm_gateway: us-east-1
  context:
    gateway_baseline_latency_ms: 180
    provider_input_price_usd_per_1k_tokens: 0.03

evaluation_set:
  dataset: s3://datasets/support-tickets/dev.jsonl
  seed: 2024

tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4o-mini", "gpt-4o", "llama3.1"]
  - name: temperature
    type: float
    domain:
      range: [0.0, 1.0]
      resolution: 0.05
  - name: retriever.k
    type: int
    domain:
      range: [0, 20]
  - name: zero_shot
    type: bool
    domain: [true, false]

constraints:
  structural:
    - when: zero_shot = true
      then: retriever.k = 0
  derived:
    - require: env.context.gateway_baseline_latency_ms <= 250
    - require: env.context.provider_input_price_usd_per_1k_tokens <= 0.05

objectives:
  - name: quality
    metric_ref: metrics.quality.v1
    direction: maximize
  - name: latency_p95_ms
    metric_ref: metrics.latency_p95_ms.v1
    direction: minimize

promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  min_effect:
    quality: 0.01
    latency_p95_ms: 50
  chance_constraints:
    - name: latency_slo
      threshold: 0.05
      confidence: 0.95
```

TVL also supports:

*   **Callable domains** such as `callable[RerankerProto]` with registry-backed lookup
*   **Banded objectives** using `TOST` for targets like acceptable response-length ranges
*   **Multiple-testing adjustment** with `none`, `bonferroni`, `holm`, or `BH`
*   **Overlay composition** and separate validation of config/measurement artifacts

When present, `metric_ref` is a stable declarative ID such as `metrics.latency_p95_ms.v1`. The evaluation harness resolves that ID to the concrete metric implementation.

Callable and registry-backed domains are supported by the current tooling, but they are linted as outside the formally verified subset.

## What a formal agent specification enables

TVL is the specification layer. It defines **what** may vary, **what** must hold, and **what** counts as improvement. That enables a full tooling stack on top.

### Tool-independent candidate search

<figure markdown>
  ![TVL Optimization Demo](assets/demos/optimization.svg){ loading=lazy }
  <figcaption>Any compatible optimizer can search the same declared agent design space.</figcaption>
</figure>

### Spec Validation

<figure markdown>
  ![TVL Validation Demo](assets/demos/validate.svg){ loading=lazy }
  <figcaption>Validate schema, types, policy fields, and operational assumptions before rollout.</figcaption>
</figure>

### Constraint Satisfiability

<figure markdown>
  ![TVL Constraints Demo](assets/demos/constraints.svg){ loading=lazy }
  <figcaption>Check structural feasibility with SAT/SMT tooling before any expensive evaluation run begins.</figcaption>
</figure>

!!! note "TVL is the stable contract boundary"
    TVL sits between authoring front-ends, validation tooling, optimizer/runtime layers, evaluation systems, and certification workflows. The contract remains reviewable when any of those implementations changes.

## Get Started

Install the published package:

```bash
python -m pip install tvl-spec
```

Or install the SDK and CLI tools from this repository in editable mode:

```bash
python -m pip install -e tvl/[dev]
```

Validate one of the shipped examples end to end:

```bash
tvl-parse spec/examples/rag-support-bot.tvl.yml
tvl-lint spec/examples/rag-support-bot.tvl.yml
tvl-validate spec/examples/rag-support-bot.tvl.yml
tvl-check-structural spec/examples/rag-support-bot.tvl.yml --json
tvl-check-operational spec/examples/rag-support-bot.tvl.yml --json
```

---

<div class="grid cards" markdown>

-   :material-book-open-variant: **[Getting Started Guide](getting-started.md)**

    Write a first valid module and run the core CLI checks.

-   :material-certificate: **[AI Agent Requirements and Certification](agent-requirements.md)**

    Understand the problem TVL solves, its agent-space model, and the scope of a TVL-based conformance claim.

-   :material-file-document: **[Language Reference](reference/language.md)**

    Review the current TVL surface, including types, constraints, objectives, and promotion policy.

-   :material-code-braces: **[Example Walkthroughs](examples/walkthroughs.md)**

    Follow the canonical examples for RAG bots, routers, tool-use agents, validation fixtures, and overlays.

-   :material-text-box-search: **[Specification PDF](tvl_specification.pdf)**

    Download the current packaged TVL specification artifact.

-   :material-github: **[Examples on GitHub](https://github.com/Traigent/tvl/tree/main/spec/examples)**

    Open the exact source files used by this site.

</div>

---

!!! info "Created by Traigent"
    TVL is developed by [Traigent](https://traigent.com). The current design and terminology on this site are aligned with the TVL schema, shipped examples, formal spec artifacts, and the latest Traigent research and publication materials in this repository.
