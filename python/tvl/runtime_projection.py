"""Project local declaration aliases into closed, tokenized hosted contracts."""

from __future__ import annotations

import copy
from tvl.backend_profile_codec import to_backend_profile
from tvl.canonical import RuntimeClosedError, _HOSTED_CHECKER_RE, _REF_RE, minimal_decimal_str
from tvl.lints import _monitor_role
from tvl.diagnostics import field_path
from tvl.schema import runtime_contract_validator
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


def token_map_template(documents: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """List local projection aliases only; customers supply all hosted tokens.

    This local authoring artifact contains names and must stay customer-side.
    """
    entries: Dict[Tuple[str, str], Dict[str, str]] = {}

    def add(namespace: str, local: str) -> None:
        entries[(namespace, local)] = {"namespace": namespace, "local": local, "hosted": ""}

    def predicate(pred: Mapping[str, Any]) -> None:
        checker = pred.get("checker")
        if isinstance(checker, str) and checker.startswith("customer:"):
            add("checker", checker)
        selectors = [pred[k] for k in ("a", "b") if isinstance(pred.get(k), Mapping)]
        selectors.extend(pred.get("alphabet") or [])
        for tr in pred.get("transitions") or []:
            selectors.append(tr["when"])
        for selector in selectors:
            if "ref" in selector:
                add("selector_ref", selector["ref"])
        for state in pred.get("states") or []:
            add("state", state)

    for doc in documents:
        is_pack = "pack" in doc and "tvl" not in doc
        add("module", doc["pack" if is_pack else "tvl"]["module"])
        reqs = {req["name"]: req for req in doc.get("requirements") or []}
        for req in reqs.values():
            add("requirement", req["name"])
            if "of" in req:
                add("monitor", req["of"])
            for key in ("among", "violation"):
                if key in req:
                    predicate(req[key])
        for mon in doc.get("monitors") or []:
            add("monitor", mon["name"])
            add("requirement", mon["requirement"])
            if _monitor_role(mon, reqs[mon["requirement"]]) in {"primary_rate", "primary_zero", "burn"}:
                env = mon["evidence"].get("deployment_environment", "production")
                if mon.get("profile") == "backend_v1":
                    env = env.strip().lower()
                add("environment", env)
        for resp in doc.get("responses") or []:
            add("response", resp["name"])
            for rule in resp["rules"]:
                add("rule", rule["id"])
                add("monitor", rule["trigger"]["monitor"])
    return {"format": "tvl-token-map/1", "tokens": [entries[key] for key in sorted(entries)]}


def _build_token_lookup(
    token_entries: Optional[Sequence[Mapping[str, Any]]],
) -> Tuple[Dict[Tuple[str, str], str], List[Dict[str, str]]]:
    if token_entries is None:
        raise RuntimeClosedError("runtime_unresolved_alias", path=["tokens"], message="tokens requires token-map entries")
    lookup: Dict[Tuple[str, str], str] = {}
    rev_lookup: Dict[Tuple[str, str], str] = {}
    normalized_entries: List[Dict[str, str]] = []
    for idx, entry in enumerate(token_entries):
        if not isinstance(entry, Mapping):
            raise RuntimeClosedError("runtime_unresolved_alias", path=["tokens", idx], message="token-map entry requires namespace, local and a valid unique hosted token")
        ns = entry.get("namespace")
        loc = entry.get("local")
        host = entry.get("hosted")
        if not isinstance(ns, str) or not isinstance(loc, str) or not isinstance(host, str):
            raise RuntimeClosedError("runtime_unresolved_alias", path=["tokens", idx], message="token-map entry requires namespace, local and a valid unique hosted token")
        if ns == "checker":
            if not _HOSTED_CHECKER_RE.match(host):
                raise RuntimeClosedError("runtime_unresolved_alias", path=["tokens", idx], message="token-map entry requires namespace, local and a valid unique hosted token")
        else:
            if not _REF_RE.match(host):
                raise RuntimeClosedError("runtime_unresolved_alias", path=["tokens", idx], message="token-map entry requires namespace, local and a valid unique hosted token")
        key = (ns, loc)
        rkey = (ns, host)
        if key in lookup and lookup[key] != host:
            raise RuntimeClosedError("runtime_unresolved_alias", path=["tokens", idx], message="token-map entry requires namespace, local and a valid unique hosted token")
        if rkey in rev_lookup and rev_lookup[rkey] != loc:
            raise RuntimeClosedError("runtime_unresolved_alias", path=["tokens", idx], message="token-map entry requires namespace, local and a valid unique hosted token")
        lookup[key] = host
        rev_lookup[rkey] = loc
        normalized_entries.append({"namespace": ns, "local": loc, "hosted": host})
    return lookup, normalized_entries


def _resolve_token(lookup: Mapping[Tuple[str, str], str], namespace: str, local_name: Any, path: Sequence[Any]) -> str:
    if not isinstance(local_name, str):
        raise RuntimeClosedError("runtime_unresolved_alias", path=path, message=f"{field_path(path)}: Missing token-map entry for namespace {namespace}")
    key = (namespace, local_name)
    if key not in lookup:
        raise RuntimeClosedError("runtime_unresolved_alias", path=path, message=f"{field_path(path)}: Missing token-map entry for namespace {namespace}")
    return lookup[key]


def _normalize_predicate_local_and_hosted(
    pred: Mapping[str, Any],
    lookup: Mapping[Tuple[str, str], str],
    checker_registry: Mapping[str, Sequence[str]],
    path: Sequence[Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if "metric" in pred:
        metric = str(pred["metric"])
        exceeds = pred["exceeds"]
        if metric in {"wall_clock_latency_ms", "total_tokens", "tool_calls"}:
            exc_val: Any = int(exceeds)
        else:
            exc_val = minimal_decimal_str(exceeds)
        obj = {"metric": metric, "exceeds": exc_val}
        return copy.deepcopy(obj), copy.deepcopy(obj)

    if "checker" in pred:
        chk = str(pred["checker"])
        labels = [str(x) for x in (pred.get("label_in") or [])]
        local_obj = {"checker": chk, "label_in": list(labels)}
        if chk == "traigent.refusal.v1":
            hosted_obj: Dict[str, Any] = {"checker": chk, "label_in": list(labels)}
        else:
            if chk not in checker_registry:
                raise RuntimeClosedError("runtime_unknown_kind", path=[*path, "checker"], message="Customer checker requires a checker-registry entry")
            reg_labels = list(checker_registry[chk])
            indices: List[int] = []
            for idx, lbl in enumerate(labels):
                if lbl not in reg_labels:
                    raise RuntimeClosedError("runtime_unknown_kind", path=[*path, "label_in", idx], message="Checker label requires a registry entry")
                indices.append(reg_labels.index(lbl))
            hosted_chk = _resolve_token(lookup, "checker", chk, [*path, "checker"])
            hosted_obj = {"checker": hosted_chk, "label_in": indices}
        return local_obj, hosted_obj

    pattern = str(pred["pattern"])

    def norm_sel(s: Mapping[str, Any], subpath: Sequence[Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        loc_s: Dict[str, Any] = {"event": str(s["event"])}
        host_s: Dict[str, Any] = {"event": str(s["event"])}
        if "tool" in s:
            loc_s["tool"] = str(s["tool"])
            host_s["tool"] = str(s["tool"])
        if "status" in s:
            loc_s["status"] = str(s["status"])
            host_s["status"] = str(s["status"])
        if "ref" in s:
            loc_s["ref"] = str(s["ref"])
            host_s["ref"] = _resolve_token(lookup, "selector_ref", s["ref"], [*subpath, "ref"])
        return loc_s, host_s

    if pattern == "absence":
        la, ha = norm_sel(pred["a"], [*path, "a"])
        return {"pattern": "absence", "a": la}, {"pattern": "absence", "a": ha}

    if pattern == "bounded_existence":
        la, ha = norm_sel(pred["a"], [*path, "a"])
        mc = int(pred["max_count"])
        return (
            {"pattern": "bounded_existence", "a": la, "max_count": mc},
            {"pattern": "bounded_existence", "a": ha, "max_count": mc},
        )

    if pattern == "precedence":
        la, ha = norm_sel(pred["a"], [*path, "a"])
        lb, hb = norm_sel(pred["b"], [*path, "b"])
        mode = str(pred.get("mode", "single_use"))
        cb = str(pred.get("correlate_by", "unit"))
        return (
            {"pattern": "precedence", "a": la, "b": lb, "mode": mode, "correlate_by": cb},
            {"pattern": "precedence", "a": ha, "b": hb, "mode": mode, "correlate_by": cb},
        )

    if pattern == "bounded_response":
        la, ha = norm_sel(pred["a"], [*path, "a"])
        lb, hb = norm_sel(pred["b"], [*path, "b"])
        wms = int(pred["within_ms"])
        cb = str(pred.get("correlate_by", "unit"))
        return (
            {"pattern": "bounded_response", "a": la, "b": lb, "within_ms": wms, "correlate_by": cb},
            {"pattern": "bounded_response", "a": ha, "b": hb, "within_ms": wms, "correlate_by": cb},
        )

    if pattern == "protocol":
        l_alpha, h_alpha = [], []
        for idx, s in enumerate(pred.get("alphabet") or []):
            ls, hs = norm_sel(s, [*path, "alphabet", idx])
            l_alpha.append(ls)
            h_alpha.append(hs)
        l_states = [str(st) for st in (pred.get("states") or [])]
        h_states = [_resolve_token(lookup, "state", st, [*path, "states", idx]) for idx, st in enumerate(l_states)]
        l_start = str(pred["start"])
        h_start = _resolve_token(lookup, "state", l_start, [*path, "start"])
        l_acc = [str(st) for st in (pred.get("accepting") or [])]
        h_acc = [_resolve_token(lookup, "state", st, [*path, "accepting", idx]) for idx, st in enumerate(l_acc)]
        l_rej = [str(st) for st in (pred.get("rejecting") or [])]
        h_rej = [_resolve_token(lookup, "state", st, [*path, "rejecting", idx]) for idx, st in enumerate(l_rej)]
        l_tr, h_tr = [], []
        for idx, tr in enumerate(pred.get("transitions") or []):
            lw, hw = norm_sel(tr["when"], [*path, "transitions", idx, "when"])
            l_tr.append({"from": str(tr["from"]), "when": lw, "to": str(tr["to"])})
            h_tr.append(
                {
                    "from": _resolve_token(lookup, "state", tr["from"], [*path, "transitions", idx, "from"]),
                    "when": hw,
                    "to": _resolve_token(lookup, "state", tr["to"], [*path, "transitions", idx, "to"]),
                }
            )
        unlisted = str(pred.get("unlisted", "reject"))
        return (
            {
                "pattern": "protocol",
                "alphabet": l_alpha,
                "states": l_states,
                "start": l_start,
                "transitions": l_tr,
                "accepting": l_acc,
                "rejecting": l_rej,
                "unlisted": unlisted,
            },
            {
                "pattern": "protocol",
                "alphabet": h_alpha,
                "states": h_states,
                "start": h_start,
                "transitions": h_tr,
                "accepting": h_acc,
                "rejecting": h_rej,
                "unlisted": unlisted,
            },
        )

    raise RuntimeClosedError("runtime_unknown_kind")


def project_runtime_declarations(
    doc: Mapping[str, Any],
    *,
    token_map: Optional[Sequence[Mapping[str, Any]]],
    checker_labels: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], List[Dict[str, str]]]:
    """Normalize and project runtime declarations to local and hosted form (§8.2, §11.4)."""
    lookup, used_tokens = _build_token_lookup(token_map)
    checker_reg: Dict[str, List[str]] = {}
    for entry in checker_labels or []:
        if isinstance(entry, Mapping) and isinstance(entry.get("checker"), str):
            checker_reg[entry["checker"]] = [str(x) for x in (entry.get("labels") or [])]

    is_pack = "pack" in doc and "tvl" not in doc
    if is_pack:
        mod_local = str((doc.get("pack") or {}).get("module", ""))
        mod_hosted = _resolve_token(lookup, "module", mod_local, ["pack" if is_pack else "tvl", "module"])
        local_decls: Dict[str, Any] = {"pack": {"module": mod_local}}
        hosted_decls: Dict[str, Any] = {"pack": {"module": mod_hosted}}
    else:
        mod_local = str((doc.get("tvl") or {}).get("module", ""))
        mod_hosted = _resolve_token(lookup, "module", mod_local, ["pack" if is_pack else "tvl", "module"])
        local_decls = {"tvl": {"module": mod_local}}
        hosted_decls = {"tvl": {"module": mod_hosted}}

    reqs_by_name: Dict[str, Mapping[str, Any]] = {}
    local_reqs: List[Dict[str, Any]] = []
    hosted_reqs: List[Dict[str, Any]] = []
    for req_idx, req in enumerate(doc.get("requirements") or []):
        rname = str(req["name"])
        reqs_by_name[rname] = req
        h_rname = _resolve_token(lookup, "requirement", rname, ["requirements", req_idx, "name"])
        kind = str(req["kind"])
        unit = str(req["unit"])
        l_req: Dict[str, Any] = {"name": rname, "kind": kind, "unit": unit}
        h_req: Dict[str, Any] = {"name": h_rname, "kind": kind, "unit": unit}
        if "among" in req and isinstance(req["among"], Mapping):
            la, ha = _normalize_predicate_local_and_hosted(req["among"], lookup, checker_reg, ["requirements", req_idx, "among"])
            l_req["among"] = la
            h_req["among"] = ha
        if "violation" in req and isinstance(req["violation"], Mapping):
            lv, hv = _normalize_predicate_local_and_hosted(req["violation"], lookup, checker_reg, ["requirements", req_idx, "violation"])
            l_req["violation"] = lv
            h_req["violation"] = hv
        if "max_rate" in req:
            mr = minimal_decimal_str(req["max_rate"])
            l_req["max_rate"] = mr
            h_req["max_rate"] = mr
        if "of" in req:
            of_loc = str(req["of"])
            l_req["of"] = of_loc
            h_req["of"] = _resolve_token(lookup, "monitor", of_loc, ["requirements", req_idx, "of"])
        if "within_hours" in req:
            wh = int(req["within_hours"])
            l_req["within_hours"] = wh
            h_req["within_hours"] = wh
        if "max_stale_windows" in req:
            msw = int(req["max_stale_windows"])
            l_req["max_stale_windows"] = msw
            h_req["max_stale_windows"] = msw
        local_reqs.append(l_req)
        hosted_reqs.append(h_req)

    local_mons: List[Dict[str, Any]] = []
    hosted_mons: List[Dict[str, Any]] = []
    backend_profiles: List[Dict[str, Any]] = []

    for mon_idx, mon in enumerate(doc.get("monitors") or []):
        mname = str(mon["name"])
        h_mname = _resolve_token(lookup, "monitor", mname, ["monitors", mon_idx, "name"])
        rname = str(mon["requirement"])
        h_rname = _resolve_token(lookup, "requirement", rname, ["monitors", mon_idx, "requirement"])
        req = reqs_by_name[rname]
        role = _monitor_role(mon, req)
        is_backend = mon.get("profile") == "backend_v1"
        phase = str(mon["phase"])
        applies_to = str(mon.get("applies_to", "tenant_floor" if is_pack else "agent"))

        ev = mon.get("evidence") or {}
        source = str(ev["source"])
        l_ev: Dict[str, Any] = {"source": source}
        h_ev: Dict[str, Any] = {"source": source}
        if role in {"primary_rate", "primary_zero", "burn"}:
            env_loc = str(ev.get("deployment_environment", "production"))
            if is_backend:
                env_loc = env_loc.strip().lower()
            env_host = _resolve_token(lookup, "environment", env_loc, ["monitors", mon_idx, "evidence", "deployment_environment"])
            l_ev["deployment_environment"] = env_loc
            h_ev["deployment_environment"] = env_host
            attr = str(ev.get("attribution", "agent_key_exact_v1"))
            l_ev["attribution"] = attr
            h_ev["attribution"] = attr
        if role in {"primary_rate", "primary_zero", "burn", "promotion"}:
            res_rule = str(ev.get("resolution", "terminal_status_v1"))
            l_ev["resolution"] = res_rule
            h_ev["resolution"] = res_rule
        if is_backend or ev.get("sampling") == "unverified":
            l_ev["sampling"] = "unverified"
            h_ev["sampling"] = "unverified"
        elif isinstance(ev.get("sampling"), Mapping):
            sm = ev["sampling"]
            s_obj = {"mode": str(sm["mode"]), "rate": minimal_decimal_str(sm["rate"])}
            l_ev["sampling"] = dict(s_obj)
            h_ev["sampling"] = dict(s_obj)

        dec = mon.get("decision") or {}
        method = str(dec["method"])
        l_dec: Dict[str, Any] = {"method": method}
        h_dec: Dict[str, Any] = {"method": method}
        if role in {"primary_rate", "burn"}:
            mdl = str(dec.get("model", "iid_bernoulli_within_window_v1"))
            l_dec["model"] = mdl
            h_dec["model"] = mdl
        if role == "primary_rate" or (role == "promotion" and req.get("kind") == "rate_bound"):
            c_str = minimal_decimal_str(dec.get("confidence", "0.95" if is_backend else dec.get("confidence")))
            l_dec["confidence"] = c_str
            h_dec["confidence"] = c_str
        if role in {"primary_rate", "burn"} or (role == "promotion" and req.get("kind") == "rate_bound"):
            b_str = minimal_decimal_str(
                dec.get("false_alarm_budget", "0.05" if is_backend else dec.get("false_alarm_budget"))
            )
            l_dec["false_alarm_budget"] = b_str
            h_dec["false_alarm_budget"] = b_str
        if role in {"primary_rate", "burn"}:
            hd = int(dec.get("horizon_days", 30 if is_backend else dec.get("horizon_days")))
            l_dec["horizon_days"] = hd
            h_dec["horizon_days"] = hd
        if role in {"primary_rate", "primary_zero", "burn", "promotion"}:
            default_ms = 200 if is_backend else (1 if role in {"primary_zero", "promotion"} else None)
            ms_val = int(dec.get("min_samples", default_ms))
            l_dec["min_samples"] = ms_val
            h_dec["min_samples"] = ms_val
        if role in {"primary_rate", "burn"} or (role == "promotion" and req.get("kind") == "rate_bound"):
            default_uf = "0.05" if is_backend else ("0" if role == "promotion" else None)
            uf_str = minimal_decimal_str(dec.get("max_unresolved_fraction", default_uf))
            l_dec["max_unresolved_fraction"] = uf_str
            h_dec["max_unresolved_fraction"] = uf_str
        if role == "burn" and "threshold_factor" in dec:
            tf_str = minimal_decimal_str(dec["threshold_factor"])
            l_dec["threshold_factor"] = tf_str
            h_dec["threshold_factor"] = tf_str

        l_mon: Dict[str, Any] = {
            "name": mname,
            "requirement": rname,
            "phase": phase,
            "applies_to": applies_to,
            "evidence": l_ev,
            "decision": l_dec,
        }
        h_mon: Dict[str, Any] = {
            "name": h_mname,
            "requirement": h_rname,
            "phase": phase,
            "applies_to": applies_to,
            "evidence": h_ev,
            "decision": h_dec,
        }
        if is_backend:
            l_mon["profile"] = "backend_v1"
            h_mon["profile"] = "backend_v1"

        if role in {"primary_rate", "primary_zero", "burn"}:
            win = mon.get("window") or {}
            w_obj = {
                "tumbling_hours": int(win.get("tumbling_hours", 6 if is_backend else win.get("tumbling_hours"))),
                "grace_minutes": int(win.get("grace_minutes", 30 if is_backend else win.get("grace_minutes"))),
            }
            l_mon["window"] = dict(w_obj)
            h_mon["window"] = dict(w_obj)

        if role in {"primary_rate", "primary_zero"}:
            ep = mon.get("episode") or {}
            ep_obj = {
                "closure_windows": int(ep.get("closure_windows", 2 if is_backend else ep.get("closure_windows"))),
                "closure_max_age_hours": int(
                    ep.get("closure_max_age_hours", 24 if is_backend else ep.get("closure_max_age_hours"))
                ),
            }
            l_mon["episode"] = dict(ep_obj)
            h_mon["episode"] = dict(ep_obj)

        if "limits" in mon and isinstance(mon["limits"], Mapping):
            lim_obj: Dict[str, int] = {}
            if "max_active_obligations" in mon["limits"]:
                lim_obj["max_active_obligations"] = int(mon["limits"]["max_active_obligations"])
            if "max_tracked_correlations" in mon["limits"]:
                lim_obj["max_tracked_correlations"] = int(mon["limits"]["max_tracked_correlations"])
            l_mon["limits"] = dict(lim_obj)
            h_mon["limits"] = dict(lim_obj)

        viol = req.get("violation") or {}
        among = req.get("among") or {}
        if ("pattern" in viol or "pattern" in among) and not is_backend:
            sp = bool(mon.get("single_producer", False))
            l_mon["single_producer"] = sp
            h_mon["single_producer"] = sp

        local_mons.append(l_mon)
        hosted_mons.append(h_mon)

        if is_backend:
            bp_local, eval_meta = to_backend_profile(req, mon)
            bp_hosted = dict(bp_local)
            bp_hosted.pop("environment", None)
            bp_hosted["environment_ref"] = h_ev["deployment_environment"]
            backend_profiles.append(
                {
                    "monitor_ref": h_mname,
                    "scope": applies_to,
                    "backend_profile": bp_hosted,
                    "evaluation_metadata": eval_meta,
                }
            )

    local_resps: List[Dict[str, Any]] = []
    hosted_resps: List[Dict[str, Any]] = []
    for resp_idx, resp in enumerate(doc.get("responses") or []):
        resp_name = str(resp["name"])
        h_resp_name = _resolve_token(lookup, "response", resp_name, ["responses", resp_idx, "name"])
        l_rules: List[Dict[str, Any]] = []
        h_rules: List[Dict[str, Any]] = []
        for rule_idx, rl in enumerate(resp.get("rules") or []):
            rid = str(rl["id"])
            h_rid = _resolve_token(lookup, "rule", rid, ["responses", resp_idx, "rules", rule_idx, "id"])
            trig = rl["trigger"]
            t_mon_loc = str(trig["monitor"])
            t_mon_host = _resolve_token(lookup, "monitor", t_mon_loc, ["responses", resp_idx, "rules", rule_idx, "trigger", "monitor"])
            t_ev = str(trig["event"])
            l_trig: Dict[str, Any] = {"monitor": t_mon_loc, "event": t_ev}
            h_trig: Dict[str, Any] = {"monitor": t_mon_host, "event": t_ev}
            if "hours" in trig:
                l_trig["hours"] = int(trig["hours"])
                h_trig["hours"] = int(trig["hours"])

            act = str(rl["do"])
            def_app = "none" if act in {"notify", "open_next_step", "block_action", "halt_unit"} else "human"
            app = str(rl.get("approval", def_app))
            l_rl: Dict[str, Any] = {"id": rid, "trigger": l_trig, "do": act, "approval": app}
            h_rl: Dict[str, Any] = {"id": h_rid, "trigger": h_trig, "do": act, "approval": app}
            if "target" in rl:
                l_rl["target"] = str(rl["target"])
                h_rl["target"] = str(rl["target"])
            if act == "notify":
                sev = str(rl.get("severity", "critical"))
                l_rl["severity"] = sev
                h_rl["severity"] = sev
            if "fallback" in rl:
                l_rl["fallback"] = str(rl["fallback"])
                h_rl["fallback"] = str(rl["fallback"])
            if "rate_floor" in rl:
                rf = minimal_decimal_str(rl["rate_floor"])
                l_rl["rate_floor"] = rf
                h_rl["rate_floor"] = rf
            if "repeat_after_hours" in rl:
                l_rl["repeat_after_hours"] = int(rl["repeat_after_hours"])
                h_rl["repeat_after_hours"] = int(rl["repeat_after_hours"])
            if "max_repeats" in rl:
                l_rl["max_repeats"] = int(rl["max_repeats"])
                h_rl["max_repeats"] = int(rl["max_repeats"])
            if "on_check_error" in rl:
                l_rl["on_check_error"] = str(rl["on_check_error"])
                h_rl["on_check_error"] = str(rl["on_check_error"])
            l_rules.append(l_rl)
            h_rules.append(h_rl)
        local_resps.append({"name": resp_name, "rules": l_rules})
        hosted_resps.append({"name": h_resp_name, "rules": h_rules})

    local_decls["requirements"] = local_reqs
    local_decls["monitors"] = local_mons
    local_decls["responses"] = local_resps

    hosted_decls["requirements"] = hosted_reqs
    hosted_decls["monitors"] = hosted_mons
    hosted_decls["responses"] = hosted_resps

    return local_decls, hosted_decls, backend_profiles, used_tokens


def validate_projected_contract(
    contract: Mapping[str, Any],
    *,
    doc: Optional[Mapping[str, Any]] = None,
    used_tokens: Optional[Sequence[Mapping[str, str]]] = None,
    checker_labels: Optional[Sequence[Mapping[str, Any]]] = None,
) -> None:
    """Validate a projected tvl-runtime-contract/1 against the closed schema and token-mapping invariants."""
    if list(runtime_contract_validator().iter_errors(dict(contract))):
        raise RuntimeClosedError("runtime_unsafe_egress")

    if used_tokens is not None:
        by_ns: Dict[Tuple[str, str], str] = {
            (str(t["namespace"]), str(t["local"])): str(t["hosted"]) for t in used_tokens
        }
        decls = contract.get("declarations") or {}
        if doc is not None:
            is_pack = "pack" in doc and "tvl" not in doc
            if is_pack:
                loc_m = str((doc.get("pack") or {}).get("module", ""))
                if (decls.get("pack") or {}).get("module") != by_ns.get(("module", loc_m)):
                    raise RuntimeClosedError("runtime_unsafe_egress")
            else:
                loc_m = str((doc.get("tvl") or {}).get("module", ""))
                if (decls.get("tvl") or {}).get("module") != by_ns.get(("module", loc_m)):
                    raise RuntimeClosedError("runtime_unsafe_egress")

            doc_reqs = list(doc.get("requirements") or [])
            h_reqs = list(decls.get("requirements") or [])
            if len(doc_reqs) != len(h_reqs):
                raise RuntimeClosedError("runtime_unsafe_egress")
            for dr, hr in zip(doc_reqs, h_reqs):
                if hr.get("name") != by_ns.get(("requirement", str(dr.get("name")))):
                    raise RuntimeClosedError("runtime_unsafe_egress")
                if "of" in dr and hr.get("of") != by_ns.get(("monitor", str(dr.get("of")))):
                    raise RuntimeClosedError("runtime_unsafe_egress")

            doc_mons = list(doc.get("monitors") or [])
            h_mons = list(decls.get("monitors") or [])
            if len(doc_mons) != len(h_mons):
                raise RuntimeClosedError("runtime_unsafe_egress")
            for dm, hm in zip(doc_mons, h_mons):
                if hm.get("name") != by_ns.get(("monitor", str(dm.get("name")))):
                    raise RuntimeClosedError("runtime_unsafe_egress")
                if hm.get("requirement") != by_ns.get(("requirement", str(dm.get("requirement")))):
                    raise RuntimeClosedError("runtime_unsafe_egress")

            doc_resps = list(doc.get("responses") or [])
            h_resps = list(decls.get("responses") or [])
            if len(doc_resps) != len(h_resps):
                raise RuntimeClosedError("runtime_unsafe_egress")
            for dresp, hresp in zip(doc_resps, h_resps):
                if hresp.get("name") != by_ns.get(("response", str(dresp.get("name")))):
                    raise RuntimeClosedError("runtime_unsafe_egress")
                d_rules = list(dresp.get("rules") or [])
                h_rules = list(hresp.get("rules") or [])
                if len(d_rules) != len(h_rules):
                    raise RuntimeClosedError("runtime_unsafe_egress")
                for drl, hrl in zip(d_rules, h_rules):
                    if hrl.get("id") != by_ns.get(("rule", str(drl.get("id")))):
                        raise RuntimeClosedError("runtime_unsafe_egress")
                    d_mon = str((drl.get("trigger") or {}).get("monitor", ""))
                    if (hrl.get("trigger") or {}).get("monitor") != by_ns.get(("monitor", d_mon)):
                        raise RuntimeClosedError("runtime_unsafe_egress")


def resolve_json_pointer(doc: Any, pointer: str) -> Any:
    """Resolve an RFC 6901 JSON pointer against doc."""
    if not pointer or pointer == "/":
        return doc
    if not pointer.startswith("/"):
        raise ValueError(f"Invalid JSON pointer: {pointer}")
    curr = doc
    for raw_part in pointer.split("/")[1:]:
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(curr, list):
            curr = curr[int(part)]
        elif isinstance(curr, Mapping):
            curr = curr[part]
        else:
            raise KeyError(part)
    return curr


def _predicate_class_for_req(req: Mapping[str, Any]) -> Optional[str]:
    viol = req.get("violation")
    if not isinstance(viol, Mapping):
        return None
    if "metric" in viol:
        return "metric"
    if "checker" in viol:
        return "checker_pred"
    if "pattern" in viol:
        return "exact_pred"
    return None
