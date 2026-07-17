"""Guards against parser/loader denial-of-service on adversarial TVL input.

Covers Traigent/tvl issues #44 (YAML billion-laughs / size cap), #45 (operational
derived-constraint AST-walker recursion), #46 (structural parser recursion + 2^N
DNF blowup), and #47 (tvl-check-structural CLI crash on a malformed structural
expression string).
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

BASE = pathlib.Path(__file__).resolve().parents[1]
PKG_ROOT = BASE / "python"
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from tvl import yaml_safe  # noqa: E402
from tvl.errors import ParseError  # noqa: E402
from tvl.loader import load  # noqa: E402
from tvl.operational import _parse_derived_expression  # noqa: E402
from tvl.structural_parser import StructuralParseError, parse_expression  # noqa: E402
from tvl.yaml_safe import safe_load  # noqa: E402


# --------------------------------------------------------------------------- #
# #44 — YAML billion-laughs / entity-expansion + size cap
# --------------------------------------------------------------------------- #

def _alias_bomb(alias_count: int) -> str:
    # NB: PyYAML resolves anchors to *shared* node references (a DAG) and caches
    # constructed objects, so the textbook exponential billion-laughs does not
    # actually OOM PyYAML. The alias budget is defense-in-depth against a
    # pathological alias-reference count; this constructs a document that trips
    # it directly.
    lines = ["base: &a value", "refs:"]
    lines.extend(["  - *a"] * alias_count)
    return "\n".join(lines) + "\n"


def test_safe_load_rejects_alias_budget_overflow() -> None:
    bomb = _alias_bomb(yaml_safe.MAX_YAML_ALIASES + 100)
    with pytest.raises(yaml_safe.YAMLLimitError):
        safe_load(bomb)


def test_safe_load_rejects_oversized_input() -> None:
    oversized = "x" * (yaml_safe.MAX_YAML_BYTES + 1)
    with pytest.raises(yaml_safe.YAMLLimitError):
        safe_load(oversized)


def test_loader_surfaces_oversized_input_as_parse_error(tmp_path: pathlib.Path) -> None:
    # The public loader wraps loader-level limit failures as ParseError
    # (contract preserved) rather than an OOM/crash.
    big = tmp_path / "big.tvl.yml"
    big.write_text("data: " + "x" * (yaml_safe.MAX_YAML_BYTES + 1), encoding="utf-8")
    with pytest.raises(ParseError):
        load(big)


def test_safe_load_still_parses_normal_yaml() -> None:
    assert safe_load("a: 1\nb: [1, 2, 3]\n") == {"a": 1, "b": [1, 2, 3]}
    # A modest, legitimate anchor/alias document is unaffected.
    assert safe_load("base: &b {k: 1}\nuse: *b\n") == {"base": {"k": 1}, "use": {"k": 1}}


# --------------------------------------------------------------------------- #
# #45 — operational derived-constraint AST walker recursion
# --------------------------------------------------------------------------- #


def test_derived_expression_deep_chain_returns_gracefully() -> None:
    # ~4000 chained terms would exhaust the stack in the unbounded walker.
    expr = " + ".join(["x"] * 4000) + " <= 1"
    terms, op, val, legacy = _parse_derived_expression(expr)
    # Graceful "unparseable" rejection — no RecursionError escapes.
    assert (terms, op, val, legacy) == (None, None, None, [])


def test_derived_expression_normal_still_parses() -> None:
    terms, op, val, legacy = _parse_derived_expression("2*x + y <= 5")
    assert op == "<="
    assert val == 5.0
    assert sorted(terms) == [(1.0, "y"), (2.0, "x")]


# --------------------------------------------------------------------------- #
# #46 — structural parser recursion + DNF blowup
# --------------------------------------------------------------------------- #


def test_structural_nested_parens_raise_parse_error() -> None:
    text = "(" * 400 + "x == 1" + ")" * 400
    with pytest.raises(StructuralParseError):
        parse_expression(text)


def test_structural_chained_not_raise_parse_error() -> None:
    text = "not " * 2000 + "x == 1"
    with pytest.raises(StructuralParseError):
        parse_expression(text)


def test_structural_dnf_blowup_raises_parse_error() -> None:
    # 24 conjunctions of binary disjunctions => 2**24 clauses if unbounded.
    text = " and ".join(f"(a{i} == 1 or b{i} == 2)" for i in range(24))
    with pytest.raises(StructuralParseError):
        parse_expression(text)


def test_structural_normal_expression_still_parses() -> None:
    dnf = parse_expression("x == 1 or y == 2")
    assert len(dnf.clauses) == 2


def test_structural_flat_and_chain_raises_parse_error() -> None:
    # A flat `a and b and c and ...` chain never deepens the parser's nesting
    # guard (conjunction() builds it via a `while` loop, not recursion), but
    # it still produces a left-deep AST that `_to_nnf`/`_to_dnf` would walk
    # *recursively* — thousands of terms would exhaust the stack there
    # without the total-unit bound. Graceful rejection, no RecursionError.
    text = " and ".join(f"x{i} == 1" for i in range(4000))
    with pytest.raises(StructuralParseError):
        parse_expression(text)


def test_structural_flat_or_chain_raises_parse_error() -> None:
    text = " or ".join(f"x{i} == 1" for i in range(4000))
    with pytest.raises(StructuralParseError):
        parse_expression(text)


# --------------------------------------------------------------------------- #
# #47 — tvl-check-structural CLI: malformed expression => exit 2 + JSON
# --------------------------------------------------------------------------- #

_MODULE_WITH_BAD_EXPR = """
tvl:
  module: book.quickstart.simple_rag_qa

environment:
  snapshot_id: "2025-01-20T00:00:00Z"

evaluation_set:
  dataset: s3://datasets/campus-rag/dev.jsonl
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
    - when: "retriever.k <"
      then: "temperature <= 0.3"

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


def test_check_structural_cli_malformed_expr(tmp_path) -> None:
    # Run the CLI as a real subprocess: this tests the true process-level
    # contract (exit code + stdout JSON) and avoids in-process sys.modules
    # pollution from sibling tests that synthesize a duplicate `tvl` package.
    module_file = tmp_path / "bad.tvl.yml"
    module_file.write_text(_MODULE_WITH_BAD_EXPR, encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(PKG_ROOT), str(BASE), env.get("PYTHONPATH", "")])
    env["TRAIGENT_MOCK_LLM"] = "true"

    proc = subprocess.run(
        [sys.executable, "-m", "tvl_tools.tvl_check_structural.cli", str(module_file), "--json"],
        capture_output=True,
        text=True,
        env=env,
    )

    # Documented validation exit code is 2, not the default-1 uncaught-crash code.
    assert proc.returncode == 2, proc.stderr
    # --json contract honoured even on parse failure (no bare traceback to stdout).
    payload = json.loads(proc.stdout)
    assert payload["kind"] == "PhaseResult"
    assert payload["ok"] is False
    assert "invalid structural constraint" in payload["error"]
