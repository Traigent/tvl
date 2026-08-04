"""Regression: tvl-lint fail-open on a non-mapping top-level document.

`cli.py` coerced the parsed document with `doc if isinstance(doc, dict) else {}`,
so a top-level YAML sequence, a bare scalar, or an empty file linted against an
empty mapping — the CLI printed "Lint checks passed." with ok=true and exited 0.
The sibling `tvl-validate` rejects the identical input (`raise TypeError` -> exit
2), so a CI step gating on tvl-lint alone failed open on a non-TVL file.

tvl-lint now emits an `invalid_document` issue and fails closed, consistent with
tvl-validate.

See Traigent/tvl#34.
"""

from __future__ import annotations

import json

import pytest

from tvl_tools.tvl_lint import cli as lint_cli


def _run_lint(tmp_path, monkeypatch, capsys, content: str):
    target = tmp_path / "broken.tvl.yml"
    target.write_text(content)
    monkeypatch.setattr("sys.argv", ["tvl-lint", str(target), "--format", "json"])
    with pytest.raises(SystemExit) as exc:
        lint_cli.main()
    out = json.loads(capsys.readouterr().out)
    return exc.value.code, out


@pytest.mark.parametrize(
    "content",
    ["- foo\n- bar\n", "just a string\n", ""],
    ids=["sequence", "scalar", "empty"],
)
def test_non_mapping_document_fails_closed(tmp_path, monkeypatch, capsys, content):
    code, out = _run_lint(tmp_path, monkeypatch, capsys, content)
    assert code == 2
    assert out["ok"] is False
    assert any(issue["code"] == "invalid_document" for issue in out["issues"])


def test_mapping_document_still_lints_normally(tmp_path, monkeypatch, capsys):
    """A real mapping is still linted (no spurious invalid_document issue)."""
    content = "tvars:\n  x:\n    type: bool\n"
    code, out = _run_lint(tmp_path, monkeypatch, capsys, content)
    # The stub module has other lint issues, but never the top-level one.
    assert not any(issue["code"] == "invalid_document" for issue in out["issues"])
