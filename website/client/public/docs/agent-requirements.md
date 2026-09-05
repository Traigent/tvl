# AI Agent Requirements and Certification

## Why AI agents need a specification layer

An AI agent is rarely defined by one prompt or one model. Its behavior depends on a connected set of choices: models, prompts, tools, permissions, retrieval, memory, routing, stopping conditions, retry policy, and orchestration. Teams also care about properties that are not implementation components, such as task success, cost, latency, refusal behavior, policy compliance, and reliability.

Today these decisions are commonly split across code, configuration, evaluation notebooks, dashboards, and release procedures. The result is an under-specified system: reviewers can see how one candidate was built, but cannot reliably recover the full set of allowed designs or the conditions that make a candidate acceptable.

TVL provides that missing contract.

## TVL specifies a space of agents

A TVL module describes a set of admissible agent configurations:

\[
\mathcal{A}_{M} = \{a \mid a \text{ is in the declared domains and satisfies the declared constraints}\}
\]

The module then states the properties to measure and the evidence needed to accept one member of that set. It does not prescribe a sequence of implementation steps and it does not require a particular search algorithm.

This distinction matters:

- A build recipe says how to construct one agent.
- A TVL module says which agents are allowed and what qualifies one for the intended use.

An optimizer may search the space, a human may choose a configuration, or a CI system may check a submitted candidate. The requirements remain the same.

## The four parts of a verifiable claim

TVL connects four separately versioned elements:

| Element | Role in a TVL-based claim |
| --- | --- |
| **Agent** | The candidate configuration or implementation binding being evaluated |
| **Evaluation set** | The pinned tasks, cases, or dataset slice on which evidence is collected |
| **Evaluator** | The named metrics, judges, checks, and aggregation rules that interpret outcomes |
| **Governed process** | The recorded procedure that binds the specification, candidate, evaluator, evidence, and decision |

A certificate that omits one of these elements is ambiguous. For example, a score without a pinned evaluation set cannot establish what was tested; a result without an evaluator definition cannot establish what the score means.

## What TVL can certify

A TVL-based certification can support a bounded conformance statement:

> Candidate C satisfied the requirements in TVL module M, using evaluator E on evaluation set D, under recorded process P.

The certificate should identify immutable versions or hashes for those artifacts and include, or point to, the decision evidence.

This is a scoped statement. It does not establish that the agent is safe in every context, correct for every input, or superior under conditions that were not evaluated. Broader claims require broader requirements and evidence.

TVL also separates two kinds of claims:

1. **Process conformance** — the required artifacts were pinned, the declared checks ran, and the decision followed the specified policy.
2. **Agent conformance** — the candidate met the declared behavioral and comparative requirements under that process.

Both are needed for a verifiable certification system. The language defines the requirements; a certification implementation must preserve the evidence chain.

### Current implementation status

The current repository supplies the language schema, validators, measurement format, and reference promotion decision. It does not yet define or issue a complete interoperable agent-certificate artifact that binds every element above. Until that profile exists and is covered by conformance cases, TVL should be described as the **specification foundation** for verifiable certification, rather than as a complete certification system.

## Public specification boundary

The TVL specification should make the following public and interoperable:

- syntax and types;
- variable domains and constraint meaning;
- evaluation-set and metric references;
- objective, acceptability, and promotion semantics;
- evidence inputs and decision outputs;
- error behavior and conformance cases; and
- the scope of any formal guarantee.

The language does not need to standardize:

- search or optimization algorithms;
- candidate scheduling and sample allocation;
- model-provider orchestration;
- internal solver encodings; or
- proprietary heuristics used to find promising candidates.

Those choices affect how an implementation finds or evaluates candidates. They do not change what a TVL module requires.

## Relationship to PAC results

Probably Approximately Correct results can be relevant to a particular optimizer or evaluation procedure. A PAC guarantee depends on a named algorithm, assumptions about the observations, a precise error definition, and a proof or cited theorem that applies to that setting.

TVL therefore treats PAC parameters or claims as implementation-specific evidence unless a future language profile defines their full semantics and conformance requirements. The core language does not promise that every conforming optimizer discovers an approximate Pareto set with a stated probability.

## Reading a TVL module

Ask these questions in order:

1. What agent decisions may vary?
2. Which combinations are forbidden or required?
3. Which operating context and evaluation set are pinned?
4. Which desired properties are measured?
5. What makes a candidate acceptable on its own?
6. What evidence is needed to prefer it over the incumbent?
7. Which exact claim may be made if every check passes?

The [Language Reference](reference/language.md) maps those questions to concrete TVL fields. The [Semantics and Verification Reference](reference/verification.md) explains which checks happen before and after evaluation.
