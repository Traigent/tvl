"""Public parse and warning-severity exit contracts."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FORMATS = [[], ["--json"], ["--format", "json"]]


@pytest.mark.parametrize("tool", ["tvl_validate", "tvl_lint"])
@pytest.mark.parametrize("flags", FORMATS)
@pytest.mark.parametrize("is_pack", [False, True], ids=["module", "pack"])
@pytest.mark.parametrize("severity, expected", [("warning", 0), ("error", 2), (None, 2)])
def test_lint_severity_controls_success(tool, flags, is_pack, severity, expected, monkeypatch, capsys):
    cli = importlib.import_module(f"tvl_tools.{tool}.cli")
    doc = {"pack": {"module": "examples.floor"}} if is_pack else {"tvl": {"module": "examples.agent"}}
    issue = {"code": "contract_diagnostic", "message": "A diagnostic", "path": []}
    if severity is not None:
        issue["severity"] = severity
    monkeypatch.setattr(cli, "load_yaml_safely", lambda _: doc)
    if tool == "tvl_validate":
        monkeypatch.setattr(cli, "_schema_issues", lambda *_: [])
    monkeypatch.setattr(cli, "lint_pack", lambda *_: [issue])
    monkeypatch.setattr(cli, "lint_module", lambda *_, **__: [issue])
    monkeypatch.setattr(sys, "argv", [tool, "document.yml", *flags])
    try:
        cli.main()
        status = 0
    except SystemExit as exc:
        status = exc.code
    captured = capsys.readouterr()
    assert status == expected
    assert "contract_diagnostic" in captured.out
    if flags:
        report = json.loads(captured.out)
        assert report["ok"] is (expected == 0)
        assert report["issues"] == [issue]
        if is_pack:
            assert report["document_kind"] == "pack"


@pytest.mark.parametrize("tool", ["tvl_validate", "tvl_lint"])
@pytest.mark.parametrize("flags", FORMATS)
def test_real_warning_only_module_succeeds(tool, flags):
    proc = subprocess.run(
        [sys.executable, "-m", f"tvl_tools.{tool}.cli", str(ROOT / "spec/examples/book/ch03/every-type.tvl.yml"), *flags],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "unverifiable_callable_type" in proc.stdout
    assert "unverifiable_registry_domain" in proc.stdout
    if flags:
        report = json.loads(proc.stdout)
        assert report["ok"] is True
        assert all(issue["severity"] == "warning" for issue in report["issues"])


@pytest.mark.parametrize("content", ["", "- a\n- b\n", "text\n", "12\n", "true\n", "null\n"])
@pytest.mark.parametrize("flags", FORMATS)
def test_parse_rejects_nonmapping_documents(content, flags, tmp_path):
    source = tmp_path / "document.yml"
    source.write_text(content)
    proc = subprocess.run(
        [sys.executable, "-m", "tvl_tools.tvl_parse.cli", str(source), *flags],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )
    assert proc.returncode == 2
    assert "TVL module must be a mapping at the top level" in proc.stdout + proc.stderr
    assert "Traceback" not in proc.stdout + proc.stderr
    if flags:
        assert json.loads(proc.stdout)["ok"] is False


@pytest.mark.parametrize("document", [{}, {"unknown_field": True}])
def test_parse_leaves_schema_validation_to_validator(document, tmp_path):
    import yaml

    source = tmp_path / "document.yml"
    source.write_text(yaml.safe_dump(document))
    proc = subprocess.run(
        [sys.executable, "-m", "tvl_tools.tvl_parse.cli", str(source), "--json"],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["ast"] == document


@pytest.mark.parametrize("domain", [["wrong"], {"set": ["wrong"]}])
def test_enum_schema_errors_name_the_variable_and_value(domain, tmp_path):
    import yaml

    doc = yaml.safe_load((ROOT / "spec/examples/rag-support-bot.tvl.yml").read_text())
    doc["tvars"] = [{"name": "choice", "type": "enum[int]", "domain": domain}]
    source = tmp_path / "document.yml"
    source.write_text(yaml.safe_dump(doc))
    proc = subprocess.run(
        [sys.executable, "-m", "tvl_tools.tvl_validate.cli", str(source), "--json"],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )
    assert proc.returncode == 2
    report = json.loads(proc.stdout)
    assert report["ok"] is False and report["schema_ok"] is False
    issue = next(i for i in report["issues"] if i["code"] == "invalid_enum_domain")
    assert "choice" in issue["message"] and "wrong" in issue["message"]


def test_compose_validate_matches_the_warning_only_contract(tmp_path):
    """`tvl-compose --validate` runs the same lints, so it gives the same verdict.

    Issue #158 is about warning-only results failing the build. tvl-compose
    --validate reuses lint_module/lint_pack, so leaving it on the old
    `any issue fails` rule would make the same module pass tvl-validate and
    fail tvl-compose.
    """
    # Both files go in tmp_path: writing a fixture into the checkout is not
    # xdist-safe and leaves an untracked file behind if the run is interrupted.
    base = ROOT / "spec/examples/book/ch03/every-type.tvl.yml"
    (tmp_path / "every-type.tvl.yml").write_text(base.read_text(encoding="utf-8"), encoding="utf-8")
    overlay = tmp_path / "warning-only.overlay.yml"
    overlay.write_text(
        "_tvl_overlay:\n  extends: every-type.tvl.yml\n\noverrides: {}\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, "-m", "tvl_tools.tvl_compose.cli", str(overlay), "--validate", "--json"],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["ok"] is True
    assert report["validation"]["ok"] is True
    codes = {issue["code"] for issue in report["validation"]["issues"]}
    assert {"unverifiable_callable_type", "unverifiable_registry_domain"} <= codes
    assert all(issue["severity"] == "warning" for issue in report["validation"]["issues"])

    # Text is the default format, and the warnings used to reach the user only
    # because the result was a failure. Succeeding must not silence them.
    text = subprocess.run(
        [sys.executable, "-m", "tvl_tools.tvl_compose.cli", str(overlay), "--validate"],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )
    assert text.returncode == 0, text.stdout + text.stderr
    rendered = text.stdout + text.stderr
    for code in ("unverifiable_callable_type", "unverifiable_registry_domain"):
        assert code in rendered, f"{code} is missing from the default text output"
