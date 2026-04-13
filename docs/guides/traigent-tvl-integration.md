# Traigent SDK Integration with TVL

This document outlines how the Traigent SDK supports TVL users building AI agents, leveraging existing features for efficient multi-objective optimization with formal guarantees.

## Overview

TVL (Tuned Variables Language) defines the **specification** for agent configuration spaces, constraints, and promotion policies. Traigent provides the **execution infrastructure** for optimization, evaluation, and deployment. Together, they enable a complete workflow:

```
TVL Spec (what to optimize)
        ↓
Traigent SDK (how to optimize)
        ↓
  ┌─────────────────────────────────────┐
  │  Phase 1: Exploration               │
  │  - Successive Halving               │
  │  - Expected Hypervolume Improvement │
  │  - Adaptive sample allocation       │
  │  - Early elimination of bad configs │
  └─────────────────────────────────────┘
        ↓
  ┌─────────────────────────────────────┐
  │  Phase 2: Promotion                 │
  │  - Welch's t-test vs baseline       │
  │  - Multiple testing correction      │
  │  - Statistical validation           │
  └─────────────────────────────────────┘
        ↓
Promoted Config (production-ready)
```

---

## Phase 1: Efficient Pareto Discovery

### Existing Features for Adaptive Sampling

Traigent already provides powerful features for efficient multi-objective optimization:

#### 1. Successive Halving Pruner

**Location**: `traigent/optimizers/optuna_optimizer.py`

Traigent auto-selects `SuccessiveHalvingPruner` for multi-objective problems:

```python
from traigent.optimizers.optuna_optimizer import OptunaOptimizer

# Traigent automatically uses Successive Halving for multi-objective
optimizer = OptunaOptimizer(
    objectives=['accuracy', 'latency', 'cost'],
    n_trials=100,
)

# What happens internally:
# Round 1: All 100 configs evaluated with 5 samples each
# Round 2: Top 50 configs evaluated with 10 samples each
# Round 3: Top 25 configs evaluated with 20 samples each
# ...until convergence

results = optimizer.optimize(evaluator)
```

**Sample savings**: For K=100 configs, naive approach needs 100×50 = 5,000 samples. Successive halving: ~800 samples (6× reduction).

#### 2. Pareto Front Calculator with Hypervolume

**Location**: `traigent/utils/multi_objective.py`

```python
from traigent.utils.multi_objective import ParetoFrontCalculator

calculator = ParetoFrontCalculator(
    objectives=['accuracy', 'latency', 'cost'],
    orientations=['maximize', 'minimize', 'minimize']
)

# Compute current Pareto front
pareto_front = calculator.compute(trial_results)

# Hypervolume metric (larger = better Pareto front)
hypervolume = calculator.hypervolume(
    pareto_front,
    reference_point=[0.0, 1000.0, 10.0]  # Worst acceptable values
)

# Expected Hypervolume Improvement for exploration
# High EHVI = config might expand Pareto front (explore!)
# Low EHVI = config is dominated (deprioritize)
```

#### 3. Ceiling Pruner for Early Stopping

**Location**: `traigent/optimizers/pruners.py`

```python
from traigent.optimizers.pruners import CeilingPruner

pruner = CeilingPruner(
    warmup_steps=2,           # Evaluate at least 2 samples before pruning
    epsilon=0.01,             # Tolerance for "equivalent" performance
    cost_ceiling_per_trial=5  # Maximum cost before forced pruning
)

# Pruner eliminates configs whose OPTIMISTIC ceiling
# (best possible outcome) still can't beat current best
```

#### 4. Sample Budget Manager

**Location**: `traigent/core/sample_budget.py`

```python
from traigent.core.sample_budget import SampleBudgetManager, SampleBudgetLease

# Global budget management
budget_manager = SampleBudgetManager(total_budget=1000)

# Per-trial lease
with budget_manager.lease(max_samples=50) as lease:
    while lease.try_take(1):
        sample = evaluate_once(config)
        if should_stop_early(sample):
            lease.rollback(remaining)  # Return unused samples
            break

# Efficiency tracking
print(f"Efficiency: {budget_manager.efficiency:.2%}")  # (consumed - wasted) / consumed
```

#### 5. Convergence Detection

**Location**: `traigent/core/stop_conditions.py`

```python
from traigent.core.stop_conditions import PlateauAfterNStopCondition

stop_condition = PlateauAfterNStopCondition(
    window_size=10,           # Look at last 10 trials
    epsilon=0.01,             # Stop if hypervolume improves < 1%
    objective_schema=schema
)

# Automatically stops when Pareto front stabilizes
# Provides implicit δ guarantee via convergence
```

#### 6. Bayesian Optimization with Exploration Control

**Location**: `traigent/optimizers/bayesian.py`

```python
from traigent.optimizers.bayesian import BayesianOptimizer

optimizer = BayesianOptimizer(
    parameter_space=config_space,
    acquisition='ei',         # Expected Improvement
    xi=0.01,                  # Exploration-exploitation tradeoff
    # xi=0 → pure exploitation
    # xi=0.1 → more exploration
)

# For multi-objective, can use scalarization
optimizer = BayesianOptimizer(
    parameter_space=config_space,
    objectives=['accuracy', 'latency'],
    weights=[0.7, 0.3],       # Weighted sum scalarization
)
```

---

## Proposed: PAC-Pareto Optimizer

Combine existing features into a unified interface with formal (ε, δ)-PAC guarantees:

```python
class PACParetoOptimizer:
    """
    Find ε-Pareto front with probability 1-δ.

    Combines:
    - Successive Halving for early elimination
    - Hypervolume for Pareto front quality
    - Adaptive budget allocation
    - Formal sample complexity bounds
    """

    def __init__(
        self,
        epsilon: float = 0.05,      # Pareto tolerance
        delta: float = 0.05,        # Failure probability
        elimination_rate: float = 0.5,  # Fraction to eliminate each round
        min_samples_per_round: int = 5
    ):
        self.epsilon = epsilon
        self.delta = delta
        self.eta = elimination_rate
        self.min_samples = min_samples_per_round

    def required_samples(self, K: int, d: int, sigma: float) -> int:
        """
        Compute total sample budget for (ε, δ)-PAC guarantee.

        Args:
            K: Number of configurations
            d: Number of objectives
            sigma: Estimated metric standard deviation

        Returns:
            Total samples needed across all rounds
        """
        # Hoeffding-style bound with successive halving factor
        base = (sigma**2 / self.epsilon**2) * np.log(K / self.delta) * d

        # Successive halving reduces by log(log(K)) factor
        elimination_factor = np.log(np.log(K + 1) + 1)

        return int(np.ceil(base * elimination_factor))

    def optimize(
        self,
        config_space: ConfigurationSpace,
        evaluator: Evaluator,
        objectives: List[Objective]
    ) -> PACParetoResult:
        """
        Run optimization with PAC guarantee.

        Returns:
            PACParetoResult with:
            - pareto_front: List of non-dominated configurations
            - hypervolume: Quality metric
            - samples_used: Total evaluations
            - guarantee: (epsilon, delta) tuple
        """
        K = config_space.size
        d = len(objectives)

        # 1. Initial variance estimation (small pilot study)
        pilot_samples = self._run_pilot(config_space, evaluator, n=10)
        sigma = np.mean([np.std(s) for s in pilot_samples.values()])

        # 2. Compute required budget
        total_budget = self.required_samples(K, d, sigma)

        # 3. Initialize successive halving
        configs = config_space.sample_all()
        round_num = 0

        while len(configs) > 1:
            round_num += 1
            samples_per_config = self._samples_for_round(round_num, total_budget, K)

            # 4. Evaluate remaining configs
            results = {}
            for config in configs:
                results[config] = evaluator.evaluate(
                    config,
                    n_samples=samples_per_config
                )

            # 5. Compute Pareto front and eliminate dominated
            pareto = self._compute_pareto(results, objectives)
            non_dominated = self._identify_non_dominated(results, pareto, self.epsilon)

            # 6. Eliminate bottom fraction
            configs = self._eliminate(
                configs,
                results,
                keep_fraction=1 - self.eta,
                protected=non_dominated  # Never eliminate Pareto-optimal
            )

            # 7. Check convergence
            if self._converged(results, pareto):
                break

        return PACParetoResult(
            pareto_front=pareto,
            hypervolume=self._hypervolume(pareto),
            samples_used=self._total_samples,
            guarantee=(self.epsilon, self.delta)
        )

    def _samples_for_round(self, round_num: int, total_budget: int, K: int) -> int:
        """Geometric increase in samples per round."""
        # Round r gets 2^r times the base samples
        base = total_budget / (K * np.log2(K + 1))
        return int(np.ceil(base * (2 ** (round_num - 1))))
```

---

## Phase 2: Promotion Validation

After exploration identifies the best configuration(s), use formal statistical tests for final promotion decision.

### Promotion Gate

```python
from enum import Enum
from dataclasses import dataclass
from typing import List, Dict
from scipy.stats import ttest_ind

class CorrectionMethod(Enum):
    NONE = "none"
    BONFERRONI = "bonferroni"
    HOLM = "holm"
    BH = "benjamini_hochberg"

@dataclass
class PromotionResult:
    approved: bool
    test_results: Dict[str, 'TestResult']
    corrected_p_values: List['CorrectedResult']
    warnings: List[str]

class PromotionGate:
    """Statistical validation for production promotion."""

    def __init__(
        self,
        alpha: float = 0.05,
        correction: CorrectionMethod = CorrectionMethod.HOLM
    ):
        self.alpha = alpha
        self.correction = correction

    def run_promotion_check(
        self,
        baseline_metrics: Dict[str, List[float]],
        candidate_metrics: Dict[str, List[float]],
        objectives: List['Objective']
    ) -> PromotionResult:
        """
        Compare candidate against production baseline.

        This is ONLY for final promotion decision, not exploration.
        """
        p_values = []
        test_results = {}
        warnings = []

        for obj in objectives:
            baseline = baseline_metrics[obj.name]
            candidate = candidate_metrics[obj.name]

            # Sample size check
            if len(baseline) < 30 or len(candidate) < 30:
                warnings.append(
                    f"{obj.name}: Sample size < 30, consider collecting more data"
                )

            # Welch's t-test (handles unequal variances)
            alternative = 'greater' if obj.orientation == 'maximize' else 'less'
            stat, p_value = ttest_ind(
                candidate, baseline,
                equal_var=False,
                alternative=alternative
            )

            test_results[obj.name] = TestResult(
                statistic=stat,
                p_value=p_value,
                effect_size=self._cohens_d(baseline, candidate)
            )
            p_values.append(p_value)

        # Apply multiple testing correction
        corrected = self._apply_correction(p_values)

        return PromotionResult(
            approved=all(c.reject for c in corrected),
            test_results=test_results,
            corrected_p_values=corrected,
            warnings=warnings
        )

    def _apply_correction(self, p_values: List[float]) -> List['CorrectedResult']:
        """Apply multiple testing correction (Holm by default)."""
        k = len(p_values)

        if self.correction == CorrectionMethod.HOLM:
            # Holm step-down procedure
            sorted_indices = np.argsort(p_values)
            adjusted = np.zeros(k)

            for i, idx in enumerate(sorted_indices):
                adjusted[idx] = min(p_values[idx] * (k - i), 1.0)

            # Enforce monotonicity
            for i in range(1, k):
                idx = sorted_indices[i]
                prev_idx = sorted_indices[i-1]
                adjusted[idx] = max(adjusted[idx], adjusted[prev_idx])

        elif self.correction == CorrectionMethod.BONFERRONI:
            adjusted = [min(p * k, 1.0) for p in p_values]

        else:
            adjusted = p_values

        return [
            CorrectedResult(original=p, adjusted=a, reject=a < self.alpha)
            for p, a in zip(p_values, adjusted)
        ]
```

---

## Complete Integration Example

```python
from traigent.tvl import TVLParser
from traigent.optimizers import PACParetoOptimizer
from traigent.promotion import PromotionGate
from traigent.utils.callbacks import StatisticsCallback

# ─────────────────────────────────────────────────────────────────
# 1. Load TVL Specification
# ─────────────────────────────────────────────────────────────────
parser = TVLParser()
tvl_module = parser.load('agent.tvl.yml')

print(f"Loaded: {tvl_module.name}")
print(f"  Tunables: {len(tvl_module.tunables)}")
print(f"  Objectives: {[o['name'] for o in tvl_module.objectives]}")

# ─────────────────────────────────────────────────────────────────
# 2. Phase 1: Exploration (PAC-Pareto Discovery)
# ─────────────────────────────────────────────────────────────────
optimizer = PACParetoOptimizer(
    epsilon=0.05,     # 5% Pareto tolerance
    delta=0.05,       # 95% confidence
    elimination_rate=0.5
)

# Convert TVL spec to Traigent config
config_space = parser.to_config_space(tvl_module)
objectives = parser.extract_objectives(tvl_module)

# Estimate sample budget
K = config_space.size
d = len(objectives)
estimated_sigma = 0.1  # Will be refined during optimization

budget = optimizer.required_samples(K, d, estimated_sigma)
print(f"Estimated budget: {budget} samples (vs {K * 50} naive)")

# Run optimization
result = optimizer.optimize(
    config_space=config_space,
    evaluator=evaluator,
    objectives=objectives
)

print(f"Pareto front: {len(result.pareto_front)} configurations")
print(f"Hypervolume: {result.hypervolume:.4f}")
print(f"Samples used: {result.samples_used}")
print(f"Guarantee: (ε={result.guarantee[0]}, δ={result.guarantee[1]})")

# Select best config for promotion (e.g., by weighted preference)
best_config = select_preferred(result.pareto_front, weights=[0.5, 0.3, 0.2])

# ─────────────────────────────────────────────────────────────────
# 3. Phase 2: Promotion (Statistical Validation)
# ─────────────────────────────────────────────────────────────────
# Collect fresh samples for promotion test
baseline_metrics = collect_production_metrics(n=100)
candidate_metrics = evaluate_config(best_config, n=100)

# Run promotion gate
gate = PromotionGate(
    alpha=0.05,
    correction=CorrectionMethod.HOLM
)

promotion_result = gate.run_promotion_check(
    baseline_metrics=baseline_metrics,
    candidate_metrics=candidate_metrics,
    objectives=objectives
)

# ─────────────────────────────────────────────────────────────────
# 4. Decision
# ─────────────────────────────────────────────────────────────────
if promotion_result.approved:
    print("✓ APPROVED for production deployment")
    for obj, result in promotion_result.test_results.items():
        print(f"  {obj}: p={result.p_value:.4f}, d={result.effect_size:.2f}")
    deploy(best_config)
else:
    print("✗ NOT APPROVED")
    for warning in promotion_result.warnings:
        print(f"  Warning: {warning}")
```

---

## Feature Summary

| TVL Concept | Traigent Feature | Status |
|-------------|------------------|--------|
| **Exploration** | | |
| Pareto front discovery | `ParetoFrontCalculator` | Existing |
| Adaptive sampling | `SuccessiveHalvingPruner` | Existing |
| Hypervolume (EHVI) | `multi_objective.py` | Existing |
| Early stopping | `CeilingPruner` | Existing |
| Budget management | `SampleBudgetManager` | Existing |
| Convergence detection | `PlateauAfterNStopCondition` | Existing |
| PAC guarantee wrapper | `PACParetoOptimizer` | **Proposed** |
| **Promotion** | | |
| Welch's t-test | `PromotionGate` | **Proposed** |
| Holm/BH correction | `PromotionGate` | **Proposed** |
| **Integration** | | |
| TVL spec parser | `TVLParser` | **Proposed** |
| Diagnostic dashboard | `DiagnosticDashboard` | **Proposed** |

---

## Sample Complexity Reference

| Scenario | K configs | d objectives | ε | Naive samples | With Traigent |
|----------|-----------|--------------|---|---------------|---------------|
| Quick prototype | 50 | 2 | 0.1 | 2,500 | ~400 |
| Production tuning | 500 | 3 | 0.05 | 75,000 | ~2,500 |
| Large-scale search | 5,000 | 4 | 0.05 | 1,000,000 | ~15,000 |

**Key insight**: Traigent's adaptive sampling provides 10-60× sample efficiency while maintaining formal guarantees.

For statistical background, see the [Statistical Validation Guide](./statistical-validation-guide.md).
