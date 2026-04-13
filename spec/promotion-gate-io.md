# Promotion Gate I/O Specification

**Version**: 1.0
**Status**: Stable
**Date**: January 2026

This document specifies the input/output format for the TVL promotion gate, the statistical testing procedures, and the decision logic.

---

## 1. Input: Measurement Bundle Schema

The promotion gate accepts a measurement bundle containing objective values and chance constraint outcomes for both the incumbent and candidate configurations.

Canonical CLI:

```bash
tvl-ci-gate <module> <incumbent-bundle> <candidate-bundle> --json
```

The module is the source of `objectives` and `promotion_policy`.

### 1.1 Objective Values

Objective values can be provided in two forms:

**Raw Sample Form** (preferred when available):

```yaml
objective_values:
  latency_p95_ms:
    samples: [142, 151, 138, 145, 139, 148, 144, 141, 147, 143]
    paired: false  # Optional: true if samples are paired with incumbent
```

**Aggregated Statistics Form** (when raw samples not available):

```yaml
objective_values:
  accuracy:
    mean: 0.91
    std: 0.04
    n: 50
```

Pre-computed objective summaries are not part of the canonical CLI contract.
`tvl-ci-gate` requires raw samples or aggregated `mean/std/n`.

### 1.2 Chance Constraint Outcomes

```yaml
chance_outcomes:
  toxicity_rate:
    violations: 2
    trials: 100
```

### 1.3 Complete Input Structure

```yaml
incumbent:
  objective_values:
    latency_p95_ms:
      samples: [142, 151, 138, 145, 139, 148, 144, 141, 147, 143]
    accuracy:
      mean: 0.87
      std: 0.03
      n: 50
  chance_outcomes:
    toxicity_rate:
      violations: 4
      trials: 100

candidate:
  objective_values:
    latency_p95_ms:
      samples: [131, 128, 142, 135, 129, 138, 134, 131, 137, 133]
    accuracy:
      mean: 0.91
      std: 0.04
      n: 50
  chance_outcomes:
    toxicity_rate:
      violations: 2
      trials: 100

# From module's promotion_policy
policy:
  alpha: 0.05
  min_effect:
    latency_p95_ms: 10    # ε for this objective (units: ms)
    accuracy: 0.02        # ε for this objective (units: fraction)
  adjust: "holm"          # "none" | "bonferroni" | "holm" | "BH" (default: "holm")
  chance_constraints:
    - name: toxicity_rate
      threshold: 0.05     # Allowed violation rate
      confidence: 0.99    # Confidence level for the bound

# From module's objectives (for banded objectives)
objectives:
  - name: latency_p95_ms
    metric_ref: metrics.latency_p95_ms.v1
    direction: minimize
  - name: accuracy
    metric_ref: metrics.accuracy.v1
    direction: maximize
  - name: response_length
    metric_ref: metrics.response_length.v1
    band:
      target: [95, 105]   # Or: { center: 100, tol: 5 }
      test: TOST
      alpha: 0.05
```

`metric_ref` is optional metadata from the module. The promotion gate still keys evidence by objective name; the
runtime may use `metric_ref` upstream to resolve how each objective was computed.

---

## 2. Output: Decision + Evidence Bundle

```yaml
decision: "Reject"   # "Promote" | "Reject" | "NoDecision"

evidence:
  per_objective:
    latency_p95_ms:
      test_type: "welch"           # "welch" | "paired" | "student"
      n_incumbent: 10
      n_candidate: 10
      mean_incumbent: 143.8
      mean_candidate: 133.8
      delta: -10.0                 # candidate - incumbent (negative is better for minimize)
      std_pooled: 5.2
      t_statistic: -4.31
      df: 17.8                     # Degrees of freedom (Welch-Satterthwaite)
      p_value_noninf: 0.0002       # H₀: candidate worse by > ε
      p_value_super: 0.021         # H₀: candidate not better by > ε
      adjusted_p_noninf: null      # Non-inferiority is unadjusted (IUT)
      adjusted_p_super: 0.032      # After multiplicity adjustment (union component)
      epsilon: 10
      verdict: "superior"          # "superior" | "noninferior" | "inferior" | "inconclusive"

    accuracy:
      test_type: "welch"
      n_incumbent: 50
      n_candidate: 50
      mean_incumbent: 0.87
      mean_candidate: 0.91
      delta: 0.04
      std_pooled: 0.035
      t_statistic: 5.71
      df: 97.2
      p_value_noninf: 0.0001
      p_value_super: 0.15          # Not significant for superiority
      adjusted_p_noninf: null
      adjusted_p_super: 0.1500
      epsilon: 0.02
      verdict: "noninferior"       # Passes non-inferiority but not superiority

    response_length:               # Banded objective
      test_type: "tost"
      n: 50
      mean: 99.2
      std: 4.1
      ci_lower: 98.0               # 90% CI lower (for α=0.05)
      ci_upper: 100.4              # 90% CI upper
      band_lower: 95
      band_upper: 105
      p_value_lower: 0.001         # H₀: μ ≤ 95
      p_value_upper: 0.0001        # H₀: μ ≥ 105
      verdict: "in_band"           # "in_band" | "out_of_band" | "inconclusive"

  chance_constraints:
    toxicity_rate:
      violations: 2
      trials: 100
      observed_rate: 0.02
      ci_lower: 0.0024             # Clopper-Pearson lower bound (reported for completeness)
      ci_upper: 0.0660             # One-sided upper bound at confidence γ
      threshold: 0.05
      confidence: 0.99
      verdict: "fail"              # "pass" | "fail"
      reason: "ci_upper (0.0660) > threshold (0.05)"

  summary:
    all_noninferior: true          # All objectives pass non-inferiority
    any_superior: true             # At least one objective is superior
    all_bands_pass: true           # All banded objectives pass TOST
    all_chance_pass: false         # Chance constraint failed (ci_upper > threshold)
    adjustment_method: "holm"
    fdr_controlled_at: null        # Set only when adjust="BH"
    decision_reason: "Chance constraints failed: toxicity_rate"
```

---

## 3. Statistical Test Procedures

### 3.1 Test Type Decision Tree

```
Are samples provided for both incumbent and candidate?
├── NO (aggregated stats only)
│   └── Use Welch's t-test over mean/std/n
│
└── YES (raw samples available)
    └── Are samples paired (same evaluation instances)?
        ├── YES: Use paired t-test
        │   └── Test: t = mean(diff) / (std(diff) / sqrt(n))
        │   └── df = n - 1
        │
        └── NO or UNKNOWN: Use Welch's t-test (DEFAULT)
            └── Welch is safer; handles unequal variances
            └── df = Welch-Satterthwaite approximation
```

**Default**: Use Welch's t-test unless `paired: true` is explicitly specified.

### 3.2 Non-Inferiority Test

For each objective i with direction σᵢ (1 for maximize, -1 for minimize) and epsilon εᵢ:

**Null hypothesis**: H₀: σᵢ × (μ_candidate - μ_incumbent) ≤ -εᵢ
(Candidate is worse than incumbent by more than ε)

**Alternative**: H₁: σᵢ × (μ_candidate - μ_incumbent) ≥ -εᵢ
(Candidate is not worse than incumbent by more than ε)

**Test statistic** (Welch):

```
t = (x̄_candidate - x̄_incumbent - (-σᵢ × εᵢ)) / SE_pooled

where SE_pooled = sqrt(s²_inc/n_inc + s²_cand/n_cand)
```

**P-value**: One-sided, `p = P(T > t)` where T ~ t(df)

### 3.3 Superiority Test

**Null hypothesis**: H₀: σᵢ × (μ_candidate - μ_incumbent) ≤ εᵢ
(Candidate is not better than incumbent by more than ε)

**Alternative**: H₁: σᵢ × (μ_candidate - μ_incumbent) > εᵢ
(Candidate is better than incumbent by more than ε)

**Test statistic**:

```
t = (x̄_candidate - x̄_incumbent - (σᵢ × εᵢ)) / SE_pooled
```

**P-value**: One-sided, `p = P(T > t)`

### 3.4 TOST for Banded Objectives

For banded objective with target [L, U] and significance α:

**Important**: TOST uses **(1 - 2α) confidence interval**, not (1 - α).

For α = 0.05, use **90% CI** (not 95% CI).

**Test 1**: H₀₁: μ ≤ L
**Test 2**: H₀₂: μ ≥ U

```
t₁ = (x̄ - L) / SE
t₂ = (U - x̄) / SE

p₁ = P(T > t₁)  # One-sided
p₂ = P(T > t₂)  # One-sided
```

**Pass condition**: max(p₁, p₂) < α

**Equivalently**: (1 - 2α) CI for μ lies entirely within [L, U]

### 3.5 Clopper-Pearson for Chance Constraints

For threshold θ and confidence γ with observed k violations in n trials:

**Compute exact binomial confidence interval**:

```python
from scipy.stats import beta

alpha_tail = 1 - γ

# One-sided lower bound (reported for completeness)
ci_lower = beta.ppf(alpha_tail, k, n - k + 1) if k > 0 else 0.0

# One-sided upper bound at confidence level γ
ci_upper = beta.ppf(1 - alpha_tail, k + 1, n - k) if k < n else 1.0
```

**Pass condition**: ci_upper ≤ θ

**Note**: This is one-sided; we only care that the true violation rate is BELOW the threshold.

---

## 4. Multiple Testing Adjustment

### 4.1 Scope of Adjustment

**Adjusted family**: Per-objective superiority p-values only (union component).

**NOT included**:

- Non-inferiority p-values (IUT; no multiplicity correction required)
- Chance constraint p-values (separate confidence budget)
- TOST p-values for banded objectives (treated separately)

### 4.2 Supported Methods

Given k superiority p-values p₁, p₂, ..., pₖ:

- `none`: no correction
- `bonferroni`: adjusted pᵢ = min(1, k · pᵢ)
- `holm`: step-down adjusted p-values (FWER control, no dependence assumptions)
- `BH`: Benjamini-Hochberg step-up (FDR control under independence/PRDS)

### 4.3 Reporting and Decision Use

For reporting, expose:

- `adjusted_p_super`: adjusted superiority p-value
- `adjusted_p_noninf`: null (non-inferiority remains unadjusted)

Decision logic uses:
- non-inferiority: raw `p_value_noninf`
- superiority: `adjusted_p_super` when adjustment is enabled, otherwise raw `p_value_super`

---

## 5. Decision Logic

### 5.1 Promote Decision

Return `"Promote"` if ALL of the following are true:

1. All non-inferiority tests pass (raw `p_value_noninf < α` for all objectives)
2. At least one superiority test passes after selected adjustment (`p_super_test < α` for at least one objective)
3. All banded objectives pass TOST
4. All chance constraints pass

### 5.2 Reject Decision

Return `"Reject"` if ANY of the following are true:

1. Any non-inferiority test fails (candidate is significantly worse)
2. Any chance constraint fails
3. Any banded objective fails TOST

### 5.3 NoDecision

Return `"NoDecision"` otherwise (insufficient evidence to promote or reject).

---

## 6. Complete Test Matrix

| Scenario | Configuration | Test | Expected Decision |
|----------|--------------|------|-------------------|
| Clear dominance | Candidate better on all objectives by > 2ε | Welch per obj | Promote |
| Clear inferiority | Candidate worse on all objectives by > 2ε | Welch per obj | Reject |
| Mixed results | Candidate better on obj1, worse on obj2 | Welch per obj | Reject (inferiority on obj2) |
| Within noise | All deltas < ε, high variance | Welch per obj | NoDecision |
| Superior on one | Better on obj1 by > ε, equal on others | Welch per obj | Promote |
| BH correction | 10 objectives, 2 superiority p-values raw < 0.05 but adjusted > 0.05 | BH | NoDecision |
| TOST pass | Mean = 100, band = [95, 105], n = 50, σ = 5 | TOST (90% CI) | Promote (if other tests pass) |
| TOST fail (power) | Mean = 100, band = [95, 105], n = 5, σ = 5 | TOST (90% CI) | NoDecision |
| TOST fail (OOB) | Mean = 110, band = [95, 105] | TOST (90% CI) | Reject |
| Chance pass | 0/120 violations, θ = 0.03, γ = 0.95 | Clopper-Pearson | (contributes to Promote) |
| Chance fail | 8/100 violations, θ = 0.05, γ = 0.95 | Clopper-Pearson | Reject |
| Paired samples | Same eval set for both configs | Paired t-test | (uses paired test) |

---

## 7. Implementation Notes

### 7.1 Dependencies

- `scipy.stats`: For t-distribution, beta distribution
- `numpy`: For numerical operations

### 7.2 Edge Cases

- **Empty samples**: Return error, cannot compute test
- **Single sample**: Use appropriate handling (large variance estimate)
- **All objectives identical**: NoDecision (no superiority)
- **No objectives defined**: Error

### 7.3 Numerical Stability

- Handle division by zero in SE calculation
- Clip p-values to [1e-300, 1.0] range
- Use log-space for very small p-values if needed

---

## 8. Error Codes

| Code | Description |
|------|-------------|
| `missing_samples` | Neither samples nor aggregated stats provided |
| `insufficient_samples` | Fewer than 2 samples for t-test |
| `missing_policy` | No promotion_policy in module |
| `missing_epsilon` | No min_effect for standard objective |
| `invalid_direction` | Unknown objective direction |
| `missing_band_target` | Banded objective without target |
