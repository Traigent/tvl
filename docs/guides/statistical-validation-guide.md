# Statistical Validation Guide

This guide explains TVL's statistical framework for efficient multi-objective optimization. Understanding these principles helps you configure TVL for optimal sample efficiency while maintaining rigorous guarantees.

## Overview: Two-Phase Statistical Model

TVL employs two distinct statistical regimes:

```
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1: EXPLORATION (Pareto Discovery)                        │
│  ─────────────────────────────────────────                      │
│  Goal: Find ε-Pareto front with probability ≥ 1-δ               │
│  Method: Adaptive sampling (Successive Halving, MOBO)           │
│  Sample size: Dynamic, based on uncertainty                     │
│  Key insight: Drop unpromising configs EARLY                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2: PROMOTION (Validation)                                │
│  ───────────────────────────────                                │
│  Goal: Confirm selected config beats production baseline        │
│  Method: Welch's t-test (pairwise comparison)                   │
│  Sample size: Fixed, based on minimum detectable effect         │
│  When: Only for FINAL promotion decision                        │
└─────────────────────────────────────────────────────────────────┘
```

**Key insight**: Most of your sample budget goes to exploration (Phase 1), which uses **adaptive sampling** that is far more efficient than exhaustive pairwise testing.

---

## Phase 1: PAC ε-Pareto Discovery

### The Guarantee

With probability ≥ 1-δ, TVL returns a configuration set S where:

1. **Coverage**: Every point on the true Pareto front has some s ∈ S within ε
2. **Quality**: Every s ∈ S is within ε of the true Pareto front

This is a **PAC (Probably Approximately Correct)** guarantee.

### Sample Complexity Comparison

For K configurations, d objectives, tolerance ε, confidence 1-δ:

| Method | Sample Complexity | K=1000, d=3, ε=0.05 | Reduction |
|--------|-------------------|---------------------|-----------|
| **Naive (all pairs)** | O(K · d · log(K/δ) / ε²) | ~90,000 samples | Baseline |
| **Successive Halving** | O(K · log(K) · d / ε²) | ~3,000 samples | **30×** |
| **UCB-style** | O(K · d · log(1/δ) / ε²) | ~5,000 samples | 18× |
| **Thompson Sampling** | O(d · log(K/δ) / ε²) | ~1,500 samples | **60×** |

### How Adaptive Sampling Works

**Successive Halving** (default in TVL):

```
Round 1: Evaluate ALL K configs with n₁ samples each
         Eliminate bottom 50%

Round 2: Evaluate remaining K/2 configs with 2n₁ samples each
         Eliminate bottom 50%

Round 3: Evaluate remaining K/4 configs with 4n₁ samples each
         ...continue until convergence
```

**Result**: Promising configs get MORE samples, dominated configs get FEWER.

### Sample Size Formula

For (ε, δ)-PAC guarantee on the Pareto front:

```
n_total ≈ (σ² / ε²) · ln(K/δ) · d · f(η)

Where:
  σ² = variance of metrics (estimated online)
  ε  = Pareto tolerance (how close to true front)
  K  = number of configurations in search space
  d  = number of objectives
  δ  = failure probability (e.g., 0.05 for 95% confidence)
  f(η) ≈ log(log(K)) for successive halving with elimination rate η
```

**Worked Example**:
```
K = 1000 configs, d = 3 objectives, ε = 0.05, δ = 0.05, σ = 0.1

Naive:    n = (0.1² / 0.05²) · ln(1000/0.05) · 3 · 1000
        ≈ 4 · 10 · 3 · 1000 = 120,000 samples

Successive Halving:
          n = (0.1² / 0.05²) · ln(1000/0.05) · 3 · log(log(1000))
        ≈ 4 · 10 · 3 · 2 = 240 samples per round
          × ~12 rounds = ~3,000 total samples
```

---

## Adaptive Sample Allocation

### Per-Configuration Budget

| Config State | Samples/Round | Rationale |
|--------------|---------------|-----------|
| **Promising** (top 50%) | 2× baseline | Exploit: refine estimate |
| **Uncertain** (middle) | 1× baseline | Explore: resolve uncertainty |
| **Dominated** | 0 (eliminated) | Save budget for promising |

### Exploration vs Exploitation

```yaml
# TVL optimization settings
optimization:
  # How much budget for pure exploration (random configs)
  exploration_budget: 0.2      # 20% explores new regions

  # When to stop exploring a config
  exploitation_threshold: 0.8  # Exploit when >80% confident it's good

  # Successive halving parameters
  elimination_rate: 0.5        # Halve configs each round
  min_samples_before_elimination: 5  # Don't eliminate too early

  # Convergence detection
  plateau_window: 10           # Stop if no improvement for 10 rounds
  plateau_epsilon: 0.01        # "No improvement" = <1% change
```

### Early Stopping Criteria

TVL stops exploration when:

1. **Hypervolume plateau**: Pareto front hasn't improved in `plateau_window` rounds
2. **Budget exhausted**: Reached `max_samples` limit
3. **Convergence**: All remaining configs have confidence intervals < ε

---

## Phase 2: Promotion Validation

**When**: Only after exploration identifies the best configuration(s).

**Purpose**: Final statistical confirmation that the candidate beats production.

### When Promotion Testing Applies

| Scenario | Use Promotion Test? | Reason |
|----------|---------------------|--------|
| Deploying to production | **Yes** | Need high confidence |
| Internal comparison | No | Exploration sufficient |
| A/B testing in production | **Yes** | Statistical rigor required |
| Hyperparameter tuning | No | Use exploration phase |

### Promotion Test Requirements

For the final promotion decision:

```yaml
promotion_policy:
  confidence_level: 0.95      # α = 0.05
  correction_method: holm     # For multiple objectives
  min_samples: 50             # Per configuration (fixed)

  # Minimum detectable effect
  mde: 0.05                   # Detect 5% improvement
```

**Sample size for promotion** (Welch's t-test):

```
n ≈ 2 · (z_α + z_β)² · σ² / MDE²

Where:
  z_α = 1.96 for α = 0.05
  z_β = 0.84 for 80% power
  σ = pooled standard deviation
  MDE = minimum detectable effect
```

**Example**: σ = 0.1, MDE = 0.05 → n ≈ 2 · (1.96 + 0.84)² · 0.01 / 0.0025 ≈ 63 per group

---

## Theoretical Foundations

### PAC-Learning Framework

TVL's guarantees are based on **PAC (Probably Approximately Correct) learning**:

**Definition** (ε-Pareto PAC):
> An algorithm is (ε, δ)-PAC for Pareto front discovery if, with probability ≥ 1-δ, it returns a set S such that:
> - ∀ s ∈ S: d(s, P*) ≤ ε (all returned points are near-optimal)
> - ∀ p ∈ P*: ∃ s ∈ S with d(p, s) ≤ ε (all optimal points are represented)
>
> where P* is the true Pareto front and d is the ε-dominance distance.

### Key References

1. **Successive Halving**: Jamieson & Talwalkar (2016), "Non-stochastic Best Arm Identification"
2. **Hyperband**: Li et al. (2018), "Hyperband: A Novel Bandit-Based Approach"
3. **ε-PAL**: Zuluaga et al. (2016), "ε-PAL: An Active Learning Approach to Multi-Objective Optimization"
4. **EHVI**: Daulton et al. (2020), "Differentiable Expected Hypervolume Improvement"

### Hoeffding-Style Bounds

For a single objective with bounded rewards in [0, 1]:

```
P(|μ̂ - μ| > ε) ≤ 2·exp(-2nε²)
```

Setting the RHS = δ and solving for n:

```
n ≥ ln(2/δ) / (2ε²)
```

For multiple objectives, apply union bound over d objectives:

```
n ≥ ln(2d/δ) / (2ε²)
```

---

## Practical Configuration

### Recommended Defaults

```yaml
# For most TVL optimization scenarios
optimization:
  algorithm: successive_halving

  # PAC parameters
  epsilon: 0.05              # 5% Pareto tolerance
  delta: 0.05                # 95% confidence

  # Efficiency settings
  elimination_rate: 0.5      # Halve each round (standard)
  min_rounds: 3              # At least 3 rounds before stopping
  max_rounds: 20             # Upper bound

  # Exploration
  initial_samples: 5         # Per config in round 1
  exploration_budget: 0.2    # 20% for pure exploration

promotion_policy:
  # Only for final deployment decision
  test: welch_t
  confidence_level: 0.95
  min_samples: 50
  correction_method: holm    # For multiple objectives
```

### Scenario-Specific Settings

| Scenario | K (configs) | d (objectives) | ε | Estimated Samples |
|----------|-------------|----------------|---|-------------------|
| Quick prototype | 50 | 2 | 0.1 | ~500 |
| Production tuning | 500 | 3 | 0.05 | ~2,000 |
| Large-scale search | 5,000 | 4 | 0.05 | ~8,000 |
| Fine-grained optimization | 100 | 3 | 0.02 | ~5,000 |

---

## Worked Examples

### Example 1: LLM Router Optimization

```yaml
# Scenario: Optimize model routing for accuracy vs cost
tunables:
  model: [gpt-4, gpt-3.5-turbo, claude-3-opus, claude-3-sonnet]
  temperature: [0.0, 0.3, 0.7, 1.0]
  max_tokens: [256, 512, 1024]

# K = 4 × 4 × 3 = 48 configurations
# d = 2 objectives (accuracy, cost)

optimization:
  epsilon: 0.05
  delta: 0.05

# Expected samples: ~400 total (not 48 × 50 = 2,400!)
# Successive halving eliminates poor configs early
```

### Example 2: RAG Pipeline Tuning

```yaml
# Scenario: Optimize RAG for accuracy, latency, and cost
tunables:
  retriever_k: [3, 5, 10, 20]
  chunk_size: [256, 512, 1024]
  embedding_model: [ada-002, text-embedding-3-small, text-embedding-3-large]
  reranker: [none, cohere, cross-encoder]

# K = 4 × 3 × 3 × 3 = 108 configurations
# d = 3 objectives

optimization:
  epsilon: 0.03          # Tighter tolerance
  delta: 0.05
  exploration_budget: 0.3  # More exploration for complex space

# Expected samples: ~1,500 total
```

### Example 3: Final Promotion Decision

```yaml
# After exploration identifies best config
# Now compare to production baseline

promotion_policy:
  baseline: production_v2.1
  candidate: optimized_v2.2

  test: welch_t
  confidence_level: 0.95
  min_samples: 100         # Higher for production decision
  mde: 0.03                # Detect 3% improvement

  objectives:
    - name: accuracy
      metric_ref: metrics.accuracy.v1
      orientation: maximize
      threshold: 0.85      # Must exceed 85%
    - name: latency_p95
      metric_ref: metrics.latency_p95.v1
      orientation: minimize
      threshold: 200       # Must be under 200ms
    - name: cost_per_1k
      metric_ref: metrics.cost_per_1k.v1
      orientation: minimize
      # No threshold, just compare

# This is traditional hypothesis testing
# Only run AFTER exploration phase completes
```

---

## Summary

| Phase | Goal | Method | Sample Efficiency |
|-------|------|--------|-------------------|
| **Exploration** | Find ε-Pareto front | Successive Halving, MOBO | **30-60× more efficient** |
| **Promotion** | Confirm vs baseline | Welch's t-test | Standard (n ≥ 50) |

**Key takeaways**:

1. **Don't use pairwise testing for exploration** - it's wasteful
2. **Adaptive sampling** drops bad configs early, saving ~30× samples
3. **PAC guarantees** provide rigorous (ε, δ) bounds on Pareto front quality
4. **Reserve Welch's t-test** for final promotion decision only
5. **Configure ε and δ** based on your quality requirements and budget

For Traigent SDK integration, see the [Traigent Integration Guide](./traigent-tvl-integration.md).
