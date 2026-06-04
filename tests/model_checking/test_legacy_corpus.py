"""P1 — conservative extension over the REAL canonical example corpus.

Phase-3 form: for every existing example module, injecting the new 1.1 blocks
at dict level changes NEITHER the lint diagnostics NOR the structural-SAT
verdict produced by the real python/tvl pipeline. (Schema-level P1 — the
loader accepting the new blocks — is the Phase 4 obligation; lint_module and
compile_constraints read only the fields they know, which is exactly what
this suite locks.)
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from tvl.constraints import check_structural_satisfiable, compile_constraints
from tvl.lints import lint_module

EXAMPLES_ROOT = Path(__file__).resolve().parents[2] / "spec" / "examples"

# The phase-6 fixtures themselves are 1.1-surface documents; exclude them from
# the LEGACY corpus (they are the forward fixtures, not the 1.0 baseline).
CORPUS = sorted(
    p
    for p in EXAMPLES_ROOT.rglob("*.yml")
    if "validation-phase6-cvars" not in str(p)
)

INJECTED_CVARS = [
    {
        "name": "injected.theta",
        "type": "float",
        "domain": {"range": [0.0, 1.0]},
        "calibration": {"source": "pool_a"},
        "governance": {"require_calibration": True},
    }
]

INJECTED_POLICIES = [
    {
        "name": "injected.cascade",
        "kind": "policy",
        "strategy": "cascade",
        "stages": ["cheap", "strong"],
        "gates": [{"kind": "margin_below", "threshold": "injected.theta"}],
    }
]


def _issues_key(issues) -> list:
    # lint_module yields Issue objects for most checks but plain dicts for
    # some (e.g. schema-shaped diagnostics) — normalize both.
    def _key(issue):
        if isinstance(issue, dict):
            return (str(issue.get("code")), str(issue.get("path", "")))
        return (str(issue.code), str(getattr(issue, "path", "")))

    return sorted(_key(i) for i in issues)


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: str(p.relative_to(EXAMPLES_ROOT)))
def test_p1_lint_and_sat_unchanged_by_injection(path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or "tvars" not in doc:
        pytest.skip("not a module document (config/measurement/policy file)")

    extended = copy.deepcopy(doc)
    extended["cvars"] = copy.deepcopy(INJECTED_CVARS)
    extended["policies"] = copy.deepcopy(INJECTED_POLICIES)

    # Lint equivalence: identical diagnostics with and without the new blocks.
    assert _issues_key(lint_module(doc)) == _issues_key(lint_module(extended))

    # SAT equivalence where the module compiles/solves at all (some corpus
    # files are intentionally broken; equivalence of the FAILURE is asserted
    # instead — P1 is about identical behavior, including identical errors).
    def _compile_and_solve(module):
        try:
            compiled = compile_constraints(module)
        except Exception as exc:  # noqa: BLE001 — corpus contains intentional errors
            return None, None, f"compile:{type(exc).__name__}"
        try:
            sat = check_structural_satisfiable(compiled)
        except Exception as exc:  # noqa: BLE001 — see pre-existing _encode_bound bug
            return compiled, None, f"solve:{type(exc).__name__}"
        return compiled, sat, None

    base_compiled, base_sat, base_error = _compile_and_solve(doc)
    ext_compiled, ext_sat, ext_error = _compile_and_solve(extended)

    assert base_error == ext_error
    if base_compiled is not None:
        assert set(base_compiled.domains) == set(ext_compiled.domains)
        assert "injected.theta" not in ext_compiled.domains
    if base_sat is not None:
        assert base_sat.get("ok") == ext_sat.get("ok")
        assert base_sat.get("ok") is not None


def test_corpus_is_nonempty():
    assert len(CORPUS) >= 20, f"corpus unexpectedly small: {len(CORPUS)}"
