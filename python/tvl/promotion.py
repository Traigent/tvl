"""TVL Promotion Gate - Statistical decision logic for configuration promotion.

This module implements ε-Pareto dominance testing with:
- Non-inferiority tests (Welch's or paired t-test)
- Superiority tests
- Multiple-testing adjustment (Holm/Bonferroni/BH) on superiority tests
- TOST equivalence for banded objectives
- Clopper-Pearson confidence intervals for chance constraints over violation rates
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

# Statistical functions - we use math for basic operations,
# but scipy is required for proper t-distribution and beta functions
try:
    from scipy import stats as scipy_stats
    SCIPY_AVAILABLE = True
except ImportError:
    scipy_stats = None  # type: ignore
    SCIPY_AVAILABLE = False


Decision = Tuple[str, Dict[str, Any]]


@dataclass
class ObjectiveSpec:
    """Specification for an objective from the TVL module."""
    name: str
    direction: str  # "maximize" or "minimize"
    epsilon: float  # min_effect threshold
    band: Optional[Dict[str, Any]] = None  # For banded objectives
    metric_ref: Optional[str] = None  # Stable evaluator metric identifier


@dataclass
class ObjectiveResult:
    """Result of statistical testing for a single objective."""
    name: str
    test_type: str  # "welch", "paired", "precomputed"
    n_incumbent: int
    n_candidate: int
    mean_incumbent: float
    mean_candidate: float
    delta: float  # candidate - incumbent
    std_pooled: Optional[float]
    t_statistic: Optional[float]
    df: Optional[float]
    p_value_noninf: float
    p_value_super: float
    adjusted_p_noninf: Optional[float] = None
    adjusted_p_super: Optional[float] = None
    epsilon: float = 0.0
    verdict: str = "inconclusive"  # "superior", "noninferior", "inferior", "inconclusive"


@dataclass
class BandedResult:
    """Result of TOST testing for a banded objective."""
    name: str
    test_type: str = "tost"
    n: int = 0
    mean: float = 0.0
    std: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    band_lower: float = 0.0
    band_upper: float = 0.0
    p_value_lower: float = 1.0
    p_value_upper: float = 1.0
    verdict: str = "inconclusive"  # "in_band", "out_of_band", "inconclusive"


@dataclass
class ChanceResult:
    """Result of Clopper-Pearson testing for a chance constraint."""
    name: str
    violations: int
    trials: int
    observed_rate: float
    ci_lower: float
    ci_upper: float
    threshold: float
    confidence: float
    verdict: str  # "pass" or "fail"
    reason: str = ""


@dataclass
class PromotionEvidence:
    """Complete evidence bundle for a promotion decision."""
    per_objective: Dict[str, Union[ObjectiveResult, BandedResult]] = field(default_factory=dict)
    chance_constraints: Dict[str, ChanceResult] = field(default_factory=dict)
    all_noninferior: bool = False
    any_superior: bool = False
    all_bands_pass: bool = True
    all_chance_pass: bool = True
    adjustment_method: str = "none"
    fdr_controlled_at: Optional[float] = None
    decision_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert evidence to dictionary for serialization."""
        return {
            "per_objective": {
                k: _result_to_dict(v) for k, v in self.per_objective.items()
            },
            "chance_constraints": {
                k: _chance_to_dict(v) for k, v in self.chance_constraints.items()
            },
            "summary": {
                "all_noninferior": self.all_noninferior,
                "any_superior": self.any_superior,
                "all_bands_pass": self.all_bands_pass,
                "all_chance_pass": self.all_chance_pass,
                "adjustment_method": self.adjustment_method,
                "fdr_controlled_at": self.fdr_controlled_at,
                "decision_reason": self.decision_reason,
            },
        }


def _result_to_dict(r: Union[ObjectiveResult, BandedResult]) -> Dict[str, Any]:
    """Convert ObjectiveResult or BandedResult to dict."""
    if isinstance(r, BandedResult):
        return {
            "test_type": r.test_type,
            "n": r.n,
            "mean": r.mean,
            "std": r.std,
            "ci_lower": r.ci_lower,
            "ci_upper": r.ci_upper,
            "band_lower": r.band_lower,
            "band_upper": r.band_upper,
            "p_value_lower": r.p_value_lower,
            "p_value_upper": r.p_value_upper,
            "verdict": r.verdict,
        }
    return {
        "test_type": r.test_type,
        "n_incumbent": r.n_incumbent,
        "n_candidate": r.n_candidate,
        "mean_incumbent": r.mean_incumbent,
        "mean_candidate": r.mean_candidate,
        "delta": r.delta,
        "std_pooled": r.std_pooled,
        "t_statistic": r.t_statistic,
        "df": r.df,
        "p_value_noninf": r.p_value_noninf,
        "p_value_super": r.p_value_super,
        "adjusted_p_noninf": r.adjusted_p_noninf,
        "adjusted_p_super": r.adjusted_p_super,
        "epsilon": r.epsilon,
        "verdict": r.verdict,
    }


def _chance_to_dict(c: ChanceResult) -> Dict[str, Any]:
    """Convert ChanceResult to dict."""
    return {
        "violations": c.violations,
        "trials": c.trials,
        "observed_rate": c.observed_rate,
        "ci_lower": c.ci_lower,
        "ci_upper": c.ci_upper,
        "threshold": c.threshold,
        "confidence": c.confidence,
        "verdict": c.verdict,
        "reason": c.reason,
    }


def epsilon_pareto_gate(
    incumbent: Dict[str, Any],
    candidate: Dict[str, Any],
    policy: Dict[str, Any],
    objectives: Optional[List[Dict[str, Any]]] = None,
) -> Decision:
    """Perform ε-Pareto dominance testing with statistical rigor.

    Args:
        incumbent: Measurement bundle for incumbent configuration
        candidate: Measurement bundle for candidate configuration
        policy: promotion_policy from TVL module
        objectives: List of objective specifications from module

    Returns:
        Tuple of (decision, evidence) where decision is one of:
        - "Promote": Candidate passes all non-inferiority tests and at least one superiority
        - "Reject": Candidate fails non-inferiority on at least one objective
        - "NoDecision": Insufficient evidence to promote or reject
    """
    require_scipy()

    alpha = policy.get("alpha", 0.05)
    min_effects = policy.get("min_effect", {})
    adjust = policy.get("adjust", "holm")
    chance_constraints = policy.get("chance_constraints", [])

    # Parse objectives
    obj_specs = _parse_objectives(objectives or [], min_effects)

    # Get measurement values
    inc_objectives = incumbent.get("objective_values", {})
    cand_objectives = candidate.get("objective_values", {})
    cand_chance = candidate.get("chance_outcomes", {})

    evidence = PromotionEvidence()
    evidence.adjustment_method = adjust

    # Test each standard objective
    super_pvalues: List[Tuple[str, float]] = []
    for spec in obj_specs:
        if spec.band is not None:
            # Banded objective - use TOST
            result = _test_banded_objective(spec, cand_objectives.get(spec.name, {}), alpha)
            evidence.per_objective[spec.name] = result
            if result.verdict != "in_band":
                evidence.all_bands_pass = False
        else:
            # Standard objective - use t-tests
            result = _test_objective(
                spec,
                inc_objectives.get(spec.name, {}),
                cand_objectives.get(spec.name, {}),
            )
            evidence.per_objective[spec.name] = result
            super_pvalues.append((spec.name, result.p_value_super))

    # Apply multiplicity adjustment to superiority p-values (union component).
    adjust_name = str(adjust).upper()
    if super_pvalues and adjust_name != "NONE":
        adjusted_super = _adjust_pvalues([p for _, p in super_pvalues], adjust_name)
        if adjust_name == "BH":
            evidence.fdr_controlled_at = alpha
        for i, (name, _) in enumerate(super_pvalues):
            obj_result = evidence.per_objective.get(name)
            if isinstance(obj_result, ObjectiveResult):
                obj_result.adjusted_p_super = adjusted_super[i]

    # Determine verdicts: non-inferiority (IUT) is unadjusted; superiority uses adjusted p-values.
    all_noninf = True
    any_superior = False
    for name, obj_result in evidence.per_objective.items():
        if isinstance(obj_result, ObjectiveResult):
            if obj_result.p_value_noninf >= alpha:
                obj_result.verdict = "inferior"
                all_noninf = False
            else:
                p_super = (
                    obj_result.adjusted_p_super
                    if obj_result.adjusted_p_super is not None
                    else obj_result.p_value_super
                )
                if p_super < alpha:
                    obj_result.verdict = "superior"
                    any_superior = True
                else:
                    obj_result.verdict = "noninferior"

    evidence.all_noninferior = all_noninf
    evidence.any_superior = any_superior

    # Test chance constraints
    for constraint in chance_constraints:
        name = constraint.get("name", "")
        threshold = constraint.get("threshold", 0.0)
        confidence = constraint.get("confidence", 0.95)
        outcome = cand_chance.get(name, {})
        result = _test_chance_constraint(name, outcome, threshold, confidence)
        evidence.chance_constraints[name] = result
        if result.verdict != "pass":
            evidence.all_chance_pass = False

    # Make decision
    decision, reason = _make_decision(evidence)
    evidence.decision_reason = reason

    return (decision, evidence.to_dict())


def require_scipy() -> None:
    """Fail fast when the statistical runtime dependency is unavailable."""
    if not SCIPY_AVAILABLE:
        raise RuntimeError(
            "scipy is required for TVL promotion and chance-constraint evaluation. "
            "Install the runtime dependencies before using tvl-ci-gate."
        )


def evaluate_chance_constraint(
    name: str,
    outcome: Dict[str, Any],
    threshold: float,
    confidence: float,
) -> ChanceResult:
    """Public wrapper for the canonical violation-rate chance-constraint test."""
    require_scipy()
    return _test_chance_constraint(name, outcome, threshold, confidence)


def _parse_objectives(
    objectives: List[Dict[str, Any]],
    min_effects: Dict[str, float],
) -> List[ObjectiveSpec]:
    """Parse objective specifications from module."""
    specs: List[ObjectiveSpec] = []
    for obj in objectives:
        name = obj.get("name", "")
        direction = obj.get("direction", "maximize")
        epsilon = min_effects.get(name, 0.0)
        band = obj.get("band")
        metric_ref = obj.get("metric_ref")
        specs.append(
            ObjectiveSpec(
                name=name,
                direction=direction,
                epsilon=epsilon,
                band=band,
                metric_ref=metric_ref,
            )
        )
    return specs


def _test_objective(
    spec: ObjectiveSpec,
    inc_data: Dict[str, Any],
    cand_data: Dict[str, Any],
) -> ObjectiveResult:
    """Perform t-tests for a standard objective."""
    # Check for pre-computed p-value
    if "p_value" in cand_data and "delta" in cand_data:
        return _from_precomputed(spec, cand_data)

    # Get samples or aggregated stats
    inc_samples = inc_data.get("samples")
    cand_samples = cand_data.get("samples")
    paired = cand_data.get("paired", False)

    if inc_samples is not None and cand_samples is not None:
        return _test_from_samples(spec, inc_samples, cand_samples, paired)

    # Fall back to aggregated stats
    return _test_from_stats(spec, inc_data, cand_data)


def _from_precomputed(spec: ObjectiveSpec, cand_data: Dict[str, Any]) -> ObjectiveResult:
    """Create result from pre-computed values."""
    delta = cand_data.get("delta", 0.0)
    p_value = cand_data.get("p_value", 1.0)
    observed = cand_data.get("observed", 0.0)

    return ObjectiveResult(
        name=spec.name,
        test_type="precomputed",
        n_incumbent=0,
        n_candidate=0,
        mean_incumbent=observed - delta,
        mean_candidate=observed,
        delta=delta,
        std_pooled=None,
        t_statistic=None,
        df=None,
        p_value_noninf=p_value,  # Assume this is the non-inferiority p-value
        p_value_super=1.0,  # Cannot determine from aggregated
        epsilon=spec.epsilon,
    )


def _test_from_samples(
    spec: ObjectiveSpec,
    inc_samples: List[float],
    cand_samples: List[float],
    paired: bool,
) -> ObjectiveResult:
    """Perform t-tests from raw sample data."""
    n_inc = len(inc_samples)
    n_cand = len(cand_samples)

    mean_inc = sum(inc_samples) / n_inc if n_inc > 0 else 0.0
    mean_cand = sum(cand_samples) / n_cand if n_cand > 0 else 0.0
    delta = mean_cand - mean_inc

    # Direction: +1 for maximize (higher is better), -1 for minimize (lower is better)
    sigma = 1 if spec.direction == "maximize" else -1
    epsilon = spec.epsilon

    if paired and n_inc == n_cand and n_inc > 1:
        # Paired t-test
        diffs = [c - i for c, i in zip(cand_samples, inc_samples)]
        mean_diff = sum(diffs) / len(diffs)
        var_diff = sum((d - mean_diff) ** 2 for d in diffs) / (len(diffs) - 1)
        std_diff = math.sqrt(var_diff) if var_diff > 0 else 1e-10
        se = std_diff / math.sqrt(len(diffs))
        df = len(diffs) - 1

        # Non-inferiority: H0: sigma * delta < -epsilon
        # Test statistic: t = (sigma * mean_diff + epsilon) / se
        t_noninf = (sigma * mean_diff + epsilon) / se
        p_noninf = 1.0 - scipy_stats.t.cdf(t_noninf, df)

        # Superiority: H0: sigma * delta <= epsilon
        t_super = (sigma * mean_diff - epsilon) / se
        p_super = 1.0 - scipy_stats.t.cdf(t_super, df)

        return ObjectiveResult(
            name=spec.name,
            test_type="paired",
            n_incumbent=n_inc,
            n_candidate=n_cand,
            mean_incumbent=mean_inc,
            mean_candidate=mean_cand,
            delta=delta,
            std_pooled=std_diff,
            t_statistic=t_noninf,
            df=df,
            p_value_noninf=max(1e-300, min(1.0, p_noninf)),
            p_value_super=max(1e-300, min(1.0, p_super)),
            epsilon=epsilon,
        )

    # Welch's t-test (default)
    var_inc = sum((x - mean_inc) ** 2 for x in inc_samples) / (n_inc - 1) if n_inc > 1 else 0
    var_cand = sum((x - mean_cand) ** 2 for x in cand_samples) / (n_cand - 1) if n_cand > 1 else 0

    se = math.sqrt(var_inc / n_inc + var_cand / n_cand) if var_inc + var_cand > 0 else 1e-10

    # Welch-Satterthwaite degrees of freedom
    if var_inc > 0 or var_cand > 0:
        num = (var_inc / n_inc + var_cand / n_cand) ** 2
        denom = (var_inc / n_inc) ** 2 / (n_inc - 1) + (var_cand / n_cand) ** 2 / (n_cand - 1)
        df = num / denom if denom > 0 else 1
    else:
        df = min(n_inc, n_cand) - 1

    # Non-inferiority test
    t_noninf = (sigma * delta + epsilon) / se
    p_noninf = 1.0 - scipy_stats.t.cdf(t_noninf, df)

    # Superiority test
    t_super = (sigma * delta - epsilon) / se
    p_super = 1.0 - scipy_stats.t.cdf(t_super, df)

    std_pooled = math.sqrt((var_inc + var_cand) / 2) if var_inc + var_cand > 0 else 0

    return ObjectiveResult(
        name=spec.name,
        test_type="welch",
        n_incumbent=n_inc,
        n_candidate=n_cand,
        mean_incumbent=mean_inc,
        mean_candidate=mean_cand,
        delta=delta,
        std_pooled=std_pooled,
        t_statistic=t_noninf,
        df=df,
        p_value_noninf=max(1e-300, min(1.0, p_noninf)),
        p_value_super=max(1e-300, min(1.0, p_super)),
        epsilon=epsilon,
    )


def _test_from_stats(
    spec: ObjectiveSpec,
    inc_data: Dict[str, Any],
    cand_data: Dict[str, Any],
) -> ObjectiveResult:
    """Perform t-tests from aggregated statistics."""
    mean_inc = inc_data.get("mean", 0.0)
    std_inc = inc_data.get("std", 0.0)
    n_inc = inc_data.get("n", 0)

    mean_cand = cand_data.get("mean", 0.0)
    std_cand = cand_data.get("std", 0.0)
    n_cand = cand_data.get("n", 0)

    if n_inc < 2 or n_cand < 2:
        return ObjectiveResult(
            name=spec.name,
            test_type="welch",
            n_incumbent=n_inc,
            n_candidate=n_cand,
            mean_incumbent=mean_inc,
            mean_candidate=mean_cand,
            delta=mean_cand - mean_inc,
            std_pooled=None,
            t_statistic=None,
            df=None,
            p_value_noninf=1.0,
            p_value_super=1.0,
            epsilon=spec.epsilon,
            verdict="inconclusive",
        )

    delta = mean_cand - mean_inc
    sigma = 1 if spec.direction == "maximize" else -1
    epsilon = spec.epsilon

    var_inc = std_inc ** 2
    var_cand = std_cand ** 2
    se = math.sqrt(var_inc / n_inc + var_cand / n_cand) if var_inc + var_cand > 0 else 1e-10

    # Welch-Satterthwaite df
    if var_inc > 0 or var_cand > 0:
        num = (var_inc / n_inc + var_cand / n_cand) ** 2
        denom = (var_inc / n_inc) ** 2 / (n_inc - 1) + (var_cand / n_cand) ** 2 / (n_cand - 1)
        df = num / denom if denom > 0 else 1
    else:
        df = min(n_inc, n_cand) - 1

    t_noninf = (sigma * delta + epsilon) / se
    p_noninf = 1.0 - scipy_stats.t.cdf(t_noninf, df)

    t_super = (sigma * delta - epsilon) / se
    p_super = 1.0 - scipy_stats.t.cdf(t_super, df)

    return ObjectiveResult(
        name=spec.name,
        test_type="welch",
        n_incumbent=n_inc,
        n_candidate=n_cand,
        mean_incumbent=mean_inc,
        mean_candidate=mean_cand,
        delta=delta,
        std_pooled=math.sqrt((var_inc + var_cand) / 2),
        t_statistic=t_noninf,
        df=df,
        p_value_noninf=max(1e-300, min(1.0, p_noninf)),
        p_value_super=max(1e-300, min(1.0, p_super)),
        epsilon=epsilon,
    )


def _test_banded_objective(
    spec: ObjectiveSpec,
    cand_data: Dict[str, Any],
    alpha: float,
) -> BandedResult:
    """Perform TOST equivalence test for banded objective.

    IMPORTANT: TOST uses (1 - 2α) confidence interval, not (1 - α).
    For α = 0.05, we use 90% CI.
    """
    band = spec.band or {}
    target = band.get("target")
    band_alpha = band.get("alpha", alpha)

    # Parse band bounds
    if isinstance(target, list) and len(target) == 2:
        band_lower, band_upper = float(target[0]), float(target[1])
    elif isinstance(target, dict):
        center = target.get("center", 0)
        tol = target.get("tol", 0)
        band_lower = center - tol
        band_upper = center + tol
    else:
        return BandedResult(name=spec.name, verdict="inconclusive")

    # Get candidate statistics
    samples = cand_data.get("samples")
    if samples is not None and len(samples) >= 2:
        n = len(samples)
        mean = sum(samples) / n
        var = sum((x - mean) ** 2 for x in samples) / (n - 1)
        std = math.sqrt(var)
    else:
        mean = cand_data.get("mean", 0.0)
        std = cand_data.get("std", 0.0)
        n = cand_data.get("n", 0)

    if n < 2:
        return BandedResult(name=spec.name, verdict="inconclusive")

    se = std / math.sqrt(n)
    df = n - 1

    # TOST: Two one-sided tests
    # H01: μ <= L, reject at α → t1 = (mean - L) / SE
    # H02: μ >= U, reject at α → t2 = (U - mean) / SE
    t1 = (mean - band_lower) / se if se > 0 else 0
    t2 = (band_upper - mean) / se if se > 0 else 0

    p1 = 1.0 - scipy_stats.t.cdf(t1, df)
    p2 = 1.0 - scipy_stats.t.cdf(t2, df)

    # (1 - 2α) confidence interval
    t_crit = scipy_stats.t.ppf(1 - band_alpha, df)
    ci_lower = mean - t_crit * se
    ci_upper = mean + t_crit * se

    # Pass if max(p1, p2) < alpha, equivalently if CI ⊂ [L, U]
    if max(p1, p2) < band_alpha:
        verdict = "in_band"
    elif ci_lower < band_lower or ci_upper > band_upper:
        verdict = "out_of_band"
    else:
        verdict = "inconclusive"

    return BandedResult(
        name=spec.name,
        test_type="tost",
        n=n,
        mean=mean,
        std=std,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        band_lower=band_lower,
        band_upper=band_upper,
        p_value_lower=max(1e-300, min(1.0, p1)),
        p_value_upper=max(1e-300, min(1.0, p2)),
        verdict=verdict,
    )


def _test_chance_constraint(
    name: str,
    outcome: Dict[str, Any],
    threshold: float,
    confidence: float,
) -> ChanceResult:
    """Perform Clopper-Pearson exact binomial test for chance constraint.

    Chance constraints are specified as upper bounds on violation rates.
    We compute a one-sided exact upper confidence bound and pass iff
    ci_upper <= threshold.
    """
    violations = outcome.get("violations", 0)
    trials = outcome.get("trials", 0)

    if trials <= 0:
        return ChanceResult(
            name=name,
            violations=0,
            trials=0,
            observed_rate=0.0,
            ci_lower=0.0,
            ci_upper=1.0,
            threshold=threshold,
            confidence=confidence,
            verdict="fail",
            reason="No trials available",
        )

    if violations < 0 or violations > trials:
        return ChanceResult(
            name=name,
            violations=max(0, int(violations)),
            trials=trials,
            observed_rate=0.0,
            ci_lower=0.0,
            ci_upper=1.0,
            threshold=threshold,
            confidence=confidence,
            verdict="fail",
            reason=f"Invalid violation count {violations} for {trials} trials",
        )

    observed_rate = violations / trials

    # Clopper-Pearson exact confidence interval
    alpha_tail = 1 - confidence

    if violations == 0:
        ci_lower = 0.0
    else:
        ci_lower = scipy_stats.beta.ppf(alpha_tail, violations, trials - violations + 1)

    if violations == trials:
        ci_upper = 1.0
    else:
        ci_upper = scipy_stats.beta.ppf(1 - alpha_tail, violations + 1, trials - violations)

    # Pass if the upper bound is at or below the allowed violation rate.
    if ci_upper <= threshold:
        verdict = "pass"
        reason = ""
    else:
        verdict = "fail"
        reason = f"ci_upper ({ci_upper:.4f}) > threshold ({threshold})"

    return ChanceResult(
        name=name,
        violations=violations,
        trials=trials,
        observed_rate=observed_rate,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        threshold=threshold,
        confidence=confidence,
        verdict=verdict,
        reason=reason,
    )


def _benjamini_hochberg(p_values: List[float]) -> List[float]:
    """Apply Benjamini-Hochberg FDR adjustment.

    Returns adjusted p-values that can be compared directly against alpha.
    """
    n = len(p_values)
    if n == 0:
        return []

    # Sort p-values with original indices
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])

    # Compute adjusted p-values
    adjusted = [0.0] * n
    adjusted[indexed[-1][0]] = indexed[-1][1]

    for i in range(n - 2, -1, -1):
        orig_idx, p = indexed[i]
        adj = p * n / (i + 1)
        adjusted[orig_idx] = min(adjusted[indexed[i + 1][0]], adj)

    return [min(1.0, p) for p in adjusted]


def _bonferroni_adjust(p_values: List[float]) -> List[float]:
    """Apply Bonferroni adjustment and return adjusted p-values."""
    n = len(p_values)
    if n == 0:
        return []
    return [min(1.0, p * n) for p in p_values]


def _holm_adjust(p_values: List[float]) -> List[float]:
    """Apply Holm step-down adjustment and return adjusted p-values."""
    n = len(p_values)
    if n == 0:
        return []

    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    sorted_adjusted: List[float] = [0.0] * n
    running_max = 0.0

    for i, (_, p) in enumerate(indexed):
        raw = (n - i) * p
        running_max = max(running_max, raw)
        sorted_adjusted[i] = min(1.0, running_max)

    adjusted = [0.0] * n
    for i, (orig_idx, _) in enumerate(indexed):
        adjusted[orig_idx] = sorted_adjusted[i]

    return adjusted


def _adjust_pvalues(p_values: List[float], method: str) -> List[float]:
    """Apply a supported multiple-testing adjustment and return adjusted p-values."""
    method_upper = method.upper()
    if method_upper == "BH":
        return _benjamini_hochberg(p_values)
    if method_upper == "BONFERRONI":
        return _bonferroni_adjust(p_values)
    if method_upper == "HOLM":
        return _holm_adjust(p_values)
    return p_values


def _make_decision(evidence: PromotionEvidence) -> Tuple[str, str]:
    """Make final promotion decision based on evidence."""
    # Check for any failures
    if not evidence.all_noninferior:
        failing = [
            name for name, r in evidence.per_objective.items()
            if isinstance(r, ObjectiveResult) and r.verdict == "inferior"
        ]
        return ("Reject", f"Non-inferiority failed on: {', '.join(failing)}")

    if not evidence.all_chance_pass:
        failing = [
            name for name, r in evidence.chance_constraints.items()
            if r.verdict == "fail"
        ]
        return ("Reject", f"Chance constraints failed: {', '.join(failing)}")

    if not evidence.all_bands_pass:
        failing = [
            name for name, r in evidence.per_objective.items()
            if isinstance(r, BandedResult) and r.verdict != "in_band"
        ]
        return ("Reject", f"Banded objectives failed TOST: {', '.join(failing)}")

    # Check for promotion (need at least one superior)
    if evidence.any_superior:
        superior = [
            name for name, r in evidence.per_objective.items()
            if isinstance(r, ObjectiveResult) and r.verdict == "superior"
        ]
        return ("Promote", f"All non-inferiority tests pass; superior on: {', '.join(superior)}")

    # All pass but no superiority demonstrated
    return ("NoDecision", "All objectives non-inferior but no superiority demonstrated")
