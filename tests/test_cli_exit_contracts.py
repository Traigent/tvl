"""Public parse and enum-diagnostic contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FORMATS = [[], ["--json"], ["--format", "json"]]


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
