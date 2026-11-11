"""Issue #247: a relax_bound repair candidate edits the bound, never digits in the symbol name."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tvl_tools.tvl_check_structural import cli as structural

MODULE = """\
tvl: {module: example.audit}
environment: {snapshot_id: "2026-10-01T00:00:00Z"}
evaluation_set: {dataset: example.eval}
tvars:
  - {name: k1, type: int, domain: {set: [0, 3, 5, 8]}}
  - {name: k2, type: int, domain: {set: [0, 3, 5, 8]}}
constraints:
  structural:
    - expr: "k1 <= 1"
    - expr: "k1 >= 5"
objectives: [{name: quality, direction: maximize}]
promotion_policy: {dominance: epsilon_pareto, alpha: 0.05, min_effect: {quality: 0.01}}
"""


@pytest.mark.parametrize(
    ("expression", "after"),
    [
        ("k1 <= 1", "k1 <= 2"),
        ("k1 >= 5", "k1 >= 4"),
        ("p10 < 10", "p10 < 11"),
        ("layer2.n >= 2", "layer2.n >= 1"),
    ],
)
def test_relax_bound_edits_the_bound_not_the_symbol(expression: str, after: str) -> None:
    [candidate] = structural._build_repair_candidates([{"expression": expression, "path": []}], Path("m.yml"))
    assert candidate["intent"] == "relax_bound"
    assert candidate["edits"][0]["after"] == after


def _run(monkeypatch, capsys, argv: list[str]) -> tuple[int, list[dict]]:
    monkeypatch.setattr(sys, "argv", ["tvl-check-structural", *argv])
    with pytest.raises(SystemExit) as exc:
        structural.main()
    decoder = json.JSONDecoder()
    out = capsys.readouterr().out
    docs, idx = [], 0
    while idx < len(out):
        if out[idx].isspace():
            idx += 1
            continue
        doc, idx = decoder.raw_decode(out, idx)
        docs.append(doc)
    return exc.value.code, docs


def test_validated_candidate_does_not_rewrite_another_variable(tmp_path, monkeypatch, capsys) -> None:
    module = tmp_path / "m.tvl.yml"
    module.write_text(MODULE, encoding="utf-8")
    code, docs = _run(monkeypatch, capsys, [str(module), "--json"])
    assert code == 2
    candidates = [d["candidate"] for d in docs if d.get("kind") == "RepairCandidateProduced"]
    upper = next(c for c in candidates if c["edits"][0]["before"] == "k1 <= 1")
    assert upper["edits"][0]["after"] == "k1 <= 2"

    cand_file = tmp_path / "cand.json"
    cand_file.write_text(json.dumps(upper), encoding="utf-8")
    code, docs = _run(monkeypatch, capsys, [str(module), "--json", "--candidate-file", str(cand_file)])
    # k1 <= 2 and k1 >= 5 is still a conflict: the relaxed candidate must not validate as sat.
    validated = next(d for d in docs if d.get("kind") == "RepairCandidateValidated")
    assert validated["status"] == "unsat"
    assert code == 2
