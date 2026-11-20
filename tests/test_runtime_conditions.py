"""DRAFT RFC 0011 Part A / RFC 0012: lints, acceptance documents and the conditions relation.

The slice assertions below are written from hand-derived oracle rows, not copied from the
evaluator's output.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tvl.canonical import RuntimeClosedError
from tvl.lints import lint_module
from tvl.release_acceptance import validate_acceptance
from tvl.runtime_compiler import compile_runtime_document
from tvl.runtime_conditions import conditions_trace, occurrence_status, scope_ref
from tvl.runtime_trace import TraceError
from tvl.yaml_safe import safe_load

CASES = Path(__file__).resolve().parents[1] / "conformance/cases/runtime"
H = 3600  # instants are whole seconds after the origin; the hand-derived oracle rows are written in hours


def _case(relative: str) -> dict:
    return safe_load((CASES / relative).read_text())


def _slice() -> tuple[dict, dict]:
    case = _case("semantic_traces/external-slice-trace.yml")
    return copy.deepcopy(case["module"]), copy.deepcopy(case["input"]["history"])


def _facts(result: dict, kind: str) -> list[dict]:
    return [f for f in result["facts"] if f["fact"] == kind]


def _codes(module: dict) -> set[str]:
    return {i["code"] for i in lint_module(module) if i["severity"] == "error"}


def test_slice_module_is_lint_clean_and_requires_version_17():
    module, _ = _slice()
    assert _codes(module) == set()
    for old in ("1.5", "1.4", "1.3"):
        old_module = copy.deepcopy(module)
        old_module["tvl_version"] = old
        assert "declared_version_below_constructs" in _codes(old_module)
    no_version = copy.deepcopy(module)
    del no_version["tvl_version"]
    assert "runtime_version_required" in _codes(no_version)


def test_slice_oracle_rows():
    module, history = _slice()
    result = conditions_trace(module, history)
    def key(event: dict) -> str:  # event identities are (issuer, event_id) mappings
        return f"{event['issuer']}:{event['event_id']}"

    events = {key(f["event"]): (f["instant"], f["result"]) for f in _facts(result, "event") if f["instant"] != 11 * H}
    assert events["P:E1"] == (10 * H, "admitted")                  # row 1
    assert (11 * H, "redelivery") in {(f["instant"], f["result"]) for f in _facts(result, "event")}  # row 2
    assert {key(f["event"]) for f in _facts(result, "no_match")} == {"P:E2", "P:E3"}                   # rows 3-4
    assert events["P:E4"] == (14 * H, "rejected(unauthenticated)")     # row 5
    assert events["P:E5"] == (15 * H, "rejected(late)")                # row 6
    domain = _facts(result, "search_domain")
    assert len(domain) == 1 and domain[0]["domain"][-1] == "anthropic/claude-haiku-5-5"            # row 1
    held = _facts(result, "held")
    assert [(f["instant"], f["reason"]) for f in held] == [(24 * H, "repair_open")]                    # row 7
    opened = {f["attempt"]: f["instant"] for f in _facts(result, "attempt_opened")}
    closed = {f["attempt"]: f["instant"] for f in _facts(result, "attempt_closed")}
    assert opened == {"A1": 10 * H, "A2": 31 * H} and closed == {"A1": 31 * H, "A2": 41 * H}                      # rows 8-9, 12
    writes = [f for f in _facts(result, "acceptance") if f["result"] == "written"]
    assert [(f["instant"], f["acceptance"], f["generation"]) for f in writes] == [(31 * H, "R1", 1)]  # row 9
    assert [f["result"] for f in _facts(result, "acceptance")] == ["written", "consumed", "refused"]  # rows 9, 10, 12
    assert _facts(result, "acceptance")[2]["reason"] == "stale_generation"
    windows = {f["start"]: f["closure"] for f in _facts(result, "window")}
    assert windows[24 * H] == "UNKNOWN(mixed_generation)"                                              # row 13
    assert [(f["instant"], f["progress"]) for f in _facts(result, "window") if f["closure"] == "counts"] == [(72 * H, 1), (96 * H, 2)]
    assert [(f["instant"], f["episode"]) for f in _facts(result, "episode_resolved")] == [(96 * H, "EP1")]  # row 15
    assert result["max_open_attempts"] == 1
    assert [g["generation"] for g in result["head_generations"] if g["instant"] in (30 * H, 31 * H, 96 * H)] == [0, 1, 1]


def test_counterfactual_any_generation_closes_at_hour_72():
    module, history = _slice()
    module["monitors"][0]["episode"]["closure_scope"] = "any_generation"
    result = conditions_trace(module, history)
    assert [f["instant"] for f in _facts(result, "episode_resolved")] == [72 * H]


def test_evaluator_is_deterministic_and_pure():
    module, history = _slice()
    before = copy.deepcopy((module, history))
    assert conditions_trace(module, history) == conditions_trace(module, history)
    assert (module, history) == before


def test_events_at_one_instant_are_ordered_by_issue_time():
    case = _case("semantic_traces/external-two-events-serialize-by-issue-order.yml")
    facts = conditions_trace(case["module"], case["input"]["history"])["facts"]
    opened = [f for f in facts if f["fact"] == "attempt_opened"]
    assert opened[0]["occurrence"]["scope"] == {"issuer": "P", "event_id": "E1"}  # issued_at 3 before issued_at 4
    assert [f["fact"] for f in facts if f["instant"] == 5 * H and f["fact"] == "held"] == ["held"]


def test_three_missed_ticks_coalesce_into_one_firing():
    case = _case("semantic_traces/schedule-three-missed-ticks-coalesce.yml")
    facts = conditions_trace(case["module"], case["input"]["history"])["facts"]
    assert [f["tick"] for f in facts if f["fact"] == "skipped"] == [0, 1]
    assert [f["occurrence"]["scope"] for f in facts if f["fact"] == "fired"] == ["2"]


def test_pre_17_contract_is_not_serialized():
    case = _case("semantic_traces/external-pre-1-7-contract-keeps-concurrent-attempts.yml")
    assert conditions_trace(case["module"], case["input"]["history"])["max_open_attempts"] == 2


def test_gate_join_must_cover_every_promotion_monitor():
    module, history = _slice()
    step = next(s for s in history["steps"] if s["instant"] == 30 * H)
    step["optimizations"][0]["candidates"][0]["monitor_verdicts"] = {}
    with pytest.raises(TraceError):
        conditions_trace(module, history)


def test_history_validation_is_closed():
    module, history = _slice()
    history["steps"][0]["events"][0]["free_text"] = "x"
    with pytest.raises(TraceError):
        conditions_trace(module, history)
    module, history = _slice()
    history["steps"][1]["instant"] = 3  # decreasing instant
    with pytest.raises(TraceError):
        conditions_trace(module, history)
    module, history = _slice()
    history["steps"][0]["events"][0]["subject"]["tier"] = "huge"
    with pytest.raises(TraceError):
        conditions_trace(module, history)


def test_acceptance_documents():
    good = _case("release/valid-accept.yml")["input"]["record"]
    assert validate_acceptance(good) == []
    assert validate_acceptance(dict(good, decision="reject")) == []
    for bad in (dict(good, extra=1), {k: v for k, v in good.items() if k != "format"},
                dict(good, expires_at="2026-11-27T00:00:01Z"), dict(good, expires_at="2026-11-19T00:00:00Z")):
        issues = validate_acceptance(bad)
        assert [i["code"] for i in issues] == ["acceptance_record_invalid"]
    assert validate_acceptance("nope")[0]["code"] == "acceptance_record_invalid"
    # closed diagnostics never echo the rejected value
    assert "free text" not in str(validate_acceptance(dict(good, note="free text")))


def test_compile_refuses_17_constructs():
    module, _ = _slice()
    with pytest.raises(RuntimeClosedError) as err:
        compile_runtime_document(module, token_map_doc=None)
    assert err.value.code in {"unsupported_construct"}


def test_lint_message_paths_are_closed():
    module, _ = _slice()
    module["responses"][0]["rules"][0]["trigger"]["match"] = {"provider_family": ["customer text"]}
    issue = next(i for i in lint_module(module) if i["code"] == "runtime_unknown_kind")
    assert "customer text" not in issue["message"]


def test_acceptance_without_history_contract_digest_is_a_trace_error():
    case = _case("semantic_traces/release-contract-digest-mismatch-is-ignored.yml")
    history = copy.deepcopy(case["input"]["history"])
    del history["contract_digest"]
    with pytest.raises(TraceError):
        conditions_trace(case["module"], history)
    # without any acceptance the digest is not needed
    for step in history["steps"]:
        step.pop("acceptances", None)
    conditions_trace(case["module"], history)


def test_release_rollback_is_deferred_out_of_17():
    # RFC 0012 §2.5: the bound target is always a configuration that breached in the open episode it repairs.
    for name in ("release-rollback-deferred", "release-rollback-deferred-on-any-trigger",
                 "release-rollback-deferred-any-generation-scope"):
        module = _case(f"release/{name}.yml")["module"]
        assert "release_rollback_deferred" in _codes(module), name
    module, _ = _slice()
    module["responses"][0]["rules"].append(
        {"id": "undo", "trigger": {"monitor": "quality_prod", "event": "episode_opened"}, "do": "rollback",
         "approval": "human", "target": "last_certified"})
    assert "release_rollback_deferred" not in _codes(module)  # other rollback targets are unaffected


def _trace_case(name: str) -> tuple[dict, dict]:
    case = _case(f"semantic_traces/{name}.yml")
    return copy.deepcopy(case["module"]), copy.deepcopy(case["input"]["history"])


_E1 = {"response": "tuning", "rule": "on_new_model", "scope_kind": "external", "scope": {"issuer": "P", "event_id": "E1"}, "j": 0}


def test_scope_ref_forms():
    from tvl.canonical import canonical_json_digest

    expected = "ext:" + canonical_json_digest({"event_id": "E1", "issuer": "P"})
    assert scope_ref("external", ("P", "E1")) == expected == scope_ref("external", {"issuer": "P", "event_id": "E1"})
    assert scope_ref("episode", "EP1") == "EP1"
    assert scope_ref("schedule", 3) == "3"
    assert scope_ref("external", ("P", "E2")) != expected


def test_occurrence_status_unapproved_attempt_expires_then_approval_is_ignored():
    module, history = _trace_case("external-scope-expiry-closes-unapproved-attempt-and-ignores-late-approval")
    history["steps"] = history["steps"][:1]
    assert occurrence_status(module, history, _E1) == {
        "scope_active": True, "attempt": "A1", "phase": "awaiting_approval", "closed_reason": None}
    module, history = _trace_case("external-scope-expiry-closes-unapproved-attempt-and-ignores-late-approval")
    assert occurrence_status(module, history, _E1) == {
        "scope_active": False, "attempt": "A1", "phase": "closed", "closed_reason": "scope_expired"}


def test_occurrence_status_optimizing_then_expired_without_deploy():
    module, history = _trace_case("external-scope-expiry-closes-optimizing-attempt-and-its-result-yields-no-deploy")
    history["steps"] = history["steps"][:2]
    assert occurrence_status(module, history, _E1)["phase"] == "optimizing"
    module, history = _trace_case("external-scope-expiry-closes-optimizing-attempt-and-its-result-yields-no-deploy")
    status = occurrence_status(module, history, _E1)
    assert (status["phase"], status["closed_reason"], status["scope_active"]) == ("closed", "scope_expired", False)
    assert not _facts(conditions_trace(module, history), "deploy_awaiting")


def test_occurrence_status_awaiting_deploy_and_unknown_occurrence():
    module, history = _trace_case("external-scope-expiry-closes-awaiting-attempt-and-releases-lock")
    history["steps"] = history["steps"][:3]
    assert occurrence_status(module, history, _E1)["phase"] == "awaiting_deploy"
    gone = {**_E1, "scope": {"issuer": "P", "event_id": "nope"}}
    assert occurrence_status(module, history, gone) == {
        "scope_active": False, "attempt": None, "phase": None, "closed_reason": None}


def test_occurrence_status_schedule_scope_ends_at_next_tick():
    module, history = _trace_case("schedule-next-tick-closes-awaiting-attempt-and-releases-lock")
    tick0 = {"response": "tuning", "rule": "recheck", "scope_kind": "schedule", "scope": "0", "j": 0}
    history["steps"] = history["steps"][:2]  # hour 0 fired, hour 1 approved
    assert occurrence_status(module, history, tick0) == {
        "scope_active": True, "attempt": "A1", "phase": "optimizing", "closed_reason": None}
    module, history = _trace_case("schedule-next-tick-closes-awaiting-attempt-and-releases-lock")
    assert occurrence_status(module, history, tick0) == {
        "scope_active": False, "attempt": "A1", "phase": "closed", "closed_reason": "scope_expired"}


def test_holdout_digest_mismatch_is_binding_mismatch():
    module, history = _trace_case("release-holdout-digest-must-match-candidate-bundle")
    results = {f["acceptance"]: f.get("reason", f["result"]) for f in _facts(conditions_trace(module, history), "acceptance")}
    assert results == {"R1": "binding_mismatch", "R2": "binding_mismatch", "R3": "written"}


def test_head_move_inside_a_window_makes_it_mixed_at_second_precision():
    # The deploy is installed at 30h 30m, inside the window [24h, 48h): no hour rounding may hide it.
    for name in ("release-head-move-mid-window-is-mixed", "release-head-move-mid-window-report-of-start-generation-is-mixed"):
        module, history = _trace_case(name)
        result = conditions_trace(module, history)
        written = [f for f in _facts(result, "acceptance") if f["result"] == "written"]
        assert [f["instant"] for f in written] == [30 * H + 1800]
        windows = {f["start"]: f["closure"] for f in _facts(result, "window")}
        assert windows[24 * H] == "UNKNOWN(mixed_generation)"
        assert windows[48 * H] == "counts"


def test_delayed_breach_report_opens_the_episode_at_the_breaching_generation():
    module, history = _trace_case("release-delayed-breach-report-after-deploy-uses-breaching-generation")
    result = conditions_trace(module, history)
    assert [f["opening_generation"] for f in _facts(result, "episode_opened")] == [0]  # head was already 1 at report time
    assert [f["instant"] for f in _facts(result, "episode_resolved")] == [96 * H]


def test_closure_needs_consecutive_windows_of_one_generation():
    module, history = _trace_case("release-since-head-move-generation-change-resets-closure-count")
    result = conditions_trace(module, history)
    progress = [(f["instant"], f["progress"]) for f in _facts(result, "window") if f["closure"] == "counts"]
    assert progress == [(72 * H, 1), (96 * H, 1), (120 * H, 2)]  # generation 1 then 2 restarts the count
    assert [f["instant"] for f in _facts(result, "episode_resolved")] == [120 * H]


def test_split_and_unsplit_instant_with_due_schedule_give_identical_facts():
    unsplit = _case("semantic_traces/external-simultaneous-events-with-due-schedule-unsplit.yml")
    split = _case("semantic_traces/external-simultaneous-events-with-due-schedule-split.yml")
    assert unsplit["module"] == split["module"]
    a = conditions_trace(unsplit["module"], unsplit["input"]["history"])
    b = conditions_trace(split["module"], split["input"]["history"])
    assert a["facts"] == b["facts"]


def test_malformed_finish_of_a_superseded_run_is_rejected_and_keeps_the_lock():
    case = _case("semantic_traces/schedule-next-tick-keeps-spending-lock-until-running-optimization-finishes.yml")
    for bad in ({"candidates": None}, {"candidates": "x"}, {"completion": "bogus"}, {"candidates": [{"evidence_valid": "no"}]}):
        history = copy.deepcopy(case["input"]["history"])
        history["steps"][-1]["optimizations"][0].update(bad)
        with pytest.raises(TraceError):
            conditions_trace(case["module"], history)
    # the well-formed record releases the lock (the case itself)
    ok = conditions_trace(case["module"], case["input"]["history"])
    assert [f["attempt"] for f in _facts(ok, "attempt_opened")] == ["A1", "A2"]
