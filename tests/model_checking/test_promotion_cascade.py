"""P7 — strict-promotion fail-closed reachability; cascade totality (§3.8).

The promotion model enumerates every (strict-trigger × verdict × dominance)
combination and asserts the fail-closed law: under any strict trigger, every
evidence-failure verdict yields no_certified_selection — never a
winner-by-objective. The legacy (non-strict) lane is also pinned so the model
documents exactly what the SDK repair must NOT change.
"""

from __future__ import annotations

import itertools

import pytest

from .model import (
    CVar,
    Module,
    NO_CERTIFIED_SELECTION,
    P7_VERDICTS,
    PROMOTE,
    REJECT,
    VoteStats,
    cascade_select,
    promotion_outcome,
    strict,
)

STRICT_TRIGGERS = {
    "require_calibration": dict(require_calibration_enabled=True),
    "chance_constraints": dict(has_chance_constraints=True),
    "guaranteed_selection": dict(has_guaranteed_selection_target=True),
}


def _module(**flags) -> Module:
    return Module(**flags)


GOVERNED_CVAR = CVar("theta", source="src", require_calibration=True)
CERT_TARGET_CVAR = CVar("theta", source="src", certificate_backed_target=True)
PLAIN_CVAR = CVar("theta", source="src", require_calibration=False)


def test_strict_trigger_enumeration():
    """§3.6: each declared trigger independently makes the module strict —
    including the per-CVAR governance trigger (review finding 5)."""
    assert not strict(_module(), [PLAIN_CVAR])
    for flags in STRICT_TRIGGERS.values():
        assert strict(_module(**flags), [PLAIN_CVAR])
    assert strict(_module(), [GOVERNED_CVAR])  # per-CVAR governance trigger alone
    assert strict(_module(), [CERT_TARGET_CVAR])  # certificate-backed target alone


@pytest.mark.parametrize("trigger_name,flags", list(STRICT_TRIGGERS.items()))
@pytest.mark.parametrize("verdict", P7_VERDICTS)
@pytest.mark.parametrize("beats", [False, True])
def test_p7_fail_closed_for_every_trigger_and_verdict(trigger_name, flags, verdict, beats):
    """The core law: strict × evidence-failure ⇒ NO_CERTIFIED_SELECTION,
    regardless of objective dominance (`beats` must not matter)."""
    outcome = promotion_outcome(_module(**flags), [PLAIN_CVAR], verdict, beats)
    assert outcome == NO_CERTIFIED_SELECTION


@pytest.mark.parametrize("verdict", P7_VERDICTS)
@pytest.mark.parametrize("beats", [False, True])
def test_p7_per_cvar_governance_trigger(verdict, beats):
    outcome = promotion_outcome(_module(), [GOVERNED_CVAR], verdict, beats)
    assert outcome == NO_CERTIFIED_SELECTION


def test_strict_clean_evidence_promotes_on_dominance():
    """Strict mode with CLEAN evidence is not a denial-of-service: dominance
    still decides."""
    module = _module(require_calibration_enabled=True)
    assert promotion_outcome(module, [PLAIN_CVAR], None, True) == PROMOTE
    assert promotion_outcome(module, [PLAIN_CVAR], None, False) == REJECT


@pytest.mark.parametrize("verdict", list(P7_VERDICTS) + [None])
@pytest.mark.parametrize("beats", [False, True])
def test_non_strict_lane_unchanged(verdict, beats):
    """The legacy lane: without any strict trigger the outcome is decided by
    dominance alone (this is the byte-identical behavior the SDK repair must
    preserve outside strict modes)."""
    outcome = promotion_outcome(_module(), [PLAIN_CVAR], verdict, beats)
    assert outcome == (PROMOTE if beats else REJECT)


def test_exhaustive_no_silent_promotion_under_strict():
    """Sweep the full cross-product: no (strict, failure-verdict) cell ever
    returns PROMOTE."""
    cells = 0
    for flags in STRICT_TRIGGERS.values():
        for verdict in P7_VERDICTS:
            for beats in (False, True):
                assert (
                    promotion_outcome(_module(**flags), [PLAIN_CVAR], verdict, beats)
                    != PROMOTE
                )
                cells += 1
    assert cells == len(STRICT_TRIGGERS) * len(P7_VERDICTS) * 2


# ---------------------------------------------------------------------------
# Cascade totality and determinism — §3.8.
# ---------------------------------------------------------------------------


def test_cascade_m1_degenerate_no_gates():
    assert cascade_select(["only"], [], []) == 0


def test_cascade_arity_invariant_enforced():
    with pytest.raises(ValueError):
        cascade_select(["s1", "s2"], [], [VoteStats(0.5)])  # |gates| != m-1
    with pytest.raises(ValueError):
        cascade_select([], [], [])  # m >= 1


def test_cascade_empty_vote_escalates_for_positive_theta():
    """§3.8: empty/abstain-only vote ⇒ margin 0 ⇒ escalate for θ > 0."""
    assert cascade_select(["cheap", "strong"], [0.6], [VoteStats(margin=0.0)]) == 1


def test_cascade_theta_zero_never_escalates():
    """θ = 0 means never escalate (strict inequality)."""
    assert cascade_select(["cheap", "strong"], [0.0], [VoteStats(margin=0.0)]) == 0


def test_cascade_deterministic_given_votes_exhaustive():
    """Determinism: over an exhaustive small scope of (margins × thetas),
    repeated evaluation returns the identical stage, and stage selection is
    exactly min{i : i = m ∨ margin_i >= theta_i}."""
    margins = [0.0, 0.3, 0.6, 1.0]
    thetas = [0.0, 0.4, 0.8]
    for m1, m2 in itertools.product(margins, repeat=2):
        for t1, t2 in itertools.product(thetas, repeat=2):
            votes = [VoteStats(m1), VoteStats(m2)]
            first = cascade_select(["a", "b", "c"], [t1, t2], votes)
            second = cascade_select(["a", "b", "c"], [t1, t2], votes)
            assert first == second
            expected = 0 if m1 >= t1 else (1 if m2 >= t2 else 2)
            assert first == expected, (m1, m2, t1, t2)


def test_cascade_tie_does_not_change_selection():
    """Ties affect representative choice (runtime), never the margin or the
    selected stage index."""
    assert cascade_select(
        ["cheap", "strong"], [0.5], [VoteStats(margin=0.6, tie=True)]
    ) == cascade_select(["cheap", "strong"], [0.5], [VoteStats(margin=0.6, tie=False)])


@pytest.mark.parametrize("verdict", P7_VERDICTS)
@pytest.mark.parametrize("beats", [False, True])
def test_p7_certificate_backed_target_trigger(verdict, beats):
    """§3.6 fifth disjunct: a consumed CVAR with a certificate-backed
    TargetProperty alone makes promotion strict."""
    outcome = promotion_outcome(_module(), [CERT_TARGET_CVAR], verdict, beats)
    assert outcome == NO_CERTIFIED_SELECTION
