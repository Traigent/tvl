"""Promotion evaluation for fully resolved evidence using standard exact binomial tests.

Evidence needing partial-observation interpretation is refused with a closed reason.
This module contains no runtime window or unresolved-count decision procedure.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

from .binomial import binomial_tails_exact
from .canonical import RuntimeClosedError, to_fraction


def evaluate_promotion_monitor(
    req: Mapping[str, Any], mon: Mapping[str, Any], outcome: Mapping[str, Any],
) -> Dict[str, Any]:
    """Evaluate complete promotion counts; unresolved evidence requires an external engine."""
    if not {"n", "k"} <= outcome.keys():
        raise RuntimeClosedError("runtime_report_conservation")
    counts = {key: outcome.get(key, 0) for key in ("n", "k", "u", "pl")}
    verdict, reason = "UNKNOWN", "insufficient"
    if any(type(value) is not int or value < 0 for value in counts.values()) or counts["k"] > counts["n"]:
        raise RuntimeClosedError("runtime_report_conservation")
    n, k = counts["n"], counts["k"]
    decision = mon.get("decision") or {}
    minimum = decision.get("min_samples", 1)
    if type(minimum) is not int or minimum < 1:
        raise RuntimeClosedError("runtime_invalid_profile")
    if counts["u"] or counts["pl"]:
        reason = "engine_required"
    elif req.get("kind") == "zero_tolerance":
        if outcome.get("complete") is not True:
            reason = "incomplete"
        elif k:
            verdict, reason = "BREACHED", None
        elif n < minimum:
            reason = "insufficient"
        else:
            verdict, reason = "MET", None
    elif req.get("kind") == "rate_bound":
        theta = to_fraction(req.get("max_rate"))
        budget = to_fraction(decision.get("false_alarm_budget"))
        confidence = to_fraction(decision.get("confidence"))
        if not (0 < theta < 1 and 0 < budget < 1 and 0 < confidence < 1):
            raise RuntimeClosedError("runtime_invalid_profile")
        if n >= minimum:
            upper, lower = binomial_tails_exact(n, theta, k)
            if k >= 1 and upper < budget:
                verdict, reason = "BREACHED", None
            elif k < n and lower <= 1 - confidence:
                verdict, reason = "MET", None
            else:
                reason = "inconclusive"
    else:
        raise RuntimeClosedError("runtime_unknown_kind")
    return {
        "verdict": verdict,
        "reason": reason,
        "mapped_decision": "Reject" if verdict == "BREACHED" else "pass" if verdict == "MET" else "NoDecision",
        "counts": counts,
    }
