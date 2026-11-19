"""DRAFT RFC 0011 Part A / RFC 0012 reference relation over recorded facts; never executes an action.

A sibling of ``tvl.runtime_trace`` (RFC 0004), reusing its closed-record helpers and its
optimize-outcome rule. One history is for one agent and environment. It is a pure,
deterministic relation: windows, events, attempt facts, acceptance records and recovery
facts go in; derived facts come out. No clock is read and no action is started.

Instants are integer lifecycle hours after ``history.origin`` (a whole-second UTC instant,
hour 0). The same convention as ``runtime_trace`` is kept: step instants are
nonnegative, nondecreasing hours; several steps may share an instant and are processed in
order. Event ``issued_at`` is an integer hour and may be negative (before the origin).
Module instants (schedule ``anchor``, acceptance ``decided_at``/``expires_at``) are UTC
strings, compared exactly in seconds against ``origin + 3600 * hour``.

Within one step the order is: windows, recovery facts, schedule clock evaluation,
attempt facts (approvals, finishes, deploy-gate rechecks), acceptance records, external
events in (issued_at, issuer, event_id) order (RFC 0011 §2.2 item 5), then dispatch of
pending occurrences in (trigger instant, response, rule id) order (§2.7).

Recorded, not recomputed (as in ``runtime_trace``): window verdicts, the gate join inputs
of each candidate, platform authentication of events and acceptances, approver authority,
recovery_overdue transitions and rollback-target eligibility. Computed here: episode
opening, closure counting under ``closure_scope``, event admission, occurrence firing,
holds, attempt serialization, search domains, acceptance checks and head writes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from tvl.lints import lint_module, parse_utc_instant
from tvl.promotion_join import join_promotion_decisions
from tvl.release_acceptance import validate_acceptance
from tvl.runtime_trace import TraceError, _enum, _hour, _optimize_outcome, _require, _shape

LATE_HOURS = 72
EXTERNAL_SCOPE_HOURS = 30 * 24
_FAMILIES = "anthropic openai google meta mistral amazon"
_TIERS = "small medium large"


def _version(module: dict) -> tuple[int, int]:
    text = str(module.get("tvl_version", "1.3"))
    major, _, minor = text.partition(".")
    return int(major), int(minor or 0)


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
        self.releases: list[dict] = []  # consumed accepts: write generation, repairs_episode, rollback_target
        self.rolled_back: set[str] = set()
        self.max_open = 0
        self.history_steps = history["steps"]
        del snap

    # -- helpers ---------------------------------------------------------------------------
    def emit(self, fact: str, **fields: Any) -> None:
        self.facts.append({"instant": self.now, "fact": fact, **fields})

    def at(self, hour: int) -> datetime:
        return self.origin + timedelta(hours=hour)

    def head(self) -> tuple[int, str]:
        return self.heads[-1][1], self.heads[-1][2]

    def generation_at(self, hour: int) -> int:
        gen = self.heads[0][1]
        for instant, generation, _ in self.heads:
            if instant <= hour:
                gen = generation
        return gen

    def fingerprint_of(self, generation: int) -> str | None:
        return next((f for _, g, f in self.heads if g == generation), None)

    def open_attempts(self) -> list[_Attempt]:
        return [a for a in self.attempts if a.open]

    @staticmethod
    def occ_ref(occ: dict) -> dict:
        return {k: occ[k] for k in ("response", "rule", "scope_kind", "scope", "j")}

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
        if occ["scope"] in self.rolled_back and kind == "episode":
            return False
        if kind == "episode":
            ep = self.episode_list[occ["scope"]]
            return ep["open"]
        if kind == "external":
            return self.now - occ["admitted_at"] < EXTERNAL_SCOPE_HOURS
        # schedule: until the next tick
        spec = self.find_rule(occ["response"], occ["rule"])["trigger"]["schedule"]
        nxt = self.tick_seconds(spec, int(occ["scope"]) + 1)
        return self.now * 3600 < nxt

    def tick_seconds(self, spec: dict, k: int) -> int:
        anchor = parse_utc_instant(spec["anchor"])
        return int((anchor - self.origin).total_seconds()) + k * spec["every_days"] * 86400  # type: ignore[operator]

    # -- firing -----------------------------------------------------------------------------
    def fire(self, response: str, rule: dict, scope_kind: str, scope: str, extra: dict) -> None:
        key = (response, rule["id"], scope_kind, scope, 0)
        if key in self.occurrences:
            return  # one scope, one occurrence 0 (redelivery / duplicate tick)
        occ = {"response": response, "rule": rule["id"], "scope_kind": scope_kind, "scope": scope, "j": 0,
               "trigger_instant": self.now, "held": False, "state": "pending", **extra}
        self.occurrences[key] = occ
        self.emit("fired", occurrence=self.occ_ref(occ))
        if rule["do"] == "optimize":
            self.pending.append(occ)
        elif rule["do"] == "notify":
            self.emit("notified", occurrence=self.occ_ref(occ))

    def dispatch(self) -> None:
        self.pending.sort(key=lambda o: (o["trigger_instant"], o["response"], o["rule"], o["scope"], o["j"]))
        for occ in list(self.pending):
            if not self.scope_active(occ):
                reason = "rolled_back" if occ["scope"] in self.rolled_back else (
                    "expired" if occ["scope_kind"] != "episode" else "scope_closed")
                self.pending.remove(occ)
                self.emit("dropped", occurrence=self.occ_ref(occ), reason=reason)
                continue
            if self.serialize and self.open_attempts():
                if not occ["held"]:
                    occ["held"] = True
                    self.emit("held", occurrence=self.occ_ref(occ), reason="repair_open")
                continue
            self.pending.remove(occ)
            self.start(occ)
        self.max_open = max(self.max_open, len(self.open_attempts()))

    def start(self, occ: dict) -> None:
        rule = self.find_rule(occ["response"], occ["rule"])
        self.attempt_count += 1
        attempt = _Attempt(f"A{self.attempt_count}", occ, rule.get("approval", "human") != "human")
        self.attempts.append(attempt)
        occ["state"] = "started"
        self.emit("attempt_opened", attempt=attempt.name, occurrence=self.occ_ref(occ))
        if "admit" in rule:
            tvar = rule["admit"]["tvar"]
            domain = list(self.tvars[tvar]["domain"])
            ref = occ["model_ref"]
            self.emit("search_domain", attempt=attempt.name, tvar=tvar,
                      domain=domain if ref in domain else domain + [ref])

    def close(self, attempt: _Attempt, reason: str) -> None:
        attempt.open = False
        self.emit("attempt_closed", attempt=attempt.name, reason=reason)

    def close_scope(self, kind: str, scope: str) -> None:
        for a in self.open_attempts():
            if a.occ["scope_kind"] == kind and a.occ["scope"] == scope:
                a.scope_closed = True
                if a.awaiting_deploy or not (a.approved and not a.finished) and not a.finished:
                    # nothing started that must still record a result: the effect never takes place
                    if a.awaiting_deploy or not a.approved:
                        self.close(a, "scope_closed")

    # -- windows and episodes ---------------------------------------------------------------
    def window(self, rec: dict) -> None:
        _shape(rec, "monitor start end verdict head_generation")
        name = rec["monitor"]
        _require(name in self.monitors and self.monitors[name]["phase"] == "runtime", "window needs a runtime monitor")
        monitor = self.monitors[name]
        width = monitor["window"]["tumbling_hours"]
        for bound in (rec["start"], rec["end"]):
            _hour(bound)
        _require(rec["end"] - rec["start"] == width and rec["start"] % width == 0, "window must be one aligned tumbling window")
        _require(rec["end"] <= self.now, "window ends after evaluation")
        _enum(rec["verdict"], "MET BREACHED UNKNOWN")
        _require(type(rec["head_generation"]) is int, "head_generation must be an integer")
        start_gen, end_gen = self.generation_at(rec["start"]), self.generation_at(rec["end"])
        _require(start_gen <= rec["head_generation"] <= end_gen,
                 "window head_generation outside the generations served during the window")
        mixed = rec["head_generation"] != start_gen
        episode_decl = monitor.get("episode") or {}
        scope_mode = episode_decl.get("closure_scope", "any_generation")
        ep = self.episodes.get(name)
        fields: dict[str, Any] = {"monitor": name, "start": rec["start"]}
        if rec["verdict"] == "BREACHED":
            if ep is None:
                self.episode_count += 1
                ep = {"id": f"EP{self.episode_count}", "monitor": name, "open": True, "count": 0, "ends": [],
                      "opening_generation": self.head()[0]}
                self.episodes[name] = ep
                self.episode_list[ep["id"]] = ep
                self.emit("window", closure="breached", **fields)
                self.emit("episode_opened", monitor=name, episode=ep["id"], opening_generation=ep["opening_generation"])
                for response, rule in self.rules:
                    t = rule["trigger"]
                    if t.get("monitor") == name and t.get("event") == "episode_opened":
                        self.fire(response, rule, "episode", ep["id"], {})
            else:
                ep["count"], ep["ends"] = 0, []
                self.emit("window", closure="breached", **fields)
            return
        if ep is None:
            self.emit("window", closure="no_episode", **fields)
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
        ep["count"] += 1
        ep["ends"].append(rec["end"])
        need = episode_decl["closure_windows"]
        self.emit("window", closure="counts", progress=min(ep["count"], need), of=need, **fields)
        if ep["count"] >= need and all(self.now - e <= episode_decl["closure_max_age_hours"] for e in ep["ends"][-need:]):
            ep["open"] = False
            del self.episodes[name]
            self.emit("episode_resolved", monitor=name, episode=ep["id"])
            self.close_scope("episode", ep["id"])

    def recovery(self, rec: dict) -> None:
        _shape(rec, "monitor episode event approval", "target_eligible")
        _enum(rec["event"], "overdue")
        _enum(rec["approval"], "granted declined")
        mon = self.monitors.get(rec["monitor"])
        _require(mon is not None and self.requirements[mon["requirement"]]["kind"] == "recovery_time",
                 "recovery fact needs a recovery_time monitor")
        _require(rec["episode"] in self.episode_list, "unknown episode")
        episode = rec["episode"]
        self.emit("recovery_overdue", monitor=rec["monitor"], episode=episode)
        for response, rule in self.rules:
            t = rule["trigger"]
            if rule["do"] != "rollback" or t.get("monitor") != rec["monitor"] or t.get("event") != "recovery_overdue":
                continue
            if rule.get("target") != "release_rollback_target":
                continue
            if rec["approval"] != "granted":
                self.emit("rollback", result="declined", episode=episode)
                continue
            gen, _ = self.head()
            release = next((r for r in reversed(self.releases) if r["repairs_episode"] == episode and r["generation"] == gen), None)
            if release is None:
                self.emit("rollback", result="rollback_no_bound_release", episode=episode)
            elif not rec.get("target_eligible", True):
                self.emit("rollback", result="held(target_ineligible)", episode=episode)
            else:
                self.heads.append((self.now, gen + 1, release["rollback_target"]))
                self.rolled_back.add(episode)
                self.emit("rollback", result="written", episode=episode, generation=gen + 1, fingerprint=release["rollback_target"])
                for a in self.open_attempts():
                    if a.occ["scope_kind"] == "episode" and a.occ["scope"] == episode:
                        a.scope_closed = True
                        if a.awaiting_deploy or not a.approved:
                            self.close(a, "rolled_back")

    # -- schedule ---------------------------------------------------------------------------
    def clock(self) -> None:
        for response, rule in self.rules:
            spec = rule["trigger"].get("schedule")
            if spec is None:
                continue
            first = self.tick_seconds(spec, 0)
            now_s = self.now * 3600
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
        _require(attempt.open, "fact for a closed attempt")
        fact = rec["fact"]
        if fact == "approval":
            _shape(rec, "attempt fact state")
            _enum(rec["state"], "granted declined expired")
            _require(not attempt.finished, "approval after the optimization finished")
            if rec["state"] == "granted":
                attempt.approved = True
            else:
                attempt.declined = True
                self.emit("approval", attempt=attempt.name, state=rec["state"])
                self.close(attempt, "approval_" + rec["state"])
        elif fact == "finished":
            _shape(rec, "attempt fact completion candidates")
            _require(attempt.approved and not attempt.finished, "optimization not running")
            _enum(rec["completion"], "normal error cancelled cost_limit")
            _require(isinstance(rec["candidates"], list), "candidates must be a list")
            converted, winner = [], None
            for cand in rec["candidates"]:
                _shape(cand, "evidence_valid", "fingerprint gate_digest legacy_decision monitor_verdicts")
                if cand["evidence_valid"] is True:
                    _require(set(cand) == {"evidence_valid", "fingerprint", "gate_digest", "legacy_decision", "monitor_verdicts"},
                             "valid candidate needs fingerprint, gate digest and promotion join inputs")
                    verdicts = self.gate_inputs(cand["monitor_verdicts"])
                    converted.append({"evidence_valid": True, "legacy_decision": cand["legacy_decision"], "monitor_verdicts": verdicts})
                    if winner is None and join_promotion_decisions(cand["legacy_decision"], verdicts) == "Promote":
                        winner = cand
                else:
                    converted.append(dict(cand))
            event, promoted = _optimize_outcome(rec["completion"], converted)
            attempt.finished = True
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

    def gate_inputs(self, verdicts: Any) -> list[str]:
        _require(isinstance(verdicts, dict) and sorted(verdicts) == self.promotion_monitors,
                 "the gate join covers every promotion monitor of the module (RFC 0011 §2.6)")
        return [verdicts[n] for n in self.promotion_monitors]

    # -- acceptances ------------------------------------------------------------------------
    def acceptance(self, rec: dict) -> None:
        _require(isinstance(rec, dict) and {"record", "authenticated", "approver_authorized"} == set(rec),
                 "acceptance input needs record, authenticated, approver_authorized")
        doc = rec["record"]
        _require(type(rec["authenticated"]) is bool and type(rec["approver_authorized"]) is bool, "booleans expected")
        ident = doc.get("acceptance_id") if isinstance(doc, dict) else None

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
                       and a.occ["scope"] == occ_rec["scope_ref"] and a.occ["j"] == occ_rec["occurrence"]), None)
        if target is None:
            return result("invalid", "no_deploy_awaiting")
        if (doc["agent_ref"], doc["environment_ref"]) != (self.agent, self.environment) \
                or doc["candidate_fingerprint"] != target.promoted["fingerprint"] \
                or doc["gate_result_digest"] != target.promoted["gate_digest"] \
                or (self.contract_digest is not None and doc["contract_digest"] != self.contract_digest):
            return result("invalid", "binding_mismatch")
        if doc["decision"] == "reject":
            self.consumed.add(ident)
            result("reject_recorded")
            return self.close(target, "deploy_rejected")
        # accept: effect-time checks (RFC 0003 §7.6 item 3 with the originating scope, RFC 0012 §2.3)
        refusal = None
        if not self.scope_active(target.occ) or target.scope_closed:
            refusal = "scope_closed"
        elif target.recheck is not None and target.recheck != "Promote":
            refusal = "gate_not_promote"
        else:
            generation, fingerprint = self.head()
            if generation != doc["expected_head_generation"]:
                refusal = "stale_generation"
            elif fingerprint != doc["rollback_target"]:
                refusal = "rollback_target_mismatch"
        if refusal:
            result("refused", refusal)
            self.emit("outcome", attempt=target.name, event="deploy_refused", reason=refusal)
            return self.close(target, "deploy_refused")
        generation, _ = self.head()
        self.heads.append((self.now, generation + 1, doc["candidate_fingerprint"]))
        self.consumed.add(ident)
        self.releases.append({"generation": generation + 1, "rollback_target": doc["rollback_target"],
                              "repairs_episode": doc.get("repairs_episode")})
        result("written", generation=generation + 1)
        self.close(target, "deploy_written")

    # -- external events --------------------------------------------------------------------
    def event(self, ev: dict) -> tuple | None:
        _shape(ev, "kind event_id issuer issued_at catalogue_revision subject authenticated")
        _enum(ev["kind"], "model_released")
        for key in ("event_id", "issuer"):
            _require(isinstance(ev[key], str) and ev[key], "event ids are nonempty strings")
        _require(type(ev["issued_at"]) is int, "issued_at is an integer hour")
        _require(type(ev["catalogue_revision"]) is int and ev["catalogue_revision"] >= 1, "catalogue_revision positive")
        _require(type(ev["authenticated"]) is bool, "authenticated must be boolean")
        sub = ev["subject"]
        _shape(sub, "model_ref provider_family tier")
        _require(isinstance(sub["model_ref"], str) and sub["model_ref"], "model_ref is an opaque id")
        _enum(sub["provider_family"], _FAMILIES)
        _enum(sub["tier"], _TIERS)
        return (ev["issued_at"], ev["issuer"], ev["event_id"])

    def process_event(self, ev: dict) -> None:
        name = f"{ev['issuer']}:{ev['event_id']}"
        if not ev["authenticated"]:
            return self.emit("event", event=name, result="rejected(unauthenticated)")
        if (ev["issuer"], ev["event_id"]) in self.seen_events:
            return self.emit("event", event=name, result="redelivery")
        if self.now - ev["issued_at"] > LATE_HOURS:
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
            self.fire(response, rule, "external", name, {"model_ref": sub["model_ref"], "admitted_at": self.now})
        if not matched:
            self.emit("no_match", event=name)

    # -- driver -----------------------------------------------------------------------------
    def run(self) -> dict:
        _require(isinstance(self.history_steps, list), "steps must be a list")
        heads_out: list[dict] = []
        previous = 0
        for step in self.history_steps:
            _shape(step, "instant", "windows recovery optimizations acceptances events")
            _hour(step["instant"])
            _require(step["instant"] >= previous, "step instants must not decrease")
            previous = self.now = step["instant"]
            for category in ("windows", "recovery", "optimizations", "acceptances", "events"):
                _require(isinstance(step.get(category, []), list), "step facts must be lists")
            for rec in step.get("windows", []):
                self.window(rec)
            for rec in step.get("recovery", []):
                self.recovery(rec)
            self.clock()
            for rec in step.get("optimizations", []):
                self.optimization(rec)
            for rec in step.get("acceptances", []):
                self.acceptance(rec)
            events = step.get("events", [])
            for ev in sorted(events, key=self.event):
                self.process_event(ev)
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
