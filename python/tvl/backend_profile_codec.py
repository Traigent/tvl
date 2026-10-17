"""Convert backend latency profiles to and from TVL requirement declarations."""

from __future__ import annotations

import copy
from tvl.canonical import RuntimeClosedError, minimal_decimal_str, to_fraction
from typing import Any, Dict, Mapping, Tuple


def to_backend_profile(
    req: Mapping[str, Any],
    mon: Mapping[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Lower a backend_v1 requirement and monitor to the 13-key BackendProfile and evaluation_metadata."""
    if mon.get("profile") != "backend_v1":
        raise RuntimeClosedError("runtime_invalid_profile")
    viol = req.get("violation") or {}
    ev = mon.get("evidence") or {}
    win = mon.get("window") or {}
    dec = mon.get("decision") or {}
    ep = mon.get("episode") or {}

    env_raw = str(ev.get("deployment_environment", "production")).strip().lower()
    if not (1 <= len(env_raw) <= 64):
        raise RuntimeClosedError("runtime_legacy_profile_override")

    thresh = int(viol["exceeds"])
    theta_f = float(to_fraction(req["max_rate"]))
    conf_f = float(to_fraction(dec.get("confidence", "0.95")))
    w_hours = int(win.get("tumbling_hours", 6))
    grace = int(win.get("grace_minutes", 30))
    min_samples = int(dec.get("min_samples", 200))
    unres_f = float(to_fraction(dec.get("max_unresolved_fraction", "0.05")))
    c_win = int(ep.get("closure_windows", 2))
    c_age = int(ep.get("closure_max_age_hours", 24))
    budget_f = float(to_fraction(dec.get("false_alarm_budget", "0.05")))
    horizon = int(dec.get("horizon_days", 30))

    profile = {
        "kind": "latency_violation_rate",
        "latency_threshold_ms": thresh,
        "environment": env_raw,
        "max_violation_rate": minimal_decimal_str(repr(theta_f)),
        "confidence": minimal_decimal_str(repr(conf_f)),
        "window_hours": w_hours,
        "grace_minutes": grace,
        "min_samples": min_samples,
        "max_unresolved_fraction": minimal_decimal_str(repr(unres_f)),
        "closure_windows": c_win,
        "closure_max_age_hours": c_age,
        "false_alarm_budget": minimal_decimal_str(repr(budget_f)),
        "horizon_days": horizon,
    }
    metadata = {
        "method": "clopper_pearson_exact_v1",
        "model": "iid_bernoulli_within_window_v1",
        "sampling": "unverified",
    }
    return profile, metadata


def from_backend_revision(
    rev: Mapping[str, Any],
    *,
    requirement_name: str = "requirement_main",
    monitor_name: str = "monitor_main",
    applies_to: str = "agent",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Lift a 13-key backend revision/profile to a normalized TVL 1.3 requirement and monitor (§10.3)."""
    if rev.get("kind") != "latency_violation_rate":
        raise RuntimeClosedError("runtime_invalid_profile")
    env_norm = str(rev.get("environment", "production")).strip().lower()
    if not (1 <= len(env_norm) <= 64):
        raise RuntimeClosedError("runtime_legacy_profile_override")

    thresh = int(rev["latency_threshold_ms"])
    theta_f = float(to_fraction(rev["max_violation_rate"]))
    conf_f = float(to_fraction(rev.get("confidence", "0.95")))
    w_hours = int(rev.get("window_hours", 6))
    grace = int(rev.get("grace_minutes", 30))
    min_samples = int(rev.get("min_samples", 200))
    unres_f = float(to_fraction(rev.get("max_unresolved_fraction", "0.05")))
    c_win = int(rev.get("closure_windows", 2))
    c_age = int(rev.get("closure_max_age_hours", 24))
    budget_f = float(to_fraction(rev.get("false_alarm_budget", "0.05")))
    horizon = int(rev.get("horizon_days", 30))

    req = {
        "name": requirement_name,
        "kind": "rate_bound",
        "unit": "trace",
        "violation": {
            "metric": "wall_clock_latency_ms",
            "exceeds": thresh,
        },
        "max_rate": float(repr(theta_f)),
    }
    mon = {
        "name": monitor_name,
        "requirement": requirement_name,
        "phase": "runtime",
        "profile": "backend_v1",
        "applies_to": applies_to,
        "evidence": {
            "source": "backend_trace_metadata",
            "deployment_environment": env_norm,
            "attribution": "agent_key_exact_v1",
            "resolution": "terminal_status_v1",
            "sampling": "unverified",
        },
        "window": {
            "tumbling_hours": w_hours,
            "grace_minutes": grace,
        },
        "decision": {
            "method": "clopper_pearson_exact_v1",
            "model": "iid_bernoulli_within_window_v1",
            "confidence": float(repr(conf_f)),
            "false_alarm_budget": float(repr(budget_f)),
            "horizon_days": horizon,
            "min_samples": min_samples,
            "max_unresolved_fraction": float(repr(unres_f)),
        },
        "episode": {
            "closure_windows": c_win,
            "closure_max_age_hours": c_age,
        },
    }
    return req, mon


def erase_runtime_extensions(doc: Mapping[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Erase requirements, monitors, responses from a TVL module (Def 12.29)."""
    erased = copy.deepcopy(dict(doc))
    reqs = erased.pop("requirements", None)
    mons = erased.pop("monitors", None)
    resps = erased.pop("responses", None)
    runtime_empty = not bool(reqs) and not bool(mons) and not bool(resps)
    return erased, runtime_empty
