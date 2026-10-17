"""Validate and join legacy promotion decisions with declared monitor verdicts."""

from __future__ import annotations

import re
from typing import Sequence

from tvl.canonical import RuntimeClosedError


def join_promotion_decisions(
    legacy_decision: str,
    monitor_verdicts: Sequence[str],
) -> str:
    """Join valid inputs with Reject > NoDecision > Promote precedence.

    ``UNKNOWN(reason)`` accepts a nonempty, lower-case reason identifier. All
    inputs are validated before joining, including when rejection already wins.
    """
    if not isinstance(legacy_decision, str) or legacy_decision not in {"Promote", "Reject", "NoDecision"}:
        raise RuntimeClosedError("schema_error", path=["legacy_decision"])
    if isinstance(monitor_verdicts, (str, bytes)) or not isinstance(monitor_verdicts, Sequence):
        raise RuntimeClosedError("schema_error", path=["monitor_verdicts"])
    verdicts = []
    for index, verdict in enumerate(monitor_verdicts):
        if not isinstance(verdict, str):
            raise RuntimeClosedError("schema_error", path=["monitor_verdicts", index])
        if re.fullmatch(r"UNKNOWN\([a-z][a-z0-9_]*\)", verdict):
            verdict = "UNKNOWN"
        if verdict not in {"MET", "BREACHED", "UNKNOWN"}:
            raise RuntimeClosedError("schema_error", path=["monitor_verdicts", index])
        verdicts.append(verdict)
    if legacy_decision == "Reject" or "BREACHED" in verdicts:
        return "Reject"
    if legacy_decision == "NoDecision" or "UNKNOWN" in verdicts:
        return "NoDecision"
    return legacy_decision
