"""Example pytest module that exercises Chapter 3 structural constraints.

This uses TVL's structural parser (typed DNF) to evaluate constraints against
sample assignments.
"""
from __future__ import annotations

from pathlib import Path

from tvl.loader import load
from tvl.structural_parser import DNF, Literal, parse_expression


SPEC_PATH = Path(__file__).with_name("ch3_constraints_units.tvl.yml")
MODULE = load(SPEC_PATH)


def _coerce(value_type: str, raw: str) -> object:
    if value_type == "STRING":
        return raw
    if value_type == "BOOLEAN":
        return raw.lower() == "true"
    if value_type == "NUMBER":
        try:
            if "." in raw or "e" in raw.lower():
                return float(raw)
            return int(raw)
        except ValueError:
            return raw
    return raw


def _literal_true(literal: Literal, assignments: dict) -> bool:
    raw_value = assignments.get(literal.ident)
    if raw_value is None:
        return False

    truth = False
    if literal.kind == "comparison":
        rhs = _coerce(literal.value_types[0] if literal.value_types else "", literal.values[0])
        op = literal.operator
        if op == "==":
            truth = raw_value == rhs
        elif op == "!=":
            truth = raw_value != rhs
        elif op == "<":
            truth = raw_value < rhs
        elif op == "<=":
            truth = raw_value <= rhs
        elif op == ">":
            truth = raw_value > rhs
        elif op == ">=":
            truth = raw_value >= rhs
        else:
            raise ValueError(f"Unsupported operator: {op}")
    elif literal.kind == "membership":
        candidates = {
            _coerce(value_type, value)
            for value_type, value in zip(literal.value_types, literal.values)
        }
        truth = raw_value in candidates
    elif literal.kind == "interval":
        left, right, op1, op2 = literal.values
        left_num = float(left)
        right_num = float(right)
        ok_left = raw_value >= left_num if op1 == "<=" else raw_value > left_num
        ok_right = raw_value <= right_num if op2 == "<=" else raw_value < right_num
        truth = ok_left and ok_right
    else:
        raise ValueError(f"Unsupported literal kind: {literal.kind}")

    return (not truth) if literal.negated else truth


def _dnf_true(dnf: DNF, assignments: dict) -> bool:
    return any(
        all(_literal_true(literal, assignments) for literal in clause)
        for clause in dnf.clauses
    )


def _structural_ok(assignments: dict) -> bool:
    structural = (MODULE.get("constraints") or {}).get("structural") or []
    for entry in structural:
        if "expr" in entry:
            if not _dnf_true(parse_expression(entry["expr"]), assignments):
                return False
            continue
        if "when" in entry and "then" in entry:
            if _dnf_true(parse_expression(entry["when"]), assignments):
                if not _dnf_true(parse_expression(entry["then"]), assignments):
                    return False
            continue
        raise ValueError(f"Unsupported structural constraint entry: {entry!r}")
    return True


def test_valid_assignment_passes() -> None:
    assignments = {
        "temperature": 0.5,
        "max_tokens": 512,
        "cache_ttl_hours": 2.0,
        "retriever_top_k": 20,
        "rerank_weight": 0.5,
    }
    assert _structural_ok(assignments)


def test_forbidden_combination_fails() -> None:
    assignments = {
        "temperature": 0.4,
        "max_tokens": 512,
        "cache_ttl_hours": 1.0,
        "retriever_top_k": 20,
        "rerank_weight": 0.85,
    }
    assert not _structural_ok(assignments)


def test_conditional_requirement_triggers() -> None:
    assignments = {
        "temperature": 0.3,
        "max_tokens": 640,
        "cache_ttl_hours": 2.5,
        "retriever_top_k": 45,
        "rerank_weight": 0.2,
    }
    assert not _structural_ok(assignments)
