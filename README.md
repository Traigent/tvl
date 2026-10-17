# TVL — an AI agent requirements specification language

[![CI](https://github.com/Traigent/tvl/actions/workflows/ci.yml/badge.svg)](https://github.com/Traigent/tvl/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Traigent/tvl/actions/workflows/codeql.yml/badge.svg)](https://github.com/Traigent/tvl/actions/workflows/codeql.yml)
[![Lean proofs](https://github.com/Traigent/tvl/actions/workflows/lean-proofs.yml/badge.svg)](https://github.com/Traigent/tvl/actions/workflows/lean-proofs.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Spec: 1.2 · 1.3 draft](https://img.shields.io/badge/spec-1.2%20%C2%B7%201.3%20draft-informational.svg)](CHANGELOG.md)

**Tuned Variables Language (TVL)** is a typed, machine-checkable language for specifying what an AI agent must achieve, what parts of its design may vary, and what evidence is required before a candidate may be accepted.

AI agent requirements are often scattered across prompts, configuration files, evaluation scripts, dashboards, and release checklists. That makes it hard to answer basic questions: Which agent designs are allowed? Which properties are required? Which evaluation set and metrics define success? What evidence supports a release or certification claim?

TVL puts those requirements in one reviewable specification. It describes an **agent design space**, rather than prescribing the code or optimization algorithm used to build one agent.

## A 30-second example

Save this as `support-bot.tvl.yml`. It declares two allowed agent choices, one rule relating them, one objective, and the promotion policy:

```yaml
tvl:
  module: example.support_bot
tvl_version: "1.2"

environment:
  snapshot_id: "2026-01-01T00:00:00Z"

evaluation_set:
  dataset: "test://support-bot"

tvars:
  - name: model
    type: enum[str]
    domain: ["small", "large"]
  - name: max_tool_calls
    type: int
    domain:
      range: [0, 5]

constraints:
  structural:
    - when: model = 'small'
      then: max_tool_calls <= 3

objectives:
  - name: resolution_rate
    metric_ref: metrics.resolution_rate.v1
    direction: maximize

promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  min_effect:
    resolution_rate: 0.01
```

From a clone of this repository (see [Quick start](#quick-start) to install), check it:

```bash
tvl-validate support-bot.tvl.yml   # prints: Schema + lint checks passed.
tvl-lint support-bot.tvl.yml       # prints: Lint checks passed.
```

## The problem TVL solves

A TVL module connects four things that otherwise drift apart:

1. **Agent design space** — typed variables for allowed models, prompts, tools, retrieval, routing, memory, orchestration, and other agent choices.
2. **Required properties** — structural rules, operating assumptions, objectives, acceptable ranges, and behavioral constraints.
3. **Evaluation contract** — the evaluation set and metric identifiers used to produce comparable evidence.
4. **Acceptance policy** — the evidence and statistical conditions required to accept or promote a candidate.

This gives developers, evaluators, CI systems, and certification workflows a shared contract for AI agent verification.

## What makes TVL different

TVL specifies the set of acceptable agents. It does not specify the construction procedure for a particular agent.

```text
TVL module
  ├── allowed agent choices
  ├── relationships between those choices
  ├── required measured properties
  ├── pinned evaluation context
  └── acceptance and promotion criteria
          ↓
    validators, optimizers, evaluators, CI gates, or certifiers
```

Any compatible tool may search the declared space. The TVL contract stays stable when the optimizer, model provider, agent framework, or implementation changes.

## Verification and certification scope

TVL can be the specification layer for a verifiable certificate. A defensible claim is scoped to:

- a versioned TVL module;
- a candidate configuration or implementation binding;
- a pinned evaluation set and environment context;
- named evaluator and metric definitions;
- evidence produced by a governed process; and
- the acceptance checks that actually ran.

Passing a TVL gate means that the candidate met the declared requirements under that pinned contract and evidence. It does not by itself prove universal safety, correctness, or performance outside that scope. See [AI Agent Requirements and Certification](docs/agent-requirements.md).

## TVL 1.3 (draft): requirements in production

TVL 1.3 is a draft, conservative extension of TVL 1.2: a module without the new blocks means exactly what it meant before. It adds three optional blocks: `requirements` (what must keep holding once the agent runs, such as "at most 5% of traces take longer than 2 s" or "the agent never calls a forbidden tool"), `monitors` (which evidence checks a requirement, before release or in production, and with what statistics) and `responses` (what should happen when a monitor reports a breach, from a notification to a human-approved suspend). A separate `tvl_pack` document carries organisation floors that modules can only tighten.

TVL states what these declarations mean and what each verdict promises; its tools validate, compose and compile them, and `tvl-ci-gate` decides promotion monitors from fully resolved evaluation-set counts. Evaluating runtime evidence and carrying out responses is outside the language ([RFC 0003 §3.5](formalization/rfc-0003-runtime-requirements-monitors-responses.md)).

- Guide: [Requirements, Monitors and Responses](docs/guides/requirements-monitors-responses.md)
- Book: [Chapter 6 · Requirements in Production](tvl_book/website_content/book/chapter-06-requirements-in-production.md)
- Specification: [RFC 0003](formalization/rfc-0003-runtime-requirements-monitors-responses.md) (DRAFT) and [formal semantics §12](formalization/tvl-formal-semantics.md)
- Examples: [`spec/examples/runtime-1.3/`](spec/examples/runtime-1.3/)

## Quick start

Install the Python package and CLI tools from the repository root:

```bash
git clone https://github.com/Traigent/tvl.git
cd tvl
python -m pip install -e ".[dev]"
```

Validate a shipped AI agent specification:

```bash
tvl-validate spec/examples/rag-support-bot.tvl.yml
tvl-check-structural spec/examples/rag-support-bot.tvl.yml
tvl-check-operational spec/examples/rag-support-bot.tvl.yml
```

## Language version

The current language version is **TVL 1.2**. TVL 1.1 added calibrated variables (`cvars`), operational `policies`, and the strict `promotion_policy.require_calibration` mode ([RFC 0001](formalization/rfc-0001-knob-bindings-cvars-policies.md)); TVL 1.2 added `composites` ([RFC 0002](formalization/rfc-0002-composite-knobs.md)). Both are conservative extensions: a module that uses none of these constructs (nor TVAR ownership `scope`, also added in 1.1) is also a valid 1.0 module. The user guides focus on the core constructs; every diagnostic the validators emit, including those for the 1.1 and 1.2 constructs, is listed in the [error code catalog](docs/reference/error-codes.md). See the [changelog](CHANGELOG.md) for details.

## Repository map

- `spec/` — normative grammar, schemas, examples, and promotion contracts
- `docs/` — problem statement, language reference, verification model, and guides
- `formalization/` — formal semantics, with normative and informative sections identified
- `python/` and `tvl_tools/` — reference validators, SDK, and CLI tools
- `tests/` and `conformance/` — executable validation and compatibility cases
- `vscode-tvl/` and `editor_shared/` — editor support
- `website/` — source for [tvl-lang.org](https://tvl-lang.org)
- `proofs/` — Lean mechanization for selected results (pre-RFC-0001/0002 core subset; `cvars`/`policies`/`composites` are not yet formalized, see `proofs/PROOF_SUMMARY.md`'s coverage note; the draft TVL 1.3 language results are listed in its *Runtime (TVL 1.3)* section)

## Start here

1. [AI Agent Requirements and Certification](docs/agent-requirements.md)
2. [Getting Started](docs/getting-started.md)
3. [Language Reference](docs/reference/language.md)
4. [Semantics and Verification Reference](docs/reference/verification.md)
5. [Agent Evaluation and Promotion Evidence](docs/guides/statistical-validation-guide.md)
6. [Requirements, Monitors and Responses (TVL 1.3 draft)](docs/guides/requirements-monitors-responses.md)
7. [Complete examples](spec/examples/)

## Specification boundary

TVL standardizes what a conforming module means and what a verifier must check. It does not standardize search algorithms, optimizer architecture, scheduling, sample allocation, or internal solver representation. Those mechanisms may be documented by individual implementations without becoming part of the language contract. Likewise, for TVL 1.3 the language defines what a runtime requirement means and what each verdict promises; how an evaluator decides from runtime evidence and how a platform executes responses are not part of the language contract.

## License

- Code, schemas, validators, CLI tools, editor support, tests, executable examples, and the website application are licensed under Apache-2.0 in [LICENSE](LICENSE), unless a subdirectory provides its own license file.
- Authored documentation, formalization notes, and learning content are licensed under CC-BY-4.0 as described in [LICENSE-content](LICENSE-content).

## Community

- [Contributing](CONTRIBUTING.md) · [RFC process](formalization/README.md) · [Governance](GOVERNANCE.md) · [Maintainers](MAINTAINERS.md)
- [Code of Conduct](CODE_OF_CONDUCT.md) · [Security policy](SECURITY.md) · [Support](SUPPORT.md)

## Links

- Website: <https://tvl-lang.org>
- Documentation: <https://tvl-lang.org/specification>
- Discussions: <https://github.com/Traigent/tvl/discussions>
- Issues: <https://github.com/Traigent/tvl/issues>
