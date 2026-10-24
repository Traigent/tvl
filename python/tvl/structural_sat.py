from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - optional dependency
    from ortools.sat.python import cp_model  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback path
    cp_model = None  # type: ignore

from .model import Domain, extract_domains
from .structural_parser import DNF, Literal, StructuralParseError, clause_to_string, parse_expression


@dataclass
class Clause:
    literals: List[Literal]


@dataclass
class Expression:
    path: List[Any]
    text: str
    dnf: DNF
    expanded_clauses: List[List["Condition"]]
    clause_strings: List[str]
    assumption: Optional[Any] = None


@dataclass
class Condition:
    ident: str
    operator: str
    value: Any
    rhs_ident: Optional[str] = None


@dataclass
class StructuralModel:
    model: Any
    domains: Dict[str, Domain]
    variables: Dict[str, Any]
    expressions: List[Expression]


@dataclass
class StructuralResult:
    ok: bool
    assignment: Optional[Dict[str, Any]]
    unsat_core: Optional[List[Dict[str, Any]]]
    core_metadata: Optional[Dict[str, Any]] = None


@dataclass
class UndecidedStructuralResult(StructuralResult):
    """Neither a witness nor a UNSAT proof was found (OR-Tools missing, domains not exhausted).

    ``ok`` is False (fail closed) but the module must NOT be reported as unsatisfiable.
    """

    undecided: bool = True
    issues: Optional[List[Dict[str, Any]]] = None


UNDECIDED_WITHOUT_SOLVER_CODE = "structural_undecided_without_solver"
UNDECIDED_WITHOUT_SOLVER_MESSAGE = (
    "Structural satisfiability could not be decided: OR-Tools is not installed and the "
    "fallback search cannot exhaust this module's domains. Install OR-Tools "
    "(pip install ortools) to decide this module."
)


def build_structural_model(module: Dict[str, Any]) -> StructuralModel:
    domains = extract_domains(module.get("tvars", {}))
    model = cp_model.CpModel() if cp_model is not None else None
    variables: Dict[str, Any] = {}

    if cp_model is not None:
        for path, domain in domains.items():
            if domain.kind == "enum":
                upper = max(len(domain.values or []) - 1, 0)
                variables[path] = model.NewIntVar(0, upper, f"{path}_enc")
            elif domain.kind in {"int", "float"}:
                lower = int(domain._encode_bound_lower(domain.minimum)) if domain.minimum is not None else -cp_model.INT32_MAX
                upper = int(domain._encode_bound_upper(domain.maximum)) if domain.maximum is not None else cp_model.INT32_MAX
                variables[path] = model.NewIntVar(lower, upper, f"{path}_val")
            elif domain.kind == "bool":
                variables[path] = model.NewBoolVar(f"{path}_bool")
            else:
                raise ValueError(f"Unsupported domain kind: {domain.kind}")

    expressions: List[Expression] = []
    tvar_names = set(domains.keys())
    structural_section = (module.get("constraints") or {}).get("structural") or []
    for idx, entry in enumerate(structural_section):
        if not isinstance(entry, dict):
            raise StructuralParseError(
                f"Structural constraint at index {idx} must be an object, got {entry!r}"
            )
        when_expr = entry.get("when")
        then_expr = entry.get("then")
        expr_expr = entry.get("expr")
        extra_keys = set(entry.keys()) - {"when", "then", "expr"}
        has_when_then = when_expr is not None and then_expr is not None
        has_expr = expr_expr is not None
        # Mirror the grammar's oneOf({when,then} | {expr}) + additionalProperties:
        # false (spec/grammar/tvl.schema.json, constraints.structural items): reject
        # loudly instead of silently dropping the entry from the SAT model — the
        # exact fail-open class this closes for tvl-check-structural (issue #15).
        if extra_keys or has_when_then == has_expr:
            raise StructuralParseError(
                f"Structural constraint at index {idx} does not match the required "
                f"{{when, then}} or {{expr}} shape (extra keys: {sorted(extra_keys)!r}): {entry!r}"
            )
        if has_when_then:
            expression_text = f"not ({when_expr}) or ({then_expr})"
        else:
            expression_text = expr_expr

        dnf = parse_expression(expression_text)
        expanded = _expand_dnf(dnf, tvar_names)
        clause_strings = [clause_to_string(clause) for clause in dnf.clauses]
        expressions.append(
            Expression(
                path=["constraints", "structural", idx],
                text=expression_text,
                dnf=dnf,
                expanded_clauses=expanded,
                clause_strings=clause_strings,
            )
        )

    return StructuralModel(model=model, domains=domains, variables=variables, expressions=expressions)


def check_structural(module: Dict[str, Any]) -> StructuralResult:
    structural = build_structural_model(module)
    if cp_model is None:
        return _check_structural_bruteforce(structural.domains, structural.expressions)

    model: cp_model.CpModel = structural.model
    var_map = structural.variables
    domains = structural.domains
    _encode_expression_assumptions(model, var_map, domains, structural.expressions)

    solver = cp_model.CpSolver()
    assumption_literals = [expr.assumption for expr in structural.expressions if expr.assumption is not None]
    have_assumptions = hasattr(solver, "SolveWithAssumptions")
    status = _solve_under_assumptions(solver, model, assumption_literals, have_assumptions)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        assignment = {
            name: domains[name].decode(int(solver.Value(var)))
            for name, var in var_map.items()
        }
        return StructuralResult(ok=True, assignment=assignment, unsat_core=None)

    if have_assumptions and hasattr(solver, "SufficientAssumptionsForInfeasibility"):
        unsat_core_vars = solver.SufficientAssumptionsForInfeasibility()
    else:
        unsat_core_vars = assumption_literals
    return _unsat_core_result(structural.expressions, unsat_core_vars)


def _encode_expression_assumptions(
    model: cp_model.CpModel,
    var_map: Dict[str, Any],
    domains: Dict[str, Domain],
    expressions: List[Expression],
) -> None:
    """Encode each expression's clauses and attach the assumption literal guarding it."""
    clause_counter = 0
    for expression in expressions:
        clause_bools: List[cp_model.BoolVar] = []
        for clause in expression.expanded_clauses:
            clause_bool = _encode_clause(model, var_map, domains, clause, clause_counter)
            clause_counter += 1
            clause_bools.append(clause_bool)
        assumption = model.NewBoolVar(f"expr_{len(clause_bools)}_{clause_counter}")
        expression.assumption = assumption
        if clause_bools:
            model.AddBoolOr(clause_bools + [assumption.Not()])
        else:
            model.Add(assumption == 0)


def _solve_under_assumptions(solver: Any, model: Any, assumption_literals: List[Any], have_assumptions: bool) -> Any:
    if have_assumptions:
        return solver.SolveWithAssumptions(model, assumption_literals)
    for lit in assumption_literals:
        model.Add(lit == 1)
    return solver.Solve(model)


def _unsat_core_result(expressions: List[Expression], unsat_core_vars: Any) -> StructuralResult:
    unsat_info: List[Dict[str, Any]] = []
    core_metadata = {
        "size": 0,
        "variables": set(),
        "clauses": [],
        "expressions": [],
    }
    for expr in expressions:
        if expr.assumption in unsat_core_vars:
            _record_core_expression(expr, unsat_info, core_metadata)
    core_metadata["variables"] = sorted(core_metadata["variables"])
    return StructuralResult(ok=False, assignment=None, unsat_core=unsat_info, core_metadata=core_metadata)


def _record_core_expression(
    expr: Expression, unsat_info: List[Dict[str, Any]], core_metadata: Dict[str, Any]
) -> None:
    core_metadata["expressions"].append({
        "path": expr.path,
        "expression": expr.text,
    })
    core_metadata["size"] += 1
    clauses = expr.clause_strings
    unsat_info.append(
        {
            "path": expr.path,
            "expression": expr.text,
            "clauses": clauses,
        }
    )
    for clause in expr.expanded_clauses:
        clause_repr = [f"{cond.ident} {cond.operator} {cond.value}" for cond in clause]
        core_metadata["clauses"].append(clause_repr)
        for cond in clause:
            core_metadata["variables"].add(cond.ident)


# Helper functions -----------------------------------------------------------


def _convert_literal_value(token_type: Optional[str], raw: Any) -> Any:
    # Non-strings (numbers, booleans, tuples, anything else) pass through unchanged.
    if not isinstance(raw, str):
        return raw
    if token_type == "BOOLEAN":
        return raw.lower() == "true"
    if token_type == "NUMBER":
        return _convert_number_token(raw)
    if token_type == "TUPLE_VAL":
        return _parse_tuple_literal(raw)
    if token_type == "STRING":
        return raw
    return _convert_untyped_literal(raw)


def _convert_number_token(raw: str) -> Any:
    if "." in raw or "e" in raw.lower():
        return float(raw)
    try:
        return int(raw)
    except ValueError:
        return float(raw)


def _convert_untyped_literal(raw: str) -> Any:
    if raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    try:
        if "." in raw or "e" in raw.lower():
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _parse_tuple_literal(raw: str) -> tuple:
    """Convert a tuple literal string like '(1, 3)' into a Python tuple.

    Handles int, float, boolean (true/false), quoted strings, and nested
    tuple components.  Commas inside nested parentheses are respected.
    """
    inner = raw.strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    parts = _split_tuple_parts(inner)
    converted = []
    for p in parts:
        converted.append(_parse_tuple_element(p))
    return tuple(converted)


def _split_tuple_parts(text: str) -> list[str]:
    """Split a comma-separated string respecting nested parens, quotes, and escapes."""
    parts: list[str] = []
    depth = 0
    in_quote: str | None = None
    current: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if in_quote is not None:
            i, in_quote = _consume_quoted_char(text, i, in_quote, current)
            continue
        if ch == "," and depth == 0:
            _append_part(parts, current)
            current = []
        else:
            in_quote, depth = _track_unquoted_char(ch, depth)
            current.append(ch)
        i += 1
    _append_part(parts, current)
    return parts


def _consume_quoted_char(text: str, i: int, in_quote: str, current: list[str]) -> tuple[int, str | None]:
    """Append the quoted character at ``i``; return the next index and quote state."""
    ch = text[i]
    current.append(ch)
    if ch == "\\" and i + 1 < len(text):
        # Escaped char inside quotes — consume next char verbatim
        current.append(text[i + 1])
        return i + 2, in_quote
    if ch == in_quote:
        return i + 1, None
    return i + 1, in_quote


def _track_unquoted_char(ch: str, depth: int) -> tuple[str | None, int]:
    """Quote state and paren depth after an unquoted, non-separator character."""
    if ch in ("'", '"'):
        return ch, depth
    if ch == "(":
        return None, depth + 1
    if ch == ")":
        return None, depth - 1
    return None, depth


def _append_part(parts: list[str], current: list[str]) -> None:
    part = "".join(current).strip()
    if part:
        parts.append(part)


def _parse_tuple_element(p: str) -> Any:
    """Parse a single tuple element: nested tuple, bool, number, or string."""
    stripped = p.strip()
    # Nested tuple
    if stripped.startswith("(") and stripped.endswith(")"):
        return _parse_tuple_literal(stripped)
    # Boolean
    if stripped.lower() == "true":
        return True
    if stripped.lower() == "false":
        return False
    # Number
    number = _parse_tuple_number(stripped)
    if number is not _NOT_A_NUMBER:
        return number
    # Quoted string
    if len(stripped) >= 2 and stripped[0] in ("'", '"') and stripped[-1] == stripped[0]:
        return _unescape_string(stripped[1:-1])
    # Bare string
    return stripped


_NOT_A_NUMBER = object()


def _parse_tuple_number(stripped: str) -> Any:
    """``float``/``int`` for a numeric element, else the ``_NOT_A_NUMBER`` sentinel."""
    try:
        if "." in stripped or "e" in stripped.lower():
            return float(stripped)
        return int(stripped)
    except ValueError:
        return _NOT_A_NUMBER


def _unescape_string(s: str) -> str:
    """Unescape ``\\X`` sequences produced by tuple re-quoting."""
    result: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            result.append(s[i + 1])
            i += 2
        else:
            result.append(s[i])
            i += 1
    return "".join(result)


def _expand_dnf(dnf: DNF, tvar_names: set[str]) -> List[List[Condition]]:
    expanded: List[List[Condition]] = []
    for clause in dnf.clauses:
        clause_variants: List[List[Condition]] = [[]]
        for literal in clause:
            clause_variants = _integrate_literal(clause_variants, literal, tvar_names)
            if not clause_variants:
                break
        expanded.extend(clause_variants)
    return expanded


def _integrate_literal(clauses: List[List[Condition]], literal: Literal, tvar_names: set[str]) -> List[List[Condition]]:
    if not clauses:
        return clauses
    if literal.kind == "membership":
        return _integrate_membership(clauses, literal)
    if literal.kind == "interval":
        return _integrate_interval(clauses, literal)
    if literal.kind == "comparison":
        return _integrate_comparison(clauses, literal, tvar_names)
    # Fallback: keep literal as unsupported, drop clause to avoid false SAT
    return []


def _integrate_membership(clauses: List[List[Condition]], literal: Literal) -> List[List[Condition]]:
    values = [_convert_literal_value(t, v) for t, v in zip(literal.value_types, literal.values)]
    if not values:
        if literal.negated:
            return clauses
        return []
    if literal.negated:
        new_clauses: List[List[Condition]] = []
        for clause in clauses:
            extended = list(clause)
            for value in values:
                extended.append(Condition(literal.ident, "!=", value))
            new_clauses.append(extended)
        return new_clauses
    new_clauses = []
    for clause in clauses:
        for value in values:
            new_clause = list(clause)
            new_clause.append(Condition(literal.ident, "==", value))
            new_clauses.append(new_clause)
    return new_clauses


def _integrate_interval(clauses: List[List[Condition]], literal: Literal) -> List[List[Condition]]:
    left, right, op1, op2 = literal.values
    left_value = _convert_literal_value("NUMBER", left)
    right_value = _convert_literal_value("NUMBER", right)
    new_clauses: List[List[Condition]] = []
    if literal.negated:
        for clause in clauses:
            new_clauses.append(list(clause) + [Condition(literal.ident, "<", left_value)])
            new_clauses.append(list(clause) + [Condition(literal.ident, ">", right_value)])
        return new_clauses
    map_op_left = {"<=": ">=", "<": ">"}
    map_op_right = {"<=": "<=", "<": "<"}
    for clause in clauses:
        new_clause = list(clause)
        new_clause.append(Condition(literal.ident, map_op_left.get(op1, ">="), left_value))
        new_clause.append(Condition(literal.ident, map_op_right.get(op2, "<="), right_value))
        new_clauses.append(new_clause)
    return new_clauses


def _integrate_comparison(
    clauses: List[List[Condition]], literal: Literal, tvar_names: set[str]
) -> List[List[Condition]]:
    value_type = literal.value_types[0] if literal.value_types else None
    operator = _normalize_operator(literal.operator, literal.negated)
    raw = literal.values[0]
    if value_type == "IDENT" and raw in tvar_names and operator in {"==", "!="}:
        return [clause + [Condition(literal.ident, operator, None, rhs_ident=raw)] for clause in clauses]
    value = _convert_literal_value(value_type, raw)
    return [clause + [Condition(literal.ident, operator, value)] for clause in clauses]


def _normalize_operator(operator: str, negated: bool) -> str:
    if not negated:
        return operator
    mapping = {
        "==": "!=",
        "!=": "==",
        "<=": ">",
        "<": ">=",
        ">=": "<",
    }
    if operator == ">":
        return "<="
    return mapping.get(operator, operator)


def _encode_clause(
    model: cp_model.CpModel,
    var_map: Dict[str, cp_model.IntVar],
    domains: Dict[str, Domain],
    clause: List[Condition],
    counter: int,
) -> cp_model.BoolVar:
    if not clause:
        bool_var = model.NewBoolVar(f"clause_true_{counter}")
        model.Add(bool_var == 1)
        return bool_var

    literal_bools: List[cp_model.BoolVar] = []
    for idx, condition in enumerate(clause):
        literal_bools.append(
            _encode_condition(model, var_map, domains, condition, f"lit_{counter}_{idx}")
        )

    clause_bool = model.NewBoolVar(f"clause_{counter}")
    model.AddBoolAnd(literal_bools).OnlyEnforceIf(clause_bool)
    model.AddBoolOr([lit.Not() for lit in literal_bools] + [clause_bool])
    return clause_bool


# Reified comparison: (constraint when the literal holds, constraint when it does not).
_REIFIED_COMPARISONS: Dict[str, Any] = {
    "==": (lambda lhs, rhs: lhs == rhs, lambda lhs, rhs: lhs != rhs),
    "!=": (lambda lhs, rhs: lhs != rhs, lambda lhs, rhs: lhs == rhs),
    ">=": (lambda lhs, rhs: lhs >= rhs, lambda lhs, rhs: lhs < rhs),
    ">": (lambda lhs, rhs: lhs > rhs, lambda lhs, rhs: lhs <= rhs),
    "<=": (lambda lhs, rhs: lhs <= rhs, lambda lhs, rhs: lhs > rhs),
    "<": (lambda lhs, rhs: lhs < rhs, lambda lhs, rhs: lhs >= rhs),
}

_NUMERIC_KINDS = {"int", "float"}


def _reify_comparison(model: cp_model.CpModel, lhs: Any, op: str, rhs: Any, bool_var: cp_model.BoolVar) -> None:
    """Constrain ``bool_var`` to be true iff ``lhs <op> rhs``."""
    holds, fails = _REIFIED_COMPARISONS[op]
    model.Add(holds(lhs, rhs)).OnlyEnforceIf(bool_var)
    model.Add(fails(lhs, rhs)).OnlyEnforceIf(bool_var.Not())


def _encode_condition(
    model: cp_model.CpModel,
    var_map: Dict[str, cp_model.IntVar],
    domains: Dict[str, Domain],
    condition: Condition,
    name: str,
) -> cp_model.BoolVar:
    var = var_map.get(condition.ident)
    domain = domains.get(condition.ident)
    bool_var = model.NewBoolVar(name)

    if var is None or domain is None:
        model.Add(bool_var == 0)
    elif condition.rhs_ident is not None:
        _encode_ident_comparison(model, var_map, domains, var, domain, condition, bool_var)
    else:
        _encode_value_comparison(model, var, domain, condition, bool_var)
    return bool_var


def _encode_ident_comparison(
    model: cp_model.CpModel,
    var_map: Dict[str, cp_model.IntVar],
    domains: Dict[str, Domain],
    var: cp_model.IntVar,
    domain: Domain,
    condition: Condition,
    bool_var: cp_model.BoolVar,
) -> None:
    """Encode ``ident ==/!= other_ident``; unsupported pairings are false."""
    rhs_var = var_map.get(condition.rhs_ident)
    rhs_domain = domains.get(condition.rhs_ident)
    op = condition.operator
    if rhs_var is None or rhs_domain is None or op not in {"==", "!="}:
        model.Add(bool_var == 0)
    elif domain.kind == "enum" and rhs_domain.kind == "enum":
        _encode_enum_pair(model, var, domain, rhs_var, rhs_domain, op, bool_var)
    elif domain.kind == "bool" and rhs_domain.kind == "bool":
        _reify_comparison(model, var, op, rhs_var, bool_var)
    elif domain.kind in _NUMERIC_KINDS and rhs_domain.kind in _NUMERIC_KINDS:
        # Cross-multiply by the other side's precision so both sides share a scale.
        left_scaled = var * _precision_denominator(rhs_domain)
        right_scaled = rhs_var * _precision_denominator(domain)
        _reify_comparison(model, left_scaled, op, right_scaled, bool_var)
    else:
        model.Add(bool_var == 0)


def _precision_denominator(domain: Domain) -> int:
    return domain.precision if domain.kind == "float" else 1


def _encode_enum_pair(
    model: cp_model.CpModel,
    var: cp_model.IntVar,
    domain: Domain,
    rhs_var: cp_model.IntVar,
    rhs_domain: Domain,
    op: str,
    bool_var: cp_model.BoolVar,
) -> None:
    """Encode equality between two enum variables over their shared values."""
    left_index = {value: idx for idx, value in enumerate(domain.values or [])}
    right_index = {value: idx for idx, value in enumerate(rhs_domain.values or [])}
    shared = sorted(set(left_index.keys()) & set(right_index.keys()), key=str)
    pairs = [(left_index[v], right_index[v]) for v in shared]
    if not pairs:
        # No value can be equal on both sides (including an empty enum).
        model.Add(bool_var == (1 if op == "!=" else 0))
        return

    equal, unequal = model.AddAllowedAssignments, model.AddForbiddenAssignments
    when_true, when_false = (equal, unequal) if op == "==" else (unequal, equal)
    when_true([var, rhs_var], pairs).OnlyEnforceIf(bool_var)
    when_false([var, rhs_var], pairs).OnlyEnforceIf(bool_var.Not())


def _encode_value_comparison(
    model: cp_model.CpModel,
    var: cp_model.IntVar,
    domain: Domain,
    condition: Condition,
    bool_var: cp_model.BoolVar,
) -> None:
    """Encode ``ident <op> literal``; unencodable literals and operators are false."""
    op = condition.operator
    try:
        encoded_value = _encode_literal_value(domain, op, condition.value)
    except Exception:
        model.Add(bool_var == 0)
        return
    if encoded_value is None:
        # Equality against a float that is off the precision grid.
        model.Add(bool_var == (0 if op == "==" else 1))
    elif op in _REIFIED_COMPARISONS:
        _reify_comparison(model, var, op, encoded_value, bool_var)
    else:
        model.Add(bool_var == 0)


def _encode_literal_value(domain: Domain, op: str, value: Any) -> Optional[int]:
    """Encode a literal for comparison; ``None`` means an off-grid float equality."""
    if domain.kind == "float" and isinstance(value, (int, float)):
        return _encode_float_literal(domain, op, value)
    return domain.encode(value)


def _encode_float_literal(domain: Domain, op: str, value: Any) -> Optional[int]:
    val = float(value)
    P = domain.precision
    if op in {"==", "!="}:
        scaled = val * P
        rounded = round(scaled)
        if abs(scaled - rounded) > 1e-9:
            return None
        return int(rounded)
    if op == ">=":
        return math.ceil(val * P)
    if op == ">":
        return math.floor(val * P) + 1
    if op == "<=":
        return math.floor(val * P)
    if op == "<":
        return math.ceil(val * P) - 1
    return domain.encode(value)


def _check_structural_bruteforce(domains: Dict[str, Domain], expressions: List[Expression]) -> StructuralResult:
    candidates = _candidate_values(domains, expressions)
    order = sorted(candidates.keys(), key=lambda name: len(candidates[name]))
    assignment: Dict[str, Any] = {}

    solution = _search_assignment(order, candidates, expressions, assignment, 0)
    if solution is not None:
        return StructuralResult(ok=True, assignment=solution, unsat_core=None)

    # No witness found. A sampled search only proves UNSAT when every domain was
    # enumerated completely; otherwise fail closed with an explicit undecided result.
    if not _candidates_are_exhaustive(domains, candidates):
        return UndecidedStructuralResult(
            ok=False,
            assignment=None,
            unsat_core=None,
            undecided=True,
            issues=[
                {
                    "code": UNDECIDED_WITHOUT_SOLVER_CODE,
                    "message": UNDECIDED_WITHOUT_SOLVER_MESSAGE,
                    "path": ["constraints", "structural"],
                    "severity": "error",
                }
            ],
        )

    core = _approximate_unsat_core(domains, expressions, candidates)
    return StructuralResult(ok=False, assignment=None, unsat_core=core)


def _candidates_are_exhaustive(domains: Dict[str, Domain], candidates: Dict[str, List[Any]]) -> bool:
    """True only if every searched variable's candidate list is its entire finite domain."""
    for name, cand in candidates.items():
        domain = domains.get(name)
        if domain is None:
            return False
        if domain.kind in ("bool", "enum"):
            continue
        if domain.kind == "int" and domain.minimum is not None and domain.maximum is not None:
            if set(cand) == set(range(int(domain.minimum), int(domain.maximum) + 1)):
                continue
        return False
    return True


def _candidate_values(domains: Dict[str, Domain], expressions: List[Expression]) -> Dict[str, List[Any]]:
    values: Dict[str, set] = {name: _seed_values(domain) for name, domain in domains.items()}
    _collect_condition_values(values, expressions)
    return {name: _candidate_list(domains[name], val_set) for name, val_set in values.items()}


def _seed_values(domain: Domain) -> set:
    """Initial candidates implied by the domain declaration alone."""
    base: set = set()
    if domain.kind == "bool":
        base.update({True, False})
    elif domain.kind == "enum":
        base.update(domain.values or [])
    elif domain.kind in _NUMERIC_KINDS:
        if domain.minimum is not None:
            base.add(domain.minimum)
        if domain.maximum is not None:
            base.add(domain.maximum)
    return base


def _collect_condition_values(values: Dict[str, set], expressions: List[Expression]) -> None:
    """Add each literal compared against, plus its numeric neighbours."""
    for expr in expressions:
        for clause in expr.expanded_clauses:
            for cond in clause:
                if cond.rhs_ident is not None:
                    continue
                vals = values.setdefault(cond.ident, set())
                vals.add(cond.value)
                if isinstance(cond.value, (int, float)):
                    vals.add(cond.value + 1)
                    vals.add(cond.value - 1)


def _candidate_list(domain: Domain, val_set: set) -> List[Any]:
    if domain.kind == "bool":
        return [True, False]
    if domain.kind == "enum":
        return list(domain.values or [])
    if domain.kind == "int":
        return _int_candidates(domain, val_set)
    if domain.kind == "float":
        return _float_candidates(domain, val_set)
    return list(val_set) if val_set else [None]


def _int_candidates(domain: Domain, val_set: set) -> List[Any]:
    valid = sorted(int(v) for v in val_set if isinstance(v, (int, float)))
    if domain.minimum is not None and domain.maximum is not None:
        if domain.maximum - domain.minimum <= 10:
            valid = list(range(int(domain.minimum), int(domain.maximum) + 1))
    if not valid:
        valid = _fallback_candidates(domain, int)
    return sorted({v for v in valid if domain.contains(v)})


def _float_candidates(domain: Domain, val_set: set) -> List[Any]:
    valid = [float(v) for v in val_set if isinstance(v, (int, float))]
    if not valid:
        valid = _fallback_candidates(domain, float)
    return sorted({v for v in valid if domain.contains(v)})


def _fallback_candidates(domain: Domain, cast: Any) -> List[Any]:
    """Candidates when no numeric value is known: the minimum, then zero."""
    fallback = [cast(domain.minimum)] if domain.minimum is not None else []
    fallback.append(cast(0))
    return fallback


def _search_assignment(
    order: List[str],
    candidates: Dict[str, List[Any]],
    expressions: List[Expression],
    assignment: Dict[str, Any],
    index: int,
) -> Optional[Dict[str, Any]]:
    if index == len(order):
        if all(_evaluate_expression(expr, assignment) for expr in expressions):
            return dict(assignment)
        return None

    name = order[index]
    for value in candidates.get(name, [None]):
        assignment[name] = value
        result = _search_assignment(order, candidates, expressions, assignment, index + 1)
        if result is not None:
            return result
        assignment.pop(name, None)
    return None


def _evaluate_expression(expr: Expression, assignment: Dict[str, Any]) -> bool:
    for clause in expr.expanded_clauses:
        if all(_evaluate_condition(cond, assignment) for cond in clause):
            return True
    return False


def _evaluate_condition(cond: Condition, assignment: Dict[str, Any]) -> bool:
    value = assignment.get(cond.ident)
    if value is None:
        return False
    if cond.rhs_ident is not None:
        target = assignment.get(cond.rhs_ident)
        if target is None:
            return False
    else:
        target = cond.value
    op = cond.operator
    if op == "==":
        return value == target
    if op == "!=":
        return value != target
    if op == ">=":
        return value >= target
    if op == ">":
        return value > target
    if op == "<=":
        return value <= target
    if op == "<":
        return value < target
    return False


def _approximate_unsat_core(
    domains: Dict[str, Domain],
    expressions: List[Expression],
    candidates: Dict[str, List[Any]],
) -> List[Dict[str, Any]]:
    core = expressions[:]
    order = sorted(candidates.keys(), key=lambda name: len(candidates[name]))

    idx = 0
    while idx < len(core):
        candidate_core = core[:idx] + core[idx + 1 :]
        if _search_assignment(order, candidates, candidate_core, {}, 0) is None:
            core = candidate_core
        else:
            idx += 1

    result: List[Dict[str, Any]] = []
    for expr in core:
        result.append(
            {
                "path": expr.path,
                "expression": expr.text,
                "clauses": expr.clause_strings,
            }
        )
    return result
