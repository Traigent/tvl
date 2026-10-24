"""Author-facing diagnostics are actionable, closed, and legacy-compatible."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import importlib
import io
import json
from pathlib import Path
import sys

import pytest
import yaml

from tvl.canonical import RuntimeClosedError
from tvl.lints import lint_module
from tvl.runtime_compiler import compile_runtime_document
from tvl.runtime_compose import compose_runtime_documents
from tvl.runtime_projection import token_map_template
from tvl.schema import load_schema, validator
from tvl.yaml_safe import safe_load
from tvl_tools.tvl_compile_runtime.cli import run_cli


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "spec/examples/runtime-1.3"


def example(number: int) -> dict:
    return safe_load(next(EXAMPLES.glob(f"{number:02}-*.yml")).read_text())


def invoke(name: str, args: list[str], monkeypatch: pytest.MonkeyPatch) -> tuple[int, str, str]:
    monkeypatch.setattr(sys, "argv", [name, *args])
    stdout, stderr = io.StringIO(), io.StringIO()
    code = 0
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            importlib.import_module(f"tvl_tools.{name.replace('-', '_')}.cli").main()
        except SystemExit as exc:
            code = exc.code
    return code, stdout.getvalue(), stderr.getvalue()


def write_doc(tmp_path: Path, doc: dict, name: str = "module.yml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return path


@pytest.mark.parametrize("number,field", [(2, "episode"), (2, "decision.confidence"), (7, "limits"), (14, "window")])
def test_monitor_role_errors_name_missing_or_forbidden_field(number: int, field: str) -> None:
    doc = example(number)
    mon = doc["monitors"][0]
    if number == 14:
        mon["window"] = {"tumbling_hours": 6, "grace_minutes": 30}
    elif "." in field:
        parent, leaf = field.split(".")
        del mon[parent][leaf]
    else:
        del mon[field]
    expected = ["monitors", 0, *field.split(".")]
    issues = lint_module(doc)
    issue = next(i for i in issues if i["code"] == "runtime_invalid_profile" and i["path"] == expected)
    assert ".".join(map(str, expected)) in issue["message"]
    assert mon["name"] not in issue["message"]


@pytest.mark.parametrize("action,params,field,hint", [
    ("rollback", {}, "target", "64 lowercase hex"),
    ("rollback", {"target": "CANARY_BAD_TARGET"}, "target", "last_certified"),
    ("degrade", {"fallback": "a" * 63}, "fallback", "64 lowercase hex"),
    ("degrade", {"fallback": "A" * 64}, "fallback", "64 lowercase hex"),
    ("suspend", {}, "fallback", "route_to_human"),
    ("throttle", {}, "rate_floor", "0 < rate_floor < 1"),
    ("throttle", {"rate_floor": 1}, "rate_floor", "0 < rate_floor < 1"),
    ("rollback", {"target": "last_certified", "severity": "CANARY_SEVERITY"}, "severity", "only on notify"),
])
def test_ladder_parameter_errors_name_path_and_expected_form(action, params, field, hint) -> None:
    doc = example(1)
    doc["responses"] = [{"name": "CANARY_RESPONSE", "rules": [{
        "id": "CANARY_RULE", "do": action, "approval": "human",
        "trigger": {"monitor": doc["monitors"][0]["name"], "event": "episode_continued"}, **params,
    }]}]
    issue = next(i for i in lint_module(doc) if i["path"] == ["responses", 0, "rules", 0, field])
    assert f"responses.0.rules.0.{field}" in issue["message"]
    assert hint in issue["message"]
    assert "CANARY" not in json.dumps(issue)


@pytest.mark.parametrize("approval", [None, "none", "standing"])
def test_suspend_requires_explicit_human_approval(approval) -> None:
    doc = example(1)
    rule = {"id": "stop", "do": "suspend", "fallback": "static_unavailable",
            "trigger": {"monitor": doc["monitors"][0]["name"], "event": "episode_continued"}}
    if approval is not None:
        rule["approval"] = approval
    doc["responses"] = [{"name": "controls", "rules": [rule]}]
    assert "response_suspend_without_human" in {i["code"] for i in lint_module(doc)}
    rule["approval"] = "human"
    assert not [i for i in lint_module(doc) if i["severity"] == "error"]


def test_bounded_existence_rejects_correlation_with_whole_unit_hint(tmp_path, monkeypatch) -> None:
    doc = example(5)
    pred = doc["requirements"][0]["violation"]
    assert pred["pattern"] == "bounded_existence"
    pred["correlate_by"] = "CANARY_KEY"
    path = write_doc(tmp_path, doc)
    for cli in ("tvl-lint", "tvl-validate"):
        code, out, _ = invoke(cli, [str(path), "--format", "json"], monkeypatch)
        assert code == 2
        issue = next(i for i in json.loads(out)["issues"] if i["code"] == "runtime_invalid_profile")
        assert issue["path"] == ["requirements", 0, "violation", "correlate_by"]
        assert "not supported by bounded_existence" in issue["message"]
        assert "whole unit" in issue["message"]
        assert "CANARY" not in out


def test_resolved_event_can_notify_but_cannot_rollback(tmp_path, monkeypatch) -> None:
    doc = example(1)
    rule = {"id": "restore", "do": "rollback", "target": "last_certified", "approval": "human",
            "trigger": {"monitor": doc["monitors"][0]["name"], "event": "episode_resolved"}}
    doc["responses"] = [{"name": "controls", "rules": [rule]}]
    path = write_doc(tmp_path, doc)
    for cli in ("tvl-lint", "tvl-validate"):
        code, out, _ = invoke(cli, [str(path), "--format", "json"], monkeypatch)
        assert code == 2
        issue = next(i for i in json.loads(out)["issues"] if i["code"] == "runtime_invalid_ladder")
        assert issue["path"] == ["responses", 0, "rules", 0, "trigger", "event"]
    rule["do"] = "notify"
    del rule["target"], rule["approval"]
    assert not [i for i in lint_module(doc) if i["severity"] == "error"]


@pytest.mark.parametrize("mutation,hint", [("version", 'quote it: "1.3"'), ("rule_on", "use `trigger:` / `when:`"),
                                          ("transition_on", "use `trigger:` / `when:`"), ("states", "quote YAML yes/no")])
def test_yaml_pitfalls_agree_between_validate_and_lint(tmp_path, monkeypatch, mutation, hint) -> None:
    doc = example(7)
    if mutation == "version":
        doc["tvl_version"] = 1.3
    elif mutation == "rule_on":
        rule = doc["responses"][0]["rules"][0]
        rule[True] = rule.pop("trigger")
    elif mutation == "transition_on":
        tr = doc["requirements"][0]["violation"]["transitions"][0]
        tr[True] = tr.pop("when")
    else:
        pred = doc["requirements"][0]["violation"]
        pred.update(states=[True, False], start=True, accepting=[False], rejecting=[], transitions=[])
    path = write_doc(tmp_path, doc)
    outputs = []
    for cli in ("tvl-lint", "tvl-validate"):
        code, out, _ = invoke(cli, [str(path), "--format", "json"], monkeypatch)
        assert code == 2
        outputs.append(json.loads(out)["issues"])
    assert outputs[0] == outputs[1]
    assert hint in outputs[0][0]["message"]


def test_alias_error_names_namespace_and_source_field_without_value(tmp_path, capsys) -> None:
    doc = example(1)
    doc["monitors"][0]["evidence"].pop("deployment_environment", None)
    tokens = token_map_template([doc])
    for idx, token in enumerate(tokens["tokens"]):
        token["hosted"] = f"t{idx}"
    tokens["tokens"] = [t for t in tokens["tokens"] if t["namespace"] != "environment"]
    path = write_doc(tmp_path, doc)
    tpath = tmp_path / "tokens.json"
    tpath.write_text(json.dumps(tokens))
    code, result = run_cli([str(path), "--token-map", str(tpath), "--out-dir", str(tmp_path / "out"), "--format", "json"])
    assert code == 2
    issue = result["issues"][0]
    assert issue["code"] == "runtime_unresolved_alias"
    assert issue["path"] == ["monitors", 0, "evidence", "deployment_environment"]
    assert "environment" in issue["message"]
    assert "production" not in issue["message"]
    assert doc["tvl"]["module"] not in json.dumps(issue)
    assert not (tmp_path / "out").exists()


def test_missing_checker_label_keeps_its_path_and_never_echoes_labels() -> None:
    doc = example(10)
    req = next(r for r in doc["requirements"] if r.get("violation", {}).get("checker", "").startswith("customer:"))
    req["violation"]["label_in"] = ["CANARY_LABEL"]
    registry = {"format": "tvl-checker-registry/1", "checkers": [
        {"checker": req["violation"]["checker"], "labels": ["other"]}]}
    with pytest.raises(RuntimeClosedError) as caught:
        compile_runtime_document(doc, token_map_doc=None, checker_registry_doc=registry)
    assert caught.value.code == "runtime_unknown_kind"
    assert caught.value.path == ["requirements", doc["requirements"].index(req), "violation", "label_in", 0]
    assert "label_in.0" in caught.value.message
    assert "CANARY" not in caught.value.message


@pytest.mark.parametrize("change,code,expected", [("rate", "requirement_weaker_than_floor", ["requirements", 0, "max_rate"]),
    ("window", "evaluation_schedule_mismatch", ["monitors", 0, "window", "tumbling_hours"])])
def test_compose_failure_prints_code_and_field_path(tmp_path, monkeypatch, change, code, expected) -> None:
    doc, pack = example(1), example(13)
    if change == "rate":
        doc["requirements"][0]["max_rate"] = 0.2
    else:
        doc["monitors"][0]["window"] = {"tumbling_hours": 3, "grace_minutes": 30}
    path = write_doc(tmp_path, doc)
    ppath = write_doc(tmp_path, pack, "pack.yml")
    status, out, err = invoke("tvl-compose", [str(path), "--pack", str(ppath)], monkeypatch)
    assert status == 2
    assert code in err and ".".join(map(str, expected)) in err
    status, out, _ = invoke("tvl-compose", [str(path), "--pack", str(ppath), "--format", "json"], monkeypatch)
    assert status == 2 and json.loads(out)["issues"][0]["path"] == expected


def test_overlay_failure_names_parameter() -> None:
    base = example(1)
    overlay = copy.deepcopy(base)
    overlay["requirements"][0]["max_rate"] = 0.2
    with pytest.raises(RuntimeClosedError) as caught:
        compose_runtime_documents(base, overlay)
    assert caught.value.code == "runtime_overlay_weakens"
    assert caught.value.path == ["requirements", 0, "max_rate"]


def test_overlay_rule_path_uses_overlay_order() -> None:
    base = example(7)
    overlay = copy.deepcopy(base)
    overlay["responses"][0]["rules"].reverse()
    overlay["responses"][0]["rules"][0]["severity"] = "info"
    with pytest.raises(RuntimeClosedError) as caught:
        compose_runtime_documents(base, overlay)
    assert caught.value.path == ["responses", 0, "rules", 0, "severity"]


def test_actual_yaml_yes_no_and_on_spellings(tmp_path, monkeypatch) -> None:
    doc = example(7)
    text = yaml.safe_dump(doc, sort_keys=False)
    states_doc = copy.deepcopy(doc)
    states_doc["requirements"][0]["violation"]["states"] = ["yes", "no"]
    states_text = yaml.safe_dump(states_doc, sort_keys=False).replace("'yes'", "yes").replace("'no'", "no")
    for before, after, hint in [(None, states_text, "quote YAML yes/no"),
                                ("trigger:", "on:", "use `trigger:` / `when:`"),
                                ("when:", "on:", "use `trigger:` / `when:`")]:
        modified = after if before is None else text.replace(before, after, 1)
        path = tmp_path / "literal.yml"
        path.write_text(modified)
        for cli in ("tvl-lint", "tvl-validate"):
            code, out, _ = invoke(cli, [str(path), "--format", "json"], monkeypatch)
            assert code == 2 and hint in json.loads(out)["issues"][0]["message"]


def test_compiler_does_not_echo_legacy_lint_values() -> None:
    doc = example(1)
    doc["tvars"] = [{"name": "CANARY_NAME", "type": "int", "domain": [1, 2]}] * 2
    with pytest.raises(RuntimeClosedError) as caught:
        compile_runtime_document(doc, token_map_doc=None)
    assert "CANARY" not in caught.value.message


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.yml")), ids=lambda path: path.name)
def test_every_example_template_can_be_filled_and_compiled(path, tmp_path, capsys) -> None:
    code, template = run_cli([str(path), "--emit-token-map-template"])
    assert code == 0
    assert json.loads(capsys.readouterr().out) == template
    assert all(t["hosted"] == "" for t in template["tokens"])
    doc = safe_load(path.read_text())
    checkers: dict[str, set[str]] = {}
    for req in doc.get("requirements", []):
        for key in ("violation", "among"):
            pred = req.get(key, {})
            if pred.get("checker", "").startswith("customer:"):
                checkers.setdefault(pred["checker"], set()).update(pred["label_in"])
    registry = {"format": "tvl-checker-registry/1", "checkers": [
        {"checker": key, "labels": sorted(labels)} for key, labels in checkers.items()]}
    for idx, token in enumerate(template["tokens"]):
        token["hosted"] = f"customer:{idx:064x}" if token["namespace"] == "checker" else f"t{idx}"
    contract, _, _ = compile_runtime_document(doc, token_map_doc=template, checker_registry_doc=registry)
    assert contract["format"] == "tvl-runtime-contract/1"


def test_template_includes_pack_and_default_environment(tmp_path, capsys) -> None:
    path = next(EXAMPLES.glob("01-*.yml"))
    pack = next(EXAMPLES.glob("13-*.yml"))
    code, template = run_cli([str(path), "--pack", str(pack), "--emit-token-map-template"])
    assert code == 0
    assert {t["local"] for t in template["tokens"] if t["namespace"] == "module"} == {example(1)["tvl"]["module"], example(13)["pack"]["module"]}
    assert {"namespace": "environment", "local": "production", "hosted": ""} in template["tokens"]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("definition,field", [("RequirementDecl", "kind"), ("PredicateDecl", "pattern"), ("SelectorDecl", "event"),
    ("TriggerDecl", "event"), ("RuleDecl", "do"), ("MonitorDecl", "phase"), ("EvidenceDecl", "source"), ("DecisionDecl", "method")])
def test_editor_hints_preserve_normative_lint_codes(definition, field, tmp_path, monkeypatch) -> None:
    declaration = load_schema()["$defs"][definition]
    if definition == "TriggerDecl":
        declaration = declaration["oneOf"][0]  # monitor-trigger editor hints
    hints = declaration["properties"][field]
    assert hints["examples"] == hints["x-enum"] and "enum" not in hints
    doc = example(7)
    targets = {"RequirementDecl": doc["requirements"][0], "PredicateDecl": doc["requirements"][0]["violation"],
               "SelectorDecl": doc["requirements"][0]["violation"]["alphabet"][0],
               "TriggerDecl": doc["responses"][0]["rules"][0]["trigger"], "RuleDecl": doc["responses"][0]["rules"][0],
               "MonitorDecl": doc["monitors"][0], "EvidenceDecl": doc["monitors"][0]["evidence"], "DecisionDecl": doc["monitors"][0]["decision"]}
    targets[definition][field] = "CANARY_UNKNOWN"
    assert not list(validator().iter_errors(doc))
    code, out, _ = invoke("tvl-validate", [str(write_doc(tmp_path, doc)), "--format", "json"], monkeypatch)
    issues = json.loads(out)["issues"]
    assert code == 2 and all(i["code"] != "schema_error" for i in issues)
    assert "CANARY" not in json.dumps(issues)


@pytest.mark.parametrize("version,expected", [("1.2", 0), ("1.3", 2)])
def test_measurement_not_ready_exit_changes_only_for_13_constructs(tmp_path, monkeypatch, version, expected) -> None:
    doc = example(1)
    if version == "1.2":
        for key in ("requirements", "monitors", "responses"):
            doc.pop(key, None)
    doc["tvl_version"] = version
    module = write_doc(tmp_path, doc)
    config = write_doc(tmp_path, {"module_id": doc["tvl"]["module"], "assignments": {"model": "m_small"}}, "config.yml")
    measurement = write_doc(tmp_path, {"objectives": {"quality": {"observed": 0.8}}}, "measurement.yml")
    code, out, _ = invoke("tvl-measure-validate", [str(module), str(config), str(measurement)], monkeypatch)
    assert "Promotion-ready: no" in out
    assert code == expected


def test_ci_gate_reason_comes_from_summary(tmp_path, monkeypatch) -> None:
    doc = example(1)
    module = write_doc(tmp_path, doc)
    incumbent = write_doc(tmp_path, {"objective_values": {"quality": {"samples": [0.49, 0.51] * 15}}}, "inc.yml")
    candidate = write_doc(tmp_path, {"objective_values": {"quality": {"samples": [0.89, 0.91] * 15}}}, "cand.yml")
    code, out, _ = invoke("tvl-ci-gate", [str(module), str(incumbent), str(candidate)], monkeypatch)
    assert code == 0
    assert "Reason: " in out and not any(line.rstrip() == "Reason:" for line in out.splitlines())
    assert "quality" not in next(line for line in out.splitlines() if line.startswith("Reason:"))


def test_schema_diagnostic_never_echoes_rejected_values_or_unknown_keys(tmp_path, monkeypatch) -> None:
    doc = example(1)
    doc["monitors"][0]["decision"]["CANARY_KEY"] = "CANARY_VALUE"
    code, out, _ = invoke("tvl-validate", [str(write_doc(tmp_path, doc)), "--format", "json"], monkeypatch)
    assert code == 2
    assert "CANARY" not in out


def test_scipy_failure_diagnostic_is_closed_and_never_echoes_monitor_name(monkeypatch) -> None:
    """RFC 0003 §5.10: a reported code carries a fixed message, without echoing any input."""
    import types

    class _BrokenBeta:
        @staticmethod
        def ppf(*_args, **_kwargs):
            raise RuntimeError("scipy unavailable")

    fake_stats = types.ModuleType("scipy.stats")
    fake_stats.beta = _BrokenBeta  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scipy.stats", fake_stats)
    doc = example(1)
    for monitor in doc["monitors"]:
        if monitor["name"] == "latency_2s_prod":
            monitor["name"] = "CANARY_MONITOR"
    for response in doc.get("responses") or []:
        for rule in response.get("rules") or []:
            trigger = rule.get("trigger") or {}
            if trigger.get("monitor") == "latency_2s_prod":
                trigger["monitor"] = "CANARY_MONITOR"
    issues = [i for i in lint_module(doc) if i["code"] == "runtime_invalid_profile"]
    assert issues, "the scipy-failure branch must be reached"
    assert all("CANARY" not in i["message"] for i in issues)
    with pytest.raises(RuntimeClosedError) as caught:
        compile_runtime_document(doc, token_map_doc=None)
    assert "CANARY" not in caught.value.message
