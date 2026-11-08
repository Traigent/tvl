"""Every shipped console script reports the installed tvl-spec version (issue #258)."""

import importlib
import importlib.metadata
import re
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
SCRIPTS = PYPROJECT["project"]["scripts"]


def test_console_scripts_match_contributing_list():
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    line = next(text for text in contributing.splitlines() if "command-line tools are installed" in text)
    listed = set(re.findall(r"`(tvl-[a-z-]+)`", line))
    assert listed == set(SCRIPTS)
    assert len(SCRIPTS) == 11


def test_installed_metadata_matches_pyproject_version():
    assert importlib.metadata.version("tvl-spec") == PYPROJECT["project"]["version"]


@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_console_script_prints_version_and_exits_zero(script, monkeypatch, capsys):
    module, function = SCRIPTS[script].split(":")
    monkeypatch.setattr(sys, "argv", [script, "--version"])
    with pytest.raises(SystemExit) as exc:
        getattr(importlib.import_module(module), function)()
    assert exc.value.code == 0
    output = capsys.readouterr()
    assert output.out.strip() == f"{script} {importlib.metadata.version('tvl-spec')}"
    assert output.err == ""
