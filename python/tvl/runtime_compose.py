"""Compose runtime declarations and organisation floors by tightening contracts."""

from __future__ import annotations

import copy
import re
from tvl.canonical import (
    APPROVAL_BY_RANK,
    APPROVAL_ORDER,
    DEPLOY_BY_RANK,
    DEPLOY_ORDER,
    RuntimeClosedError,
    SEVERITY_BY_RANK,
    SEVERITY_ORDER,
    canonical_json_digest,
    canonical_guards,
    minimal_decimal_str,
    to_fraction,
)
from tvl.lints import _monitor_effective_key, _requirement_identity, lint_module, lint_pack
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple


def _normalize_decimal_or_int(val: Any) -> Any:
    if type(val) is int:
        return val
    return minimal_decimal_str(val)


def _fraction_to_yaml_number(val: Any) -> Any:
    """Convert an exact decimal Fraction/value to a schema-valid YAML number (int or float)."""
    frac = to_fraction(val)
    dec_str = minimal_decimal_str(frac)
    if "." not in dec_str and type(val) is int:
        return int(frac)
    return float(dec_str)


def _with_backend_defaults(mon: Mapping[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(dict(mon))
    if out.get("profile") != "backend_v1":
        return out
    ev = dict(out.get("evidence") or {})
    ev.setdefault("deployment_environment", "production")
    ev.setdefault("attribution", "agent_key_exact_v1")
    ev.setdefault("resolution", "terminal_status_v1")
    ev.setdefault("sampling", "unverified")
    out["evidence"] = ev

    win = dict(out.get("window") or {})
    win.setdefault("tumbling_hours", 6)
    win.setdefault("grace_minutes", 30)
    out["window"] = win

    dec = dict(out.get("decision") or {})
    dec.setdefault("model", "iid_bernoulli_within_window_v1")
    dec.setdefault("confidence", 0.95)
    dec.setdefault("false_alarm_budget", 0.05)
    dec.setdefault("horizon_days", 30)
    dec.setdefault("min_samples", 200)
    dec.setdefault("max_unresolved_fraction", 0.05)
    out["decision"] = dec

    ep = dict(out.get("episode") or {})
    ep.setdefault("closure_windows", 2)
    ep.setdefault("closure_max_age_hours", 24)
    out["episode"] = ep
    return out


def _with_monitor_defaults(mon: Mapping[str, Any]) -> Dict[str, Any]:
    """Fill only the defaults allowed for this monitor's role (§4.5–§4.6)."""
    out = _with_backend_defaults(mon)
    evidence = dict(out.get("evidence") or {})
    decision = dict(out.get("decision") or {})
    primary_or_burn = out.get("phase") == "runtime" and evidence.get("source") in {
        "customer_side", "backend_trace_metadata",
    }
    promotion = out.get("phase") == "promotion"
    if primary_or_burn:
        evidence.setdefault("deployment_environment", "production")
        evidence.setdefault("attribution", "agent_key_exact_v1")
        if decision.get("method") not in {"exact_count_v1", "exact_aggregate_v1"}:
            decision.setdefault("model", "iid_bernoulli_within_window_v1")
    if primary_or_burn or promotion:
        evidence.setdefault("resolution", "terminal_status_v1")
    # exact_aggregate_v1 forbids min_samples (RFC 0005 §2.3): no default is filled.
    if promotion or (primary_or_burn and decision.get("method") == "exact_count_v1"):
        decision.setdefault("min_samples", 1)
    if promotion and decision.get("method") == "clopper_pearson_rational_v2":
        decision.setdefault("max_unresolved_fraction", 0)
    out["evidence"] = evidence
    out["decision"] = decision
    return out


def _monitors_immutable_equal(m1_raw: Mapping[str, Any], m2_raw: Mapping[str, Any]) -> bool:
    m1 = _with_monitor_defaults(m1_raw)
    m2 = _with_monitor_defaults(m2_raw)
    if m1.get("requirement") != m2.get("requirement"):
        return False
    if m1.get("phase") != m2.get("phase") or m1.get("profile") != m2.get("profile"):
        return False
    ev1, ev2 = m1.get("evidence") or {}, m2.get("evidence") or {}
    if ev1.get("source") != ev2.get("source"):
        return False
    env1 = str(ev1.get("deployment_environment", "production")).strip().lower()
    env2 = str(ev2.get("deployment_environment", "production")).strip().lower()
    if env1 != env2:
        return False
    if ev1.get("attribution", "agent_key_exact_v1") != ev2.get("attribution", "agent_key_exact_v1"):
        return False
    if ev1.get("resolution", "terminal_status_v1") != ev2.get("resolution", "terminal_status_v1"):
        return False
    s1, s2 = ev1.get("sampling"), ev2.get("sampling")
    if isinstance(s1, Mapping) and isinstance(s2, Mapping):
        if s1.get("mode") != s2.get("mode") or to_fraction(s1.get("rate")) != to_fraction(s2.get("rate")):
            return False
    elif s1 != s2:
        return False
    d1, d2 = m1.get("decision") or {}, m2.get("decision") or {}
    if d1.get("method") != d2.get("method"):
        return False
    if d1.get("model", "iid_bernoulli_within_window_v1") != d2.get("model", "iid_bernoulli_within_window_v1"):
        return False
    tf1 = to_fraction(d1["threshold_factor"]) if "threshold_factor" in d1 else None
    tf2 = to_fraction(d2["threshold_factor"]) if "threshold_factor" in d2 else None
    if tf1 != tf2:
        return False
    if bool(m1.get("single_producer", False)) != bool(m2.get("single_producer", False)):
        return False
    if (m1.get("limits") or None) != (m2.get("limits") or None):
        return False
    return True


def _schedules_equal(m1_raw: Mapping[str, Any], m2_raw: Mapping[str, Any]) -> bool:
    m1 = _with_monitor_defaults(m1_raw)
    m2 = _with_monitor_defaults(m2_raw)
    w1, w2 = m1.get("window") or {}, m2.get("window") or {}
    d1, d2 = m1.get("decision") or {}, m2.get("decision") or {}
    if w1.get("tumbling_hours") != w2.get("tumbling_hours"):
        return False
    if w1.get("grace_minutes") != w2.get("grace_minutes"):
        return False
    if d1.get("horizon_days") != d2.get("horizon_days"):
        return False
    b1 = to_fraction(d1["false_alarm_budget"]) if "false_alarm_budget" in d1 else None
    b2 = to_fraction(d2["false_alarm_budget"]) if "false_alarm_budget" in d2 else None
    return b1 == b2


def _merge_rules(
    base_rules: Sequence[Mapping[str, Any]],
    over_rules: Sequence[Mapping[str, Any]],
    *,
    is_meet: bool,
    path: Sequence[Any] = ("responses",),
) -> List[Dict[str, Any]]:
    over_by_id = {str(r["id"]): dict(r) for r in over_rules if isinstance(r, Mapping) and "id" in r}
    result: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    for rule_idx, br in enumerate(base_rules):
        rule_path = [*path, "rules", rule_idx]
        rid = str(br["id"])
        seen_ids.add(rid)
        if rid not in over_by_id:
            if not is_meet:
                raise RuntimeClosedError("runtime_overlay_weakens", path=rule_path)
            r_copy = copy.deepcopy(dict(br))
            if r_copy.get("do") == "notify":
                r_copy["severity"] = r_copy.get("severity", "critical")
            result.append(r_copy)
            continue

        orr = over_by_id[rid]
        rule_path = [*path, "rules", over_rules.index(orr)]
        for field in ("only_while", "unless"):
            if canonical_guards(br.get(field, [])) != canonical_guards(orr.get(field, [])):
                raise RuntimeClosedError("runtime_incompatible_replacement", path=[*rule_path, field])
        if ("rule" in br.get("trigger", {}) or "rule" in orr.get("trigger", {})) and br.get("trigger") != orr.get("trigger"):
            raise RuntimeClosedError("runtime_incompatible_replacement", path=[*rule_path, "trigger"])
        if br.get("persist") != orr.get("persist"):
            # Both persistence coordinates, and its presence, are immutable (RFC 0005 §2.5).
            raise RuntimeClosedError("runtime_incompatible_replacement", path=[*rule_path, "persist"])
        for key in ("trigger", "do", "target", "fallback", "on_check_error"):
            if orr.get(key) != br.get(key):
                raise RuntimeClosedError("runtime_overlay_weakens", path=[*rule_path, key])
        rf_b = to_fraction(br["rate_floor"]) if "rate_floor" in br else None
        rf_o = to_fraction(orr["rate_floor"]) if "rate_floor" in orr else None
        if rf_b != rf_o:
            raise RuntimeClosedError("runtime_overlay_weakens", path=[*rule_path, "rate_floor"])

        action = str(br["do"])
        def_app = "none" if action in {"notify", "open_next_step", "block_action", "halt_unit"} else "human"
        app_b = APPROVAL_ORDER[str(br.get("approval", def_app))]
        app_o = APPROVAL_ORDER[str(orr.get("approval", def_app))]
        if not is_meet and app_o < app_b:
            raise RuntimeClosedError("runtime_overlay_weakens", path=[*rule_path, "approval"])

        if br.get("repeat_after_hours") != orr.get("repeat_after_hours"):
            raise RuntimeClosedError("runtime_overlay_weakens", path=[*rule_path, "repeat_after_hours"])
        mr_b = br.get("max_repeats")
        mr_o = orr.get("max_repeats")
        if mr_b is not None and (mr_o is None or int(mr_o) > int(mr_b)):
            if not is_meet:
                raise RuntimeClosedError("runtime_overlay_weakens", path=[*rule_path, "max_repeats"])

        merged = copy.deepcopy(orr)
        for field in ("only_while", "unless"):
            if field in merged:
                merged[field] = canonical_guards(merged[field])
        if "approval" in br or "approval" in orr:
            merged["approval"] = APPROVAL_BY_RANK[max(app_b, app_o)]
        # An absent cap is unbounded, so a meet retains either finite cap.
        finite_caps = [int(cap) for cap in (mr_b, mr_o) if cap is not None]
        if finite_caps:
            merged["max_repeats"] = min(finite_caps)

        if action == "optimize":
            dep_b = DEPLOY_ORDER.get(str(br.get("deploy", "never")))
            dep_o = DEPLOY_ORDER.get(str(orr.get("deploy", "never")))
            if dep_b is None or dep_o is None:
                raise RuntimeClosedError("runtime_unknown_kind", path=[*rule_path, "deploy"])
            if not is_meet and dep_o < dep_b:
                raise RuntimeClosedError("runtime_overlay_weakens", path=[*rule_path, "deploy"])
            if "deploy" in br or "deploy" in orr:
                merged["deploy"] = DEPLOY_BY_RANK[max(dep_b, dep_o)]

        if action == "notify":
            sev_b = SEVERITY_ORDER[str(br.get("severity", "critical"))]
            sev_o = SEVERITY_ORDER[str(orr.get("severity", "critical"))]
            if not is_meet and sev_o < sev_b:
                raise RuntimeClosedError("runtime_overlay_weakens", path=[*rule_path, "severity"])
            merged["severity"] = SEVERITY_BY_RANK[max(sev_b, sev_o)]

        result.append(merged)

    for orr in over_rules:
        rid = str(orr["id"])
        if rid not in seen_ids:
            r_copy = copy.deepcopy(dict(orr))
            if r_copy.get("do") == "notify":
                r_copy["severity"] = r_copy.get("severity", "critical")
            result.append(r_copy)

    return result


def _meet_requirement_pair(
    base_req: Mapping[str, Any],
    over_req: Mapping[str, Any],
    *,
    mode: str,  # "overlay" | "pack" | "meet"
    path: Sequence[Any] = ("requirements",),
) -> Dict[str, Any]:
    if _requirement_identity(dict(base_req)) != _requirement_identity(dict(over_req)):
        raise RuntimeClosedError("runtime_incompatible_replacement", path=path)
    weaken_code = "requirement_weaker_than_floor" if mode == "pack" else "runtime_overlay_weakens"
    merged = copy.deepcopy(dict(over_req))
    kind = base_req.get("kind")
    if kind == "rate_bound":
        r_b = to_fraction(base_req["max_rate"])
        r_o = to_fraction(over_req["max_rate"])
        if mode != "meet" and r_o > r_b:
            raise RuntimeClosedError(weaken_code, path=[*path, "max_rate"])
        merged["max_rate"] = _fraction_to_yaml_number(min(r_b, r_o))
    elif kind == "aggregate_bound":
        # Identity fixes the direction; a lower lte or a higher gte is the tighter bound.
        direction = "lte" if "lte" in base_req["bound"] else "gte"
        b_b, b_o = to_fraction(base_req["bound"][direction]), to_fraction(over_req["bound"][direction])
        weaker = b_o > b_b if direction == "lte" else b_o < b_b
        if mode != "meet" and weaker:
            raise RuntimeClosedError(weaken_code, path=[*path, "bound", direction])
        tighter = min(b_b, b_o) if direction == "lte" else max(b_b, b_o)
        merged["bound"] = {direction: _fraction_to_yaml_number(tighter)}
    elif kind == "recovery_time":
        w_b = int(base_req["within_hours"])
        w_o = int(over_req["within_hours"])
        if mode != "meet" and w_o > w_b:
            raise RuntimeClosedError(weaken_code, path=[*path, "within_hours"])
        merged["within_hours"] = min(w_b, w_o)
    elif kind == "evidence_liveness":
        s_b = int(base_req["max_stale_windows"])
        s_o = int(over_req["max_stale_windows"])
        if mode != "meet" and s_o > s_b:
            raise RuntimeClosedError(weaken_code, path=[*path, "max_stale_windows"])
        merged["max_stale_windows"] = min(s_b, s_o)
    return merged


def _meet_monitor_pair(
    base_mon_raw: Mapping[str, Any],
    over_mon_raw: Mapping[str, Any],
    *,
    mode: str,  # "overlay" | "pack" | "meet"
    path: Sequence[Any] = ("monitors",),
) -> Dict[str, Any]:
    base_mon = _with_monitor_defaults(base_mon_raw)
    over_mon = _with_monitor_defaults(over_mon_raw)
    if not _monitors_immutable_equal(base_mon, over_mon):
        raise RuntimeClosedError("runtime_incompatible_replacement", path=path)
    if not _schedules_equal(base_mon, over_mon):
        for group, field in (("window", "tumbling_hours"), ("window", "grace_minutes"), ("decision", "horizon_days"), ("decision", "false_alarm_budget")):
            if (base_mon.get(group) or {}).get(field) != (over_mon.get(group) or {}).get(field):
                raise RuntimeClosedError("evaluation_schedule_mismatch", path=[*path, group, field])
        raise RuntimeClosedError("evaluation_schedule_mismatch", path=path)
    weaken_code = "requirement_weaker_than_floor" if mode == "pack" else "runtime_overlay_weakens"
    merged = copy.deepcopy(dict(over_mon))
    d_b = base_mon.get("decision") or {}
    d_o = over_mon.get("decision") or {}
    d_m = dict(merged.get("decision") or {})

    if "confidence" in d_b and "confidence" in d_o:
        c_b, c_o = to_fraction(d_b["confidence"]), to_fraction(d_o["confidence"])
        if mode != "meet" and c_o < c_b:
            raise RuntimeClosedError(weaken_code, path=[*path, "decision", "confidence"])
        d_m["confidence"] = _fraction_to_yaml_number(max(c_b, c_o))
    if "min_samples" in d_b and "min_samples" in d_o:
        ms_b, ms_o = int(d_b["min_samples"]), int(d_o["min_samples"])
        if mode != "meet" and ms_o < ms_b:
            raise RuntimeClosedError(weaken_code, path=[*path, "decision", "min_samples"])
        d_m["min_samples"] = max(ms_b, ms_o)
    if "max_unresolved_fraction" in d_b and "max_unresolved_fraction" in d_o:
        uf_b, uf_o = to_fraction(d_b["max_unresolved_fraction"]), to_fraction(d_o["max_unresolved_fraction"])
        if mode != "meet" and uf_o > uf_b:
            raise RuntimeClosedError(weaken_code, path=[*path, "decision", "max_unresolved_fraction"])
        d_m["max_unresolved_fraction"] = _fraction_to_yaml_number(min(uf_b, uf_o))
    if "false_alarm_budget" in d_m:
        d_m["false_alarm_budget"] = _fraction_to_yaml_number(d_m["false_alarm_budget"])
    if "threshold_factor" in d_m:
        d_m["threshold_factor"] = _fraction_to_yaml_number(d_m["threshold_factor"])
    merged["decision"] = d_m
    if isinstance((merged.get("evidence") or {}).get("sampling"), Mapping):
        sm = dict(merged["evidence"]["sampling"])
        if "rate" in sm:
            sm["rate"] = _fraction_to_yaml_number(sm["rate"])
        merged["evidence"] = dict(merged["evidence"])
        merged["evidence"]["sampling"] = sm

    ep_b = base_mon.get("episode")
    ep_o = over_mon.get("episode")
    if isinstance(ep_b, Mapping) and isinstance(ep_o, Mapping):
        cw_b, cw_o = int(ep_b["closure_windows"]), int(ep_o["closure_windows"])
        ca_b, ca_o = int(ep_b["closure_max_age_hours"]), int(ep_o["closure_max_age_hours"])
        if mode != "meet" and (cw_o < cw_b or ca_o > ca_b):
            raise RuntimeClosedError(weaken_code, path=[*path, "episode", "closure_windows" if cw_o < cw_b else "closure_max_age_hours"])
        merged["episode"] = {
            "closure_windows": max(cw_b, cw_o),
            "closure_max_age_hours": min(ca_b, ca_o),
        }

    return merged


def _validate_floor_provenance(
    provenance: Sequence[Mapping[str, Any]],
    documents: Sequence[Mapping[str, Any]],
) -> None:
    """Require complete digest-bearing origin records for existing monitors.

    These local composition records are not proof of pack activation (§9.4).
    """
    monitors = {
        str(mon["name"]): mon
        for doc in documents
        for mon in doc.get("monitors") or []
    }
    for idx, entry in enumerate(provenance):
        if not isinstance(entry, Mapping) or not all(
            isinstance(entry.get(key), str) and entry[key]
            for key in ("monitor", "pack_module", "pack_monitor", "pack_digest", "match")
        ):
            raise RuntimeClosedError("tenant_floor_outside_pack", path=["floor_provenance", idx])
        mon = monitors.get(entry["monitor"])
        if (
            mon is None
            or re.fullmatch(r"[0-9a-f]{64}", entry["pack_digest"]) is None
            or entry["match"] not in {"merged", "floor_only"}
            or (entry["match"] == "floor_only") != (mon.get("applies_to") == "tenant_floor")
        ):
            raise RuntimeClosedError("tenant_floor_outside_pack", path=["floor_provenance", idx])


def _check_authored_pack_rules(pack: Mapping[str, Any]) -> None:
    for resp_idx, resp in enumerate(pack.get("responses") or []):
        if not isinstance(resp, Mapping):
            continue
        for rule_idx, rl in enumerate(resp.get("rules") or []):
            if isinstance(rl, Mapping):
                trig = rl.get("trigger") or {}
                if "rule" in trig or any(
                    isinstance(g, Mapping) and "rule" in g
                    for field in ("only_while", "unless") for g in rl.get(field, [])
                ):
                    raise RuntimeClosedError("runtime_invalid_ladder", path=["responses", resp_idx, "rules", rule_idx])
            if isinstance(rl, Mapping) and rl.get("deploy", "never") != "never":
                raise RuntimeClosedError(
                    "response_deploy_without_promotion_monitor",
                    path=["responses", resp_idx, "rules", rule_idx, "deploy"],
                )

    # A composed module must not lend its monitors to an authored pack guard (§2.4/§7.3).
    if any(
        isinstance(rule, Mapping) and ("only_while" in rule or "unless" in rule)
        for response in pack.get("responses") or [] if isinstance(response, Mapping)
        for rule in response.get("rules") or []
    ):
        for issue in lint_pack(dict(pack)):
            if issue.get("severity") == "error" and any(
                field in issue.get("path", []) for field in ("only_while", "unless")
            ):
                raise RuntimeClosedError(issue["code"], path=issue["path"], message=issue["message"])


def compose_runtime_documents(
    base: Mapping[str, Any],
    overlay: Mapping[str, Any],
    *,
    operation: str = "overlay",  # "overlay" | "meet"
    post_validate_without_provenance: bool = False,
    floor_provenance: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Compose base and overlay (module/module or pack/module) under overlay or meet semantics (§9)."""
    if operation not in {"overlay", "meet"}:
        raise RuntimeClosedError("runtime_invalid_profile")
    base_is_pack = "pack" in base and "tvl" not in base
    overlay_is_pack = "pack" in overlay and "tvl" not in overlay
    if overlay_is_pack and not base_is_pack:
        if operation != "meet":
            raise RuntimeClosedError("runtime_invalid_profile")
        base, overlay = overlay, base
        base_is_pack, overlay_is_pack = True, False
    if base_is_pack and overlay_is_pack and operation != "meet":
        raise RuntimeClosedError("runtime_invalid_profile")
    # RFC 0003 §7.6 item 9: a pack has no promotion monitors, so a floor can never declare a deploy.
    # Check the authored pack before reference rewriting lets its rule borrow a module's promotion monitor.
    for doc in (base, overlay):
        if "pack" in doc and "tvl" not in doc:
            _check_authored_pack_rules(doc)
    composed = copy.deepcopy(dict(overlay))
    previous_provenance = floor_provenance if floor_provenance is not None else []
    _validate_floor_provenance(previous_provenance, [overlay] if base_is_pack else [base, overlay])
    provenance = [copy.deepcopy(dict(entry)) for entry in previous_provenance]
    proven_floors = {entry["monitor"] for entry in provenance if entry["match"] == "floor_only"}
    for doc in (base, overlay):
        if "pack" in doc and "tvl" not in doc:
            continue
        for idx, mon in enumerate(doc.get("monitors") or []):
            if mon.get("applies_to") == "tenant_floor" and mon.get("name") not in proven_floors:
                raise RuntimeClosedError("tenant_floor_outside_pack", path=["monitors", idx, "applies_to"])

    if base_is_pack:
        # Pack floor composition (§9.4)
        mode = "meet" if operation == "meet" else "pack"
        is_meet = operation == "meet"
        pack_mod_name = str((base.get("pack") or {}).get("module", ""))
        pack_digest = canonical_json_digest(base)

        pack_reqs = {str(r["name"]): copy.deepcopy(dict(r)) for r in (base.get("requirements") or [])}
        pack_mons = [_with_monitor_defaults(m) for m in (base.get("monitors") or [])]

        mod_reqs_list = [copy.deepcopy(dict(r)) for r in (overlay.get("requirements") or [])]
        mod_reqs_by_name = {str(r["name"]): r for r in mod_reqs_list}
        mod_mons_list = [_with_monitor_defaults(m) for m in (overlay.get("monitors") or [])]
        mod_mons_by_name = {str(m["name"]): m for m in mod_mons_list}

        alias_map: Dict[str, str] = {}
        matched_pack_mons: Dict[str, Tuple[str, str]] = {}  # pack_mon_name -> (match_kind, composed_mon_name)
        if overlay_is_pack:
            for mon in mod_mons_list:
                provenance.append({
                    "monitor": mon["name"], "pack_module": overlay["pack"]["module"],
                    "pack_monitor": mon["name"], "pack_digest": canonical_json_digest(overlay),
                    "match": "floor_only",
                })

        # Pass 1: Primary and burn monitors
        for pm in pack_mons:
            pm_name = str(pm["name"])
            pr = pack_reqs[str(pm["requirement"])]
            if pr.get("kind") in {"recovery_time", "evidence_liveness"}:
                continue
            pm_key = _monitor_effective_key(pm, pr)
            paired_mm: Optional[Dict[str, Any]] = None
            for mm in mod_mons_list:
                mr = mod_reqs_by_name[str(mm["requirement"])]
                if mr.get("kind") in {"recovery_time", "evidence_liveness"}:
                    continue
                if _monitor_effective_key(mm, mr) == pm_key:
                    paired_mm = mm
                    break
                if _requirement_identity(mr)[0] == _requirement_identity(pr)[0] and mm.get("name") == pm_name:
                    paired_mm = mm
                    break

            if paired_mm is not None:
                mm_name = str(paired_mm["name"])
                mr_name = str(paired_mm["requirement"])
                mr = mod_reqs_by_name[mr_name]
                merged_req = _meet_requirement_pair(pr, mr, mode=mode, path=["requirements", mod_reqs_list.index(mr)])
                merged_req["name"] = mr_name
                mod_reqs_by_name[mr_name].update(merged_req)
                # Pack names are aliases only after requirement identity has matched.
                aliased_pm = dict(pm, requirement=mr_name)
                merged_mon = _meet_monitor_pair(aliased_pm, paired_mm, mode=mode, path=["monitors", mod_mons_list.index(paired_mm)])
                merged_mon["name"] = mm_name
                merged_mon["requirement"] = mr_name
                merged_mon["applies_to"] = paired_mm.get("applies_to", "agent")
                paired_mm.update(merged_mon)
                alias_map[pm_name] = mm_name
                matched_pack_mons[pm_name] = ("floor_only" if merged_mon["applies_to"] == "tenant_floor" else "merged", mm_name)
            else:
                if pm_name in mod_mons_by_name or str(pr["name"]) in mod_reqs_by_name:
                    raise RuntimeClosedError("runtime_name_collision", path=["monitors"])
                pr_copy = copy.deepcopy(pr)
                if "max_rate" in pr_copy:
                    pr_copy["max_rate"] = _fraction_to_yaml_number(pr_copy["max_rate"])
                mod_reqs_list.append(pr_copy)
                mod_reqs_by_name[str(pr_copy["name"])] = pr_copy
                pm_copy = copy.deepcopy(pm)
                pm_copy["applies_to"] = "tenant_floor"
                mod_mons_list.append(pm_copy)
                mod_mons_by_name[pm_name] = pm_copy
                matched_pack_mons[pm_name] = ("floor_only", pm_name)

        # Pass 2: Rewrite pack `of` references and pair/carry obligation monitors
        for pm in pack_mons:
            pm_name = str(pm["name"])
            pr = copy.deepcopy(pack_reqs[str(pm["requirement"])])
            if pr.get("kind") not in {"recovery_time", "evidence_liveness"}:
                continue
            if "of" in pr and str(pr["of"]) in alias_map:
                pr["of"] = alias_map[str(pr["of"])]
            pm_key = _monitor_effective_key(pm, pr)

            paired_mm = None
            for mm in mod_mons_list:
                mr = mod_reqs_by_name[str(mm["requirement"])]
                if mr.get("kind") not in {"recovery_time", "evidence_liveness"}:
                    continue
                if _monitor_effective_key(mm, mr) == pm_key:
                    paired_mm = mm
                    break

            if paired_mm is not None:
                mm_name = str(paired_mm["name"])
                mr_name = str(paired_mm["requirement"])
                mr = mod_reqs_by_name[mr_name]
                merged_req = _meet_requirement_pair(pr, mr, mode=mode, path=["requirements", mod_reqs_list.index(mr)])
                merged_req["name"] = mr_name
                mod_reqs_by_name[mr_name].update(merged_req)
                aliased_pm = dict(pm, requirement=mr_name)
                merged_mon = _meet_monitor_pair(aliased_pm, paired_mm, mode=mode, path=["monitors", mod_mons_list.index(paired_mm)])
                merged_mon["name"] = mm_name
                merged_mon["requirement"] = mr_name
                merged_mon["applies_to"] = paired_mm.get("applies_to", "agent")
                paired_mm.update(merged_mon)
                alias_map[pm_name] = mm_name
                matched_pack_mons[pm_name] = ("floor_only" if merged_mon["applies_to"] == "tenant_floor" else "merged", mm_name)
            else:
                if pm_name in mod_mons_by_name or str(pr["name"]) in mod_reqs_by_name:
                    raise RuntimeClosedError("runtime_name_collision", path=["monitors"])
                mod_reqs_list.append(pr)
                mod_reqs_by_name[str(pr["name"])] = pr
                pm_copy = copy.deepcopy(pm)
                pm_copy["applies_to"] = "tenant_floor"
                mod_mons_list.append(pm_copy)
                mod_mons_by_name[pm_name] = pm_copy
                matched_pack_mons[pm_name] = ("floor_only", pm_name)

        # Build provenance in pack-monitor order
        for pm in pack_mons:
            pm_name = str(pm["name"])
            match_kind, comp_mon_name = matched_pack_mons[pm_name]
            provenance.append(
                {
                    "monitor": comp_mon_name,
                    "pack_module": pack_mod_name,
                    "pack_monitor": pm_name,
                    "pack_digest": pack_digest,
                    "match": match_kind,
                }
            )

        # Pass 3: Responses (rewrite pack trigger.monitor aliases and merge)
        mod_resps_list = [copy.deepcopy(dict(r)) for r in (overlay.get("responses") or [])]
        mod_resps_by_name = {str(r["name"]): r for r in mod_resps_list}
        for pr_resp in base.get("responses") or []:
            pr_copy = copy.deepcopy(dict(pr_resp))
            for rl in pr_copy.get("rules") or []:
                trig = rl.get("trigger")
                if isinstance(trig, dict) and str(trig.get("monitor")) in alias_map:
                    trig["monitor"] = alias_map[str(trig["monitor"])]
                for field in ("only_while", "unless"):
                    for guard in rl.get(field, []):
                        if "monitor" in guard and guard["monitor"] in alias_map:
                            guard["monitor"] = alias_map[guard["monitor"]]
                if rl.get("do") == "notify":
                    rl["severity"] = rl.get("severity", "critical")
            r_name = str(pr_copy["name"])
            if r_name in mod_resps_by_name:
                target_resp = mod_resps_by_name[r_name]
                target_resp["rules"] = _merge_rules(
                    pr_copy.get("rules") or [],
                    target_resp.get("rules") or [],
                    is_meet=is_meet,
                    path=["responses", mod_resps_list.index(target_resp)],
                )
            else:
                mod_resps_list.append(pr_copy)
                mod_resps_by_name[r_name] = pr_copy

        composed["requirements"] = mod_reqs_list
        composed["monitors"] = mod_mons_list
        if mod_resps_list or "responses" in overlay or "responses" in base:
            composed["responses"] = mod_resps_list

    else:
        # Module overlay or meet (§9.1–§9.3, §9.4 "Meet without a candidate")
        mode = "meet" if operation == "meet" else "overlay"
        is_meet = mode == "meet"

        # Requirements
        if "requirements" in base or "requirements" in overlay:
            if "requirements" not in overlay:
                composed["requirements"] = copy.deepcopy(list(base.get("requirements") or []))
            else:
                base_reqs = [copy.deepcopy(dict(r)) for r in (base.get("requirements") or [])]
                over_reqs = [copy.deepcopy(dict(r)) for r in (overlay.get("requirements") or [])]
                over_by_name = {str(r["name"]): r for r in over_reqs}
                res_reqs: List[Dict[str, Any]] = []
                seen_r: Set[str] = set()
                for br in base_reqs:
                    rname = str(br["name"])
                    seen_r.add(rname)
                    if rname not in over_by_name:
                        if not is_meet:
                            raise RuntimeClosedError("runtime_overlay_weakens", path=["requirements"])
                        res_reqs.append(br)
                    else:
                        res_reqs.append(_meet_requirement_pair(br, over_by_name[rname], mode=mode, path=["requirements", over_reqs.index(over_by_name[rname])]))
                for orq in over_reqs:
                    rname = str(orq["name"])
                    if rname not in seen_r:
                        if "max_rate" in orq:
                            orq["max_rate"] = _fraction_to_yaml_number(orq["max_rate"])
                        res_reqs.append(orq)
                composed["requirements"] = res_reqs

        # Monitors
        if "monitors" in base or "monitors" in overlay:
            if "monitors" not in overlay:
                composed["monitors"] = [_with_monitor_defaults(m) for m in (base.get("monitors") or [])]
            else:
                base_mons = [_with_monitor_defaults(m) for m in (base.get("monitors") or [])]
                over_mons = [_with_monitor_defaults(m) for m in (overlay.get("monitors") or [])]
                over_m_by_name = {str(m["name"]): m for m in over_mons}
                res_mons: List[Dict[str, Any]] = []
                seen_m: Set[str] = set()
                for bm in base_mons:
                    mname = str(bm["name"])
                    seen_m.add(mname)
                    if mname not in over_m_by_name:
                        if not is_meet:
                            raise RuntimeClosedError("runtime_overlay_weakens", path=["monitors"])
                        res_mons.append(bm)
                    else:
                        res_mons.append(_meet_monitor_pair(bm, over_m_by_name[mname], mode=mode, path=["monitors", over_mons.index(over_m_by_name[mname])]))
                for om in over_mons:
                    mname = str(om["name"])
                    if mname not in seen_m:
                        res_mons.append(om)
                composed["monitors"] = res_mons

        # Responses
        if "responses" in base or "responses" in overlay:
            if "responses" not in overlay:
                composed["responses"] = copy.deepcopy(list(base.get("responses") or []))
            else:
                base_resps = [copy.deepcopy(dict(r)) for r in (base.get("responses") or [])]
                over_resps = [copy.deepcopy(dict(r)) for r in (overlay.get("responses") or [])]
                over_resp_by_name = {str(r["name"]): r for r in over_resps}
                res_resps: List[Dict[str, Any]] = []
                seen_resp: Set[str] = set()
                for bresp in base_resps:
                    rname = str(bresp["name"])
                    seen_resp.add(rname)
                    if rname not in over_resp_by_name:
                        if not is_meet:
                            raise RuntimeClosedError("runtime_overlay_weakens", path=["responses"])
                        res_resps.append(bresp)
                    else:
                        merged_r = copy.deepcopy(over_resp_by_name[rname])
                        merged_r["rules"] = _merge_rules(
                            bresp.get("rules") or [],
                            merged_r.get("rules") or [],
                            is_meet=is_meet,
                            path=["responses", over_resps.index(over_resp_by_name[rname])],
                        )
                        res_resps.append(merged_r)
                for oresp in over_resps:
                    rname = str(oresp["name"])
                    if rname not in seen_resp:
                        for rl in oresp.get("rules") or []:
                            if rl.get("do") == "notify":
                                rl["severity"] = rl.get("severity", "critical")
                        res_resps.append(oresp)
                composed["responses"] = res_resps

    # Post-composition validation (§9.5) directly on the composed document (no float-conversion copy)
    _validate_floor_provenance(provenance, [composed])
    prov_to_pass = None if post_validate_without_provenance else provenance
    issues = lint_pack(composed) if overlay_is_pack else lint_module(composed, floor_provenance=prov_to_pass)
    errors = [iss for iss in issues if iss.get("severity") == "error"]
    if errors:
        raise RuntimeClosedError(str(errors[0]["code"]), path=errors[0]["path"], message=errors[0]["message"])

    return composed, provenance
