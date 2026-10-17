"""Promotion joins validate every input and share precedence with the release gate."""

import itertools

import pytest

from tvl import promotion
from tvl.canonical import RuntimeClosedError
from tvl.runtime import join_promotion_decisions


@pytest.mark.parametrize("legacy", ["Promote", "NoDecision", "Reject"])
@pytest.mark.parametrize("verdicts", list(itertools.product(["MET", "BREACHED", "UNKNOWN", "UNKNOWN(engine_required)"], repeat=2)))
def test_gate_and_public_join_share_precedence(monkeypatch, legacy, verdicts):
    expected = (
        "Reject" if legacy == "Reject" or "BREACHED" in verdicts else
        "NoDecision" if legacy == "NoDecision" or any(v.startswith("UNKNOWN") for v in verdicts) else
        "Promote"
    )
    monkeypatch.setattr(promotion, "_make_legacy_decision", lambda _: (legacy, "Legacy explanation"))
    evidence = promotion.PromotionEvidence()
    evidence.promotion_monitors = {f"monitor_{i}": {"verdict": v} for i, v in enumerate(verdicts)}
    assert promotion._make_decision(evidence)[0] == expected
    assert join_promotion_decisions(legacy, verdicts) == expected


@pytest.mark.parametrize("legacy", ["", "promote", "MET", None, 1, []])
def test_invalid_legacy_decisions_are_rejected(legacy):
    with pytest.raises(RuntimeClosedError, match="^schema_error$"):
        join_promotion_decisions(legacy, ["MET"])


@pytest.mark.parametrize("verdict", ["", "met", "Promote", "Reject", "NoDecision", "UNKNOWN()",
                                    "UNKNOWN(incomplete", "UNKNOWN(incomplete)extra", "UNKNOWN(two words)",
                                    "UNKNOWN(incomplete)\n", None, 1, {}])
@pytest.mark.parametrize("legacy", ["Promote", "Reject"])
def test_invalid_verdicts_cannot_be_masked_by_a_rejection(monkeypatch, legacy, verdict):
    with pytest.raises(RuntimeClosedError, match="^schema_error$"):
        join_promotion_decisions(legacy, ["BREACHED", verdict])
    monkeypatch.setattr(promotion, "_make_legacy_decision", lambda _: (legacy, "Legacy explanation"))
    evidence = promotion.PromotionEvidence()
    evidence.promotion_monitors = {"monitor": {"verdict": verdict}}
    with pytest.raises(RuntimeClosedError, match="^schema_error$"):
        promotion._make_decision(evidence)


@pytest.mark.parametrize("verdicts", ["MET", None, 1, {"MET": True}])
def test_verdict_collection_must_be_a_sequence(verdicts):
    with pytest.raises(RuntimeClosedError, match="^schema_error$"):
        join_promotion_decisions("Promote", verdicts)


@pytest.mark.parametrize("legacy", ["Promote", "NoDecision", "Reject"])
def test_no_monitors_preserves_the_legacy_decision(legacy):
    assert join_promotion_decisions(legacy, []) == legacy
