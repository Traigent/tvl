# Promotion Gate I/O Specification

**Version**: 1.1
**Status**: Draft
**Date**: September 2026

This document specifies the input/output format for the TVL promotion gate, the statistical testing procedures, and the decision logic.

Two abbreviations recur. **TOST** (two one-sided tests) checks that a mean lies inside a target band (§3.4). **CI** means confidence interval.

---

## 1. Input: Measurement Bundle Schema

The promotion gate accepts a measurement bundle containing objective values and chance constraint outcomes for both the incumbent and candidate configurations.

Canonical CLI:

```bash
tvl-ci-gate <module> <incumbent-bundle> <candidate-bundle> --json
```

The module is the source of `objectives` and `promotion_policy`.

Calibration certificates are not supported yet. A module is in a *strict evidence mode* when one of the triggers of [RFC 0001 §3.6](../formalization/rfc-0001-knob-bindings-cvars-policies.md#36-strict-promotion-fail-closed-semantics) holds; promotion then requires a valid certificate for every calibrated value. The current measurement-bundle format cannot carry these certificates.

Until a versioned certificate input and verifier are part of this contract, `tvl-ci-gate` MUST report `calibration_evidence_unsupported` and MUST NOT return `Promote` when the module:

- enables `promotion_policy.require_calibration`,
- declares any CVAR (a calibrated variable: a value fit from calibration evidence rather than searched, RFC 0001 §3.3), or
- declares a composite with a calibrated member (a gate threshold, accept threshold, stop threshold or cardinality bound to a CVAR; [RFC 0002 §3.6](../formalization/rfc-0002-composite-knobs.md#36-certificate-coverage-fold-extends-rfc-0001-36)).

A module with `chance_constraints` and none of these has nothing to certify and still gets a decision.

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

No other summary form is part of the canonical CLI contract. A summary with neither a non-empty `samples` list nor all three of
`mean`, `std` and `n` (for example, the deprecated top-level `objectives` map) is not accepted as promotion evidence:
`tvl-ci-gate` requires raw samples or the complete aggregated `mean/std/n`.

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
    response_length:
      mean: 101.0
      std: 3.0
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
    response_length:
      mean: 100.0
      std: 2.5
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
decision: "Reject"   # "Promote" | "Reject" | "NoDecision" | "Error"

evidence:
  per_objective:
    latency_p95_ms:
      test_type: "welch"           # "welch" | "paired" ("precomputed" only for library calls with pre-computed p-values)
      n_incumbent: 10
      n_candidate: 10
      mean_incumbent: 143.8
      mean_candidate: 133.8
      delta: -10.0                 # candidate - incumbent (negative is better for minimize)
      std_pooled: 4.21
      t_statistic: 10.62           # Non-inferiority statistic (σᵢ × delta + εᵢ) / SE
      df: 17.9                     # Degrees of freedom (Welch-Satterthwaite)
      p_value_noninf: 1.8e-09      # H₀: candidate worse by > ε
      p_value_super: 0.5           # H₀: candidate not better by > ε (the improvement equals ε exactly)
      p_value_inferior: 1.0        # H₀: candidate is within the allowed regression margin
      adjusted_p_noninf: null      # Non-inferiority is unadjusted (intersection-union test, §4.1)
      adjusted_p_super: 0.5        # After multiplicity adjustment (union component)
      adjusted_p_inferior: 1.0     # After multiplicity adjustment (union component)
      epsilon: 10
      verdict: "noninferior"       # "superior" | "noninferior" | "inferior" | "inconclusive"

    accuracy:
      test_type: "welch"
      n_incumbent: 50
      n_candidate: 50
      mean_incumbent: 0.87
      mean_candidate: 0.91
      delta: 0.04
      std_pooled: 0.035
      t_statistic: 8.49
      df: 90.9
      p_value_noninf: 1.9e-13
      p_value_super: 0.0029        # Significant for superiority
      p_value_inferior: 1.0        # No evidence of regression beyond ε
      adjusted_p_noninf: null
      adjusted_p_super: 0.0058     # Holm over [0.0029, 0.5]
      adjusted_p_inferior: 1.0
      epsilon: 0.02
      verdict: "superior"          # Passes non-inferiority and superiority

    response_length:               # Banded objective
      test_type: "tost"
      n: 50
      mean: 100.0
      std: 2.5
      ci_lower: 99.41              # 90% CI lower (for α=0.05)
      ci_upper: 100.59             # 90% CI upper
      band_lower: 95
      band_upper: 105
      p_value_lower: 1e-300        # H₀: μ ≤ 95 (clipped at 1e-300)
      p_value_upper: 1e-300        # H₀: μ ≥ 105 (clipped at 1e-300)
      verdict: "in_band"           # "in_band" | "out_of_band" | "inconclusive"

  chance_constraints:
    toxicity_rate:
      violations: 2
      trials: 100
      observed_rate: 0.02
      ci_lower: 0.0015             # Clopper-Pearson lower bound (reported for completeness)
      ci_upper: 0.0814             # One-sided upper bound at confidence γ
      threshold: 0.05
      confidence: 0.99
      verdict: "fail"              # "pass" | "fail" | "error" (undefined check, e.g. zero_trials)
      reason: "ci_upper (0.0814) > threshold (0.05)"

  summary:
    all_noninferior: true          # All objectives pass non-inferiority
    any_superior: true             # At least one objective is superior
    all_bands_pass: true           # All banded objectives pass TOST
    any_band_out_of_band: false    # No banded point estimate lies outside its declared band
    all_chance_pass: false         # Chance constraint failed (ci_upper > threshold)
    adjustment_method: "holm"
    fdr_controlled_at: null        # Set only when adjust="BH"
    decision_reason: "Chance constraints failed: toxicity_rate"
```

---

## 3. Statistical Test Procedures

### 3.1 Test Type Decision Tree

This tree is for standard (non-banded) objectives; banded objectives follow §3.4.

```
Does either arm have fewer than 2 observations (n < 2)?
├── YES: no variance estimate; the objective result is "inconclusive" (no test is run)
│
└── NO: Are samples provided for both incumbent and candidate?
    ├── NO (aggregated stats only)
    │   └── Use Welch's t-test over mean/std/n
    │
    └── YES (raw samples available)
        └── Is `paired: true` set AND do both sample lists have the same length?
            ├── YES: Use paired t-test on diff = candidate − incumbent (per instance)
            │   └── Non-inferiority: t = (σᵢ × mean(diff) + εᵢ) / (std(diff) / sqrt(n))
            │   └── Superiority:     t = (σᵢ × mean(diff) − εᵢ) / (std(diff) / sqrt(n))
            │   └── df = n - 1
            │
            └── NO: Use Welch's t-test (DEFAULT)
                └── Welch is safer; handles unequal variances
                └── df = Welch-Satterthwaite approximation
```

**Default**: Use Welch's t-test unless `paired: true` is set in the candidate's objective entry and the two sample lists have equal length.

### 3.2 Non-Inferiority Test

For each objective i with direction σᵢ (1 for maximize, -1 for minimize) and epsilon εᵢ:

**Null hypothesis**: H₀: σᵢ × (μ_candidate - μ_incumbent) ≤ -εᵢ
(Candidate is worse than incumbent by at least ε)

**Alternative**: H₁: σᵢ × (μ_candidate - μ_incumbent) > -εᵢ
(Candidate is worse than incumbent by less than ε, if at all)

**Test statistic** (Welch):

```
t = (σᵢ × (x̄_candidate - x̄_incumbent) + εᵢ) / SE_pooled

where SE_pooled = sqrt(s²_inc/n_inc + s²_cand/n_cand)
```

**P-value**: One-sided, `p = P(T > t)` where T ~ t(df)

Failure to reject this null is inconclusive. It does not establish that the candidate is inferior. A hard regression verdict uses the opposite one-sided test, `H₀: σᵢ × (μ_candidate - μ_incumbent) ≥ -εᵢ`, and rejects only when its p-value is below α: `adjusted_p_inferior < α` when a multiplicity adjustment is enabled (`adjust` is not `"none"`), otherwise `p_value_inferior < α`.

### 3.3 Superiority Test

**Null hypothesis**: H₀: σᵢ × (μ_candidate - μ_incumbent) ≤ εᵢ
(Candidate is not better than incumbent by more than ε)

**Alternative**: H₁: σᵢ × (μ_candidate - μ_incumbent) > εᵢ
(Candidate is better than incumbent by more than ε)

**Test statistic**:

```
t = (σᵢ × (x̄_candidate - x̄_incumbent) - εᵢ) / SE_pooled
```

**P-value**: One-sided, `p = P(T > t)`

### 3.4 TOST for Banded Objectives

TOST (two one-sided tests) shows that a mean lies inside a band: it runs one one-sided test
against each band edge and passes only when both reject (formal semantics §9.5).

For a band `[L, U]`, the candidate's statistics decide the result. They must be a finite mean, a whole-number `n` and, when `n ≥ 2`, a
finite non-negative `std`; anything else is `inconclusive`.

- **Point estimate outside the band** (`mean < L` or `mean > U`, with at least one observation): `out_of_band`, and the
  decision is `Reject` (§5.2), even when `n < 2`.
- **`n < 2` with the point estimate inside the band, or no observations**: no variance estimate, no test is run, and
  the result is `inconclusive`.
- **`std = 0`** (`n ≥ 2`): each test statistic is +∞ or −∞ by the sign of its numerator. A mean strictly inside
  `(L, U)` passes; a mean exactly on `L` or `U` gives `t = 0` for that edge, so the result is `inconclusive`.

For a banded objective with target [L, U] and significance level α:

**Important**: TOST uses a confidence interval with confidence level **1 − 2α**, rather than 1 − α.

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

**Equivalently**: the (1 - 2α) CI for μ lies strictly inside the open interval (L, U). A CI that touches a band
edge does not pass; with `std = 0` the CI is the single point `mean`, so a mean exactly on an edge does not pass.

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

**Precondition**: n ≥ 1. With n = 0, or no trial count, the check is undefined: the constraint gets verdict `"error"` with code `zero_trials`, and the gate returns the decision `"Error"` (§5.0).

**Note**: This is one-sided; we only care that the true violation rate is BELOW the threshold.

---

## 4. Multiple Testing Adjustment

### 4.1 Scope of Adjustment

**Adjusted families**: Per-objective superiority p-values and per-objective inferiority p-values. Each supports a union claim: at least one improvement, or at least one regression.

**NOT included**:

- Non-inferiority p-values. These form an intersection-union test (IUT): promotion needs every objective's
  non-inferiority test to pass at α, so no multiplicity correction is required
- Chance constraint p-values (separate confidence budget)
- TOST p-values for banded objectives (treated separately)

### 4.2 Supported Methods

For each adjusted family of k p-values p₁, p₂, ..., pₖ:

- `none`: no correction
- `bonferroni`: adjusted pᵢ = min(1, k · pᵢ)
- `holm`: step-down adjusted p-values (controls the family-wise error rate, FWER: the chance of
  at least one false claim in the family; no dependence assumptions)
- `BH`: Benjamini-Hochberg step-up (controls the false discovery rate, FDR: the expected share of
  false claims among the claims made; valid under independence or positive regression dependence
  on a subset, PRDS)

### 4.3 Reporting and Decision Use

For reporting, expose:

- `adjusted_p_super`: adjusted superiority p-value
- `adjusted_p_inferior`: adjusted inferiority p-value
- `adjusted_p_noninf`: null (non-inferiority remains unadjusted)

Decision logic uses:
- non-inferiority: raw `p_value_noninf`
- superiority: `adjusted_p_super` when adjustment is enabled, otherwise raw `p_value_super`
- inferiority: `adjusted_p_inferior` when adjustment is enabled, otherwise raw `p_value_inferior`

When α ≤ 0.5, adjusting the inferiority family cannot make a candidate promotable. The inferiority and non-inferiority tests share one statistic, so `p_value_inferior = 1 − p_value_noninf`; a raw inferiority rejection (`p_value_inferior < α`) then gives `p_value_noninf > 1 − α ≥ α`, so non-inferiority already fails. The adjustment can only prevent a family-level regression claim from being made on unadjusted evidence, changing some otherwise-`Reject` outcomes to `NoDecision`. The schema accepts any α with 0 < α < 1; with α > 0.5 both tests can reject on the same objective, and the adjustment can change a `Reject` into a `Promote`.

---

## 5. Decision Logic

### 5.0 Error

Return `"Error"` first, before any other branch, when a check is undefined. Today this is a chance constraint with zero trials or no trial count (`zero_trials`, Definition 9.8 of the formal semantics). `Error` is neither `Reject` nor `NoDecision`. The evidence bundle lists the codes in `summary.chance_error_codes`, and `summary.decision_reason` names the constraints.

`tvl-ci-gate` reports this decision as `Decision: Error` and exits 2. Through the CLI, only a bundle that uses the
deprecated top-level `chance` summary can reach this decision (see below), so `warnings` lists
`deprecated_measurement_chance` for that bundle. With `--json` it prints:

```json
{
  "ok": false,
  "decision": "Error",
  "error": "zero_trials: no trials for chance constraints: toxicity_rate",
  "codes": ["zero_trials"],
  "warnings": [
    {
      "code": "deprecated_measurement_chance",
      "message": "Top-level 'chance' is deprecated. Use 'chance_outcomes.<name>.violations' and 'chance_outcomes.<name>.trials'.",
      "source": "candidate.json"
    }
  ],
  "evidence": { "...": "..." }
}
```

With canonical `chance_outcomes`, a `trials` of 0 or a missing `trials` is a schema error when the file is loaded (exit 2, no `decision`). With the deprecated top-level `chance` summary, `summary.trials: 0` passes the schema and reaches the gate, which returns `Error` with `zero_trials` (exit 2). A bundle passed to the gate in Python also gets `Error`.

### 5.1 Promote Decision

Return `"Promote"` if ALL of the following are true:

1. All non-inferiority tests pass (raw `p_value_noninf < α` for all standard, non-banded objectives)
2. At least one superiority test passes after selected adjustment (for at least one standard objective, `adjusted_p_super < α` when `adjust` is not `"none"`, otherwise `p_value_super < α`)
3. All banded objectives pass TOST
4. All chance constraints pass
5. No inferiority test demonstrates a regression (§5.2, item 1)
6. If the module declares promotion monitors (TVL 1.3, formal semantics Definition 12.15), every promotion monitor returns `MET`

Items 1–5 are the TVL 1.2 decision. A promotion monitor that returns `BREACHED` turns the result into `Reject`, and one that returns `UNKNOWN` turns a `Promote` into `NoDecision`; passing all monitors never turns a `NoDecision` into `Promote`.

### 5.2 Reject Decision

Return `"Reject"` if ANY of the following are true:

1. Any inferiority test demonstrates regression beyond the allowed margin (adjusted `p_value_inferior < α` when adjustment is enabled)
2. Any chance constraint fails
3. Any banded objective has a point estimate outside its declared band
4. Any promotion monitor returns `BREACHED`

### 5.3 NoDecision

Return `"NoDecision"` otherwise, including when non-inferiority has not been established but inferiority has not been demonstrated.

---

## 6. Complete Test Matrix

| Scenario | Configuration | Test | Expected Decision |
|----------|--------------|------|-------------------|
| Clear dominance | Candidate better on all objectives by > 2ε; non-inferiority and superiority significant | Welch per obj | Promote |
| Clear inferiority | Candidate worse on all objectives by > 2ε; inferiority significant | Welch per obj | Reject |
| Mixed results | Candidate better on obj1, worse on obj2 by more than ε; inferiority on obj2 significant | Welch per obj | Reject (inferiority on obj2) |
| Within noise | All deltas < ε, high variance | Welch per obj | NoDecision |
| Superior on one | Better on obj1 by > ε (superiority significant), non-inferiority significant on the others | Welch per obj | Promote |
| BH correction | 10 objectives, 2 superiority p-values raw < 0.05 but adjusted > 0.05 | BH | NoDecision |
| TOST pass | Mean = 100, band = [95, 105], n = 50, std = 5 | TOST (90% CI) | Promote (if other tests pass) |
| TOST fail (power) | Mean = 100, band = [95, 105], n = 5, std = 8 | TOST (90% CI) | NoDecision |
| TOST fail (out of band) | Mean = 110, band = [95, 105] | TOST (90% CI) | Reject |
| Chance pass | 0/120 violations, θ = 0.03, γ = 0.95 | Clopper-Pearson | (contributes to Promote) |
| Chance fail | 8/100 violations, θ = 0.05, γ = 0.95 | Clopper-Pearson | Reject |
| Paired samples | Same eval set for both configs, `paired: true` on the candidate's objective, and sample lists of equal length | Paired t-test | (uses paired test) |

Effect sizes alone never decide statistical objective comparisons: a `Promote` row, or a `Reject` row that comes from a significant inferiority test, assumes enough observations for the named tests to reject at α; the same effects with too few observations give `NoDecision`. Two `Reject` rows fall outside this caveat: a failed chance constraint, and an objective mean outside its band (a point estimate, which needs only n ≥ 1), still give `Reject` when the objective tests lack enough observations.

---

## 7. Implementation Notes

### 7.1 Dependencies

- `scipy.stats`: For t-distribution, beta distribution
- `numpy`: For numerical operations

### 7.2 Edge Cases

- **Empty or single-sample arm, standard objectives** (a non-banded objective with fewer than 2 observations in either the incumbent or the candidate arm): no variance can be estimated, so no t-test runs and the objective result is `inconclusive`; with every other check passing, the decision is `NoDecision`.
- **Banded objectives** use the candidate's statistics only, so the incumbent's sample count does not matter. A candidate with fewer than 2 observations gives `out_of_band` (and `Reject`) when its point estimate is outside the band, and `inconclusive` when it is inside or there are no observations (§3.4).
- **No statistics at all**: `tvl-ci-gate` refuses such a bundle with exit 2 before the gate runs. An objective entry with an empty `samples` list and no complete `mean/std/n` fails the measurement schema, so the error is a schema message. A module objective with no entry in `objective_values` passes the schema and is reported as `missing_statistical_evidence` under `readiness_issues`.
- **All objectives identical**: NoDecision (no superiority), provided every chance constraint passes and every banded objective is in band; a failing chance constraint or an out-of-band banded objective still gives `Reject`.
- **No objectives defined**: the module schema requires at least one objective, so such a module is rejected at validation. Called directly in Python with no objectives and no failing checks, the gate returns `NoDecision`.

### 7.3 Numerical Stability

- Handle division by zero in SE calculation
- Clip p-values to [1e-300, 1.0] range
- Use log-space for very small p-values if needed

---

## 8. Error Codes

The diagnostic catalog is [docs/reference/error-codes.md](../docs/reference/error-codes.md); its introduction lists the codes it does not yet cover. The codes below are the ones emitted for promotion inputs.

**Measurement bundle not promotion-ready** (`tvl-ci-gate` exits 2 with no decision; `tvl-measure-validate` reports `promotion_ready: false`):

| Code | Description |
|------|-------------|
| `missing_statistical_evidence` | `objective_values.<name>` gives neither a nonempty `samples` list nor `mean/std/n` |
| `missing_chance_counts` | `chance_outcomes.<name>` does not give `violations` and `trials` |
| `missing_monitor_counts` | A promotion monitor has no valid `monitor_outcomes.<name>` counts in the candidate bundle |
| `measurement_module_mismatch` | The bundle's `module_id` names a different module from the one the gate uses |
| `calibration_evidence_unsupported` | The module needs calibration certificates, which the bundle cannot carry (§1) |

**Gate and measurement results**:

| Code | Reported by | Description |
|------|-------------|-------------|
| `zero_trials` | gate; `tvl-measure-validate` | Chance constraint with zero trials or no trial count; the gate returns `Error` (§5.0) |
| `chance_violation` | `tvl-measure-validate` | A chance constraint's upper confidence bound exceeds its threshold |
| `missing_measurement` | `tvl-measure-validate` | No chance outcome for a declared chance constraint |
| `missing_statistical_runtime` | `tvl-measure-validate` | scipy is not installed, so chance constraints cannot be evaluated |
| `unsupported_construct` | both tools | The input is a `tvl-runtime-report/1` file, not a measurement bundle |

**Warnings** for deprecated input forms: `deprecated_measurement_objectives`, `deprecated_measurement_chance`, `legacy_chance_not_convertible` (a legacy `chance` summary whose violation count cannot be reconstructed exactly), and `deprecated_ci_gate_policy_flag` (`--policy` used).

**Module errors found by `tvl-lint`** (`tvl-ci-gate` also runs these checks on modules that use TVL 1.3 constructs): `missing_min_effect` (no `promotion_policy.min_effect` entry for a standard objective), `invalid_direction` (direction is not `maximize` or `minimize`) and `missing_band_target` (banded objective without a target).

Fewer than 2 observations in an arm is not an error code: the objective result is `inconclusive` (§7.2).
