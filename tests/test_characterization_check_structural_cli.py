"""Characterization tests for the ``tvl-check-structural`` CLI ``main``.

They pin stdout, stderr, exit codes, the emitted JSON documents (events and the
final PhaseResult, in order) and temp-file cleanup for every path through
``main``. Volatile fields (``timestamp``, ``durationMs``, ``witnessId``) are
checked for shape and then normalised.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

pytest.importorskip("ortools.sat.python.cp_model")

from tvl.structural_sat import StructuralResult  # noqa: E402
from tvl_tools.tvl_check_structural import cli  # noqa: E402

_MODULE = """\
tvl:
  module: demo.check_structural

environment:
  snapshot_id: "2025-01-20T00:00:00Z"

evaluation_set:
  dataset: s3://datasets/demo/dev.jsonl
  seed: 2025

tvars:
  - name: retriever.k
    type: int
    domain:
      set: [3, 5, 8]
  - name: temperature
    type: float
    domain:
      range: [0.0, 0.6]
      resolution: 0.1

constraints:
  structural:
{structural}

objectives:
  - name: answer_accuracy
    metric_ref: metrics.answer_accuracy.v1
    direction: maximize

promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  adjust: holm
  min_effect:
    answer_accuracy: 0.01

exploration:
  strategy:
    type: grid
  budgets:
    max_trials: 24
    max_wallclock_s: 900
"""

SAT = '    - expr: "retriever.k = 5"\n    - expr: "temperature = 0.2"'
UNSAT = '    - expr: "temperature <= 0.2"\n    - expr: "temperature >= 0.4"'
BAD = '    - when: "retriever.k <"\n      then: "temperature <= 0.3"'


def _write(tmp_path: Path, structural: str, name: str = "m.tvl.yml") -> Path:
    path = tmp_path / name
    path.write_text(_MODULE.format(structural=structural), encoding="utf-8")
    return path


def _run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *argv: str) -> Tuple[Any, str, str]:
    monkeypatch.setattr(sys, "argv", ["tvl-check-structural", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    out, err = capsys.readouterr()
    return exc.value.code, out, err


def _docs(out: str) -> List[Dict[str, Any]]:
    """Split stdout into its JSON documents, normalising volatile fields."""
    decoder = json.JSONDecoder()
    docs: List[Dict[str, Any]] = []
    idx = 0
    while idx < len(out):
        if out[idx].isspace():
            idx += 1
            continue
        doc, idx = decoder.raw_decode(out, idx)
        if "timestamp" in doc:
            datetime.fromisoformat(doc["timestamp"])
            doc["timestamp"] = "<ts>"
        if "durationMs" in doc:
            assert isinstance(doc["durationMs"], int) and doc["durationMs"] >= 0
            doc["durationMs"] = "<ms>"
        if doc.get("witnessId") is not None:
            assert doc["witnessId"].startswith("w-") and len(doc["witnessId"]) == 8
            doc["witnessId"] = "<w>"
        docs.append(doc)
    return docs


class _TempSpy:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.paths: List[Path] = []
        real = cli._write_temp_file

        def spy(content: str, suffix: str = "") -> Path:
            path = real(content, suffix=suffix)
            self.paths.append(path)
            return path

        monkeypatch.setattr(cli, "_write_temp_file", spy)


def _candidate(tmp_path: Path, payload: Dict[str, Any]) -> Path:
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


_UNSAT_CORE = [
    {"path": ["constraints", "structural", 0], "expression": "temperature <= 0.2", "clauses": ["temperature <= 0.2"]},
    {"path": ["constraints", "structural", 1], "expression": "temperature >= 0.4", "clauses": ["temperature >= 0.4"]},
]


# --- text mode -------------------------------------------------------------- #

def test_text_sat_prints_sorted_assignment(monkeypatch, capsys, tmp_path) -> None:
    code, out, err = _run(monkeypatch, capsys, str(_write(tmp_path, SAT)))
    assert code == 0
    assert out == "Structural constraints satisfiable.\n  retriever.k: 5\n  temperature: 0.2\n"
    assert err == ""


def test_text_unsat_prints_core(monkeypatch, capsys, tmp_path) -> None:
    code, out, err = _run(monkeypatch, capsys, str(_write(tmp_path, UNSAT)))
    assert code == 2
    assert out == (
        "Structural constraints UNSAT.\n"
        "- constraints.structural.0\n"
        "    expression: temperature <= 0.2\n"
        "      clause: temperature <= 0.2\n"
        "- constraints.structural.1\n"
        "    expression: temperature >= 0.4\n"
        "      clause: temperature >= 0.4\n"
    )
    assert err == ""


def test_text_sat_with_empty_assignment_and_root_core(monkeypatch, capsys, tmp_path) -> None:
    module = str(_write(tmp_path, SAT))
    monkeypatch.setattr(cli, "check_structural", lambda m: StructuralResult(ok=True, assignment={}, unsat_core=None))
    assert _run(monkeypatch, capsys, module) == (0, "Structural constraints satisfiable.\n", "")

    monkeypatch.setattr(cli, "check_structural", lambda m: StructuralResult(ok=True, assignment=None, unsat_core=None))
    assert _run(monkeypatch, capsys, module) == (0, "Structural constraints satisfiable.\n", "")

    core = [{"expression": "e1", "clauses": []}, {"path": ["a", 1], "expression": "e2", "clauses": None}, {}]
    monkeypatch.setattr(cli, "check_structural", lambda m: StructuralResult(ok=False, assignment=None, unsat_core=core))
    assert _run(monkeypatch, capsys, module) == (
        2,
        "Structural constraints UNSAT.\n- <root>\n    expression: e1\n- a.1\n    expression: e2\n- <root>\n    expression: None\n",
        "",
    )

    monkeypatch.setattr(cli, "check_structural", lambda m: StructuralResult(ok=False, assignment=None, unsat_core=None))
    assert _run(monkeypatch, capsys, module) == (2, "Structural constraints UNSAT.\n", "")


def test_text_load_error(monkeypatch, capsys, tmp_path) -> None:
    missing = tmp_path / "missing.yml"
    code, out, err = _run(monkeypatch, capsys, str(missing))
    assert code == 2
    assert out == ""
    assert err.startswith("Error loading module: ") and "missing.yml" in err


def test_text_schema_error(monkeypatch, capsys, tmp_path) -> None:
    path = tmp_path / "bad.yml"
    path.write_text("tvl: {}\n", encoding="utf-8")
    code, out, err = _run(monkeypatch, capsys, str(path))
    assert (code, out) == (2, "")
    assert err.startswith("Error loading module: ")


def test_text_structural_parse_error(monkeypatch, capsys, tmp_path) -> None:
    code, out, err = _run(monkeypatch, capsys, str(_write(tmp_path, BAD)))
    assert (code, out) == (2, "")
    assert err.startswith("Error: invalid structural constraint: ")


# --- json mode -------------------------------------------------------------- #

def test_json_sat(monkeypatch, capsys, tmp_path) -> None:
    code, out, err = _run(monkeypatch, capsys, str(_write(tmp_path, SAT)), "--json")
    assert (code, err) == (0, "")
    assert _docs(out) == [
        {
            "schemaVersion": "1.0",
            "kind": "PhaseResult",
            "phase": "structural",
            "ok": True,
            "status": "passed",
            "assignment": {"retriever.k": 5, "temperature": 0.2},
            "exact_assignment": {"retriever.k": "5", "temperature": "0.2"},
            "unsat_core": None,
            "repair_candidates": [],
            "timestamp": "<ts>",
            "durationMs": "<ms>",
        }
    ]
    assert out.endswith("}\n") and out.startswith('{\n  "schemaVersion"')


def test_json_unsat_emits_candidate_events_then_result(monkeypatch, capsys, tmp_path) -> None:
    module = _write(tmp_path, UNSAT)
    code, out, err = _run(monkeypatch, capsys, str(module), "--json")
    assert (code, err) == (2, "")
    docs = _docs(out)
    candidates = cli._build_repair_candidates(_UNSAT_CORE, module)
    assert len(candidates) == 2
    assert docs == [
        {"schemaVersion": "1.0", "kind": "RepairCandidateProduced", "coreId": candidates[0]["coreId"], "candidate": candidates[0], "timestamp": "<ts>"},
        {"schemaVersion": "1.0", "kind": "RepairCandidateProduced", "coreId": candidates[1]["coreId"], "candidate": candidates[1], "timestamp": "<ts>"},
        {
            "schemaVersion": "1.0",
            "kind": "PhaseResult",
            "phase": "structural",
            "ok": False,
            "status": "unsat",
            "assignment": None,
            "exact_assignment": None,
            "unsat_core": _UNSAT_CORE,
            "repair_candidates": candidates,
            "timestamp": "<ts>",
            "durationMs": "<ms>",
        },
    ]
    # Events are single-line documents.
    assert out.splitlines()[0].startswith('{"schemaVersion": "1.0", "kind": "RepairCandidateProduced"')


def test_json_candidate_core_id_fallback(monkeypatch, capsys, tmp_path) -> None:
    module = str(_write(tmp_path, UNSAT))
    monkeypatch.setattr(cli, "_build_repair_candidates", lambda core, path: [{"id": "x"}, {"id": "y", "coreId": ""}])
    code, out, _ = _run(monkeypatch, capsys, module, "--json")
    docs = _docs(out)
    assert code == 2
    assert [d.get("coreId") for d in docs[:2]] == ["core-1", "core-2"]
    assert docs[2]["repair_candidates"] == [{"id": "x"}, {"id": "y", "coreId": ""}]


def test_json_sat_with_core_does_not_emit_events(monkeypatch, capsys, tmp_path) -> None:
    module = str(_write(tmp_path, SAT))
    monkeypatch.setattr(cli, "check_structural", lambda m: StructuralResult(ok=True, assignment={"a": 1}, unsat_core=_UNSAT_CORE))
    code, out, _ = _run(monkeypatch, capsys, module, "--json")
    docs = _docs(out)
    assert code == 0
    assert len(docs) == 1 and docs[0]["kind"] == "PhaseResult"
    assert len(docs[0]["repair_candidates"]) == 2


def test_json_load_error(monkeypatch, capsys, tmp_path) -> None:
    code, out, err = _run(monkeypatch, capsys, str(tmp_path / "missing.yml"), "--json")
    assert (code, err) == (2, "")
    raw = json.loads(out)
    assert raw["durationMs"] == 0
    docs = _docs(out)
    assert list(docs[0]) == ["schemaVersion", "kind", "phase", "ok", "status", "error", "timestamp", "durationMs"]
    assert docs[0]["status"] == "error" and docs[0]["ok"] is False and docs[0]["phase"] == "structural"
    assert "missing.yml" in docs[0]["error"]


def test_json_structural_parse_error(monkeypatch, capsys, tmp_path) -> None:
    code, out, err = _run(monkeypatch, capsys, str(_write(tmp_path, BAD)), "--json")
    assert (code, err) == (2, "")
    docs = _docs(out)
    assert len(docs) == 1
    doc = docs[0]
    assert doc["error"].startswith("invalid structural constraint: ")
    doc["error"] = "<e>"
    assert doc == {
        "schemaVersion": "1.0",
        "kind": "PhaseResult",
        "phase": "structural",
        "ok": False,
        "status": "error",
        "error": "<e>",
        "assignment": None,
        "unsat_core": None,
        "repair_candidates": [],
        "timestamp": "<ts>",
        "durationMs": "<ms>",
    }


# --- candidate validation --------------------------------------------------- #

def test_json_candidate_that_repairs_validates_sat(monkeypatch, capsys, tmp_path) -> None:
    spy = _TempSpy(monkeypatch)
    module = _write(tmp_path, UNSAT)
    cand = _candidate(tmp_path, {"id": "rc-9", "edits": [{"before": "temperature >= 0.4", "after": "temperature >= 0.1"}]})
    code, out, err = _run(monkeypatch, capsys, str(module), "--json", "--candidate-file", str(cand))
    assert (code, err) == (0, "")
    docs = _docs(out)
    assert docs[0] == {
        "schemaVersion": "1.0",
        "kind": "RepairCandidateValidated",
        "candidateId": "rc-9",
        "status": "sat",
        "durationMs": "<ms>",
        "witnessId": "<w>",
        "timestamp": "<ts>",
    }
    assert docs[1]["status"] == "passed" and docs[1]["repair_candidates"] == []
    assert len(docs) == 2
    assert len(spy.paths) == 1 and spy.paths[0].suffix == ".yml"
    assert not spy.paths[0].exists()
    # The module on disk is untouched.
    assert "temperature >= 0.4" in module.read_text(encoding="utf-8")


def test_json_candidate_noop_validates_unsat_without_temp_file(monkeypatch, capsys, tmp_path) -> None:
    spy = _TempSpy(monkeypatch)
    module = _write(tmp_path, UNSAT)
    cand = _candidate(tmp_path, {"edits": [{"before": "nope", "after": "x"}, "junk", {"before": 1, "after": 2}]})
    code, out, _ = _run(monkeypatch, capsys, str(module), "--json", "--candidate-file", str(cand))
    docs = _docs(out)
    assert code == 2
    assert docs[0]["candidateId"] == "candidate"
    assert docs[0]["status"] == "unsat"
    assert docs[0]["witnessId"] is None
    assert docs[1]["status"] == "unsat" and docs[1]["repair_candidates"] == []
    assert spy.paths == []


def test_json_candidate_sat_with_unsortable_assignment(monkeypatch, capsys, tmp_path) -> None:
    module = str(_write(tmp_path, SAT))
    cand = _candidate(tmp_path, {"id": "c", "edits": "not-a-list"})
    monkeypatch.setattr(cli, "check_structural", lambda m: StructuralResult(ok=True, assignment={1: 0, "a": 0}, unsat_core=None))
    code, out, _ = _run(monkeypatch, capsys, module, "--json", "--candidate-file", str(cand))
    assert code == 0
    assert _docs(out)[0]["witnessId"] is None


def test_json_candidate_sat_with_unhashable_assignment_raises(monkeypatch, capsys, tmp_path) -> None:
    module = str(_write(tmp_path, SAT))
    cand = _candidate(tmp_path, {"id": "c", "edits": []})
    monkeypatch.setattr(cli, "check_structural", lambda m: StructuralResult(ok=True, assignment={"a": [1]}, unsat_core=None))
    monkeypatch.setattr(sys, "argv", ["x", module, "--json", "--candidate-file", str(cand)])
    with pytest.raises(TypeError, match="unhashable"):
        cli.main()


def test_text_candidate_mode_prints_text_only(monkeypatch, capsys, tmp_path) -> None:
    spy = _TempSpy(monkeypatch)
    module = _write(tmp_path, UNSAT)
    cand = _candidate(tmp_path, {"id": "rc", "edits": [{"before": "temperature >= 0.4", "after": "temperature >= 0.0"}]})
    code, out, err = _run(monkeypatch, capsys, str(module), "--candidate-file", str(cand))
    assert code == 0
    assert out.startswith("Structural constraints satisfiable.\n")
    assert err == ""
    assert len(spy.paths) == 1 and not spy.paths[0].exists()


def test_candidate_load_error_cleans_temp_file(monkeypatch, capsys, tmp_path) -> None:
    spy = _TempSpy(monkeypatch)
    module = _write(tmp_path, SAT)
    cand = _candidate(tmp_path, {"edits": [{"before": "tvl:\n", "after": "tvl: [\n"}]})
    code, out, err = _run(monkeypatch, capsys, str(module), "--candidate-file", str(cand))
    assert (code, out) == (2, "")
    assert err.startswith("Error loading module: ")
    assert len(spy.paths) == 1 and not spy.paths[0].exists()


def test_candidate_parse_error_cleans_temp_file(monkeypatch, capsys, tmp_path) -> None:
    spy = _TempSpy(monkeypatch)
    module = _write(tmp_path, SAT)
    cand = _candidate(tmp_path, {"edits": [{"before": '"retriever.k = 5"', "after": '"retriever.k ="'}]})
    code, out, _ = _run(monkeypatch, capsys, str(module), "--json", "--candidate-file", str(cand))
    assert code == 2
    assert _docs(out)[0]["status"] == "error"
    assert len(spy.paths) == 1 and not spy.paths[0].exists()


@pytest.mark.parametrize(
    "structural,edit_after,expect_code",
    [
        (SAT, "tvl: [\n", 2),  # load error
        (SAT, '"retriever.k ="', 2),  # structural parse error
        (UNSAT, "temperature >= 0.0", 0),  # normal path
    ],
    ids=["load-error", "parse-error", "checked"],
)
def test_unlink_oserror_is_swallowed(monkeypatch, capsys, tmp_path, structural: str, edit_after: str, expect_code: int) -> None:
    spy = _TempSpy(monkeypatch)
    module = _write(tmp_path, structural)
    before = {"tvl: [\n": "tvl:\n", '"retriever.k ="': '"retriever.k = 5"', "temperature >= 0.0": "temperature >= 0.4"}[edit_after]
    cand = _candidate(tmp_path, {"edits": [{"before": before, "after": edit_after}]})

    def boom(self: Path, missing_ok: bool = False) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(Path, "unlink", boom)
    code, _, _ = _run(monkeypatch, capsys, str(module), "--candidate-file", str(cand))
    monkeypatch.undo()
    assert code == expect_code
    assert len(spy.paths) == 1 and spy.paths[0].exists()
    spy.paths[0].unlink()


# --- uncaught errors -------------------------------------------------------- #

def test_missing_candidate_file_raises(monkeypatch, tmp_path) -> None:
    module = _write(tmp_path, SAT)
    monkeypatch.setattr(sys, "argv", ["x", str(module), "--candidate-file", str(tmp_path / "nope.json")])
    with pytest.raises(FileNotFoundError):
        cli.main()


def test_invalid_candidate_json_raises(monkeypatch, tmp_path) -> None:
    module = _write(tmp_path, SAT)
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["x", str(module), "--candidate-file", str(bad)])
    with pytest.raises(json.JSONDecodeError):
        cli.main()


def test_candidate_with_missing_module_raises(monkeypatch, tmp_path) -> None:
    cand = _candidate(tmp_path, {"edits": []})
    monkeypatch.setattr(sys, "argv", ["x", str(tmp_path / "missing.yml"), "--candidate-file", str(cand)])
    with pytest.raises(FileNotFoundError):
        cli.main()


def test_unexpected_check_error_propagates(monkeypatch, tmp_path) -> None:
    spy = _TempSpy(monkeypatch)
    module = _write(tmp_path, UNSAT)
    cand = _candidate(tmp_path, {"edits": [{"before": "temperature >= 0.4", "after": "temperature >= 0.0"}]})

    def explode(m: Any) -> Optional[StructuralResult]:
        raise RuntimeError("solver exploded")

    monkeypatch.setattr(cli, "check_structural", explode)
    monkeypatch.setattr(sys, "argv", ["x", str(module), "--candidate-file", str(cand)])
    with pytest.raises(RuntimeError, match="solver exploded"):
        cli.main()
    # The temp file is not cleaned on an unexpected error.
    assert len(spy.paths) == 1 and spy.paths[0].exists()
    spy.paths[0].unlink()
