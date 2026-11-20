"""DRAFT RFC 0011 Part A / RFC 0012 reference relation over recorded facts; never executes an action.

A sibling of ``tvl.runtime_trace`` (RFC 0004), reusing its closed-record helpers and its
optimize-outcome rule. One history is for one agent and environment. It is a pure,
deterministic relation: windows, events, attempt facts, acceptance records
go in; derived facts come out. No clock is read and no action is started.

Instants are whole seconds after ``history.origin`` (a whole-second UTC instant, second 0;
RFC 0011 §2.2 item 1): step instants are nonnegative, nondecreasing integers; several steps
may share an instant and are processed in order. Event ``issued_at`` is an integer and may
be negative (before the origin). Window bounds are seconds too, aligned to
``3600 * tumbling_hours``. Module instants (schedule ``anchor``, acceptance
``decided_at``/``expires_at``) are UTC strings, compared exactly in seconds against
``origin + seconds``. Nothing is rounded to hours.

Events of consecutive event-only steps sharing one whole-second instant are buffered and ordered once, so the
facts do not depend on how those events are split into steps; a step of that instant that carries windows,
optimizations or acceptances ends the batch. Within one step the order is: windows, schedule clock evaluation,
derived scope closures (an attempt whose scope ended while its optimization runs closes, keeping the spending lock
until its finish record), attempt facts (approvals, starts, finishes, deploy-gate rechecks), derived scope closures again
(a fact of the step cannot leave an expired scope deploy-eligible), acceptance records, external events in
(issued_at, issuer, event_id) order (RFC 0011 §2.2 item 5), then one dispatch of pending occurrences in
(trigger instant, response, rule id) order (§2.7) after the whole instant's event batch.

Recorded, not recomputed (as in ``runtime_trace``): window verdicts, the gate join inputs
of each candidate, platform authentication of events and acceptances and approver authority.
Computed here: breached-configuration sets per open episode (RFC 0011 §2.13 item 5), episode
opening, closure counting under ``closure_scope``, event admission, occurrence firing,
holds, attempt serialization, search domains, acceptance checks and head writes.
Release rollback is deferred out of TVL 1.7 (RFC 0012 §2.5) and is not part of this relation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from tvl.canonical import canonical_json_digest
from tvl.lints import _parse_collection, lint_module, parse_utc_instant
from tvl.promotion_join import join_promotion_decisions
from tvl.release_acceptance import validate_acceptance
from tvl.runtime_trace import TraceError, _enum, _optimize_outcome, _require, _shape

HOUR = 3600
LATE_SECONDS = 72 * HOUR
EXTERNAL_SCOPE_SECONDS = 30 * 24 * HOUR
_FAMILIES = "anthropic openai google meta mistral amazon"
_TIERS = "small medium large"


__all__ = ["conditions_trace", "occurrence_status", "scope_ref"]


def scope_ref(scope_kind: str, scope: Any) -> str:
    """The hosted ``scope_ref`` of a scope identity (RFC 0011 §2.13 item 10).

    ``external``: ``scope`` is ``(issuer, event_id)`` or the fact rendering ``{"issuer", "event_id"}``; the result is
    ``ext:`` plus the SHA-256 hex of ``{"event_id", "issuer"}`` under the canonical digest. ``episode`` (episode id)
    and ``schedule`` (tick index) scopes are their own opaque ref, as a string.
    """
    if scope_kind == "external":
        issuer, event_id = (scope["issuer"], scope["event_id"]) if isinstance(scope, dict) else scope
        return "ext:" + canonical_json_digest({"event_id": event_id, "issuer": issuer})
    return str(scope)


def _version(module: dict) -> tuple[int, int]:
    text = str(module.get("tvl_version", "1.3"))
    major, _, minor = text.partition(".")
    return int(major), int(minor or 0)


def _second(value: Any) -> None:
    _require(type(value) is int and value >= 0, "instants must be nonnegative integer seconds")


class _Attempt:
    def __init__(self, name: str, occ: dict, approved: bool):
        self.name = name
        self.occ = occ
        self.approved = approved
        self.declined = False
        self.finished = False
        self.promoted: dict | None = None
        self.awaiting_deploy = False
        self.recheck: str | None = None
        self.scope_closed = False
        self.open = True
        self.closed_reason: str | None = None
        # scope ended while the optimization ran: deploy eligibility is gone, the spending lock is not
        self.lock_held = False
        # an optimization actually began (a granted approval, a `started` fact, or a finish record implies it)
        self.started = False


class _Run:
    def __init__(self, module: dict, history: dict):
        _shape(history, "agent environment origin head steps", "contract_digest")
        errors = [i for i in lint_module(module) if i["severity"] == "error"]
        _require(not errors, f"invalid trace module: {errors}")
        self.module = module
        self.serialize = _version(module) >= (1, 7)
        origin = parse_utc_instant(history["origin"])
        _require(origin is not None, "origin must be a whole-second UTC instant")
        self.origin: datetime = origin  # type: ignore[assignment]
        self.agent, self.environment = history["agent"], history["environment"]
        _require(all(isinstance(v, str) and v for v in (self.agent, self.environment)), "agent and environment identities")
        self.contract_digest = history.get("contract_digest")
        head = history["head"]
        _shape(head, "fingerprint generation")
        _require(isinstance(head["fingerprint"], str) and type(head["generation"]) is int and head["generation"] >= 0,
                 "invalid initial head")
        self.heads: list[tuple[int, int, str]] = [(0, head["generation"], head["fingerprint"])]
        self.monitors = {m["name"]: m for m in module.get("monitors", [])}
        self.requirements = {r["name"]: r for r in module.get("requirements", [])}
        self.promotion_monitors = sorted(n for n, m in self.monitors.items() if m.get("phase") == "promotion")
        self.tvars = {t["name"]: t for t in module.get("tvars", [])}
        self.rules = [(r["name"], rule) for r in module.get("responses", []) for rule in r["rules"]]
        snap = parse_utc_instant((module.get("environment") or {}).get("snapshot_id"))
        self.facts: list[dict] = []
        self.now = 0
        self.seen_events: set[tuple[str, str]] = set()
        self.episodes: dict[str, dict] = {}  # monitor -> open episode
        self.episode_list: dict[str, dict] = {}  # id -> episode (open or closed)
        self.episode_count = 0
        self.pending: list[dict] = []
        self.occurrences: dict[tuple, dict] = {}
        self.attempts: list[_Attempt] = []
        self.attempt_count = 0
        self.last_tick: dict[tuple[str, str], int] = {}
        self.consumed: set[str] = set()
        self.seen_windows: set[tuple[str, int]] = set()
        self.fire_count = 0
        self.max_open = 0
        self.history_steps = history["steps"]
        del snap

    # -- helpers ---------------------------------------------------------------------------
    def emit(self, fact: str, **fields: Any) -> None:
        self.facts.append({"instant": self.now, "fact": fact, **fields})

    def at(self, second: int) -> datetime:
        return self.origin + timedelta(seconds=second)

    def head(self) -> tuple[int, str]:
        return self.heads[-1][1], self.heads[-1][2]

    def generation_at(self, second: int) -> int:
        """The generation serving at an instant: a head installed at ``t`` serves from ``t`` on."""
        gen = self.heads[0][1]
        for instant, generation, _ in self.heads:
            if instant <= second:
                gen = generation
        return gen

    def served_fingerprints(self, first: int, last: int) -> set[str]:
        """Head fingerprints that served any generation in first..last."""
        return {f for _, g, f in self.heads if first <= g <= last}

    def fingerprint_of(self, generation: int) -> str | None:
        return next((f for _, g, f in self.heads if g == generation), None)

    def open_attempts(self) -> list[_Attempt]:
        return [a for a in self.attempts if a.open]

    def lock_holders(self) -> list[_Attempt]:
        """Attempts holding the one-open-repair lock: open ones, and superseded ones whose optimization still runs."""
        return [a for a in self.attempts if a.open or a.lock_held]

    @staticmethod
    def render_scope(occ: dict) -> Any:
        """Injective rendering of a scope identity in facts (an external scope is a mapping, RFC 0011 §2.3)."""
        if occ["scope_kind"] == "external":
            issuer, event_id = occ["scope"]
            return {"issuer": issuer, "event_id": event_id}
        return occ["scope"]

    @staticmethod
    def scope_ref(occ: dict) -> str:
        """The opaque ``scope_ref`` an acceptance record uses for this scope; injective in the identity."""
        return scope_ref(occ["scope_kind"], occ["scope"])

    @classmethod
    def occ_ref(cls, occ: dict) -> dict:
        ref = {k: occ[k] for k in ("response", "rule", "scope_kind", "j")}
        ref["scope"] = cls.render_scope(occ)
        return {k: ref[k] for k in ("response", "rule", "scope_kind", "scope", "j")}

    def breached_fingerprints(self) -> set[str]:
        """Configurations that breached in some open episode of the agent (RFC 0011 §2.13 item 5)."""
        return set().union(*(ep["breached"] for ep in self.episodes.values())) if self.episodes else set()

    def find_rule(self, response: str, rule_id: str) -> dict:
        for name, rule in self.rules:
            if (name, rule["id"]) == (response, rule_id):
                return rule
        raise TraceError("unknown rule")

    def attempt(self, name: Any) -> _Attempt:
        for a in self.attempts:
            if a.name == name:
                return a
        raise TraceError("unknown attempt")

    # -- scopes -----------------------------------------------------------------------------
    def scope_active(self, occ: dict) -> bool:
        kind = occ["scope_kind"]
        if kind == "episode":
            ep = self.episode_list[occ["scope"]]
            return ep["open"]
        if kind == "external":
            return self.now - occ["admitted_at"] < EXTERNAL_SCOPE_SECONDS
        # schedule: until the next tick
        spec = self.find_rule(occ["response"], occ["rule"])["trigger"]["schedule"]
        nxt = self.tick_seconds(spec, int(occ["scope"]) + 1)
        return self.now < nxt

    def tick_seconds(self, spec: dict, k: int) -> int:
        anchor = parse_utc_instant(spec["anchor"])
        return int((anchor - self.origin).total_seconds()) + k * spec["every_days"] * 86400  # type: ignore[operator]

    # -- firing -----------------------------------------------------------------------------
    def fire(self, response: str, rule: dict, scope_kind: str, scope: str, extra: dict) -> None:
        key = (response, rule["id"], scope_kind, scope, 0)
        if key in self.occurrences:
            return  # one scope, one occurrence 0 (redelivery / duplicate tick)
        self.fire_count += 1
        occ = {"response": response, "rule": rule["id"], "scope_kind": scope_kind, "scope": scope, "j": 0,
               "trigger_instant": self.now, "held": False, "state": "pending", "seq": self.fire_count, **extra}
        self.occurrences[key] = occ
        self.emit("fired", occurrence=self.occ_ref(occ))
        if rule["do"] == "optimize":
            self.pending.append(occ)
        elif rule["do"] == "notify":
            self.emit("notified", occurrence=self.occ_ref(occ))

    def dispatch(self) -> None:
        # (trigger instant, response, rule id), ties in admission order (RFC 0011 §2.7, §2.13 item 2)
        self.pending.sort(key=lambda o: (o["trigger_instant"], o["response"], o["rule"], o["seq"]))
        for occ in list(self.pending):
            if not self.scope_active(occ):
                reason = "expired" if occ["scope_kind"] != "episode" else "scope_closed"
                self.pending.remove(occ)
                self.emit("dropped", occurrence=self.occ_ref(occ), reason=reason)
                continue
            if self.serialize and self.lock_holders():
                if not occ["held"]:
                    occ["held"] = True
                    self.emit("held", occurrence=self.occ_ref(occ), reason="repair_open")
                continue
            self.pending.remove(occ)
            self.start(occ)
        self.max_open = max(self.max_open, len(self.lock_holders()))

    def start(self, occ: dict) -> None:
        rule = self.find_rule(occ["response"], occ["rule"])
        self.attempt_count += 1
        attempt = _Attempt(f"A{self.attempt_count}", occ, rule.get("approval", "human") != "human")
        self.attempts.append(attempt)
        occ["state"] = "started"
        self.emit("attempt_opened", attempt=attempt.name, occurrence=self.occ_ref(occ))
        if "admit" in rule:
            tvar = rule["admit"]["tvar"]
            values = _parse_collection(self.tvars[tvar]["domain"])
            _require(values is not None and all(isinstance(v, str) for v in values), "admit tvar domain must list model refs")
            domain = list(values)  # type: ignore[arg-type]
            ref = occ["model_ref"]
            self.emit("search_domain", attempt=attempt.name, tvar=tvar,
                      domain=domain if ref in domain else domain + [ref])

    def close(self, attempt: _Attempt, reason: str) -> None:
        attempt.open = False
        attempt.closed_reason = reason
        self.emit("attempt_closed", attempt=attempt.name, reason=reason)

    def close_scope(self, kind: str, scope: str) -> None:
        for a in self.open_attempts():
            if a.occ["scope_kind"] == kind and a.occ["scope"] == scope:
                a.scope_closed = True
                if a.awaiting_deploy or not (a.approved and not a.finished) and not a.finished:
                    # nothing started that must still record a result: the effect never takes place
                    if a.awaiting_deploy or not a.approved:
                        self.close(a, "scope_closed")

    def release_expired_scopes(self) -> None:
        """An open attempt whose external or schedule scope stopped requiring intervention closes (RFC 0011 §2.13 item 6).

        Any phase: awaiting approval, optimizing (not interrupted; its result is later ignored) or awaiting a deploy.
        Episode scopes keep their own closure rules (``close_scope``) and only release a pending deploy here.
        """
        for a in self.open_attempts():
            if (a.occ["scope_kind"] != "episode" or a.awaiting_deploy) and not self.scope_active(a.occ):
                a.scope_closed = True
                self.close(a, "scope_expired")
                # RFC 0011 §2.13 item 6: an optimization already spending is not interrupted by TVL, so the
                # lock stays until its finish record (a confirmed cancellation is a finish record)
                a.lock_held = a.started and not a.finished

    # -- windows and episodes ---------------------------------------------------------------
    def window(self, rec: dict) -> None:
        _shape(rec, "monitor start end verdict head_generation")
        name = rec["monitor"]
        _require(name in self.monitors and self.monitors[name]["phase"] == "runtime", "window needs a runtime monitor")
        monitor = self.monitors[name]
        width = monitor["window"]["tumbling_hours"] * HOUR  # seconds
        for bound in (rec["start"], rec["end"]):
            _second(bound)
        _require(rec["end"] - rec["start"] == width and rec["start"] % width == 0, "window must be one aligned tumbling window")
        _require(rec["end"] <= self.now, "window ends after evaluation")
        _enum(rec["verdict"], "MET BREACHED UNKNOWN")
        _require(type(rec["head_generation"]) is int, "head_generation must be an integer")
        # half-open [start, end): a generation installed exactly at end did not serve the window (RFC 0011 §2.13 item 8)
        start_gen, end_gen = self.generation_at(rec["start"]), self.generation_at(rec["end"] - 1)
        _require(start_gen <= rec["head_generation"] <= end_gen,
                 "window head_generation outside the generations served during the window")
        # Mixed (RFC 0012 §2.4 Counting): the head moved inside the window, or the report names a generation other than
        # the one in effect at the window's start.
        mixed = start_gen != end_gen or rec["head_generation"] != start_gen
        episode_decl = monitor.get("episode") or {}
        scope_mode = episode_decl.get("closure_scope", "any_generation")
        ep = self.episodes.get(name)
        fields: dict[str, Any] = {"monitor": name, "start": rec["start"]}
        if (name, rec["start"]) in self.seen_windows:  # a redelivered window report counts once (RFC 0003 §7.4 item 1)
            return self.emit("window", closure="redelivery", **fields)
        self.seen_windows.add((name, rec["start"]))
        if rec["verdict"] == "BREACHED":
            if ep is None:
                self.episode_count += 1
                # The opening generation is the greatest generation that served the breaching window (RFC 0012 §2.4),
                # not the head at report arrival: a delayed report after a deploy must not raise it.
                ep = {"id": f"EP{self.episode_count}", "monitor": name, "open": True, "count": 0, "ends": [],
                      "opening_generation": end_gen, "breached": set(), "last_start": None, "last_gen": None,
                      "last_breach_start": rec["start"]}
                self.episodes[name] = ep
                self.episode_list[ep["id"]] = ep
                ep["breached"].update(self.served_fingerprints(start_gen, end_gen))
                self.emit("window", closure="breached", **fields)
                self.emit("episode_opened", monitor=name, episode=ep["id"], opening_generation=ep["opening_generation"])
                for response, rule in self.rules:
                    t = rule["trigger"]
                    if t.get("monitor") == name and t.get("event") == "episode_opened":
                        self.fire(response, rule, "episode", ep["id"], {})
            else:
                ep["count"], ep["ends"] = 0, []
                ep["last_breach_start"] = max(ep["last_breach_start"], rec["start"])
                ep["breached"].update(self.served_fingerprints(start_gen, end_gen))
                self.emit("window", closure="breached", **fields)
            return
        if ep is None:
            self.emit("window", closure="no_episode", **fields)
            return
        if rec["start"] < ep["last_breach_start"]:
            # a delayed report for a window before the latest breaching window cannot show recovery from it
            self.emit("window", closure="not_counted(before_breach)", **fields)
            return
        if rec["verdict"] == "UNKNOWN":
            ep["count"], ep["ends"] = 0, []
            self.emit("window", closure="unknown", **fields)
            return
        if scope_mode == "since_head_move" and mixed:
            ep["count"], ep["ends"] = 0, []
            self.emit("window", closure="UNKNOWN(mixed_generation)", **fields)
            return
        if scope_mode == "since_head_move" and rec["head_generation"] <= ep["opening_generation"]:
            ep["count"], ep["ends"] = 0, []
            self.emit("window", closure="not_counted(old_generation)", **fields)
            return
        if ep["count"] and rec["start"] != ep["last_start"] + width:  # a gap: closure needs consecutive windows
            ep["count"], ep["ends"] = 0, []
        if ep["count"] and scope_mode == "since_head_move" and rec["head_generation"] != ep["last_gen"]:
            # the run must be of one repair generation: a generation change restarts the count at this window
            ep["count"], ep["ends"] = 0, []
        ep["last_start"], ep["last_gen"] = rec["start"], rec["head_generation"]
        ep["count"] += 1
        ep["ends"].append(rec["end"])
        need = episode_decl["closure_windows"]
        self.emit("window", closure="counts", progress=min(ep["count"], need), of=need, **fields)
        max_age = episode_decl["closure_max_age_hours"] * HOUR
        if ep["count"] >= need and all(self.now - e <= max_age for e in ep["ends"][-need:]):
            ep["open"] = False
            del self.episodes[name]
            self.emit("episode_resolved", monitor=name, episode=ep["id"])
            self.close_scope("episode", ep["id"])

    # -- schedule ---------------------------------------------------------------------------
    def clock(self) -> None:
        for response, rule in self.rules:
            spec = rule["trigger"].get("schedule")
            if spec is None:
                continue
            first = self.tick_seconds(spec, 0)
            now_s = self.now
            if now_s < first:
                continue
            latest = (now_s - first) // (spec["every_days"] * 86400)
            done = self.last_tick.get((response, rule["id"]), -1)
            if latest <= done:
                continue
            for k in range(done + 1, latest):
                self.emit("skipped", response=response, rule=rule["id"], tick=k, reason="coalesced")
            self.last_tick[(response, rule["id"])] = latest
            self.fire(response, rule, "schedule", str(latest), {})

    # -- optimize facts ---------------------------------------------------------------------
    def optimization(self, rec: dict) -> None:
        _shape(rec, "attempt fact", "state completion candidates legacy_decision monitor_verdicts")
        attempt = self.attempt(rec["attempt"])
        fact = rec["fact"]
        if not attempt.open and attempt.closed_reason == "scope_expired":
            # RFC 0011 §2.13 item 6: a result or approval for an attempt whose scope ended is recorded, never acted on
            if fact == "finished" and attempt.lock_held:
                _shape(rec, "attempt fact completion candidates")
                self.finish_record(rec)  # same validation as a normal finish: a malformed record keeps the lock
                attempt.lock_held = False
                attempt.finished = True
            return self.emit("attempt_fact", attempt=attempt.name, kind=fact, result="ignored(scope_closed)")
        _require(attempt.open, "fact for a closed attempt")
        if fact == "approval":
            _shape(rec, "attempt fact state")
            _enum(rec["state"], "granted declined expired")
            _require(not attempt.finished, "approval after the optimization finished")
            if rec["state"] == "granted":
                attempt.approved = attempt.started = True
            else:
                attempt.declined = True
                self.emit("approval", attempt=attempt.name, state=rec["state"])
                self.close(attempt, "approval_" + rec["state"])
        elif fact == "started":
            # the optimizer actually began spending; a standing approval alone does not hold the lock after scope end
            _shape(rec, "attempt fact")
            _require(attempt.approved and not attempt.finished, "start needs an approved, unfinished attempt")
            attempt.started = True
        elif fact == "finished":
            _shape(rec, "attempt fact completion candidates")
            _require(attempt.approved and not attempt.finished, "optimization not running")
            converted, winner = self.finish_record(rec)
            event, promoted = _optimize_outcome(rec["completion"], converted)
            attempt.finished = attempt.started = True
            rule = self.find_rule(attempt.occ["response"], attempt.occ["rule"])
            self.emit("optimization_finished", attempt=attempt.name, outcome="promoted" if promoted else event)
            if event:
                self.emit("outcome", attempt=attempt.name, event=event)
                self.close(attempt, event)
            elif rule.get("deploy", "never") != "if_promoted" or attempt.scope_closed:
                self.close(attempt, "promoted_no_deploy")
            else:
                attempt.promoted = winner
                attempt.awaiting_deploy = True
                self.emit("deploy_awaiting", attempt=attempt.name, occurrence=self.occ_ref(attempt.occ),
                          candidate=winner["fingerprint"])
        elif fact == "deploy_gate":
            _shape(rec, "attempt fact legacy_decision monitor_verdicts")
            _require(attempt.awaiting_deploy, "deploy gate recheck needs a deploy awaiting acceptance")
            attempt.recheck = join_promotion_decisions(rec["legacy_decision"], self.gate_inputs(rec["monitor_verdicts"]))
        else:
            raise TraceError("unknown optimize fact")

    def finish_record(self, rec: dict) -> tuple[list, dict | None]:
        """Validate a finish record and return its converted candidates and the first promotable one.

        Shared by the normal finish path and by the finish of a superseded (draining) run: a malformed record is
        rejected (TraceError) in both, so it can never release the spending lock.
        """
        _enum(rec["completion"], "normal error cancelled cost_limit")
        _require(isinstance(rec["candidates"], list), "candidates must be a list")
        converted, winner = [], None
        for cand in rec["candidates"]:
            _shape(cand, "evidence_valid", "fingerprint gate_digest code_version legacy_decision monitor_verdicts holdout_digest")
            if cand["evidence_valid"] is True:
                _require(set(cand) - {"holdout_digest"} == {"evidence_valid", "fingerprint", "gate_digest", "code_version",
                                                            "legacy_decision", "monitor_verdicts"},
                         "valid candidate needs fingerprint, gate digest, code version and promotion join inputs")
                _require(isinstance(cand["code_version"], str) and cand["code_version"],
                         "code_version must be a nonempty string")
                _require("holdout_digest" not in cand or (isinstance(cand["holdout_digest"], str) and cand["holdout_digest"]),
                         "holdout_digest must be a nonempty string")
                verdicts = self.gate_inputs(cand["monitor_verdicts"])
                converted.append({"evidence_valid": True, "legacy_decision": cand["legacy_decision"], "monitor_verdicts": verdicts})
                if winner is None and join_promotion_decisions(cand["legacy_decision"], verdicts) == "Promote":
                    winner = cand
            else:
                converted.append(dict(cand))
        return converted, winner

    def gate_inputs(self, verdicts: Any) -> list[str]:
        _require(isinstance(verdicts, dict) and sorted(verdicts) == self.promotion_monitors,
                 "the gate join covers every promotion monitor of the module (RFC 0011 §2.6)")
        return [verdicts[n] for n in self.promotion_monitors]

    # -- acceptances ------------------------------------------------------------------------
    def acceptance(self, rec: dict) -> None:
        _require(isinstance(rec, dict) and {"record", "authenticated", "approver_authorized", "serving_code_version"} == set(rec),
                 "acceptance input needs record, authenticated, approver_authorized, serving_code_version")
        _require(isinstance(rec["serving_code_version"], str) and rec["serving_code_version"],
                 "serving_code_version must be a nonempty string")
        doc = rec["record"]
        _require(type(rec["authenticated"]) is bool and type(rec["approver_authorized"]) is bool, "booleans expected")
        ident = doc.get("acceptance_id") if isinstance(doc, dict) else None
        _require(isinstance(self.contract_digest, str) and self.contract_digest,
                 "the history must carry the authoritative contract_digest to evaluate acceptances (RFC 0012 §2.3)")

        def result(res: str, reason: str | None = None, **more: Any) -> None:
            extra = {"reason": reason} if reason else {}
            self.emit("acceptance", acceptance=ident, result=res, **extra, **more)

        if isinstance(ident, str) and ident in self.consumed:
            return result("consumed")
        if validate_acceptance(doc):
            return result("invalid", "schema")
        if not rec["authenticated"]:
            return result("invalid", "unauthenticated")
        if not rec["approver_authorized"]:
            return result("invalid", "unauthorized")
        decided, expires = parse_utc_instant(doc["decided_at"]), parse_utc_instant(doc["expires_at"])
        moment = self.at(self.now)
        if moment >= expires:  # type: ignore[operator]
            return result("invalid", "expired")
        if moment < decided:  # type: ignore[operator]
            return result("invalid", "not_yet_usable")
        if doc["rollback_target"] != self.fingerprint_of(doc["expected_head_generation"]):
            return result("invalid", "rollback_target_mismatch")
        occ_rec = doc["occurrence"]
        target = next((a for a in self.open_attempts() if a.awaiting_deploy and a.occ["response"] == occ_rec["response_ref"]
                       and a.occ["rule"] == occ_rec["rule_ref"] and a.occ["scope_kind"] == occ_rec["scope_kind"]
                       and self.scope_ref(a.occ) == occ_rec["scope_ref"] and a.occ["j"] == occ_rec["occurrence"]), None)
        if target is None:
            closed = any(a.closed_reason in ("scope_expired", "scope_closed") and a.awaiting_deploy
                         and a.occ["response"] == occ_rec["response_ref"] and a.occ["rule"] == occ_rec["rule_ref"]
                         and a.occ["scope_kind"] == occ_rec["scope_kind"] and self.scope_ref(a.occ) == occ_rec["scope_ref"]
                         and a.occ["j"] == occ_rec["occurrence"] for a in self.attempts)
            if closed:  # RFC 0011 §2.13 item 7: closure precedes acceptances and yields no outcome (RFC 0004 §2.2)
                return result("ignored(scope_closed)")
            return result("invalid", "no_deploy_awaiting")
        if (doc["agent_ref"], doc["environment_ref"]) != (self.agent, self.environment) \
                or doc["candidate_fingerprint"] != target.promoted["fingerprint"] \
                or doc["gate_result_digest"] != target.promoted["gate_digest"] \
                or doc["contract_digest"] != self.contract_digest \
                or doc["agent_code_version"] != target.promoted["code_version"] \
                or doc.get("holdout_digest") != target.promoted.get("holdout_digest") \
                or doc.get("repairs_episode") != (target.occ["scope"] if target.occ["scope_kind"] == "episode" else None):
            return result("invalid", "binding_mismatch")
        if doc["decision"] == "reject":
            self.consumed.add(ident)
            result("reject_recorded")
            return self.close(target, "deploy_rejected")
        # accept: effect-time checks (RFC 0003 §7.6 item 3 with the originating scope, RFC 0012 §2.3)
        refusal = None
        if target.recheck is not None and target.recheck != "Promote":
            refusal = "gate_not_promote"
        else:
            generation, fingerprint = self.head()
            if generation != doc["expected_head_generation"]:
                refusal = "stale_generation"
            elif fingerprint != doc["rollback_target"]:
                refusal = "rollback_target_mismatch"
            elif doc["agent_code_version"] != rec["serving_code_version"]:
                refusal = "code_version_mismatch"
            elif doc["candidate_fingerprint"] in self.breached_fingerprints():
                refusal = "candidate_breached_in_open_episode"
        if refusal:
            result("refused", refusal)
            self.emit("outcome", attempt=target.name, event="deploy_refused", reason=refusal)
            return self.close(target, "deploy_refused")
        generation, _ = self.head()
        self.heads.append((self.now, generation + 1, doc["candidate_fingerprint"]))
        self.consumed.add(ident)
        result("written", generation=generation + 1)
        self.close(target, "deploy_written")

    # -- external events --------------------------------------------------------------------
    def event(self, ev: dict) -> tuple | None:
        _shape(ev, "kind event_id issuer issued_at catalogue_revision subject authenticated")
        _enum(ev["kind"], "model_released")
        for key in ("event_id", "issuer"):
            _require(isinstance(ev[key], str) and ev[key], "event ids are nonempty strings")
        _require(type(ev["issued_at"]) is int, "issued_at is an integer number of seconds after the origin")
        _require(type(ev["catalogue_revision"]) is int and ev["catalogue_revision"] >= 1, "catalogue_revision positive")
        _require(type(ev["authenticated"]) is bool, "authenticated must be boolean")
        sub = ev["subject"]
        _shape(sub, "model_ref provider_family tier")
        _require(isinstance(sub["model_ref"], str) and sub["model_ref"], "model_ref is an opaque id")
        _enum(sub["provider_family"], _FAMILIES)
        _enum(sub["tier"], _TIERS)
        return (ev["issued_at"], ev["issuer"], ev["event_id"])

    def process_event(self, ev: dict) -> None:
        name = {"issuer": ev["issuer"], "event_id": ev["event_id"]}
        if not ev["authenticated"]:
            return self.emit("event", event=name, result="rejected(unauthenticated)")
        if (ev["issuer"], ev["event_id"]) in self.seen_events:
            return self.emit("event", event=name, result="redelivery")
        if self.now - ev["issued_at"] > LATE_SECONDS:
            return self.emit("event", event=name, result="rejected(late)")
        self.seen_events.add((ev["issuer"], ev["event_id"]))
        self.emit("event", event=name, result="admitted")
        matched = False
        sub = ev["subject"]
        for response, rule in self.rules:
            trigger = rule["trigger"]
            if trigger.get("external") != ev["kind"]:
                continue
            match = trigger.get("match", {})
            if sub["provider_family"] not in match.get("provider_family", [sub["provider_family"]]):
                continue
            if sub["tier"] not in match.get("tier", [sub["tier"]]):
                continue
            matched = True
            self.fire(response, rule, "external", (ev["issuer"], ev["event_id"]), {"model_ref": sub["model_ref"], "admitted_at": self.now})
        if not matched:
            self.emit("no_match", event=name)

    # -- driver -----------------------------------------------------------------------------
    def run(self) -> dict:
        _require(isinstance(self.history_steps, list), "steps must be a list")
        heads_out: list[dict] = []
        previous = 0
        instant_events: list[dict] = []
        for index, step in enumerate(self.history_steps):
            _shape(step, "instant", "windows optimizations acceptances events")
            _second(step["instant"])
            _require(step["instant"] >= previous, "step instants must not decrease")
            previous = self.now = step["instant"]
            for category in ("windows", "optimizations", "acceptances", "events"):
                _require(isinstance(step.get(category, []), list), "step facts must be lists")
            for rec in step.get("windows", []):
                self.window(rec)
            self.clock()
            self.release_expired_scopes()  # derived closures precede attempt facts and acceptances (RFC 0011 §2.13 item 7)
            for rec in step.get("optimizations", []):
                self.optimization(rec)
            self.release_expired_scopes()  # again: a fact of this step may not leave an expired scope deploy-eligible
            for rec in step.get("acceptances", []):
                self.acceptance(rec)
            instant_events.extend(step.get("events", []))
            for ev in step.get("events", []):
                self.event(ev)  # validate now; order and process once the whole instant is in
            nxt = self.history_steps[index + 1] if index + 1 < len(self.history_steps) else None
            if isinstance(nxt, dict) and nxt.get("instant") == self.now \
                    and not any(nxt.get(c) for c in ("windows", "optimizations", "acceptances")):
                # a following step of the same instant that only delivers events joins this batch: the instant's
                # events are ordered across all of them (RFC 0011 §2.2 item 5). A step that carries evaluations
                # is a later observation of the instant and ends the batch. Dispatch runs once, after the whole batch.
                continue
            for ev in sorted(instant_events, key=self.event):
                self.process_event(ev)
            instant_events = []
            self.dispatch()
            if heads_out and heads_out[-1]["instant"] == self.now:
                heads_out.pop()
            heads_out.append({"instant": self.now, "generation": self.head()[0]})
        return {"facts": self.facts, "head_generations": heads_out, "max_open_attempts": self.max_open}


def conditions_trace(module: dict, history: dict) -> dict:
    """Return ``{facts, head_generations, max_open_attempts}`` for a recorded history.

    ``facts`` is the ordered list of derived facts; ``head_generations`` has one
    ``{instant, generation}`` per distinct step instant (generation after that instant).
    """
    return _Run(module, history).run()


def occurrence_status(module: dict, history: dict, occurrence: dict) -> dict:
    """State of one occurrence after evaluating ``history`` (evaluated at the last step's instant).

    ``occurrence`` is an occurrence reference as rendered in facts: ``response``, ``rule``, ``scope_kind``, ``scope``
    (an external scope is ``{"issuer", "event_id"}``) and ``j``. Returns ``{scope_active, attempt, phase,
    closed_reason}``: ``phase`` is ``awaiting_approval``, ``optimizing``, ``awaiting_deploy`` or ``closed`` (``None``
    with ``attempt`` ``None`` when no attempt has opened); ``closed_reason`` is the ``attempt_closed`` reason.
    An occurrence that never fired has ``scope_active`` false.
    """
    run = _Run(module, history)
    facts = run.run()["facts"]
    want = _Run.occ_ref({"response": occurrence["response"], "rule": occurrence["rule"],
                         "scope_kind": occurrence["scope_kind"], "scope": _raw_scope(occurrence), "j": occurrence["j"]})
    occ = next((o for o in run.occurrences.values() if run.occ_ref(o) == want), None)
    status: dict = {"scope_active": False, "attempt": None, "phase": None, "closed_reason": None}
    if occ is None:
        return status
    status["scope_active"] = bool(run.scope_active(occ))
    opened = [f["attempt"] for f in facts if f["fact"] == "attempt_opened" and f["occurrence"] == want]
    if not opened:
        return status
    attempt = run.attempt(opened[-1])
    status["attempt"] = attempt.name
    if not attempt.open:
        status["phase"], status["closed_reason"] = "closed", attempt.closed_reason
    elif attempt.awaiting_deploy:
        status["phase"] = "awaiting_deploy"
    elif attempt.approved and not attempt.finished:
        status["phase"] = "optimizing"
    else:
        status["phase"] = "awaiting_approval"
    return status


def _raw_scope(occurrence: dict) -> Any:
    scope = occurrence["scope"]
    if occurrence["scope_kind"] == "external" and isinstance(scope, dict):
        return (scope["issuer"], scope["event_id"])
    if occurrence["scope_kind"] == "external":
        return tuple(scope)
    return str(scope)
