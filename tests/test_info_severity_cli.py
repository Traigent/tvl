"""`info` diagnostics (outside_proved_subset) print but never decide ok/exit."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "spec" / "examples"
CVARS = EX / "validation-phase6-cvars" / "cvar-policies-happy.tvl.yml"
CALLABLE = EX / "book" / "ch03" / "every-type.tvl.yml"


def _run(tool: str, path: Path, *flags: str) -> tuple[int, str]:
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "python"), str(ROOT)]))
    p = subprocess.run(
        [sys.executable, "-m", f"tvl_tools.{tool}.cli", str(path), *flags],
        capture_output=True, text=True, env=env, timeout=120, cwd=ROOT,
    )
    return p.returncode, p.stdout


def test_cvars_module_exits_zero_and_prints_info_line() -> None:
    for tool in ("tvl_lint", "tvl_validate"):
        code, out = _run(tool, CVARS)
        assert code == 0, (tool, out)
        assert "[outside_proved_subset]" in out, (tool, out)
        code, out = _run(tool, CVARS, "--json")
        report = json.loads(out)
        assert code == 0 and report["ok"] is True
        infos = [i for i in report["issues"] if i["code"] == "outside_proved_subset"]
        assert infos and all(i["severity"] == "info" for i in infos)


def test_existing_warning_still_exits_nonzero() -> None:
    for tool in ("tvl_lint", "tvl_validate"):
        code, out = _run(tool, CALLABLE, "--json")
        assert code == 2, (tool, out)
        report = json.loads(out)
        assert report["ok"] is False
        assert any(i["code"] == "unverifiable_callable_type" for i in report["issues"])
