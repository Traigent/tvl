"""RFC 0004 reference relation over recorded facts; never executes an action.

One history is for one agent/environment. Instants and window bounds are integer
lifecycle hours. RFC 0003 verdicts, episodes and liveness transitions are inputs,
not statistical or episode evaluations performed by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tvl.lints import lint_module
from tvl.canonical import RuntimeClosedError
from tvl.promotion_join import join_promotion_decisions


class TraceError(ValueError):
    """An unsupported or inconsistent recorded history (never silently ignored)."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TraceError(message)


def _shape(value: Any, required: str, optional: str = "") -> None:
    _require(isinstance(value, dict), "record must be a mapping")
    _require(set(required.split()) <= value.keys(), f"missing fields: {required}")
    _require(value.keys() <= set((required + " " + optional).split()), "unknown record field")


def _hour(value: Any) -> None:
    _require(type(value) is int and value >= 0, "hours must be nonnegative integers")


def _enum(value: Any, choices: str) -> None:
    _require(isinstance(value, str) and value in choices.split(), f"expected one of {choices}")


def _delivered(only: list[bool | None], unless: list[bool | None]) -> bool:
    """Strong Kleene conjunction/disjunction, with UNDECIDED never suppressing."""
    return False not in only and True not in unless


def _optimize_outcome(completion: str, candidates: list[dict]) -> tuple[str | None, bool]:
    # Validate all candidates even when one Promote wins (§2.2 precedence).
    gates = []
    invalid = False
    for candidate in candidates:
        _shape(candidate, "evidence_valid", "legacy_decision monitor_verdicts")
        _require(type(candidate["evidence_valid"]) is bool, "evidence_valid must be boolean")
        if candidate["evidence_valid"]:
            _require(set(candidate) == {"evidence_valid", "legacy_decision", "monitor_verdicts"},
                     "valid candidate needs promotion join inputs")
            try:
                gates.append(join_promotion_decisions(candidate["legacy_decision"], candidate["monitor_verdicts"]))
            except RuntimeClosedError as exc:
                raise TraceError("invalid candidate promotion join inputs") from exc
        else:
            _require(set(candidate) == {"evidence_valid"}, "invalid evidence has no gate decision")
            invalid = True
    if "Promote" in gates:
        return None, True
    if completion != "normal" or invalid:
        return "optimize_failed", False
    return "optimize_no_candidate", False


@dataclass
class _Attempt:
    monitor: str
    scope: str
    deploy: str
    open: bool = True
    started: bool = False
    finished: bool = False
    promoted: bool = False
    deploy_started: bool = False
    scope_closed: bool = False

    def close_pending(self) -> None:
        # RFC 0003 §7.2: optimize's effect is starting the run. A started run
        # still records its result; a later deploy remains a pending effect.
        self.scope_closed = True
        if not self.started or self.finished:
            self.open = False


class _Trace:
    def __init__(self, module: dict, history: dict):
        _shape(history, "agent environment evaluations")
        _require(all(isinstance(history[k], str) and history[k] for k in ("agent", "environment")),
                 "history needs agent and environment identities")
        _require(isinstance(history["evaluations"], list), "evaluations must be a list")
        errors = [issue for issue in lint_module(module) if issue["severity"] == "error"]
        _require(not errors, f"invalid trace module: {errors}")
        self.environment = history["environment"]
        self.requirements = {r["name"]: r for r in module.get("requirements", [])}
        self.monitors = {m["name"]: m for m in module.get("monitors", [])}
        self.rules = {(r["name"], rule["id"]): rule
                      for r in module.get("responses", []) for rule in r["rules"]}
        supported = {"episode_opened", "episode_continued", "episode_resolved", "episode_withdrawn",
                     "unknown_for", "stale", "live_again", "optimize_no_candidate", "optimize_failed",
                     "deploy_refused", "deploy_failed"}
        for rule in self.rules.values():
            if rule["do"] == "notify":
                event = rule["trigger"]["event"]
                _require(event in supported, "unsupported trace notification trigger")
                if "repeat_after_hours" in rule:
                    _require(event in {"unknown_for", "episode_opened"},
                             "trace repeats support unknown_for and episode_opened only")
        self.revisions = {r["name"]: "1" for r in module.get("responses", [])}
        self.monitor_keys = {name: "1" for name in self.monitors}
        self.episodes: dict[str, str | None] = {}
        self.attempts: dict[tuple, _Attempt] = {}
        self.windows: dict[str, dict[int, dict]] = {}
        self.fired: set[tuple] = set()
        self.repeats: dict[tuple, tuple[int, int]] = {}
        self.events: list[tuple[str, str, str, Any]] = []

    def monitor(self, name: str) -> dict:
        _require(name in self.monitors, "unknown monitor")
        monitor = self.monitors[name]
        _require(monitor["phase"] == "runtime", "history monitor must be runtime")
        _require(self.monitor_environment(name) == self.environment,
                 "history monitor environment mismatch")
        return monitor

    def monitor_environment(self, name: str) -> str | None:
        monitor = self.monitors.get(name, {})
        requirement = self.requirements.get(monitor.get("requirement"), {})
        if requirement.get("kind") == "evidence_liveness":
            return self.monitors.get(requirement["of"], {}).get("evidence", {}).get("deployment_environment")
        return monitor.get("evidence", {}).get("deployment_environment")

    def revision(self, record: dict) -> None:
        _shape(record, "kind name value")
        _enum(record["kind"], "response monitor")
        _require(isinstance(record["value"], str) and record["value"], "revision must be a nonempty string")
        name, value = record["name"], record["value"]
        revisions = self.revisions if record["kind"] == "response" else self.monitor_keys
        _require(name in revisions and revisions[name] != value, "unknown or unchanged revision")
        revisions[name] = value
        if record["kind"] == "monitor":
            self.windows.pop(name, None)
            self.episodes.pop(name, None)
        for key, attempt in self.attempts.items():
            if (record["kind"] == "response" and key[0] == name) or (
                record["kind"] == "monitor" and attempt.monitor == name
            ):
                attempt.close_pending()

    def window(self, record: dict, instant: int) -> None:
        _shape(record, "monitor start end verdict usable")
        monitor = self.monitor(record["monitor"])
        _require("window" in monitor, "window record needs primary monitor")
        for bound in (record["start"], record["end"]):
            _hour(bound)
        _require(record["end"] - record["start"] == monitor["window"]["tumbling_hours"],
                 "window width differs from monitor")
        _require(record["start"] % monitor["window"]["tumbling_hours"] == 0,
                 "window must align to tumbling boundaries")
        _require(record["end"] <= instant, "window ends after evaluation")
        _enum(record["verdict"], "MET BREACHED UNKNOWN")
        _require(type(record["usable"]) is bool, "usable must be boolean")
        _require(record["usable"] or record["verdict"] == "UNKNOWN",
                 "decided window requires usable evidence")
        self.windows.setdefault(record["monitor"], {})[record["start"]] = dict(record)
        # Evaluation is known; episode boundaries remain the recorded authority.
        self.episodes.setdefault(record["monitor"], None)

    def episode(self, record: dict) -> None:
        _shape(record, "monitor scope event", "reason")
        name = record["monitor"]
        self.monitor(name)
        _require(isinstance(record["scope"], str) and record["scope"], "episode scope must be a string")
        _enum(record["event"], "opened continued closed")
        current = self.episodes.get(name)
        if record["event"] == "closed":
            _require(current == record["scope"], "closing episode must be open")
            _enum(record.get("reason"), "resolved withdrawn")
            self.episodes[name] = None
            event = "episode_" + record["reason"]
            for attempt in self.attempts.values():
                if attempt.monitor == name and attempt.scope == current:
                    attempt.close_pending()
        else:
            _require("reason" not in record, "only closure has a reason")
            _require(current is None if record["event"] == "opened" else current == record["scope"],
                     "inconsistent episode boundary")
            self.episodes[name] = record["scope"]
            event = "episode_" + record["event"]
        self.events.append(("monitor", name, event, record["scope"]))

    def liveness(self, record: dict) -> None:
        # RFC 0003 §6.14 events are recorded inputs, not recalculated here.
        _shape(record, "monitor event scope")
        monitor = self.monitor(record["monitor"])
        _require(self.requirements[monitor["requirement"]]["kind"] == "evidence_liveness",
                 "liveness fact needs an evidence_liveness monitor")
        _enum(record["event"], "stale live_again")
        _require(isinstance(record["scope"], str), "liveness scope must be a string")
        self.events.append(("monitor", record["monitor"], record["event"], record["scope"]))

    def optimize(self, record: dict) -> None:
        _shape(record, "response revision rule scope occurrence fact",
               "completion candidates effect state checks write retries_exhausted")
        base = {"response", "revision", "rule", "scope", "occurrence", "fact"}
        fact = record["fact"]
        extras = {"fired": set(), "started": set(), "finished": {"completion", "candidates"},
                  "approval": {"effect", "state"}, "authority": {"state"},
                  "deploy_started": set(), "deploy_result": {"checks", "write", "retries_exhausted"}}
        _require(isinstance(fact, str) and fact in extras, "unknown optimize fact")
        _require(set(record) == base | extras[fact], "fields do not match optimize fact")
        outcome = (None, False)
        if fact == "finished":
            _enum(record["completion"], "normal error cancelled cost_limit")
            _require(isinstance(record["candidates"], list), "candidates must be a list")
            outcome = _optimize_outcome(record["completion"], record["candidates"])
        elif fact == "approval":
            _enum(record["effect"], "optimize deploy")
            _enum(record["state"], "granted declined expired")
        elif fact == "authority":
            _enum(record["state"], "reachable unreachable")
        elif fact == "deploy_result":
            _enum(record["checks"], "passed refused unreachable")
            _enum(record["write"], "succeeded failed not_attempted")
            _require(type(record["retries_exhausted"]) is bool, "retry bound fact must be boolean")
            _require(record["checks"] == "passed" or record["write"] == "not_attempted",
                     "write without passed checks")
        pair = record["response"], record["rule"]
        _require(pair in self.rules and self.rules[pair]["do"] == "optimize", "not an optimize rule")
        _require(type(record["occurrence"]) is int and record["occurrence"] >= 0, "invalid occurrence")
        _require(isinstance(record["scope"], str) and isinstance(record["revision"], str), "invalid attempt identity")
        key = (pair[0], record["revision"], pair[1], record["scope"], record["occurrence"])
        rule = self.rules[pair]
        if fact == "fired":
            _require(key not in self.attempts, "duplicate optimize firing")
            monitor = rule["trigger"]["monitor"]
            _require(self.revisions[pair[0]] == record["revision"], "fired on obsolete response revision")
            _require(self.episodes.get(monitor) == record["scope"], "optimize needs an open recorded episode")
            self.attempts[key] = _Attempt(monitor, record["scope"], rule.get("deploy", "never"))
            return
        _require(key in self.attempts, "optimize fact without firing")
        attempt = self.attempts[key]
        # Late external records cannot manufacture outcomes for a closed attempt.
        if not attempt.open:
            return
        event = None
        if fact == "started":
            _require(not attempt.started, "optimization already started")
            attempt.started = True
        elif fact == "finished":
            _require(attempt.started and not attempt.finished, "optimization not running")
            event, attempt.promoted = outcome
            attempt.finished = True
            if event or attempt.deploy == "never" or attempt.scope_closed:
                attempt.open = False
        elif fact == "approval":
            deploy = record["effect"] == "deploy"
            _require(not deploy or (attempt.promoted and attempt.deploy == "if_promoted"),
                     "deploy approval before promotion")
            started = attempt.deploy_started if deploy else attempt.started
            if record["state"] in {"declined", "expired"} and not started:
                attempt.open = False
        elif fact == "authority":
            pass  # Recorded authority availability is not itself an outcome.
        else:
            _require(attempt.promoted and attempt.deploy == "if_promoted", "deploy without promoted candidate")
            if fact == "deploy_started":
                _require(not attempt.deploy_started, "deploy already started")
                attempt.deploy_started = True
            else:
                if record["checks"] != "passed":
                    if record["checks"] == "refused":
                        event = "deploy_refused"
                else:
                    _require(attempt.deploy_started and record["write"] != "not_attempted", "deploy write without start")
                    if record["write"] == "succeeded":
                        attempt.open = False
                    elif record["retries_exhausted"]:
                        event = "deploy_failed"
                if event:
                    attempt.open = False
        if event:
            self.events.append((pair[0], pair[1], event, key))

    def guard(self, response: str, guard: dict) -> bool | None:
        if "monitor" in guard:
            name = guard["monitor"]
            if self.monitor_environment(name) != self.environment:
                return None
            return self.episodes.get(name) is not None if name in self.episodes else None
        return any(a.open for key, a in self.attempts.items()
                   if key[0] == response and key[1] == self.revisions[response] and key[2] == guard["rule"])

    def unknown_runs(self, monitor: str) -> list[tuple[int, int]]:
        runs = []
        first = last = None
        for window in sorted(self.windows.get(monitor, {}).values(), key=lambda w: w["start"]):
            if window["verdict"] != "UNKNOWN":
                if first is not None:
                    runs.append((first, last))
                first = last = None
            elif window["usable"]:
                if first is None:
                    first = window["start"]
                last = window["end"]
        if first is not None:
            runs.append((first, last))
        return runs

    def notifications(self, instant: int) -> list[dict]:
        emitted = []
        for (response, rule_id), rule in self.rules.items():
            if rule["do"] != "notify":
                continue
            trigger = rule["trigger"]
            event = trigger["event"]
            scopes = []
            active = set()
            if event == "unknown_for":
                monitor = trigger["monitor"]
                runs = self.unknown_runs(monitor)
                scopes = [(monitor, self.monitor_keys[monitor], first)
                          for first, last in runs if last - first >= trigger["hours"]]
                windows = self.windows.get(monitor, {})
                if runs and windows and max(windows.values(), key=lambda w: w["start"])["verdict"] == "UNKNOWN":
                    active.add((monitor, self.monitor_keys[monitor], runs[-1][0]))
            else:
                source = trigger.get("rule", trigger.get("monitor"))
                namespace = response if "rule" in trigger else "monitor"
                scopes = [scope for ns, name, ev, scope in self.events
                          if ns == namespace and name == source and ev == event]
                if event == "episode_opened" and self.episodes.get(source) is not None:
                    active.add(self.episodes[source])
            for event_index, scope in enumerate(scopes):
                key = (response, self.revisions[response], rule_id, scope)
                # episode_continued is an event at every further breached window.
                identity = (*key, instant, event_index) if event == "episode_continued" else key
                if identity in self.fired:
                    continue
                self.fired.add(identity)
                self.repeats[key] = (instant, 0)
                if self.deliver(response, rule):
                    emitted.append({"response": response, "rule": rule_id, "event": event, "instant": instant})
            if "repeat_after_hours" in rule:
                for scope in active:
                    key = (response, self.revisions[response], rule_id, scope)
                    if key not in self.repeats:
                        continue
                    origin, done = self.repeats[key]
                    due = (instant - origin) // rule["repeat_after_hours"]
                    if "max_repeats" in rule:
                        due = min(due, rule["max_repeats"])
                    if due > done:
                        _require(due == done + 1 and instant == origin + due * rule["repeat_after_hours"],
                                 "repeat due instant must be recorded; no catch-up policy is inferred")
                    for _ in range(done, due):
                        if self.deliver(response, rule):
                            emitted.append({"response": response, "rule": rule_id, "event": event, "instant": instant})
                    self.repeats[key] = (origin, due)
        return emitted

    def deliver(self, response: str, rule: dict) -> bool:
        return _delivered([self.guard(response, g) for g in rule.get("only_while", [])],
                          [self.guard(response, g) for g in rule.get("unless", [])])


def notification_trace(module: dict, history: dict) -> list[dict]:
    """Return the exact delivered notification sequence for a recorded history.

    Per evaluation: revisions, windows, episode/liveness facts, optimize facts,
    then all notification guards. Facts within a category retain input order.
    Output order is evaluation order, then module response/rule order.
    """
    trace = _Trace(module, history)
    result = []
    previous = -1
    for evaluation in history["evaluations"]:
        _shape(evaluation, "instant", "revisions windows episodes liveness optimizations")
        instant = evaluation["instant"]
        _hour(instant)
        _require(instant > previous, "evaluation instants must increase strictly")
        previous = instant
        trace.events = []
        for category in ("revisions", "windows", "episodes", "liveness", "optimizations"):
            _require(isinstance(evaluation.get(category, []), list), "evaluation facts must be lists")
        for record in evaluation.get("revisions", []):
            trace.revision(record)
        for record in evaluation.get("windows", []):
            trace.window(record, instant)
        for record in evaluation.get("episodes", []):
            trace.episode(record)
        for record in evaluation.get("liveness", []):
            trace.liveness(record)
        for record in evaluation.get("optimizations", []):
            trace.optimize(record)
        result.extend(trace.notifications(instant))
    return result
