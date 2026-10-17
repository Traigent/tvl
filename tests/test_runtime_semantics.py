"""Unit and property tests for TVL 1.3 runtime semantics (RFC 0003, §12)."""


from __future__ import annotations


import pytest


from tvl.runtime import from_backend_revision, to_backend_profile


@pytest.mark.parametrize(
    "thresh,theta,conf,w_hours,grace,min_samples,unres,c_win,c_age,budget,horizon,env",
    [
        (1, "0.001", "0.9", 1, 0, 1, "0", 1, 3, "0.01", 1, "production"),
        (2000, "0.05", "0.95", 6, 30, 200, "0.05", 2, 24, "0.05", 30, "  Staging  "),
        (600000, "0.5", "0.99", 24, 360, 10000000, "0.5", 24, 720, "0.5", 365, "EU_WEST_1"),
        (500, "0.025", "0.95", 3, 15, 50, "0.1", 4, 24, "0.25", 14, "prod"),
        (10000, "0.1", "0.9", 12, 60, 500, "0.02", 2, 48, "0.05", 90, "canary"),
    ],
)
def test_backend_profile_roundtrip_property(
    thresh: int,
    theta: str,
    conf: str,
    w_hours: int,
    grace: int,
    min_samples: int,
    unres: str,
    c_win: int,
    c_age: int,
    budget: str,
    horizon: int,
    env: str,
) -> None:
    """Property test: lift ∘ lower = id and lower ∘ lift = id on valid backend_v1 profiles (§10.3)."""
    rev = {
        "kind": "latency_violation_rate",
        "latency_threshold_ms": thresh,
        "environment": env,
        "max_violation_rate": theta,
        "confidence": conf,
        "window_hours": w_hours,
        "grace_minutes": grace,
        "min_samples": min_samples,
        "max_unresolved_fraction": unres,
        "closure_windows": c_win,
        "closure_max_age_hours": c_age,
        "false_alarm_budget": budget,
        "horizon_days": horizon,
    }
    req, mon = from_backend_revision(rev, requirement_name="lat_req", monitor_name="lat_mon")
    lowered, meta = to_backend_profile(req, mon)

    expected_norm = dict(rev)
    expected_norm["environment"] = env.strip().lower()
    assert lowered == expected_norm
    assert meta == {
        "method": "clopper_pearson_exact_v1",
        "model": "iid_bernoulli_within_window_v1",
        "sampling": "unverified",
    }

    req2, mon2 = from_backend_revision(lowered, requirement_name="lat_req", monitor_name="lat_mon")
    assert req2 == req
    assert mon2 == mon
