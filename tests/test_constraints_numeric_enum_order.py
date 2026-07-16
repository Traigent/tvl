"""Regression: numeric-enum inequality constraints assumed index order == value order.

The `<`/`<=`/`>`/`>=` encoder in `_atom_literal` built the set of indices whose
VALUE satisfies the comparison, then constrained `var <= max(allowed)` (or
`var >= min(allowed)`). That is only correct when the enum values are sorted so
the satisfying indices are contiguous. List-form tvar declarations sort numeric
enums, but the legacy dict-form path stores them verbatim, so an out-of-order
numeric enum encoded a wrong SAT/UNSAT verdict (fail-open): the solver could
satisfy `temperature < 0.6` by picking the value 1.0.

The encoder now reifies membership over the exact satisfying index set, so the
verdict is correct regardless of declaration form / value order.

See Traigent/tvl#33.
"""

from __future__ import annotations

from tvl.constraints import check_structural_satisfiable, compile_constraints


def test_unsorted_dict_form_numeric_enum_is_unsat():
    """`temp < 0.6 AND temp = 1.0` is UNSAT; the buggy encoder reported SAT."""
    module = {
        "tvars": {"sampling": {"temperature": {"type": "enum", "values": [1.0, 0.0, 0.5]}}},
        "constraints": {
            "structural": [
                {"expr": "sampling.temperature < 0.6"},
                {"expr": "sampling.temperature = 1.0"},
            ]
        },
    }
    result = check_structural_satisfiable(compile_constraints(module))
    assert result["ok"] is False


def test_unsorted_dict_form_numeric_enum_sat_witness_respects_threshold():
    """A genuinely satisfiable spec still solves, with a value below threshold."""
    module = {
        "tvars": {"sampling": {"temperature": {"type": "enum", "values": [1.0, 0.0, 0.5]}}},
        "constraints": {"structural": [{"expr": "sampling.temperature < 0.6"}]},
    }
    result = check_structural_satisfiable(compile_constraints(module))
    assert result["ok"] is True
    assert result["assignment"]["sampling.temperature"] < 0.6


def test_dict_form_and_list_form_agree():
    """The verdict must depend on semantics, not declaration form."""
    dict_form = {
        "tvars": {"sampling": {"temperature": {"type": "enum", "values": [1.0, 0.0, 0.5]}}},
        "constraints": {
            "structural": [
                {"expr": "sampling.temperature < 0.6"},
                {"expr": "sampling.temperature = 1.0"},
            ]
        },
    }
    list_form = {
        "tvars": [{"name": "temperature", "type": "enum", "domain": {"set": [1.0, 0.0, 0.5]}}],
        "constraints": {
            "structural": [
                {"expr": "temperature < 0.6"},
                {"expr": "temperature = 1.0"},
            ]
        },
    }
    d = check_structural_satisfiable(compile_constraints(dict_form))
    l = check_structural_satisfiable(compile_constraints(list_form))
    assert d["ok"] == l["ok"] is False


def test_greater_than_on_unsorted_enum():
    """The same fix must hold for the `>` direction."""
    module = {
        "tvars": {"sampling": {"temperature": {"type": "enum", "values": [1.0, 0.0, 0.5]}}},
        "constraints": {
            "structural": [
                {"expr": "sampling.temperature > 0.6"},
                {"expr": "sampling.temperature = 0.0"},
            ]
        },
    }
    result = check_structural_satisfiable(compile_constraints(module))
    assert result["ok"] is False
