"""Composition preserves monitor bindings, effective defaults and pack origins."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from tvl.canonical import RuntimeClosedError, canonical_json_digest
from tvl.lints import lint_module, lint_pack
from tvl.promotion_monitor import evaluate_promotion_monitor
from tvl.runtime_compose import compose_runtime_documents
from tvl.schema import validator
from tvl_tools.tvl_compose.cli import main


def _module(*, kind: str = "rate_bound", phase: str = "promotion") -> dict:
    req = {"name": "bound", "kind": kind, "unit": "invocation"}
    if kind == "rate_bound":
        req.update(violation={"metric": "wall_clock_latency_ms", "exceeds": 2000}, max_rate=0.05)
        decision = {"method": "clopper_pearson_rational_v2", "confidence": 0.95, "false_alarm_budget": 0.05}
    else:
        req["violation"] = {"pattern": "absence", "a": {"event": "tool_call", "tool": "payments.charge"}}
        decision = {"method": "exact_count_v1"}
    mon = {"name": "check", "requirement": "bound", "phase": phase,
           "evidence": {"source": "evaluation_set" if phase == "promotion" else "customer_side"},
           "decision": decision}
    if phase == "runtime":
        mon["window"] = {"tumbling_hours": 6, "grace_minutes": 30}
        mon["episode"] = {"closure_windows": 2, "closure_max_age_hours": 24}
        if kind == "rate_bound":
            decision.update(horizon_days=30, min_samples=200, max_unresolved_fraction=0.05)
    return {
        "tvl": {"module": "example.agent"}, "tvl_version": "1.3",
        "environment": {"snapshot_id": "2026-10-16T00:00:00Z"},
        "evaluation_set": {"dataset": "test://composition"},
        "tvars": [{"name": "model_choice", "type": "enum[str]", "domain": ["small", "large"]}],
        "objectives": [{"name": "quality", "direction": "maximize"}],
        "promotion_policy": {"dominance": "epsilon_pareto", "alpha": 0.05, "min_effect": {"quality": 0.02}},
        "requirements": [req], "monitors": [mon],
    }


def _pack(label: str, *, tool: str = "payments.charge") -> dict:
    module = _module(kind="zero_tolerance", phase="runtime")
    req, mon = module["requirements"][0], module["monitors"][0]
    req["name"] = f"{label}_bound"
    req["violation"]["a"]["tool"] = tool
    mon.update(name=f"{label}_check", requirement=req["name"], applies_to="tenant_floor")
    return {"pack": {"module": f"example.{label}"}, "tvl_version": "1.3",
            "requirements": [req], "monitors": [mon]}


def _valid(doc: dict, *, provenance: list | None = None) -> None:
    issues = lint_pack(doc) if "pack" in doc else lint_module(doc, floor_provenance=provenance)
    assert not [issue for issue in issues if issue["severity"] == "error"], issues


def test_overlay_cannot_retarget_monitor_to_looser_requirement() -> None:
    base = _module()
    overlay = copy.deepcopy(base)
    looser = copy.deepcopy(base["requirements"][0])
    looser.update(name="looser", max_rate=0.5)
    overlay["requirements"].append(looser)
    overlay["monitors"][0]["requirement"] = "looser"
    _valid(base)
    _valid(overlay)
    counts = {"n": 100, "k": 20}
    assert evaluate_promotion_monitor(base["requirements"][0], base["monitors"][0], counts)["verdict"] == "BREACHED"
    assert evaluate_promotion_monitor(looser, overlay["monitors"][0], counts)["verdict"] == "MET"
    with pytest.raises(RuntimeClosedError, match="runtime_incompatible_replacement"):
        compose_runtime_documents(base, overlay)


def test_overlay_cannot_remove_promotion_minimum_to_turn_unknown_into_met() -> None:
    base = _module()
    base["monitors"][0]["decision"]["min_samples"] = 100
    overlay = copy.deepcopy(base)
    del overlay["monitors"][0]["decision"]["min_samples"]
    _valid(base)
    _valid(overlay)
    counts = {"n": 60, "k": 0}
    req = base["requirements"][0]
    assert evaluate_promotion_monitor(req, base["monitors"][0], counts)["verdict"] == "UNKNOWN"
    assert evaluate_promotion_monitor(req, overlay["monitors"][0], counts)["verdict"] == "MET"
    with pytest.raises(RuntimeClosedError, match="runtime_overlay_weakens"):
        compose_runtime_documents(base, overlay)


@pytest.mark.parametrize("kind,phase", [("rate_bound", "promotion"), ("zero_tolerance", "promotion"),
                                        ("zero_tolerance", "runtime")])
@pytest.mark.parametrize("reverse", [False, True])
def test_meet_keeps_minimum_when_other_side_uses_role_default(kind: str, phase: str, reverse: bool) -> None:
    explicit = _module(kind=kind, phase=phase)
    explicit["monitors"][0]["decision"]["min_samples"] = 100
    implicit = _module(kind=kind, phase=phase)
    left, right = (implicit, explicit) if reverse else (explicit, implicit)
    composed, _ = compose_runtime_documents(left, right, operation="meet")
    assert composed["monitors"][0]["decision"]["min_samples"] == 100
    _valid(composed)


@pytest.mark.parametrize("phase", ["promotion", "runtime"])
def test_zero_tolerance_overlay_cannot_omit_explicit_minimum(phase: str) -> None:
    base = _module(kind="zero_tolerance", phase=phase)
    base["monitors"][0]["decision"]["min_samples"] = 100
    overlay = copy.deepcopy(base)
    del overlay["monitors"][0]["decision"]["min_samples"]
    with pytest.raises(RuntimeClosedError, match="runtime_overlay_weakens"):
        compose_runtime_documents(base, overlay)


@pytest.mark.parametrize("operation", ["overlay", "meet"])
@pytest.mark.parametrize("explicit_on_left", [False, True])
def test_promotion_rate_unresolved_default_is_zero(operation: str, explicit_on_left: bool) -> None:
    implicit = _module()
    explicit = copy.deepcopy(implicit)
    explicit["monitors"][0]["decision"]["max_unresolved_fraction"] = 0.1
    left, right = (explicit, implicit) if explicit_on_left else (implicit, explicit)
    if operation == "overlay" and not explicit_on_left:
        with pytest.raises(RuntimeClosedError, match="runtime_overlay_weakens"):
            compose_runtime_documents(left, right)
    else:
        composed, _ = compose_runtime_documents(left, right, operation=operation)
        assert composed["monitors"][0]["decision"]["max_unresolved_fraction"] == 0


def _backend_module() -> dict:
    module = _module(phase="runtime")
    module["requirements"][0]["unit"] = "trace"
    mon = module["monitors"][0]
    mon["profile"] = "backend_v1"
    mon["evidence"] = {"source": "backend_trace_metadata", "deployment_environment": "production",
                       "attribution": "agent_key_exact_v1", "resolution": "terminal_status_v1", "sampling": "unverified"}
    mon["decision"].update(method="clopper_pearson_exact_v1", model="iid_bernoulli_within_window_v1")
    return module


@pytest.mark.parametrize("caps,expected", [((2, None), 2), ((None, None), None), ((2, 5), 2), ((2, 2), 2)])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("as_packs", [False, True])
def test_meet_repeat_caps_are_symmetric(caps: tuple, expected: int | None, reverse: bool, as_packs: bool) -> None:
    docs = []
    for cap in caps:
        doc = _pack("floor") if as_packs else _module(kind="zero_tolerance", phase="runtime")
        rule = {"id": "opened", "trigger": {"monitor": doc["monitors"][0]["name"], "event": "episode_opened"},
                "do": "notify", "repeat_after_hours": 1}
        if cap is not None:
            rule["max_repeats"] = cap
        doc["responses"] = [{"name": "alerts", "rules": [rule]}]
        _valid(doc)
        docs.append(doc)
    left, right = reversed(docs) if reverse else docs
    original = copy.deepcopy([left, right])
    composed, _ = compose_runtime_documents(left, right, operation="meet")
    rule = composed["responses"][0]["rules"][0]
    assert rule.get("max_repeats") == expected
    assert ("max_repeats" in rule) == (expected is not None)
    assert rule["repeat_after_hours"] == 1
    assert [left, right] == original
    _valid(composed)


@pytest.mark.parametrize("base_cap,overlay_cap", [(2, None), (2, 3), (None, 2), (2, 1), (None, None), (2, 2)])
def test_overlay_repeat_cap_cannot_widen(base_cap: int | None, overlay_cap: int | None) -> None:
    docs = []
    for cap in (base_cap, overlay_cap):
        doc = _module(kind="zero_tolerance", phase="runtime")
        rule = {"id": "opened", "trigger": {"monitor": "check", "event": "episode_opened"},
                "do": "notify", "repeat_after_hours": 1}
        if cap is not None:
            rule["max_repeats"] = cap
        doc["responses"] = [{"name": "alerts", "rules": [rule]}]
        _valid(doc)
        docs.append(doc)
    if base_cap is not None and (overlay_cap is None or overlay_cap > base_cap):
        with pytest.raises(RuntimeClosedError, match="runtime_overlay_weakens"):
            compose_runtime_documents(*docs)
    else:
        composed, _ = compose_runtime_documents(*docs)
        assert composed["responses"][0]["rules"][0].get("max_repeats") == overlay_cap
        _valid(composed)


@pytest.mark.parametrize("operation", ["overlay", "meet"])
@pytest.mark.parametrize("group,field", [
    ("evidence", "deployment_environment"), ("evidence", "attribution"), ("evidence", "resolution"),
    ("evidence", "sampling"), ("window", "tumbling_hours"), ("window", "grace_minutes"),
    ("decision", "model"), ("decision", "confidence"), ("decision", "false_alarm_budget"),
    ("decision", "horizon_days"), ("decision", "min_samples"), ("decision", "max_unresolved_fraction"),
    ("episode", "closure_windows"), ("episode", "closure_max_age_hours"),
])
def test_backend_defaults_compare_like_explicit_values(operation: str, group: str, field: str) -> None:
    base = _backend_module()
    overlay = copy.deepcopy(base)
    expected = overlay["monitors"][0][group].pop(field)
    composed, _ = compose_runtime_documents(base, overlay, operation=operation)
    assert composed["monitors"][0][group][field] == expected
    _valid(composed)


@pytest.mark.parametrize("group,field,tighter", [
    ("decision", "confidence", 0.99), ("decision", "min_samples", 300),
    ("decision", "max_unresolved_fraction", 0), ("episode", "closure_windows", 3),
    ("episode", "closure_max_age_hours", 20),
])
def test_backend_omission_cannot_weaken_tightened_fields(group: str, field: str, tighter: int | float) -> None:
    base = _backend_module()
    base["monitors"][0][group][field] = tighter
    overlay = copy.deepcopy(base)
    del overlay["monitors"][0][group][field]
    _valid(base)
    _valid(overlay)
    with pytest.raises(RuntimeClosedError, match="runtime_overlay_weakens"):
        compose_runtime_documents(base, overlay)
    composed, _ = compose_runtime_documents(base, overlay, operation="meet")
    assert composed["monitors"][0][group][field] == tighter


@pytest.mark.parametrize("burn", [False, True])
@pytest.mark.parametrize("field", ["min_samples", "max_unresolved_fraction", "horizon_days", "false_alarm_budget"])
def test_required_rate_fields_have_no_invented_defaults(burn: bool, field: str) -> None:
    base = _module(phase="runtime")
    if burn:
        base["monitors"][0]["decision"].pop("confidence")
        base["monitors"][0]["decision"]["threshold_factor"] = 2
        base["monitors"][0].pop("episode")
    overlay = copy.deepcopy(base)
    del overlay["monitors"][0]["decision"][field]
    with pytest.raises(RuntimeClosedError, match="runtime_invalid_profile|evaluation_schedule_mismatch"):
        compose_runtime_documents(base, overlay)


def test_repeated_packs_keep_all_digest_bound_floor_origins() -> None:
    module = _module()
    first = _pack("charge")
    second = _pack("refund", tool="payments.refund")
    _valid(first)
    _valid(second)
    composed, provenance = compose_runtime_documents(first, module)
    prior = copy.deepcopy(provenance)
    composed, provenance = compose_runtime_documents(second, composed, floor_provenance=provenance)
    assert provenance[:len(prior)] == prior
    assert {p["pack_digest"] for p in provenance} == {canonical_json_digest(first), canonical_json_digest(second)}
    assert {p["monitor"] for p in provenance} == {"charge_check", "refund_check"}
    _valid(composed, provenance=provenance)
    assert "tenant_floor_outside_pack" in {i["code"] for i in lint_module(composed)}


def test_repeated_packs_do_not_promote_carried_floors_to_agent_scope() -> None:
    first, second = _pack("first"), _pack("second")
    first["monitors"][0]["decision"]["min_samples"] = 200
    second["monitors"][0]["decision"]["min_samples"] = 100
    composed, provenance = compose_runtime_documents(first, _module())
    composed, provenance = compose_runtime_documents(second, composed, floor_provenance=provenance)
    floor = next(mon for mon in composed["monitors"] if mon["name"] == "first_check")
    assert floor["applies_to"] == "tenant_floor"
    assert floor["decision"]["min_samples"] == 200
    assert len(provenance) == 2
    assert {p["monitor"] for p in provenance} == {"first_check"}
    assert {p["match"] for p in provenance} == {"floor_only"}
    _valid(composed, provenance=provenance)


def test_pack_cannot_supply_missing_origin_of_existing_floor() -> None:
    pack = _pack("charge")
    composed, _ = compose_runtime_documents(pack, _module())
    with pytest.raises(RuntimeClosedError, match="tenant_floor_outside_pack"):
        compose_runtime_documents(pack, composed)


def test_non_mapping_floor_origin_fails_closed() -> None:
    composed, _ = compose_runtime_documents(_pack("charge"), _module())
    with pytest.raises(RuntimeClosedError, match="tenant_floor_outside_pack"):
        compose_runtime_documents(_pack("refund", tool="payments.refund"), composed, floor_provenance=[None])


@pytest.mark.parametrize("field,value", [("pack_digest", "invalid"), ("pack_module", ""),
                                         ("pack_monitor", ""), ("match", "unknown"),
                                         ("monitor", "missing")])
def test_invalid_accumulated_floor_provenance_is_refused(field: str, value: str) -> None:
    composed, provenance = compose_runtime_documents(_pack("charge"), _module())
    provenance[0][field] = value
    with pytest.raises(RuntimeClosedError, match="tenant_floor_outside_pack"):
        compose_runtime_documents(_pack("refund", tool="payments.refund"), composed,
                                  floor_provenance=provenance)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("floor_rate", [0.01, 0.1])
def test_pack_meet_keeps_module_shape_and_rewrites_aliases(reverse: bool, floor_rate: float) -> None:
    module = _module(kind="rate_bound", phase="runtime")
    module["monitors"][0]["decision"]["min_samples"] = 300
    pack = copy.deepcopy(module)
    for key in tuple(pack):
        if key not in {"tvl_version", "requirements", "monitors"}:
            del pack[key]
    pack["pack"] = {"module": "example.floors"}
    pack["requirements"][0].update(name="floor_bound", max_rate=floor_rate)
    pack["monitors"][0].update(name="floor_check", requirement="floor_bound", applies_to="tenant_floor")
    pack["responses"] = [{"name": "alerts", "rules": [
        {"id": "opened", "trigger": {"monitor": "floor_check", "event": "episode_opened"}, "do": "notify"}]}]
    _valid(pack)
    left, right = (pack, module) if reverse else (module, pack)
    composed, provenance = compose_runtime_documents(left, right, operation="meet")
    assert composed["tvl"] == module["tvl"]
    assert "pack" not in composed
    assert composed["objectives"] == module["objectives"]
    assert composed["requirements"][0]["max_rate"] == min(0.05, floor_rate)
    assert composed["monitors"][0]["requirement"] == "bound"
    assert composed["responses"][0]["rules"][0]["trigger"]["monitor"] == "check"
    assert provenance == [{"monitor": "check", "pack_module": "example.floors", "pack_monitor": "floor_check",
                           "pack_digest": canonical_json_digest(pack), "match": "merged"}]
    assert not list(validator().iter_errors(composed))
    _valid(composed, provenance=provenance)


@pytest.mark.parametrize("operation", ["overlay", "meet"])
def test_pack_aliases_preserve_obligation_and_response_references(operation: str) -> None:
    fixture = Path(__file__).resolve().parents[1] / "conformance/cases/runtime/composition/compose-pack-output-validates-as-authored.yml"
    case = yaml.safe_load(fixture.read_text())
    composed, provenance = compose_runtime_documents(case["base"], case["overlay"], operation=operation)
    assert composed["requirements"][1]["of"] == "agent_monitor"
    assert composed["responses"][0]["rules"][0]["trigger"]["monitor"] == "agent_monitor"
    assert [p["match"] for p in provenance] == ["merged", "merged"]
    _valid(composed, provenance=provenance)


@pytest.mark.parametrize("operation", ["overlay", "meet"])
def test_pack_normalises_zero_tolerance_minimum_before_comparison(operation: str) -> None:
    pack = _pack("floor")
    pack["monitors"][0]["decision"]["min_samples"] = 100
    module = _module(kind="zero_tolerance", phase="runtime")
    if operation == "overlay":
        with pytest.raises(RuntimeClosedError, match="requirement_weaker_than_floor"):
            compose_runtime_documents(pack, module)
    else:
        composed, _ = compose_runtime_documents(pack, module, operation="meet")
        assert composed["monitors"][0]["decision"]["min_samples"] == 100


def test_pack_meet_preserves_pack_shape_and_both_origins() -> None:
    first, second = _pack("first"), _pack("second")
    first["monitors"][0]["decision"]["min_samples"] = 100
    composed, provenance = compose_runtime_documents(first, second, operation="meet")
    assert composed["pack"] == second["pack"]
    assert "tvl" not in composed
    assert composed["monitors"][0]["decision"]["min_samples"] == 100
    assert {p["pack_digest"] for p in provenance} == {canonical_json_digest(first), canonical_json_digest(second)}
    _valid(composed)


@pytest.mark.parametrize("use_meet", [False, True])
def test_compose_cli_preserves_pack_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture, use_meet: bool) -> None:
    import sys

    module_path = tmp_path / "module.yml"
    module_path.write_text(yaml.safe_dump(_module()))
    pack_paths = [tmp_path / "charge.yml", tmp_path / "refund.yml"]
    for path, pack in zip(pack_paths, [_pack("charge"), _pack("refund", tool="payments.refund")]):
        label = pack["requirements"][0]["name"]
        pack["requirements"].append({"name": f"{label}_live", "kind": "evidence_liveness", "unit": "window",
                                     "of": pack["monitors"][0]["name"], "max_stale_windows": 1})
        pack["monitors"].append({"name": f"{label}_live_check", "requirement": f"{label}_live",
                                 "phase": "runtime", "applies_to": "tenant_floor",
                                 "evidence": {"source": "windows"}, "decision": {"method": "exact_count_v1"}})
        path.write_text(yaml.safe_dump(pack))
    args = ["tvl-compose", str(module_path), "--json", "--validate"]
    if use_meet:
        args.extend(["--meet", str(pack_paths[0])])
    else:
        for path in pack_paths:
            args.extend(["--pack", str(path)])
    monkeypatch.setattr(sys, "argv", args)
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] and result["validation"]["ok"]
    assert len(result["floor_provenance"]) == (2 if use_meet else 4)
    assert all(len(p["pack_digest"]) == 64 for p in result["floor_provenance"])
