"""Validate declarations and compile local and hosted TVL runtime contracts."""

from __future__ import annotations

import copy
from tvl.canonical import RuntimeClosedError, canonical_json_digest
from tvl.diagnostics import closed_lint_issue, closed_schema_issues, runtime_syntax_issues
from tvl.lints import _CUSTOMER_CHECKER_RE, _RUNTIME_IDENT_RE, lint_module, lint_pack
from tvl.runtime_compose import compose_runtime_documents
from tvl.runtime_projection import project_runtime_declarations, validate_projected_contract
from tvl.schema import pack_validator, runtime_local_validator, validator as module_validator
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


def compile_runtime_document(
    doc: Mapping[str, Any],
    *,
    token_map_doc: Optional[Mapping[str, Any]],
    packs: Optional[Sequence[Mapping[str, Any]]] = None,
    checker_registry_doc: Optional[Mapping[str, Any]] = None,
    toolchain_version: str = "1.3.0",
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Compile declarations to closed exchange artifacts; evaluation requires an external engine."""
    is_pack = "pack" in doc and "tvl" not in doc
    if is_pack and packs:
        raise RuntimeClosedError("runtime_invalid_profile")

    # Parse optional checker registry
    checker_reg_map: Optional[Dict[str, Sequence[str]]] = None
    checker_labels_list: Optional[List[Mapping[str, Any]]] = None
    checker_reg_digest: Optional[str] = None
    has_customer_checker = False
    for r in doc.get("requirements") or []:
        if isinstance(r, Mapping):
            for k in ("violation", "among"):
                p = r.get(k)
                if isinstance(p, Mapping) and str(p.get("checker", "")).startswith("customer:"):
                    has_customer_checker = True

    if checker_registry_doc is not None:
        if (
            not isinstance(checker_registry_doc, Mapping)
            or checker_registry_doc.get("format") != "tvl-checker-registry/1"
            or not isinstance(checker_registry_doc.get("checkers"), list)
        ):
            raise RuntimeClosedError("runtime_unknown_kind")
        checker_reg_map = {}
        checker_labels_list = []
        for entry in checker_registry_doc["checkers"]:
            if not isinstance(entry, Mapping):
                raise RuntimeClosedError("runtime_unknown_kind")
            cid = entry.get("checker")
            lbls = entry.get("labels")
            if (
                not isinstance(cid, str)
                or not _CUSTOMER_CHECKER_RE.match(cid)
                or cid in checker_reg_map
                or not isinstance(lbls, list)
                or not lbls
                or not all(isinstance(x, str) and _RUNTIME_IDENT_RE.match(x) for x in lbls)
                or len(set(lbls)) != len(lbls)
            ):
                raise RuntimeClosedError("runtime_unknown_kind")
            checker_reg_map[cid] = list(lbls)
            checker_labels_list.append(entry)
        if has_customer_checker:
            checker_reg_digest = canonical_json_digest(checker_registry_doc)
    elif has_customer_checker:
        checker_reg_map = {}

    # Step 1: Schema and lints
    v = pack_validator() if is_pack else module_validator()
    syntax_issues = runtime_syntax_issues(doc)
    if syntax_issues:
        issue = syntax_issues[0]
        raise RuntimeClosedError(issue["code"], path=issue["path"], message=issue["message"])
    s_errs = sorted(v.iter_errors(dict(doc)), key=lambda e: list(e.path))
    if s_errs:
        issue = closed_schema_issues(s_errs)[0]
        raise RuntimeClosedError("schema_error", path=issue["path"], message=issue["message"])

    issues = (
        lint_pack(dict(doc), checker_registry=checker_reg_map)
        if is_pack
        else lint_module(dict(doc), checker_registry=checker_reg_map)
    )
    err_issues = [i for i in issues if i.get("severity") == "error"]
    if err_issues:
        issue = closed_lint_issue(err_issues[0])
        raise RuntimeClosedError(str(issue["code"]), path=issue["path"], message=issue["message"])

    # Step 2: Compose with each --pack (recording packs_checked; contract keeps module's own monitors per §16.3 item 10)
    working_doc = copy.deepcopy(dict(doc))
    packs_checked: List[Dict[str, str]] = []
    if packs:
        if not isinstance(token_map_doc, Mapping) or token_map_doc.get("format") != "tvl-token-map/1":
            raise RuntimeClosedError("runtime_unresolved_alias", path=["tokens"], message="Expected tvl-token-map/1 with tokens entries")
        for p_doc in packs:
            # Validate pack first
            pv_errs = list(pack_validator().iter_errors(dict(p_doc)))
            if pv_errs:
                issue = closed_schema_issues(pv_errs)[0]
                raise RuntimeClosedError("schema_error", path=issue["path"], message=issue["message"])
            p_issues = lint_pack(dict(p_doc), checker_registry=checker_reg_map)
            p_err = [i for i in p_issues if i.get("severity") == "error"]
            if p_err:
                issue = p_err[0]
                raise RuntimeClosedError(str(issue["code"]), path=issue["path"], message=issue["message"])
            composed_doc, _prov = compose_runtime_documents(p_doc, working_doc, operation="overlay")
            # Keep only agent-scope monitors on the module's own contract while retaining tightened fields and composed responses
            agent_mons = [m for m in composed_doc.get("monitors") or [] if m.get("applies_to") != "tenant_floor"]
            agent_mon_names = {str(m.get("name")) for m in agent_mons}
            agent_req_names = {m.get("requirement") for m in agent_mons}
            agent_reqs = [r for r in composed_doc.get("requirements") or [] if r.get("name") in agent_req_names]
            agent_resps: List[Dict[str, Any]] = []
            for resp in composed_doc.get("responses") or []:
                if not isinstance(resp, Mapping):
                    continue
                kept_rules = [
                    copy.deepcopy(dict(rl))
                    for rl in (resp.get("rules") or [])
                    if isinstance(rl, Mapping)
                    and isinstance(rl.get("trigger"), Mapping)
                    and str(rl["trigger"].get("monitor")) in agent_mon_names
                ]
                if kept_rules:
                    resp_copy = copy.deepcopy(dict(resp))
                    resp_copy["rules"] = kept_rules
                    agent_resps.append(resp_copy)
            working_doc["requirements"] = agent_reqs
            working_doc["monitors"] = agent_mons
            if agent_resps or "responses" in working_doc:
                working_doc["responses"] = agent_resps
            p_contract, _, _ = compile_runtime_document(
                p_doc,
                token_map_doc=token_map_doc,
                checker_registry_doc=checker_registry_doc,
                toolchain_version=toolchain_version,
            )
            packs_checked.append(
                {
                    "pack_module_ref": p_contract["declarations"]["pack"]["module"],
                    "pack_contract_digest": canonical_json_digest(p_contract),
                }
            )

    # Step 3: Projection with token map (§8.2)
    if (
        not isinstance(token_map_doc, Mapping)
        or token_map_doc.get("format") != "tvl-token-map/1"
        or not isinstance(token_map_doc.get("tokens"), list)
    ):
        raise RuntimeClosedError("runtime_unresolved_alias", path=["tokens"], message="Expected tvl-token-map/1 with tokens entries")

    local_decls, hosted_decls, backend_profiles, used_tokens = project_runtime_declarations(
        working_doc,
        token_map=token_map_doc["tokens"],
        checker_labels=checker_labels_list,
    )

    contract: Dict[str, Any] = {
        "format": "tvl-runtime-contract/1",
        "tvl_version": "1.3",
        "document": "pack" if is_pack else "module",
        "declarations": hosted_decls,
        "backend_profiles": backend_profiles,
        "packs_checked": packs_checked,
        "toolchain": {"name": "tvl", "version": toolchain_version},
    }
    contract_digest = canonical_json_digest(contract)

    customer_monitors = [
        str(m["name"])
        for m in local_decls["monitors"]
        if m.get("phase") == "runtime" and (m.get("evidence") or {}).get("source") == "customer_side"
    ]
    harness_monitors = [
        str(m["name"])
        for m in local_decls["monitors"]
        if m.get("phase") == "promotion"
    ]
    guards: List[Dict[str, str]] = []
    for resp in local_decls["responses"]:
        for rl in resp.get("rules") or []:
            if rl.get("do") in {"block_action", "halt_unit"}:
                guards.append(
                    {
                        "response": str(resp["name"]),
                        "rule_id": str(rl["id"]),
                        "monitor": str(rl["trigger"]["monitor"]),
                        "action": str(rl["do"]),
                        "on_check_error": str(rl["on_check_error"]),
                    }
                )

    local_prog: Dict[str, Any] = {
        "format": "tvl-runtime-local/1",
        "tvl_version": "1.3",
        "document": "pack" if is_pack else "module",
        "contract_digest": contract_digest,
        "source_digest": canonical_json_digest(local_decls),
        "token_map_digest": canonical_json_digest(token_map_doc),
        "checker_registry_digest": checker_reg_digest,
        "declarations": local_decls,
        "tokens": used_tokens,
        "customer_monitors": customer_monitors,
        "harness_monitors": harness_monitors,
        "guards": guards,
    }

    # Validate generated contract and local program against their schemas and projection invariants
    validate_projected_contract(
        contract,
        doc=working_doc,
        used_tokens=used_tokens,
        checker_labels=checker_labels_list,
    )
    if list(runtime_local_validator().iter_errors(local_prog)):
        raise RuntimeClosedError("runtime_invalid_profile")

    return contract, local_prog, issues
