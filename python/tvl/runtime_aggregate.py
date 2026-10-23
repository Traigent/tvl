"""RFC 0005 reference relations over recorded facts; never executes an action.

Two pure relations and two exchange checks:

* ``persistence_result``: the k-of-n completion semantics of breach persistence
  (formal semantics 14.1) over finalized window slots, and ``persistence_decisions``
  for the per-occurrence notification ledger.
* ``aggregate_verdict``: the exact census sum/mean comparison (14.2-14.3) over a
  recorded population, with exact rational arithmetic and no rounded quotient.
* ``validate_report_v2``: the closed count identities and window/source binding of
  ``tvl-runtime-report/2`` (RFC 0005 2.5).
* ``units_commitment_v2``: the keyed commitment of report/2 (``units_commitment_v1`` is the
  unchanged report/1 digest).

Nothing here reads a clock, a network or a customer store; every input is a recorded
fact. Results are conformance relations, not an evaluator.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from fractions import Fraction
from typing import Any, Mapping, Sequence

from tvl.canonical import RuntimeClosedError, canonical_json_bytes, minimal_decimal_str, to_fraction
from tvl.schema import runtime_report_v2_validator

PERSIST_MAX = 168
_VERDICTS = ("MET", "BREACHED", "UNKNOWN")
_DECIMAL_RE = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]+)?")
_MINIMAL_DECIMAL_RE = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]*[1-9])?")
# Longest accepted numeric encoding (characters); longer inputs are a precision limit, never converted.
_MAX_NUMERIC_CHARS = 256
_IDENTITY_FIELDS = ("contract_digest", "monitor_revision", "agent", "environment", "schedule")


class AggregateError(ValueError):
    """An unsupported or inconsistent recorded fact (never silently ignored)."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AggregateError(message)


def _shape(value: Any, required: str, optional: str = "") -> None:
    _require(isinstance(value, Mapping), "record must be a mapping")
    _require(set(required.split()) <= value.keys(), f"missing fields: {required}")
    _require(value.keys() <= set((required + " " + optional).split()), "unknown record field")


def _nat(value: Any) -> bool:
    return type(value) is int and value >= 0


# ---------------------------------------------------------------------------
# Breach persistence
# ---------------------------------------------------------------------------


def persistence_result(k: int, n: int, slots: Sequence[str]) -> tuple[str, str | None]:
    """Return (result, reason) for ``breached_in: k`` of the last ``of_last: n`` slots."""
    _require(type(k) is int and type(n) is int and 1 <= k <= n <= PERSIST_MAX, "persist out of range")
    _require(len(slots) == n, "history must contain exactly n slots")
    _require(all(slot in _VERDICTS for slot in slots), "slots are MET, BREACHED or UNKNOWN")
    breached = sum(slot == "BREACHED" for slot in slots)
    unknown = sum(slot == "UNKNOWN" for slot in slots)
    if breached >= k:
        return "BREACHED", None
    if breached + unknown < k:
        return "MET", None
    return "UNKNOWN", "inconclusive"


def persistence_slots(n: int, index: int, windows: Sequence[Mapping[str, Any]],
                      identity: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The n consecutive tumbling slots ending at window ``index``, oldest first.

    A window counts only when finalized, explicitly available and recorded under the same
    contract digest, monitor revision, agent, environment and schedule as ``identity``. A window
    that omits any of those identity fields, or ``available``, is not trusted: every other
    position is an UNKNOWN placeholder with reason ``persistence_history_gap`` and is never
    replaced by an older decided window.
    """
    _require(isinstance(identity, Mapping) and all(field in identity for field in _IDENTITY_FIELDS),
             "identity names contract_digest, monitor_revision, agent, environment and schedule")
    by_index: dict[int, Mapping[str, Any]] = {}
    for window in windows:
        _shape(window, "index verdict", "available reason charge horizon " + " ".join(_IDENTITY_FIELDS))
        _require(_nat(window["index"]) and window["index"] not in by_index, "window indexes are unique naturals")
        _require(window["verdict"] in _VERDICTS, "window verdict is MET, BREACHED or UNKNOWN")
        by_index[window["index"]] = window
    slots: list[dict[str, Any]] = []
    for position in range(index - n + 1, index + 1):
        window = by_index.get(position)
        usable = (
            window is not None
            and window.get("available") is True
            and all(field in window and window[field] == identity[field] for field in _IDENTITY_FIELDS)
        )
        if not usable:
            slots.append({"index": position, "verdict": "UNKNOWN", "reason": "persistence_history_gap"})
            continue
        slot = {"index": position, "verdict": window["verdict"]}
        if window["verdict"] == "UNKNOWN":
            slot["reason"] = window.get("reason", "inconclusive")
        if "charge" in window:
            slot["charge"] = window["charge"]
        slots.append(slot)
    return slots


def persistence_decisions(persist: Mapping[str, Any], rule_event: str, windows: Sequence[Mapping[str, Any]],
                          events: Sequence[Mapping[str, Any]], identity: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Customer-side ledger of one persistence rule over one episode.

    ``rule_event`` is the rule's trigger event. The first fresh event of that kind allocates
    occurrence 0 even when it is not delivered. A rule whose trigger is ``episode_continued``
    may reconsider that same undelivered occurrence at a later fresh continuation and allocates
    no new one; a rule on ``episode_opened`` is never re-delivered at a continuation (a rule
    keeps its original trigger). A delivered occurrence is never delivered again. An event is allowed only at a window whose own
    verdict is BREACHED. An exact replay (``replay_of``) returns the original decision.
    """
    _shape(persist, "breached_in of_last")
    k, n = persist["breached_in"], persist["of_last"]
    _require(rule_event in {"episode_opened", "episode_continued"}, "persist needs an episode trigger")
    by_index = {w["index"]: w for w in windows if isinstance(w, Mapping) and "index" in w}
    decisions: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    occurrence_allocated = False
    delivered = False
    for event in events:
        _shape(event, "id window event", "replay_of only_while unless")
        source_event = event["event"]
        _require(source_event in {"episode_opened", "episode_continued"}, "unknown source event")
        if "replay_of" in event:
            _require(event["replay_of"] in by_id, "a replay names an earlier event")
            entry = dict(by_id[event["replay_of"]], event_id=event["id"], replay=True, delivered=False, notified=False)
            decisions.append(entry)
            by_id[event["id"]] = entry
            continue
        _require(event["id"] not in by_id, "event ids are unique")
        _require(by_index.get(event["window"], {}).get("verdict") == "BREACHED",
                 "an allowed breach event sits at a BREACHED window")
        slots = persistence_slots(n, event["window"], windows, identity)
        result, reason = persistence_result(k, n, [slot["verdict"] for slot in slots])
        starts = not occurrence_allocated and source_event == rule_event
        # The rule keeps its original trigger: only an episode_continued rule is evaluated at a continuation.
        reconsiders = occurrence_allocated and rule_event == "episode_continued" and source_event == "episode_continued"
        # Guards (RFC 0004) resolve after qualification; UNDECIDED (None) never suppresses.
        only_while, unless = event.get("only_while", []), event.get("unless", [])
        _require(all(v in (True, False, None) for v in [*only_while, *unless]), "guard values are true, false or null")
        guards_pass = False not in only_while and True not in unless
        entry: dict[str, Any] = {"event_id": event["id"], "result": result, "replay": False, "notified": False}
        if reason:
            entry["reason"] = reason
        if starts:
            occurrence_allocated = True
        if not (starts or reconsiders):
            entry["decision"] = "not_eligible"
            entry["delivered"] = False
        elif delivered:
            entry.update(occurrence=0, decision="already_delivered", delivered=False)
        else:
            entry["occurrence"] = 0
            entry["decision"] = {"BREACHED": "qualified", "MET": "suppressed", "UNKNOWN": "withheld"}[result]
            entry["notified"] = result == "BREACHED" and guards_pass
            entry["delivered"] = entry["notified"]
            delivered = delivered or entry["delivered"]
        decisions.append(entry)
        by_id[event["id"]] = entry
    return decisions


# ---------------------------------------------------------------------------
# Census aggregates
# ---------------------------------------------------------------------------


class _PrecisionLimit(Exception):
    """A numeric encoding longer than the reference relation converts (never a crash)."""


def _decimal(value: Any) -> Fraction | None:
    """Exact value of a lossless finite decimal encoding, else None (invalid).

    Raises ``_PrecisionLimit`` before any conversion when the encoding exceeds the length limit.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if value >= 10 ** _MAX_NUMERIC_CHARS:
            raise _PrecisionLimit
        return Fraction(value) if value >= 0 else None
    if isinstance(value, str):
        if len(value) > _MAX_NUMERIC_CHARS:
            raise _PrecisionLimit
        return Fraction(value) if _DECIMAL_RE.fullmatch(value) else None
    return None


def _scale(value: str | int) -> int:
    text = str(value)
    return len(text.split(".")[1]) if "." in text else 0


def _membership_valid(value: Any) -> bool:
    return value is True or value is False or (isinstance(value, str) and value == "unknown")


def aggregate_verdict(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Exact verdict of a census sum/mean over recorded units (formal semantics 14.2-14.3).

    The census is complete only when the ``coverage`` block is present and attests every
    completeness flag with a watermark at or past due; a missing or null block is incomplete
    evidence (UNKNOWN), never complete by default. A unit that arrives after due, and every
    unit record that is invalid, also makes the census incomplete.
    """
    _shape(spec, "op metric bound window evaluated_at_ms units", "coverage precision_scale")
    op, metric = spec["op"], spec["metric"]
    _require(op in {"sum", "mean"} and metric in {"cost_usd", "score"}, "unknown operator or metric")
    bound = spec["bound"]
    _require(isinstance(bound, Mapping) and len(bound) == 1 and set(bound) <= {"lte", "gte"}, "exactly one bound")
    direction = next(iter(bound))
    raw_bound = bound[direction]
    _require(not (isinstance(raw_bound, str) and len(raw_bound) > _MAX_NUMERIC_CHARS), "bound encoding is too long")
    try:
        bound_value = to_fraction(raw_bound)  # exact decimal literal recovery
    except RuntimeClosedError:
        bound_value = None
    _require(bound_value is not None and bound_value >= 0, "bounds are nonnegative decimals")
    _require(not (op == "mean" and metric == "score" and bound_value > 1), "mean score bound is at most 1")
    window = spec["window"]
    _shape(window, "start_ms end_ms grace_ms")
    due = window["end_ms"] + window["grace_ms"]
    if spec["evaluated_at_ms"] < due:
        return {"verdict": "UNKNOWN", "reason": "aggregate_pending"}

    coverage = spec.get("coverage")
    complete = False  # absent or null coverage is incomplete evidence
    if coverage is not None:
        _shape(coverage, "census unit_histories_complete producer_set_complete producer_sequences_contiguous "
                         "response_deadlines_covered watermark_ms")
        complete = (
            all(coverage[key] is True for key in coverage if key != "watermark_ms")
            and type(coverage["watermark_ms"]) is int and coverage["watermark_ms"] >= due
        )

    limit = spec.get("precision_scale")
    precision_hit = False
    seen: dict[str, tuple[Any, Any, Any]] = {}
    members: dict[str, Fraction] = {}
    scales: list[int] = []
    late: list[tuple[str, tuple[Any, Any, Any]]] = []
    for unit in spec["units"]:
        _shape(unit, "key membership status", "value arrived_ms")
        _require(isinstance(unit["key"], str) and unit["key"], "units have a stable identifier")
        _require(unit["status"] in {"completed", "failed", "rejected"}, "unit status is terminal")
        if not _membership_valid(unit["membership"]):
            complete = False  # an invalid record is never silently an exclusion
            continue
        value = unit.get("value")
        exact: Fraction | None = None
        over_long = False
        if unit["membership"] is True:
            try:
                exact = _decimal(value)
            except _PrecisionLimit:
                over_long = True
        # Values compare after exact decimal parsing, so "1" and "1.0" are one identical replay.
        fingerprint = (unit["membership"], ("exact", exact) if exact is not None else ("raw", type(value).__name__, value),
                       unit["status"])
        if "arrived_ms" in unit:
            if not _nat(unit["arrived_ms"]):
                complete = False
                continue
            if unit["arrived_ms"] > due:
                late.append((unit["key"], fingerprint))
                continue
        if unit["key"] in seen:
            if seen[unit["key"]] != fingerprint:
                complete = False  # conflicting duplicate histories or values
            continue
        seen[unit["key"]] = fingerprint
        if unit["membership"] == "unknown":
            complete = False
        elif unit["membership"] is True:
            if over_long:
                precision_hit = True  # decided only if the rest of the census is complete
                continue
            if exact is None or (metric == "score" and exact > 1):
                complete = False  # a missing or invalid value is never zero
            else:
                members[unit["key"]] = exact
                scales.append(_scale(value))
    for key, fingerprint in late:
        # Evidence after due never changes the finalized sum; it is a replay only when identical.
        if seen.get(key) != fingerprint:
            complete = False
    if not complete:
        return {"verdict": "UNKNOWN", "reason": "incomplete"}
    if precision_hit:
        return {"verdict": "UNKNOWN", "reason": "aggregate_precision_limit"}
    if not members:
        return {"verdict": "UNKNOWN", "reason": "insufficient"}
    total = sum(members.values(), Fraction(0))
    if limit is not None and max([*scales, _scale(minimal_decimal_str(bound_value))]) > limit:
        return {"verdict": "UNKNOWN", "reason": "aggregate_precision_limit"}
    count = len(members)
    # For mean, compare S with C * bound: equal to S / C against bound because C > 0, no division.
    limit_value = bound_value * (count if op == "mean" else 1)
    holds = total <= limit_value if direction == "lte" else total >= limit_value
    return {"verdict": "MET" if holds else "BREACHED", "sum": minimal_decimal_str(total), "member_count": count}


# ---------------------------------------------------------------------------
# report/2 exchange
# ---------------------------------------------------------------------------


def validate_report_v2(report: Mapping[str, Any], binding: Mapping[str, Any]) -> dict[str, str] | None:
    """Check a tvl-runtime-report/2 against its registration; raise a closed code on refusal.

    ``binding`` carries the registered contract_digest, monitor_ref, monitor_revision,
    source_digest, window_hours and grace_ms. No input is echoed in the error. Returns None for
    an accepted report, or the verdict ``UNKNOWN(aggregate_precision_limit)`` for a complete report
    that omits ``sum`` and carries ``unknown_reason: "aggregate_precision_limit"``.
    """
    if list(runtime_report_v2_validator().iter_errors(dict(report))):
        raise RuntimeClosedError("schema_error")
    counts = report["counts"]
    due = report["window_end_ms"] + binding["grace_ms"]
    width = binding["window_hours"] * 3_600_000
    if (
        report["window_end_ms"] - report["window_start_ms"] != width
        or report["window_start_ms"] % width != 0
        or any(report[key] != binding[key] for key in ("contract_digest", "monitor_ref", "monitor_revision", "source_digest"))
    ):
        raise RuntimeClosedError("runtime_report_conservation")
    if (
        counts["selected"] != counts["reported"] + counts["dropped"]
        or counts["reported"] != counts["member_count"] + counts["unknown_membership"] + counts["unplaceable"] + counts["excluded"]
        or counts["member_count"] != counts["contribution_count"] + counts["missing_value"] + counts["invalid_value"]
    ):
        raise RuntimeClosedError("runtime_report_conservation")
    coverage = report["coverage"]
    complete = (
        all(coverage[key] is True for key in coverage if key != "watermarks_through_ms")
        and coverage["watermarks_through_ms"] is not None and coverage["watermarks_through_ms"] >= due
        and counts["dropped"] == 0 and counts["unknown_membership"] == 0 and counts["unplaceable"] == 0
        and counts["missing_value"] == 0 and counts["invalid_value"] == 0
    )
    unknown_reason = report.get("unknown_reason")
    if counts["member_count"] == 0 and "sum" in report:
        raise RuntimeClosedError("runtime_report_numeric")  # an empty population has no sum, not even zero
    if "sum" in report:
        value = report["sum"]
        if not isinstance(value, str) or not _MINIMAL_DECIMAL_RE.fullmatch(value) or unknown_reason is not None:
            raise RuntimeClosedError("runtime_report_numeric")
        return None
    if unknown_reason is not None:
        # The only exception: a complete, nonempty report whose exact sum exceeds the producer's precision.
        if not (complete and counts["member_count"] > 0) or unknown_reason != "aggregate_precision_limit":
            raise RuntimeClosedError("runtime_report_numeric")
        return {"verdict": "UNKNOWN", "reason": "aggregate_precision_limit"}
    if complete and counts["member_count"] > 0:
        raise RuntimeClosedError("runtime_report_numeric")
    return None


def units_commitment_v1(units: Sequence[Mapping[str, Any]]) -> str:
    """Unchanged report/1 digest: SHA-256 of the canonical JSON of {unit_id, class} sorted by unit_id."""
    listed = sorted(({"unit_id": u["unit_id"], "class": u["class"]} for u in units), key=lambda u: u["unit_id"])
    return hashlib.sha256(canonical_json_bytes(listed)).hexdigest()


def units_commitment_v2(secret: bytes, report: Mapping[str, Any], units: Sequence[Mapping[str, Any]]) -> str:
    """Keyed commitment of report/2: HMAC-SHA-256 over the bound canonical payload.

    ``secret`` is the customer-held random 256-bit key. Each unit carries its full local key
    (agent, environment, unit_kind, unit_id), membership, canonical exact value or its
    missing/invalid state, and the source digest. Units are deduplicated and sorted by the UTF-8 bytes of the canonical JSON of the key object.
    """
    _require(isinstance(secret, bytes) and len(secret) == 32, "the secret is 256 bits")
    entries: dict[bytes, dict[str, Any]] = {}
    for unit in units:
        _shape(unit, "agent environment unit_kind unit_id membership state source_digest", "value")
        _require(_membership_valid(unit["membership"]) and unit["state"] in {"valid", "missing", "invalid"},
                 "closed membership and state")
        entry = {
            "key": {key: unit[key] for key in ("agent", "environment", "unit_kind", "unit_id")},
            "membership": unit["membership"],
            "state": unit["state"],
            "source_digest": unit["source_digest"],
        }
        if unit["state"] == "valid":
            _require("value" in unit, "a valid unit carries its value")
            try:
                entry["value"] = minimal_decimal_str(unit["value"])
            except (RuntimeClosedError, ValueError, TypeError) as exc:
                raise AggregateError("a valid unit carries a decimal value") from exc
        # Identity and order: the canonical JSON bytes of the key object (agent, environment, unit_id, unit_kind).
        local_key = canonical_json_bytes(entry["key"])
        _require(entries.setdefault(local_key, entry) == entry, "conflicting duplicate unit")
    payload = {
        **{key: report[key] for key in ("contract_digest", "monitor_ref", "monitor_revision",
                                         "window_start_ms", "window_end_ms", "source_digest")},
        "units": [entries[key] for key in sorted(entries)],
    }
    return hmac.new(secret, canonical_json_bytes(payload), hashlib.sha256).hexdigest()
