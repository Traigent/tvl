"""DRAFT RFC 0011 Part A / RFC 0012: lints, acceptance documents and the conditions relation.

The slice assertions below are written from the hand-derived oracle rows (SLICE-TRACE
revision 2), not copied from the evaluator's output.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tvl.canonical import RuntimeClosedError
from tvl.lints import lint_module
from tvl.release_acceptance import validate_acceptance
from tvl.runtime_compiler import compile_runtime_document
from tvl.runtime_conditions import conditions_trace
from tvl.runtime_trace import TraceError
from tvl.yaml_safe import safe_load

CASES = Path(__file__).resolve().parents[1] / "conformance/cases/runtime"


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

    events = {key(f["event"]): (f["instant"], f["result"]) for f in _facts(result, "event") if f["instant"] != 11}
    assert events["P:E1"] == (10, "admitted")                      # row 1
    assert (11, "redelivery") in {(f["instant"], f["result"]) for f in _facts(result, "event")}  # row 2
    assert {key(f["event"]) for f in _facts(result, "no_match")} == {"P:E2", "P:E3"}                   # rows 3-4
    assert events["P:E4"] == (14, "rejected(unauthenticated)")     # row 5
    assert events["P:E5"] == (15, "rejected(late)")                # row 6
    domain = _facts(result, "search_domain")
    assert len(domain) == 1 and domain[0]["domain"][-1] == "anthropic/claude-haiku-5-5"            # row 1
    held = _facts(result, "held")
    assert [(f["instant"], f["reason"]) for f in held] == [(24, "repair_open")]                    # row 7
    opened = {f["attempt"]: f["instant"] for f in _facts(result, "attempt_opened")}
    closed = {f["attempt"]: f["instant"] for f in _facts(result, "attempt_closed")}
    assert opened == {"A1": 10, "A2": 31} and closed == {"A1": 31, "A2": 41}                      # rows 8-9, 12
    writes = [f for f in _facts(result, "acceptance") if f["result"] == "written"]
    assert [(f["instant"], f["acceptance"], f["generation"]) for f in writes] == [(31, "R1", 1)]  # row 9
    assert [f["result"] for f in _facts(result, "acceptance")] == ["written", "consumed", "refused"]  # rows 9, 10, 12
    assert _facts(result, "acceptance")[2]["reason"] == "stale_generation"
    windows = {f["start"]: f["closure"] for f in _facts(result, "window")}
    assert windows[24] == "UNKNOWN(mixed_generation)"                                              # row 13
    assert [(f["instant"], f["progress"]) for f in _facts(result, "window") if f["closure"] == "counts"] == [(72, 1), (96, 2)]
    assert [(f["instant"], f["episode"]) for f in _facts(result, "episode_resolved")] == [(96, "EP1")]  # row 15
    assert result["max_open_attempts"] == 1
    assert [g["generation"] for g in result["head_generations"] if g["instant"] in (30, 31, 96)] == [0, 1, 1]


def test_counterfactual_any_generation_closes_at_h72():
    module, history = _slice()
    module["monitors"][0]["episode"]["closure_scope"] = "any_generation"
    result = conditions_trace(module, history)
    assert [f["instant"] for f in _facts(result, "episode_resolved")] == [72]


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
    assert [f["fact"] for f in facts if f["instant"] == 5 and f["fact"] == "held"] == ["held"]


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
    step = next(s for s in history["steps"] if s["instant"] == 30)
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


@pytest.mark.parametrize("name", [
    "release-recovery-overdue-rolls-back-to-non-breached-target", "release-rollback-without-bound-release",
    "release-recovery-overdue-holds-when-bound-target-breached",
    "release-rollback-target-ineligible-holds", "release-rollback-declined-writes-nothing"])
def test_rollback_results(name):
    case = _case(f"semantic_traces/{name}.yml")
    facts = conditions_trace(case["module"], case["input"]["history"])["facts"]
    result = [f["result"] for f in facts if f["fact"] == "rollback"]
    assert result == [{"release-recovery-overdue-rolls-back-to-non-breached-target": "written",
                       "release-recovery-overdue-holds-when-bound-target-breached": "held(target_ineligible)",
                       "release-rollback-without-bound-release": "rollback_no_bound_release",
                       "release-rollback-target-ineligible-holds": "held(target_ineligible)",
                       "release-rollback-declined-writes-nothing": "declined"}[name]]
    written = name.endswith("non-breached-target")
    assert bool(_facts({"facts": facts}, "rollback")[0].get("fingerprint")) is written
    if written:
        assert [f for f in facts if f["fact"] == "dropped"] == []  # no other repair of EP1 was pending


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


def test_recorded_target_eligible_false_holds_and_absence_never_permits():
    # RFC 0011 2.13 item 5: eligibility is computed from the history; an explicit false only narrows it.
    case = _case("semantic_traces/release-recovery-overdue-rolls-back-to-non-breached-target.yml")
    history = copy.deepcopy(case["input"]["history"])
    assert "target_eligible" not in history["steps"][-1]["recovery"][0]
    explicit_false = copy.deepcopy(history)
    explicit_false["steps"][-1]["recovery"][0]["target_eligible"] = False
    assert [f["result"] for f in _facts(conditions_trace(case["module"], explicit_false), "rollback")] == ["held(target_ineligible)"]
    explicit_true = copy.deepcopy(history)
    explicit_true["steps"][-1]["recovery"][0]["target_eligible"] = True
    assert [f["result"] for f in _facts(conditions_trace(case["module"], explicit_true), "rollback")] == ["written"]
    bad = copy.deepcopy(history)
    bad["steps"][-1]["recovery"][0]["target_eligible"] = "yes"
    with pytest.raises(TraceError):
        conditions_trace(case["module"], bad)
