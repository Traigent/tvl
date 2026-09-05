# Agent Evaluation and Promotion Evidence

This guide explains the evidence contract used to decide whether an AI agent candidate meets a TVL specification. It describes what the evidence and decision mean. It does not prescribe how an optimizer searches the declared agent design space.

## The separation TVL preserves

Three activities are related but distinct:

| Activity | Question | TVL's role |
| --- | --- | --- |
| Candidate construction | How do we find or build a candidate? | Outside the language contract |
| Evaluation | What happened when this candidate ran on the pinned evaluation set? | Names the evaluation context, metrics, and required observations |
| Acceptance or promotion | Does the evidence satisfy the declared requirements? | Defines the decision rule and its inputs |

Search algorithms, adaptive sampling, Bayesian optimization, successive halving, and scheduling are implementation choices. A tool may use any of them, or no optimizer at all, while consuming the same TVL module.

## Evidence must be bound to the specification

A promotion decision is meaningful only when the evidence identifies the contract it evaluates. A measurement bundle should bind at least:

- the TVL module identifier and version or digest;
- the candidate configuration or implementation binding;
- the evaluation-set version or digest;
- the environment snapshot;
- the evaluator and metric versions;
- observation counts and measured values; and
- provenance needed to reproduce or audit the decision.

The current command-line contract is documented in [Promotion Gate I/O](../../spec/promotion-gate-io.md). The reference CLI validates measured evidence separately from structural and operational checks.

## Desired properties in TVL

TVL distinguishes three kinds of requirement:

1. **Directional objectives** express properties to maximize or minimize, such as task success, groundedness, cost, or latency.
2. **Banded objectives** express an acceptable interval, such as a response length or tool-call count that should stay within a range.
3. **Chance constraints** express an upper limit on the rate of an undesirable event, such as policy violations or latency-SLO breaches.

These fields specify what a candidate must demonstrate. The evaluator implementation determines how observations are produced and must be identified in the evidence.

## Candidate versus incumbent

For a directional objective, TVL normalizes direction so that a positive difference always means the candidate is better:

```text
normalized difference = direction sign × (candidate mean - incumbent mean)
```

The promotion policy then asks two different questions:

- **Non-inferiority**: is there enough evidence that the candidate is not worse than the allowed regression margin?
- **Superiority**: is there enough evidence that it improves at least one objective by more than the declared minimum effect?

Failure to establish non-inferiority is not automatically evidence of inferiority. When the data are insufficient to establish either conclusion, the correct result is `NoDecision`.

## Decision meanings

The reference decision vocabulary is:

| Decision | Meaning |
| --- | --- |
| `Promote` | The candidate passed every required acceptability check, established non-inferiority on all directional objectives, and established a required improvement. |
| `Reject` | The evidence established a hard failure, such as a breached chance constraint, an observed point estimate outside a hard band, an invalid candidate, or demonstrated regression beyond the allowed margin. |
| `NoDecision` | The available evidence was insufficient to justify either promotion or rejection. |
| `Error` | The inputs were invalid, inconsistent, unbound, or could not support the declared checks. |

A production or certification workflow should preserve this distinction. Treating missing evidence as demonstrated failure misstates the result; treating it as success is unsafe.

## Chance constraints

TVL chance constraints are expressed as limits on a **violation rate**. For observed violations `k` in `n` trials and a declared threshold `θ`, the candidate passes only when the one-sided upper confidence bound on the true violation rate is at or below `θ`:

```text
ChancePass(k, n, θ, γ) iff CI_upper(k, n, γ) ≤ θ
```

No trials means no decision can be computed. The confidence value belongs to this bound and is separate from the significance level used for comparative objectives.

## Multiple objectives

TVL's current promotion contract uses an intersection-union rule for non-inferiority: every directional objective must pass. The configured multiple-testing adjustment applies separately to the superiority family used to establish that at least one objective improved and the inferiority family used to establish that at least one objective regressed.

The selected method changes the interpretation of the error control:

- `bonferroni` and `holm` control family-wise error for the adjusted family under their standard assumptions.
- `BH` controls false discovery rate under its stated dependence assumptions; it does not control the probability of any false discovery.
- `none` applies no family-level correction.

These statements concern the named statistical tests and their assumptions. They do not turn a TVL result into a universal guarantee about an agent.

## Minimum effect is a requirement, not a sample-size formula

`promotion_policy.min_effect` declares the smallest difference that counts as a meaningful improvement or allowable regression margin for each directional objective. It is part of the requirements contract.

TVL does not calculate a universal minimum sample size from that value. Sample-size planning also depends on variance, power, dependence, evaluator behavior, and the chosen test. An evaluation implementation should record its design and assumptions as process evidence.

## PAC theory and TVL

PAC multi-objective optimization is useful background for implementations that use a proven algorithm under matching assumptions. For example, ε-PAL provides guarantees for its particular Gaussian-process active-learning procedure and problem setting.

The TVL core specification makes no blanket PAC claim. A tool that advertises an `(ε, δ)` guarantee must identify:

1. the algorithm and theorem being invoked;
2. the observation and model assumptions;
3. the exact definition of approximation error;
4. how TVL fields map to the theorem's parameters; and
5. evidence that the implementation satisfies those conditions.

Without those elements, `epsilon` and `confidence` values are requirements or configuration data, not proof that a Pareto set was discovered with a particular probability.

## Certification interpretation

A successful decision supports a bounded statement about the evaluated candidate and contract. A certificate should report:

- what was specified;
- what candidate was evaluated;
- which evaluation set and evaluator produced the evidence;
- which checks ran and their results;
- which decision procedure was used; and
- any assumptions, exclusions, or unresolved checks.

This evidence chain lets an independent verifier reproduce the decision and prevents the claim from silently expanding beyond what was tested.

## References

- Zuluaga, Krause, and Püschel, [ε-PAL: An Active Learning Approach to the Multi-Objective Optimization Problem](https://www.jmlr.org/papers/v17/15-047.html), JMLR 2016. This is an algorithm-specific result, not a guarantee supplied by TVL itself.
- Cawley and Talbot, [On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation](https://jmlr.org/papers/v11/cawley10a.html), JMLR 2010. This motivates separating candidate selection from final evaluation.
- The [Promotion Gate I/O specification](../../spec/promotion-gate-io.md) defines the current executable decision contract.
