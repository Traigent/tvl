# tvl-ci-gate

Offline run of the TVL promotion gate: it reads the module and two measurement bundles and prints a decision. It does not deploy anything. It evaluates t-tests per objective (Welch, or paired when requested), TOST bands (TOST is two one-sided tests: a banded objective passes when the confidence interval for its mean lies strictly inside the target band), Clopper-Pearson bounds for chance constraints (an upper confidence bound on the violation rate), and a multiple-comparison adjustment (`adjust`: default Holm; `BH`, the Benjamini-Hochberg procedure, controls the false discovery rate within each adjusted family of tests (superiority, inferiority) only when those tests are independent or positively dependent, and it does not control the family-wise error rate).

```
tvl-ci-gate spec/examples/rag-support-bot.tvl.yml \
  spec/measurements/rag-support-bot.incumbent.measure.yml \
  spec/measurements/rag-support-bot.candidate.measure.yml --json
```

Input:

- Canonical input bundles use `objective_values` with `samples` or summary statistics `mean`, `std` (sample standard
  deviation) and `n` (number of observations), and
  `chance_outcomes` with `violations` and `trials`.
- `--policy` is kept only as a deprecated fallback for standalone dry-runs.

Exit codes:

- Exit 0: the decision is `Promote`. This is the only exit 0.
- Exit 2: the decision is `Reject` or `NoDecision`, or the run could not give a decision (parse or schema failure, measurement bundles not promotion-ready, an undefined check, an unsupported construct)
