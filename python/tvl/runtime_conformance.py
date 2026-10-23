"""Public declaration conformance. Passing these cases never enables an engine."""
from __future__ import annotations
from fractions import Fraction
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple
from tvl.canonical import canonical_json_digest
from tvl.lints import lint_module, lint_pack
from tvl.measurement import prepare_measurement_bundle
from tvl.runtime_projection import has_projected_15_construct, has_projected_reactive_construct
from tvl.runtime import (
    RuntimeClosedError, compose_runtime_documents, erase_runtime_extensions,
    from_backend_revision, join_promotion_decisions, minimal_decimal_str,
    project_runtime_declarations, resolve_json_pointer, to_backend_profile,
    validate_projected_contract,
)

class ConformanceFailureError(Exception):
    """Raised when a runtime conformance assertion fails (never stripped under python -O)."""


def _check(condition: bool, message: str = "Runtime conformance assertion failed") -> None:
    if not condition:
        raise ConformanceFailureError(message)


_ALLOWED_EXPECTED_KEYS_BY_KIND = {'compose': {'absent_diagnostics', 'floor_matches', 'error', 'composed_fields'},
 'trace': {'notifications'},
 'join': {'promotion_decision', 'error'},
 'lint': {'absent_diagnostics', 'diagnostics'},
 'measurement': {'normalized_monitor_outcomes', 'readiness_issues'},
 'projection': {'forbidden_substrings', 'projected_fields', 'contract_digest', 'error'},
 'roundtrip': {'backend_profile',
               'evaluation_metadata',
               'legacy_projection',
               'roundtrip_preserved',
               'runtime_empty'},
 'toolchain': {'composed_fields',
               'construct',
               'document_kind',
               'error',
               'exit_code',
               'projected_fields',
               'roundtrip_preserved'}}

def run_runtime_conformance_case(case, *, case_path=None):
    """Check a public language fixture; unknown kinds and assertions fail closed."""
    inp, expected = case["input"], case["expected"]
    kind = str(inp["kind"])
    doc = case.get("module") or case.get("pack") or {}
    allowed_keys = _ALLOWED_EXPECTED_KEYS_BY_KIND.get(kind)
    _check(allowed_keys is not None, f"Unsupported input kind: {kind}")
    _check(isinstance(expected, Mapping) and bool(expected) and set(expected) <= allowed_keys,
           f"Unknown or disallowed expected keys for {kind}")
    if kind == "trace":
        from tvl.runtime_trace import notification_trace
        _check(set(inp) == {"kind", "history"}, "Unknown trace input key")
        _check("module" in case, "Trace needs a module")
        actual = notification_trace(case["module"], inp["history"])
        _check(actual == expected["notifications"],
               f"Notification sequence mismatch: actual={actual!r}, expected={expected['notifications']!r}")
        return
    if kind == "toolchain":
        if inp.get("reader") in {"pre_13", "pre_15"}:
            tool_keys = {"exit_code", "error"}
        elif inp.get("entrypoint") == "tvl-compile-runtime":
            tool_keys = {"exit_code", "composed_fields", "projected_fields"}
        elif inp.get("entrypoint") == "tvl-compose":
            tool_keys = {"exit_code", "composed_fields", "roundtrip_preserved"}
        else:
            tool_keys = {"exit_code", "error", "construct", "document_kind"}
        _check(set(expected) <= tool_keys, "Assertion is not supported by this language command")
    if kind in {"persistence", "aggregate", "report", "commitment"}:
        _run_rfc0005_case(kind, inp, expected)
        return
    if kind == "schema":
        from tvl.schema import runtime_report_validator
        _check((not list(runtime_report_validator().iter_errors(inp["instance"]))) is expected["schema_valid"], "Report schema mismatch")
        return
    if kind == "join":
        try:
            decision = join_promotion_decisions(inp["legacy_decision"], inp["monitor_verdicts"])
        except RuntimeClosedError as exc:
            _check(expected == {"error": exc.code}, f"Unexpected error {exc.code}")
            return
        _check(expected == {"promotion_decision": decision}, "Promotion join mismatch")
        return
    if kind == "compose":
        try:
            composed, prov = compose_runtime_documents(
                case["base"],
                case["overlay"],
                operation=str(inp["operation"]),
                post_validate_without_provenance=bool(inp.get("post_validate_without_provenance", False)),
            )
        except RuntimeClosedError as exc:
            _check("error" in expected and expected["error"] == exc.code, f"Unexpected error {exc.code}")
            return

        _check("error" not in expected, f"Expected error {expected['error'] if 'error' in expected else None}, got success")
        if "composed_fields" in expected:
            for ptr, exp_val in expected["composed_fields"].items():
                got_val = resolve_json_pointer(composed, ptr)
                if isinstance(exp_val, str) and isinstance(got_val, (int, float, Fraction)):
                    got_val = minimal_decimal_str(got_val)
                _check(got_val == exp_val, f"composed_fields mismatch at {ptr}")
        if "floor_matches" in expected:
            _check([p["match"] for p in prov] == expected["floor_matches"], "floor_matches mismatch")
        if "absent_diagnostics" in expected:
            issues = lint_module(
                composed,
                floor_provenance=None if inp.get("post_validate_without_provenance") else prov,
            )
            got_codes = {i["code"] for i in issues}
            for ac in expected["absent_diagnostics"]:
                _check(ac not in got_codes, f"Unexpected diagnostic {ac}")
        return

    if kind == "lint":
        issues = lint_pack(case["pack"]) if "pack" in case else lint_module(case["module"])
        got_pairs = {(i["code"], i["severity"]) for i in issues}
        got_codes = {i["code"] for i in issues}
        if "diagnostics" in expected:
            for d in expected["diagnostics"]:
                _check((d["code"], d["severity"]) in got_pairs, f"Missing diagnostic {d}")
        if "absent_diagnostics" in expected:
            for a in expected["absent_diagnostics"]:
                _check(a not in got_codes, f"Unexpected diagnostic {a}")
        return

    if kind == "projection":
        try:
            _loc, hosted_decls, bp_entries, used_tokens = project_runtime_declarations(
                doc,
                token_map=inp.get("token_map"),
                checker_labels=inp.get("checker_labels"),
            )
            from tvl.conformance_helpers import inject_projection_fields
            inject_projection_fields(hosted_decls, inp.get("requested_fields"))
            has_reactive_construct = has_projected_reactive_construct(hosted_decls)
            has_15_construct = has_projected_15_construct(hosted_decls)
            contract_slice = {
                "format": inp.get("contract_format", "tvl-runtime-contract/3" if has_15_construct else ("tvl-runtime-contract/2" if has_reactive_construct else "tvl-runtime-contract/1")),
                "tvl_version": inp.get("contract_version", "1.5" if has_15_construct else ("1.4" if has_reactive_construct else "1.3")),
                "document": "pack" if "pack" in case else "module",
                "declarations": hosted_decls,
                "backend_profiles": bp_entries,
                "packs_checked": [],
                "toolchain": {"name": "tvl", "version": "1.3.0"},
            }
            validate_projected_contract(
                contract_slice,
                doc=doc,
                used_tokens=used_tokens,
                checker_labels=inp.get("checker_labels"),
            )
            serialized = json.dumps(contract_slice, sort_keys=True)
        except RuntimeClosedError as exc:
            err_payload = {"code": exc.code}
            serialized = json.dumps(err_payload, sort_keys=True)
            _check("error" in expected and expected["error"] == exc.code, f"Unexpected error {exc.code}")
            if "forbidden_substrings" in expected:
                for sub in expected["forbidden_substrings"]:
                    _check(sub not in serialized, f"Forbidden substring {sub!r} leaked in error")
            return

        _check("error" not in expected, f"Expected error {expected['error'] if 'error' in expected else None}, got success")
        if "contract_digest" in expected:
            _check(canonical_json_digest(contract_slice) == expected["contract_digest"], "Canonical contract bytes differ from the frozen digest")
        if "projected_fields" in expected:
            for ptr, exp_val in expected["projected_fields"].items():
                got_val = resolve_json_pointer(contract_slice, ptr)
                _check(got_val == exp_val, f"projected_fields mismatch at {ptr}")
        if "forbidden_substrings" in expected:
            for sub in expected["forbidden_substrings"]:
                _check(sub not in serialized, f"Forbidden substring {sub!r} leaked in contract")
        # Also verify local declaration names do not leak into the hosted contract unless equal to hosted token
        hosted_token_vals = {str(t["hosted"]) for t in (inp.get("token_map") or []) if isinstance(t, Mapping) and "hosted" in t}
        local_decl_names: List[str] = []
        mod_hdr = doc.get("tvl") or doc.get("pack") or {}
        if isinstance(mod_hdr, Mapping) and isinstance(mod_hdr.get("module"), str):
            local_decl_names.append(mod_hdr["module"])
        for blk in ("requirements", "monitors", "responses"):
            for item in doc.get(blk) or []:
                if isinstance(item, Mapping) and isinstance(item.get("name"), str):
                    local_decl_names.append(item["name"])
        for ln in local_decl_names:
            if ln and ln not in hosted_token_vals:
                _check(f'"{ln}"' not in serialized, f"Local declaration name {ln!r} leaked into hosted contract")
        return

    if kind == "roundtrip":
        op = inp["operation"]
        if op == "legacy_erasure":
            erased, rt_empty = erase_runtime_extensions(doc)
            if "legacy_projection" in expected:
                _check(erased == expected["legacy_projection"], "legacy_projection mismatch")
            if "runtime_empty" in expected:
                _check(rt_empty == expected["runtime_empty"], "runtime_empty mismatch")
        else:
            mon_name = str(inp["monitor"])
            mons = {m["name"]: m for m in (doc.get("monitors") or []) if isinstance(m, Mapping)}
            reqs = {r["name"]: r for r in (doc.get("requirements") or []) if isinstance(r, Mapping)}
            mon = mons[mon_name]
            req = reqs[mon["requirement"]]
            bp, meta = to_backend_profile(req, mon)
            lifted_req, lifted_mon = from_backend_revision(
                inp["backend_profile"],
                requirement_name=req["name"],
                monitor_name=mon["name"],
                applies_to=mon.get("applies_to", "agent"),
            )
            bp2, meta2 = to_backend_profile(lifted_req, lifted_mon)
            rt_preserved = (bp == inp["backend_profile"]) and (bp2 == inp["backend_profile"]) and (meta == meta2)
            if "backend_profile" in expected:
                _check(bp == expected["backend_profile"], "backend_profile mismatch")
            if "evaluation_metadata" in expected:
                _check(meta == expected["evaluation_metadata"], "evaluation_metadata mismatch")
            if "roundtrip_preserved" in expected:
                _check(rt_preserved == expected["roundtrip_preserved"], "roundtrip_preserved mismatch")
        return

    if kind == "measurement":
        role = str(inp["role"])
        meas_bundle = {
            "objective_values": {
                "quality": {"samples": [1.0, 1.1, 1.2]}
            },
            "monitor_outcomes": inp["monitor_outcomes"],
        }
        norm_b, _warns, readiness = prepare_measurement_bundle(doc, meas_bundle, role=role)
        ext_readiness = [r["code"] for r in readiness if r.get("code") == "missing_monitor_counts"]
        if "readiness_issues" in expected:
            _check(ext_readiness == expected["readiness_issues"], "readiness_issues mismatch")
        if "normalized_monitor_outcomes" in expected:
            _check(
                norm_b.get("monitor_outcomes") == expected["normalized_monitor_outcomes"],
                "normalized_monitor_outcomes mismatch",
            )
        return

    if kind == "toolchain":
        _run_toolchain_conformance_case(case)
        return

    raise ConformanceFailureError(f"Unsupported input kind: {kind}")

def _build_synthetic_tokens_for_docs(docs: Sequence[Mapping[str, Any]]) -> List[Dict[str, str]]:
    """Build synthetic token map entries following README-oracle-findings.md conventions."""
    tokens: List[Dict[str, str]] = []
    seen: Set[Tuple[str, str]] = set()

    def add_tok(ns: str, local_name: str, hosted_name: str) -> None:
        if not local_name or (ns, local_name) in seen:
            return
        seen.add((ns, local_name))
        tokens.append({"namespace": ns, "local": local_name, "hosted": hosted_name})

    for d in docs:
        hdr = d.get("tvl") or d.get("pack") or {}
        if isinstance(hdr, Mapping) and isinstance(hdr.get("module"), str):
            m_loc = hdr["module"]
            add_tok("module", m_loc, "opaque_module" if m_loc == "conformance.runtime" else f"opaque_{m_loc}")
        for r in d.get("requirements") or []:
            if isinstance(r, Mapping) and isinstance(r.get("name"), str):
                r_loc = r["name"]
                add_tok("requirement", r_loc, "opaque_req" if r_loc == "requirement_main" else f"opaque_{r_loc}")
        for m in d.get("monitors") or []:
            if isinstance(m, Mapping) and isinstance(m.get("name"), str):
                m_loc = m["name"]
                add_tok("monitor", m_loc, "opaque_monitor" if m_loc == "monitor_main" else f"opaque_{m_loc}")
                ev = m.get("evidence") or {}
                if isinstance(ev, Mapping):
                    env_loc = str(ev.get("deployment_environment", "production"))
                    add_tok("environment", env_loc, "opaque_env" if env_loc == "production" else f"opaque_{env_loc}")
        add_tok("environment", "production", "opaque_env")
        for resp in d.get("responses") or []:
            if isinstance(resp, Mapping) and isinstance(resp.get("name"), str):
                resp_loc = resp["name"]
                add_tok("response", resp_loc, f"opaque_{resp_loc}")
                for rl in resp.get("rules") or []:
                    if isinstance(rl, Mapping) and isinstance(rl.get("id"), str):
                        rl_loc = rl["id"]
                        add_tok("rule", rl_loc, f"opaque_{rl_loc}")
    return tokens


def _run_toolchain_conformance_case(case: Mapping[str, Any]) -> None:
    """Execute a toolchain conformance probe (reader pre_13 or v1_3 CLI entrypoints)."""
    from contextlib import ExitStack, redirect_stderr, redirect_stdout
    import copy
    import io
    import sys
    import shutil
    from tempfile import mkdtemp
    import yaml

    from jsonschema import Draft202012Validator
    from tvl.runtime import resolve_json_pointer
    from tvl.schema import load_schema, runtime_contract_validator, runtime_local_validator
    from tvl.yaml_safe import safe_load

    inp = case["input"]
    expected = case["expected"]
    entrypoint = str(inp["entrypoint"])
    reader = str(inp["reader"])
    args_list = [str(a) for a in (inp.get("arguments") or [])]

    if reader in {"pre_13", "pre_15"}:
        raw_schema = copy.deepcopy(load_schema("tvl.schema.json"))
        if reader == "pre_13":
            for k in ("requirements", "monitors", "responses"):
                raw_schema.get("properties", {}).pop(k, None)
        else:
            # A TVL 1.4 reader: closed shapes without the RFC 0005 keys refuse them.
            for definition, keys in (("RequirementDecl", ("aggregate", "bound")), ("RuleDecl", ("persist",))):
                for key in keys:
                    raw_schema["$defs"][definition]["properties"].pop(key)
        v_old = Draft202012Validator(raw_schema)
        doc = safe_load(inp["document_yaml"]) if "document_yaml" in inp else case.get("module")
        errs = list(v_old.iter_errors(doc))
        exit_code = 2 if errs else 0
        err_code = "schema_error" if errs else None
        if "exit_code" in expected:
            _check(exit_code == expected["exit_code"], "pre_13 exit_code mismatch")
        if "error" in expected:
            _check(err_code == expected["error"], "pre_13 error mismatch")
        return

    with ExitStack() as cleanup:
        tmpdir = mkdtemp()
        cleanup.callback(shutil.rmtree, tmpdir)
        tmp = Path(tmpdir)
        if entrypoint == "tvl-compile-runtime":
            from tvl_tools.tvl_compile_runtime.cli import run_cli as run_compile_cli

            docs_for_tokens: List[Mapping[str, Any]] = []
            pack_path = tmp / "pack.yml"
            mod_path = tmp / "module.yml"
            if "base" in case and isinstance(case["base"], Mapping):
                pack_path.write_text(yaml.safe_dump(case["base"], sort_keys=False), encoding="utf-8")
                docs_for_tokens.append(case["base"])
            src_doc = case.get("overlay") or case.get("module") or case.get("pack")
            _check(isinstance(src_doc, Mapping), "Missing source document for tvl-compile-runtime")
            mod_path.write_text(yaml.safe_dump(src_doc, sort_keys=False), encoding="utf-8")
            docs_for_tokens.append(src_doc)  # type: ignore[arg-type]

            tokens_path = tmp / "tokens.json"
            tokens_path.write_text(
                json.dumps({"format": "tvl-token-map/1", "tokens": _build_synthetic_tokens_for_docs(docs_for_tokens)}),
                encoding="utf-8",
            )
            expanded_args: List[str] = []
            for a in args_list:
                if a == "--pack":
                    expanded_args.extend(["--pack", str(pack_path)])
                else:
                    expanded_args.append(a)
            out_dir = tmp / "out"
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exit_code, _res = run_compile_cli(
                    [str(mod_path), *expanded_args, "--token-map", str(tokens_path), "--out-dir", str(out_dir), "--format", "json"],
                        )
            if "exit_code" in expected:
                _check(exit_code == expected["exit_code"], f"compile exit_code {exit_code} != {expected['exit_code']}")
            if exit_code == 0:
                emitted_contract = json.loads((out_dir / "runtime-contract.json").read_text(encoding="utf-8"))
                emitted_local = json.loads((out_dir / "runtime-local.json").read_text(encoding="utf-8"))
                _check(not list(runtime_contract_validator(emitted_contract["format"]).iter_errors(emitted_contract)), "Emitted contract failed schema")
                _check(not list(runtime_local_validator(emitted_local["format"]).iter_errors(emitted_local)), "Emitted local failed schema")
                if "composed_fields" in expected:
                    for ptr, exp_val in expected["composed_fields"].items():
                        got_val = resolve_json_pointer(emitted_local, ptr)
                        _check(got_val == exp_val, f"compile composed_fields mismatch at {ptr}")
                if "projected_fields" in expected:
                    for ptr, exp_val in expected["projected_fields"].items():
                        got_val = resolve_json_pointer(emitted_contract, ptr)
                        _check(got_val == exp_val, f"compile projected_fields mismatch at {ptr}")
            return

        if entrypoint == "tvl-compose":
            from tvl_tools.tvl_compose.cli import main as compose_main
            from tvl_tools.tvl_validate.cli import main as validate_main

            pack_path = tmp / "pack.yml"
            mod_path = tmp / "module.yml"
            composed_path = tmp / "composed.yml"
            if "base" in case and isinstance(case["base"], Mapping):
                pack_path.write_text(yaml.safe_dump(case["base"], sort_keys=False), encoding="utf-8")
            src_doc = case.get("overlay") or case.get("module")
            _check(isinstance(src_doc, Mapping), "Missing module for tvl-compose")
            mod_path.write_text(yaml.safe_dump(src_doc, sort_keys=False), encoding="utf-8")

            expanded_args = []
            for a in args_list:
                if a == "--pack":
                    expanded_args.extend(["--pack", str(pack_path)])
                else:
                    expanded_args.append(a)

            argv = ["tvl-compose", str(mod_path), *expanded_args, "-o", str(composed_path), "--format", "json"]
            old_argv = sys.argv
            exit_code = 0
            try:
                sys.argv = argv
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    compose_main()
            except SystemExit as exc:
                exit_code = int(exc.code) if isinstance(exc.code, int) else 2
            finally:
                sys.argv = old_argv

            if "exit_code" in expected:
                _check(exit_code == expected["exit_code"], f"tvl-compose exit_code {exit_code} != {expected['exit_code']}")
            if exit_code == 0 and composed_path.exists():
                emitted_yaml_doc = safe_load(composed_path.read_text(encoding="utf-8"))
                if "composed_fields" in expected:
                    for ptr, exp_val in expected["composed_fields"].items():
                        got_val = resolve_json_pointer(emitted_yaml_doc, ptr)
                        _check(
                            type(got_val) is type(exp_val) and got_val == exp_val,
                            f"tvl-compose field {ptr} mismatch: {got_val!r} ({type(got_val).__name__}) != {exp_val!r}",
                        )
                if "roundtrip_preserved" in expected:
                    v_out = io.StringIO()
                    v_exit = 0
                    try:
                        sys.argv = ["tvl-validate", str(composed_path), "--format", "json"]
                        with redirect_stdout(v_out), redirect_stderr(io.StringIO()):
                            validate_main()
                    except SystemExit as exc:
                        v_exit = int(exc.code) if isinstance(exc.code, int) else 2
                    finally:
                        sys.argv = old_argv
                    v_json = json.loads(v_out.getvalue()) if v_out.getvalue().strip() else {}
                    rt_ok = (v_exit == 0) and (v_json.get("ok") is True)
                    _check(rt_ok == expected["roundtrip_preserved"], f"tvl-validate on composed output failed: {v_json}")
            return

        doc_path = tmp / "doc.yml"
        if "document_yaml" in inp:
            doc_path.write_text(str(inp["document_yaml"]), encoding="utf-8")
        else:
            payload_doc = case.get("pack") if "pack" in case else case.get("module")
            doc_path.write_text(yaml.safe_dump(payload_doc, sort_keys=False), encoding="utf-8")

        from tvl_tools.runtime_cli_harness import invoke_entrypoint

        exit_code, out_data = invoke_entrypoint(
            entrypoint=entrypoint,
            doc_path=doc_path,
            extra_args=args_list,
            measurement_role=inp.get("measurement_role"),
            monitor_outcomes=inp.get("monitor_outcomes"),
            measurement_format=inp.get("measurement_format"),
            tmp_dir=tmp,
        )
        if "exit_code" in expected:
            _check(exit_code == expected["exit_code"], f"CLI {entrypoint} exit_code {exit_code} != {expected['exit_code']}")
        if "error" in expected:
            got_err = out_data.get("code") or out_data.get("error")
            if got_err != expected["error"] and isinstance(out_data.get("issues"), list) and out_data["issues"]:
                got_err = out_data["issues"][0].get("code")
            _check(got_err == expected["error"], f"CLI {entrypoint} error {got_err!r} != {expected['error']!r}")
        if "construct" in expected:
            _check(out_data.get("construct") == expected["construct"], "CLI construct mismatch")
        if "document_kind" in expected:
            _check(out_data.get("document_kind") == expected["document_kind"], "CLI document_kind mismatch")


LANGUAGE_FAMILY_GLOBS = {'language/codec': ('latency_roundtrip/*.yml',),
 'language/compat': ('compatibility/*.yml',),
 'language/compose': ('composition/*.yml',),
 'language/lint': ('lints/*.yml',),
 'language/projection': ('projection/*.yml',),
 'language/promotion': ('promotion/*.yml',)}

_ALLOWED_EXPECTED_KEYS_BY_KIND["schema"] = {"schema_valid"}
LANGUAGE_FAMILY_GLOBS["language/report_shape"] = ("report_schema/*.yml",)
LANGUAGE_FAMILY_GLOBS["language/semantic_trace"] = ("semantic_traces/*.yml",)
_ALLOWED_EXPECTED_KEYS_BY_KIND.update({
    "persistence": {"persistence"},
    "aggregate": {"aggregate"},
    "report": {"accepted", "error"},
    "commitment": {"commitment"},
})
LANGUAGE_FAMILY_GLOBS["language/persistence"] = ("persistence/*.yml",)
LANGUAGE_FAMILY_GLOBS["language/aggregate"] = ("aggregate/*.yml",)
LANGUAGE_FAMILY_GLOBS["language/aggregate_report"] = ("aggregate_report/*.yml",)


def _subset(expected: Any, actual: Any, where: str = "") -> None:
    """Every asserted key must match; keys the case does not assert are not compared."""
    if isinstance(expected, Mapping):
        _check(isinstance(actual, Mapping), f"{where}: expected a mapping")
        for key, value in expected.items():
            _check(key in actual, f"{where}/{key}: missing")
            _subset(value, actual[key], f"{where}/{key}")
    elif isinstance(expected, list):
        _check(isinstance(actual, list) and len(actual) == len(expected), f"{where}: list length differs")
        for index, (want, got) in enumerate(zip(expected, actual)):
            _subset(want, got, f"{where}/{index}")
    else:
        _check(type(expected) is type(actual) and expected == actual, f"{where}: {actual!r} != {expected!r}")


def _run_rfc0005_case(kind: str, inp: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    """RFC 0005 recorded-history relations (reference relations, not an evaluator)."""
    import hashlib
    from tvl.runtime_aggregate import (
        aggregate_verdict, persistence_decisions, persistence_result, persistence_slots,
        units_commitment_v1, units_commitment_v2, validate_report_v2,
    )
    if kind == "persistence":
        _check(set(inp) <= {"kind", "persist", "rule_event", "identity", "windows", "events", "index"}, "Unknown persistence input key")
        persist, identity, windows = inp["persist"], inp["identity"], inp["windows"]
        if "events" in inp:
            actual: dict[str, Any] = {"decisions": persistence_decisions(persist, inp["rule_event"], windows, inp["events"], identity)}
            if "index" in inp:
                slots = persistence_slots(persist["of_last"], inp["index"], windows, identity)
                actual["result"] = persistence_result(persist["breached_in"], persist["of_last"], [s["verdict"] for s in slots])[0]
        else:
            slots = persistence_slots(persist["of_last"], inp["index"], windows, identity)
            result, reason = persistence_result(persist["breached_in"], persist["of_last"], [s["verdict"] for s in slots])
            actual = {"result": result, "slots": slots}
            if reason:
                actual["reason"] = reason
        _subset(expected["persistence"], actual, "persistence")
        return
    if kind == "aggregate":
        _check(set(inp) == {"kind", "aggregate"}, "Unknown aggregate input key")
        _subset(expected["aggregate"], aggregate_verdict(inp["aggregate"]), "aggregate")
        return
    if kind == "report":
        _check(set(inp) == {"kind", "report", "binding"}, "Unknown report input key")
        try:
            validate_report_v2(inp["report"], inp["binding"])
        except RuntimeClosedError as exc:
            _check(expected == {"error": exc.code}, f"Unexpected error {exc.code}")
            return
        _check(expected == {"accepted": True}, "Report accepted but an error was expected")
        return
    _check(set(inp) <= {"kind", "version", "secret_hex", "report", "units"}, "Unknown commitment input key")
    if inp["version"] == 1:
        digest = units_commitment_v1(inp["units"])
        # Independent recomputation of the report/1 rule (RFC 0003 11.4.3), not via the same function.
        listed = sorted(({"unit_id": u["unit_id"], "class": u["class"]} for u in inp["units"]), key=lambda u: u["unit_id"])
        reference = hashlib.sha256((json.dumps(listed, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()).hexdigest()
        _check(digest == reference, "report/1 digest changed")
    else:
        digest = units_commitment_v2(bytes.fromhex(inp["secret_hex"]), inp["report"], inp["units"])
    _check(digest == expected["commitment"], "Commitment mismatch")


def run_language_conformance_families(cases_root=None):
    """Run public cases; results describe language conformance only."""
    from tvl.yaml_safe import safe_load
    if cases_root is None:
        bundled = Path(__file__).parent / "conformance/cases/runtime"
        cases_root = bundled if bundled.is_dir() else Path(__file__).resolve().parents[2] / "conformance/cases/runtime"
    cases_root = Path(cases_root)
    outcomes = {}
    for path in sorted(cases_root.rglob("*.yml")):
        relative = path.relative_to(cases_root).as_posix()
        try:
            run_runtime_conformance_case(safe_load(path.read_text()), case_path=path)
            outcomes[relative] = True
        except Exception:
            outcomes[relative] = False
    families = {}
    for family, globs in LANGUAGE_FAMILY_GLOBS.items():
        selected = [value for relative, value in outcomes.items() if any(Path(relative).match(g) for g in globs)]
        families[family] = {"total": len(selected), "passed": sum(selected), "failed": len(selected) - sum(selected)}
    unmapped = [relative for relative in outcomes if not any(Path(relative).match(g) for globs in LANGUAGE_FAMILY_GLOBS.values() for g in globs)]
    return {"ok": all(value["total"] and not value["failed"] for value in families.values()) and not unmapped,
            "families": families, "unmapped": unmapped}
