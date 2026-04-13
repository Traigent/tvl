from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # pragma: no cover - optional dependency
    from ortools.sat.python import cp_model  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback path
    cp_model = None  # type: ignore

from .model import Domain, extract_domains
from .structural_parser import DNF, Literal, clause_to_string, parse_expression


@dataclass
class Clause:
    literals: List[Literal]
import math


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
            continue
        when_expr = entry.get("when")
        then_expr = entry.get("then")
        expr_expr = entry.get("expr")

        if when_expr is not None or then_expr is not None:
            if when_expr is None or then_expr is None:
                continue
            expression_text = f"not ({when_expr}) or ({then_expr})"
        elif expr_expr is not None:
            expression_text = expr_expr
        else:
            continue

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

    clause_counter = 0
    for expression in structural.expressions:
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

    solver = cp_model.CpSolver()
    assumption_literals = [expr.assumption for expr in structural.expressions if expr.assumption is not None]
    have_assumptions = hasattr(solver, "SolveWithAssumptions")
    if have_assumptions:
        status = solver.SolveWithAssumptions(model, assumption_literals)
    else:
        for lit in assumption_literals:
            model.Add(lit == 1)
        status = solver.Solve(model)

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
    unsat_info: List[Dict[str, Any]] = []
    core_metadata = {
        "size": 0,
        "variables": set(),
        "clauses": [],
        "expressions": [],
    }
    for expr in structural.expressions:
        if expr.assumption in unsat_core_vars:
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
    core_metadata["variables"] = sorted(core_metadata["variables"])
    return StructuralResult(ok=False, assignment=None, unsat_core=unsat_info, core_metadata=core_metadata)


# Helper functions -----------------------------------------------------------


def _convert_literal_value(token_type: Optional[str], raw: Any) -> Any:
    if isinstance(raw, (int, float, bool)):
        return raw
    if isinstance(raw, tuple):
        return raw
    if not isinstance(raw, str):
        return raw
    if token_type == "BOOLEAN":
        return raw.lower() == "true"
    if token_type == "NUMBER":
        if "." in raw or "e" in raw.lower():
            return float(raw)
        try:
            return int(raw)
        except ValueError:
            return float(raw)
    if token_type == "TUPLE_VAL":
        return _parse_tuple_literal(raw)
    if token_type == "STRING":
        return raw
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
            current.append(ch)
            if ch == "\\" and i + 1 < len(text):
                # Escaped char inside quotes — consume next char verbatim
                current.append(text[i + 1])
                i += 2
                continue
            if ch == in_quote:
                in_quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_quote = ch
            current.append(ch)
        elif ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(ch)
        i += 1
    remainder = "".join(current).strip()
    if remainder:
        parts.append(remainder)
    return parts


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
    try:
        if "." in stripped or "e" in stripped.lower():
            return float(stripped)
        return int(stripped)
    except ValueError:
        pass
    # Quoted string
    if len(stripped) >= 2 and stripped[0] in ("'", '"') and stripped[-1] == stripped[0]:
        return _unescape_string(stripped[1:-1])
    # Bare string
    return stripped


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
                    new_op = "!="
                    extended.append(Condition(literal.ident, new_op, value))
                new_clauses.append(extended)
            return new_clauses
        new_clauses = []
        for clause in clauses:
            for value in values:
                new_clause = list(clause)
                new_clause.append(Condition(literal.ident, "==", value))
                new_clauses.append(new_clause)
        return new_clauses

    if literal.kind == "interval":
        left, right, op1, op2 = literal.values
        left_value = _convert_literal_value("NUMBER", left)
        right_value = _convert_literal_value("NUMBER", right)
        if literal.negated:
            new_clauses: List[List[Condition]] = []
            for clause in clauses:
                new_clauses.append(list(clause) + [Condition(literal.ident, "<", left_value)])
                new_clauses.append(list(clause) + [Condition(literal.ident, ">", right_value)])
            return new_clauses
        else:
            new_clauses: List[List[Condition]] = []
            map_op_left = {"<=": ">=", "<": ">"}
            map_op_right = {"<=": "<=", "<": "<"}
            for clause in clauses:
                new_clause = list(clause)
                new_clause.append(Condition(literal.ident, map_op_left.get(op1, ">="), left_value))
                new_clause.append(Condition(literal.ident, map_op_right.get(op2, "<="), right_value))
                new_clauses.append(new_clause)
            return new_clauses

    if literal.kind == "comparison":
        value_type = literal.value_types[0] if literal.value_types else None
        operator = _normalize_operator(literal.operator, literal.negated)
        raw = literal.values[0]
        if value_type == "IDENT" and raw in tvar_names and operator in {"==", "!="}:
            return [clause + [Condition(literal.ident, operator, None, rhs_ident=raw)] for clause in clauses]
        value = _convert_literal_value(value_type, raw)
        return [clause + [Condition(literal.ident, operator, value)] for clause in clauses]

    # Fallback: keep literal as unsupported, drop clause to avoid false SAT
    return []


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
        return bool_var

    if condition.rhs_ident is not None:
        rhs_var = var_map.get(condition.rhs_ident)
        rhs_domain = domains.get(condition.rhs_ident)
        op = condition.operator
        if rhs_var is None or rhs_domain is None or op not in {"==", "!="}:
            model.Add(bool_var == 0)
            return bool_var

        if domain.kind == "enum" and rhs_domain.kind == "enum":
            left_values = domain.values or []
            right_values = rhs_domain.values or []
            if not left_values or not right_values:
                model.Add(bool_var == (1 if op == "!=" else 0))
                return bool_var

            left_index = {value: idx for idx, value in enumerate(left_values)}
            right_index = {value: idx for idx, value in enumerate(right_values)}
            shared = sorted(set(left_index.keys()) & set(right_index.keys()), key=str)
            pairs = [(left_index[v], right_index[v]) for v in shared]
            if not pairs:
                model.Add(bool_var == (1 if op == "!=" else 0))
                return bool_var

            if op == "==":
                model.AddAllowedAssignments([var, rhs_var], pairs).OnlyEnforceIf(bool_var)
                model.AddForbiddenAssignments([var, rhs_var], pairs).OnlyEnforceIf(bool_var.Not())
            else:
                model.AddForbiddenAssignments([var, rhs_var], pairs).OnlyEnforceIf(bool_var)
                model.AddAllowedAssignments([var, rhs_var], pairs).OnlyEnforceIf(bool_var.Not())
            return bool_var

        if domain.kind == "bool" and rhs_domain.kind == "bool":
            if op == "==":
                model.Add(var == rhs_var).OnlyEnforceIf(bool_var)
                model.Add(var != rhs_var).OnlyEnforceIf(bool_var.Not())
            else:
                model.Add(var != rhs_var).OnlyEnforceIf(bool_var)
                model.Add(var == rhs_var).OnlyEnforceIf(bool_var.Not())
            return bool_var

        if domain.kind in {"int", "float"} and rhs_domain.kind in {"int", "float"}:
            left_denom = domain.precision if domain.kind == "float" else 1
            right_denom = rhs_domain.precision if rhs_domain.kind == "float" else 1
            left_scaled = var * right_denom
            right_scaled = rhs_var * left_denom
            if op == "==":
                model.Add(left_scaled == right_scaled).OnlyEnforceIf(bool_var)
                model.Add(left_scaled != right_scaled).OnlyEnforceIf(bool_var.Not())
            else:
                model.Add(left_scaled != right_scaled).OnlyEnforceIf(bool_var)
                model.Add(left_scaled == right_scaled).OnlyEnforceIf(bool_var.Not())
            return bool_var

        model.Add(bool_var == 0)
        return bool_var

    op = condition.operator
    try:
        if domain.kind == "float" and isinstance(condition.value, (int, float)):
            val = float(condition.value)
            P = domain.precision
            if op in {"==", "!="}:
                scaled = val * P
                rounded = round(scaled)
                if abs(scaled - rounded) > 1e-9:
                    # Non-grid point
                    if op == "==":
                        model.Add(bool_var == 0)
                        return bool_var
                    else:
                        model.Add(bool_var == 1)
                        return bool_var
                encoded_value = int(rounded)
            elif op == ">=":
                encoded_value = math.ceil(val * P)
            elif op == ">":
                encoded_value = math.floor(val * P) + 1
            elif op == "<=":
                encoded_value = math.floor(val * P)
            elif op == "<":
                encoded_value = math.ceil(val * P) - 1
            else:
                encoded_value = domain.encode(condition.value)
        else:
            encoded_value = domain.encode(condition.value)
    except Exception:
        model.Add(bool_var == 0)
        return bool_var
    if op == "==":
        model.Add(var == encoded_value).OnlyEnforceIf(bool_var)
        model.Add(var != encoded_value).OnlyEnforceIf(bool_var.Not())
    elif op == "!=":
        model.Add(var != encoded_value).OnlyEnforceIf(bool_var)
        model.Add(var == encoded_value).OnlyEnforceIf(bool_var.Not())
    elif op == ">=":
        model.Add(var >= encoded_value).OnlyEnforceIf(bool_var)
        model.Add(var < encoded_value).OnlyEnforceIf(bool_var.Not())
    elif op == ">":
        model.Add(var > encoded_value).OnlyEnforceIf(bool_var)
        model.Add(var <= encoded_value).OnlyEnforceIf(bool_var.Not())
    elif op == "<=":
        model.Add(var <= encoded_value).OnlyEnforceIf(bool_var)
        model.Add(var > encoded_value).OnlyEnforceIf(bool_var.Not())
    elif op == "<":
        model.Add(var < encoded_value).OnlyEnforceIf(bool_var)
        model.Add(var >= encoded_value).OnlyEnforceIf(bool_var.Not())
    else:
        model.Add(bool_var == 0)
    return bool_var


def _check_structural_bruteforce(domains: Dict[str, Domain], expressions: List[Expression]) -> StructuralResult:
    candidates = _candidate_values(domains, expressions)
    order = sorted(candidates.keys(), key=lambda name: len(candidates[name]))
    assignment: Dict[str, Any] = {}

    solution = _search_assignment(order, candidates, expressions, assignment, 0)
    if solution is not None:
        return StructuralResult(ok=True, assignment=solution, unsat_core=None)

    core = _approximate_unsat_core(domains, expressions, candidates)
    return StructuralResult(ok=False, assignment=None, unsat_core=core)


def _candidate_values(domains: Dict[str, Domain], expressions: List[Expression]) -> Dict[str, List[Any]]:
    values: Dict[str, set] = {}
    for name, domain in domains.items():
        base: set = set()
        if domain.kind == "bool":
            base.update({True, False})
        elif domain.kind == "enum":
            base.update(domain.values or [])
        elif domain.kind in {"int", "float"}:
            if domain.minimum is not None:
                base.add(domain.minimum)
            if domain.maximum is not None:
                base.add(domain.maximum)
        values[name] = base

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

    candidate_lists: Dict[str, List[Any]] = {}
    for name, val_set in values.items():
        domain = domains[name]
        if domain.kind == "bool":
            candidate_lists[name] = [True, False]
        elif domain.kind == "enum":
            candidate_lists[name] = list(domain.values or [])
        elif domain.kind == "int":
            valid = sorted(int(v) for v in val_set if isinstance(v, (int, float)))
            if domain.minimum is not None and domain.maximum is not None:
                if domain.maximum - domain.minimum <= 10:
                    valid = list(range(int(domain.minimum), int(domain.maximum) + 1))
            if not valid:
                if domain.minimum is not None:
                    valid.append(int(domain.minimum))
                valid.append(0)
            candidate_lists[name] = sorted({v for v in valid if domain.contains(v)})
        elif domain.kind == "float":
            valid = [float(v) for v in val_set if isinstance(v, (int, float))]
            if not valid:
                if domain.minimum is not None:
                    valid.append(float(domain.minimum))
                valid.append(0.0)
            candidate_lists[name] = sorted({v for v in valid if domain.contains(v)})
        else:
            candidate_lists[name] = list(val_set) if val_set else [None]
    return candidate_lists


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
