# TVL — an AI agent requirements specification language

**Tuned Variables Language (TVL)** is a typed, machine-checkable language for specifying what an AI agent must achieve, what parts of its design may vary, and what evidence is required before a candidate may be accepted.

AI agent requirements are often scattered across prompts, configuration files, evaluation scripts, dashboards, and release checklists. That makes it hard to answer basic questions: Which agent designs are allowed? Which properties are required? Which evaluation set and metrics define success? What evidence supports a release or certification claim?

TVL puts those requirements in one reviewable specification. It describes an **agent design space**, rather than prescribing the code or optimization algorithm used to build one agent.

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

## Quick start

Install the Python package and CLI tools from the repository root:

```bash
python -m pip install -e ".[dev]"
```

Validate a shipped AI agent specification:

```bash
tvl-validate spec/examples/rag-support-bot.tvl.yml
tvl-check-structural spec/examples/rag-support-bot.tvl.yml
tvl-check-operational spec/examples/rag-support-bot.tvl.yml
```

## Repository map

- `spec/` — normative grammar, schemas, examples, and promotion contracts
- `docs/` — problem statement, language reference, verification model, and guides
- `formalization/` — formal semantics, with normative and informative sections identified
- `python/` and `tvl_tools/` — reference validators, SDK, and CLI tools
- `tests/` and `conformance/` — executable validation and compatibility cases
- `vscode-tvl/` and `editor_shared/` — editor support
- `website/` — source for [tvl-lang.org](https://tvl-lang.org)
- `proofs/` — Lean mechanization for selected results

## Start here

1. [AI Agent Requirements and Certification](docs/agent-requirements.md)
2. [Getting Started](docs/getting-started.md)
3. [Language Reference](docs/reference/language.md)
4. [Semantics and Verification Reference](docs/reference/verification.md)
5. [Agent Evaluation and Promotion Evidence](docs/guides/statistical-validation-guide.md)
6. [Complete examples](spec/examples/)

## Specification boundary

TVL standardizes what a conforming module means and what a verifier must check. It does not standardize search algorithms, optimizer architecture, scheduling, sample allocation, or internal solver representation. Those mechanisms may be documented by individual implementations without becoming part of the language contract.

## License

- Code, schemas, validators, CLI tools, editor support, tests, executable examples, and the website application are licensed under Apache-2.0 in [LICENSE](LICENSE), unless a subdirectory provides its own license file.
- Authored documentation, website/book learning content, formalization notes, figures, and the specification PDF are licensed under CC-BY-4.0 as described in [LICENSE-content](LICENSE-content).

## Links

- Website: <https://tvl-lang.org>
- Documentation: <https://tvl-lang.org/specification>
- Issues: <https://github.com/Traigent/tvl/issues>
