"""Exercise the in-process CLI harness, including the argv-taking microsim bridge."""

from __future__ import annotations

from pathlib import Path

import pytest

from tvl_tools.runtime_cli_harness import invoke_entrypoint

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = REPO_ROOT / "spec" / "examples" / "agent-router.tvl.yml"


def _invoke(entrypoint: str, tmp_path: Path) -> tuple[int, dict]:
    return invoke_entrypoint(
        entrypoint=entrypoint,
        doc_path=MODULE,
        extra_args=[],
        tmp_dir=tmp_path,
    )


def test_microsim_bridge_receives_its_argv(tmp_path: Path) -> None:
    code, parsed = _invoke("tvl-microsim-bridge", tmp_path)
    assert code == 0
    assert isinstance(parsed, dict) and parsed


def test_no_argument_entrypoint_returns_parsed_json(tmp_path: Path) -> None:
    code, parsed = _invoke("tvl-validate", tmp_path)
    assert code in (0, 1)
    assert isinstance(parsed, dict) and parsed
    assert "raw_stdout" not in parsed


def test_unknown_entrypoint_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown entrypoint"):
        _invoke("tvl-nope", tmp_path)
