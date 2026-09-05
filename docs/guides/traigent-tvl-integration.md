# Integrating an Optimizer or Agent Platform with TVL

TVL is the requirements boundary between an AI agent specification and the tools that construct, evaluate, or approve candidates. This guide describes the interoperability contract. It does not define Traigent's optimizer architecture or proprietary search methods.

## Responsibilities

| TVL module | Integrating tool |
| --- | --- |
| Declares allowed agent variables and domains | Maps declarations to executable agent configuration |
| Declares constraints between choices | Generates or accepts only admissible candidates |
| Identifies evaluation set and metrics | Resolves identifiers to versioned evaluation implementations |
| Declares desired properties and acceptance policy | Runs evaluations and emits the required evidence |
| Defines promotion semantics | Preserves the resulting decision and provenance |

## Integration flow

1. Load and validate the TVL module.
2. Resolve the declared variable domains against the target agent implementation.
3. Produce a candidate by any method: manual selection, enumeration, an optimizer, or an external agent platform.
4. Validate the candidate configuration against the module.
5. Run the pinned evaluation set with the named evaluator and metric versions.
6. Produce canonical measurement bundles for the incumbent and candidate.
7. Apply the TVL acceptance and promotion policy.
8. Store the module, candidate, evaluator identifiers, evidence, and decision together.

## Required invariants

An integration should fail closed when:

- a candidate contains an undeclared value or violates a structural constraint;
- a module, candidate, or measurement bundle targets a different module identity;
- an evaluation-set, environment, or metric binding required by the contract cannot be resolved;
- required evidence is absent or statistically inconclusive;
- a chance or band requirement fails; or
- a strict certification requirement cannot be verified.

Inconclusive evidence should produce `NoDecision`, not a claim of failure or success.

## Search remains replaceable

TVL does not require grid search, evolutionary search, Bayesian optimization, successive halving, or any other candidate-selection method. An implementation may expose these features, but their settings and guarantees belong to that implementation or to a separately named profile.

An algorithm-specific guarantee must state its assumptions and theorem. Merely accepting TVL fields such as `min_effect`, an exploration budget, or a confidence value does not establish a PAC or sample-efficiency guarantee.

## Evidence output

Use the canonical formats described by:

- [Promotion Evidence Contract](../../spec/promotion-evidence-contract.md)
- [Promotion Gate I/O](../../spec/promotion-gate-io.md)
- [Agent Evaluation and Promotion Evidence](statistical-validation-guide.md)

For a certification workflow, also pin the exact TVL module, candidate configuration or implementation binding, evaluation set, evaluator definitions, environment context, and governed decision process. See [AI Agent Requirements and Certification](../agent-requirements.md).
