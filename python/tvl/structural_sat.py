from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple

try:  # pragma: no cover - optional dependency
    from ortools.sat.python import cp_model  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback path
    cp_model = None  # type: ignore

from .model import (
    Domain,
    ExactFormatLimitError,
    ExactLiteralLimitError,
    ExactNumber,
    bounded_fraction,
    exact_to_str,
    extract_domains,
    _exact,
)
from .structural_parser import (
    DNF,
    MAX_DNF_CLAUSES,
    Literal,
    StructuralParseError,
    clause_to_string,
    parse_expression,
)


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
    # Exact rational of a numeric literal, from its source text (None for non-numeric literals).
    # Conditions built without one take the decimal of the value's shortest repr.
    exact: Optional[Fraction] = None

    def __post_init__(self) -> None:
        if self.exact is None and self.rhs_ident is None and _is_plain_number(self.value):
            key = _num(self.value)
            self.exact = key if isinstance(key, Fraction) else None


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
    # Exact witness: name -> exact decimal / "p/q" string for numeric values (non-numeric
    # values unchanged). ``assignment`` keeps plain binary64 floats for compatibility, and
    # two distinct grid points may round to the same float there; this field never does.
    exact_assignment: Optional[Dict[str, Any]] = None


@dataclass
class UndecidedStructuralResult(StructuralResult):
    """Neither a witness nor a UNSAT proof was found (OR-Tools missing, domains not exhausted).

    ``ok`` is False (fail closed) but the module must NOT be reported as unsatisfiable.
    """

    undecided: bool = True
    issues: Optional[List[Dict[str, Any]]] = None


# CP-SAT needs every coefficient * bound product within signed 64-bit; stay well inside it.
_INT_LIMIT = 2**62

ENCODING_OVERFLOW_CODE = "structural_encoding_overflow"
SOLVER_INCONCLUSIVE_CODE = "structural_solver_inconclusive"
WITNESS_UNVERIFIED_CODE = "structural_witness_unverified"
WITNESS_TOO_LARGE_CODE = "structural_witness_too_large"
ILL_TYPED_CODE = "structural_ill_typed_atom"
NON_FINITE_CODE = "structural_non_finite_domain"
UNRESOLVED_DOMAIN_CODE = "structural_unresolved_domain"
PAIR_TABLE_TOO_LARGE_CODE = "structural_pair_table_too_large"
EXPANSION_TOO_LARGE_CODE = "structural_expansion_too_large"
VALUE_TOO_LARGE_CODE = "structural_value_too_large"

_ORDERING_OPS = {"<", "<=", ">", ">="}
# Largest allowed-assignment table one TVAR-vs-TVAR equality atom may build. Domains are
# deduplicated first (so an enum-vs-enum table has at most min(|D|, |D'|) rows); this bound
# is counted BEFORE any table is materialised.
_MAX_PAIR_TABLE = 1_000_000
# Exact keys (:func:`_atom_key`) and witness text are structural, so a tuple member costs its
# EXPANDED size: ``value = (value, value)`` thirty times is 31 objects but 2**31 nodes. One
# enum domain's members may expand to at most this many nested nodes in total (scalar members
# are free), and nest at most this deep; both are counted by identity BEFORE any key is built.
_MAX_VALUE_NODES = 1_000_000
_MAX_VALUE_DEPTH = 100


class _EncodingOverflow(Exception):
    def __init__(self, variable: str) -> None:
        super().__init__(variable)
        self.variable = variable


class _PairTableTooLarge(Exception):
    def __init__(self, left: str, right: str, rows: int) -> None:
        super().__init__(left, right, rows)
        self.left, self.right, self.rows = left, right, rows


class _ValueTooLarge(StructuralParseError):
    """An enum domain's members expand past ``_MAX_VALUE_NODES`` nodes or ``_MAX_VALUE_DEPTH`` levels.

    A :class:`StructuralParseError` for direct :func:`build_structural_model` callers;
    :func:`check_structural` reports it undecided.
    """

    def __init__(self, variable: str) -> None:
        super().__init__(
            f"enum domain of '{variable}' has members whose nested components exceed "
            f"{_MAX_VALUE_NODES} expanded nodes or {_MAX_VALUE_DEPTH} levels of nesting"
        )
        self.variable = variable


class _ExpansionTooLarge(StructuralParseError):
    """Membership / negated-interval expansion of one expression exceeds ``MAX_DNF_CLAUSES``.

    A :class:`StructuralParseError` for direct :func:`build_structural_model` callers (the
    parser's own DNF limit raises one too); :func:`check_structural` reports it undecided.
    """

    def __init__(self, clauses: int) -> None:
        super().__init__(
            f"structural expression expands to at least {clauses} clauses, above the limit "
            f"of {MAX_DNF_CLAUSES}"
        )
        self.clauses = clauses
        self.path: List[Any] = ["constraints", "structural"]


def _undecided(code: str, message: str) -> "UndecidedStructuralResult":
    return UndecidedStructuralResult(
        ok=False,
        assignment=None,
        unsat_core=None,
        undecided=True,
        issues=[
            {
                "code": code,
                "message": message,
                "path": ["constraints", "structural"],
                "severity": "error",
            }
        ],
    )


def _overflow_result(variable: str) -> "UndecidedStructuralResult":
    return _undecided(
        ENCODING_OVERFLOW_CODE,
        f"Structural satisfiability could not be decided: the exact encoding of variable "
        f"'{variable}' exceeds the solver's signed 64-bit integer range. Narrow its range "
        "or use a coarser resolution.",
    )


def _is_plain_number(v: Any) -> bool:
    return isinstance(v, (int, float, Fraction)) and not isinstance(v, bool)


def _num(v: Any) -> Any:
    """Comparison key of a number: its exact rational when finite, else the float itself.

    ``Fraction`` compares exactly against +-inf and is never equal to NaN, so mixing the
    two keeps IEEE semantics for non-finite values and exact semantics for the rest.
    """
    if isinstance(v, float) and not math.isfinite(v):
        return v
    return _exact(v)


def _sat_result(
    expressions: List["Expression"], exact: Dict[str, Any], domains: Optional[Dict[str, Domain]] = None
) -> "StructuralResult":
    """Report SAT only after re-verifying the exact witness against every expression AND domain.

    ``exact`` holds float values as ``Fraction``. With ``domains``, every witness value must be
    an exact member of its declared domain (grid point within the exact bounds, enum member by
    :func:`_atom_key`); the expressions alone do not prove the witness admissible. The public
    ``assignment`` carries plain binary64 numbers (compatibility); ``exact_assignment`` carries
    every numeric leaf, tuple components included, as an exact decimal / ``"p/q"`` string.
    """
    if domains is not None:
        outside = [name for name, v in exact.items() if name in domains and not _domain_member(domains[name], v)]
        if outside:
            return _undecided(
                WITNESS_UNVERIFIED_CODE,
                "Structural satisfiability could not be decided: the solver's witness for "
                f"'{outside[0]}' is not an exact member of its declared domain.",
            )
    if not all(_evaluate_expression(expr, exact) for expr in expressions):
        return _undecided(
            WITNESS_UNVERIFIED_CODE,
            "Structural satisfiability could not be decided: the solver's witness does not "
            "satisfy the constraints under exact evaluation.",
        )
    try:
        assignment = {name: _public_value(v) for name, v in exact.items()}
        exact_assignment = {name: _exact_value(v) for name, v in exact.items()}
    except (ExactFormatLimitError, OverflowError):
        # Fail closed: a witness that cannot be printed exactly (and within bounds) is not
        # reported as SAT; a lossy or truncated value would break the exact-witness contract.
        return _undecided(
            WITNESS_TOO_LARGE_CODE,
            "Structural satisfiability could not be decided: the witness has a value too large "
            "to report exactly. Use literals with fewer digits or smaller exponents.",
        )
    return StructuralResult(ok=True, assignment=assignment, unsat_core=None, exact_assignment=exact_assignment)


def _public_value(v: Any) -> Any:
    """Compatibility witness value: numeric leaves as plain ``float``/``int`` (recursively)."""
    if isinstance(v, tuple):
        return tuple(_public_value(x) for x in v)
    if isinstance(v, list):
        return [_public_value(x) for x in v]
    if isinstance(v, bool) or not isinstance(v, (int, float, Fraction)):
        return v
    if isinstance(v, int):
        return int(v)
    return float(v)  # Fraction / float subclass -> plain binary64 (lossy by contract)


def _exact_value(v: Any) -> Any:
    """Exact witness value: every finite numeric leaf (tuple/list components too) as exact text."""
    if isinstance(v, tuple):
        return tuple(_exact_value(x) for x in v)
    if isinstance(v, list):
        return [_exact_value(x) for x in v]
    if _is_plain_number(v):
        key = _num(v)
        return exact_to_str(key) if isinstance(key, Fraction) else v
    return v


def _domain_member(domain: Domain, value: Any) -> bool:
    """True iff ``value`` is EXACTLY a member of ``domain`` (Definition 3.6)."""
    if domain.kind == "bool":
        return isinstance(value, bool)
    if domain.kind == "enum":
        key = _atom_key(value)
        return any(_atom_key(member) == key for member in domain.values or [])
    if domain.kind not in _NUMERIC_KINDS or not _is_plain_number(value):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    if domain.kind == "int" and not domain.gridded:
        if not (isinstance(value, int) or _exact(value).denominator == 1):
            return False
        index = int(_exact(value))
    else:
        grid_index = domain.grid_index(value)
        if grid_index.denominator != 1:
            return False
        index = int(grid_index)
    lower, upper = domain.index_lower(), domain.index_upper()
    return (lower is None or index >= lower) and (upper is None or index <= upper)


def _index_bounds(domain: Domain) -> Tuple[int, int]:
    lower, upper = domain.index_lower(), domain.index_upper()
    return (
        int(lower) if lower is not None else -cp_model.INT32_MAX,
        int(upper) if upper is not None else cp_model.INT32_MAX,
    )


UNDECIDED_WITHOUT_SOLVER_CODE = "structural_undecided_without_solver"
UNDECIDED_WITHOUT_SOLVER_MESSAGE = (
    "Structural satisfiability could not be decided: OR-Tools is not installed and the "
    "fallback search cannot exhaust this module's domains. Install OR-Tools "
    "(pip install ortools) to decide this module."
)


def build_structural_model(module: Dict[str, Any]) -> StructuralModel:
    try:
        domains = extract_domains(module.get("tvars", {}))
    except ExactLiteralLimitError as exc:
        raise StructuralParseError(f"TVAR domain literal out of bounds: {exc}") from exc
    for path, domain in domains.items():
        _check_value_budget(path, domain)
        _dedupe_enum_values(domain)
    model = cp_model.CpModel() if cp_model is not None else None
    variables: Dict[str, Any] = {}

    if cp_model is not None:
        for path, domain in domains.items():
            if domain.kind == "enum" and not domain.values:
                # Unresolved (registry-backed) domain: no value to decode. check_structural
                # refuses to decide any atom that references it, so it needs no variable.
                continue
            if domain.kind == "enum":
                upper = max(len(domain.values or []) - 1, 0)
                variables[path] = model.NewIntVar(0, upper, f"{path}_enc")
            elif domain.kind in {"int", "float"}:
                lower, upper = _index_bounds(domain)
                if max(abs(lower), abs(upper)) > _INT_LIMIT:
                    raise _EncodingOverflow(path)
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
        try:
            expanded = _expand_dnf(dnf, tvar_names)
        except _ExpansionTooLarge as exc:
            exc.path = ["constraints", "structural", idx]
            raise
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
    non_finite = _non_finite_issue(module.get("tvars", {}))
    if non_finite is not None:
        return _undecided(NON_FINITE_CODE, non_finite)
    try:
        structural = build_structural_model(module)
        problem = _typing_problem(structural.domains, structural.expressions)
        if problem is not None:
            return _undecided(*problem)
        if cp_model is None:
            searchable = {n: d for n, d in structural.domains.items() if not _is_empty_enum(d)}
            return _check_structural_bruteforce(searchable, structural.expressions)

        model: cp_model.CpModel = structural.model
        var_map = structural.variables
        domains = structural.domains
        _encode_expression_assumptions(model, var_map, domains, structural.expressions)
    except _EncodingOverflow as exc:
        return _overflow_result(exc.variable)
    except _ValueTooLarge as exc:
        return _undecided(
            VALUE_TOO_LARGE_CODE,
            f"Structural satisfiability could not be decided: the enum domain of '{exc.variable}' "
            f"has members whose nested (shared or deep) tuple components expand to more than "
            f"{_MAX_VALUE_NODES} nodes or {_MAX_VALUE_DEPTH} levels; exact comparison would have "
            "to expand every shared component. Flatten or shrink the values.",
        )
    except _ExpansionTooLarge as exc:
        result = _undecided(
            EXPANSION_TOO_LARGE_CODE,
            f"Structural satisfiability could not be decided: the expression at "
            f"{'.'.join(str(p) for p in exc.path)} expands to at least {exc.clauses} clauses "
            f"(membership 'in' sets and negated intervals multiply), above the limit of "
            f"{MAX_DNF_CLAUSES} (the parser's DNF clause limit). Split or simplify the constraint.",
        )
        result.issues[0]["path"] = list(exc.path)
        return result
    except _PairTableTooLarge as exc:
        return _undecided(
            PAIR_TABLE_TOO_LARGE_CODE,
            f"Structural satisfiability could not be decided: the equality between TVARs "
            f"'{exc.left}' and '{exc.right}' needs a table of at least {exc.rows} equal-value "
            f"pairs, above the limit of {_MAX_PAIR_TABLE}. Narrow their domains.",
        )

    solver = cp_model.CpSolver()
    assumption_literals = [expr.assumption for expr in structural.expressions if expr.assumption is not None]
    have_assumptions = hasattr(solver, "SolveWithAssumptions")
    status = _solve_under_assumptions(solver, model, assumption_literals, have_assumptions)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        exact = {
            name: domains[name].decode_exact(int(solver.Value(var)))
            for name, var in var_map.items()
        }
        return _sat_result(structural.expressions, exact, domains)

    # Only INFEASIBLE proves UNSAT; MODEL_INVALID, UNKNOWN, ... are inconclusive.
    if status != cp_model.INFEASIBLE:
        return _undecided(
            SOLVER_INCONCLUSIVE_CODE,
            f"Structural satisfiability could not be decided: the solver returned status "
            f"{solver.StatusName(status) if hasattr(solver, 'StatusName') else status}, not INFEASIBLE.",
        )

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


# Fail-closed input checks -------------------------------------------------------


def _non_finite_issue(tvars: Any) -> Optional[str]:
    """Message for the first NaN/infinite number in the TVAR declarations, else None.

    The formal semantics interprets ``float`` (and ``enum[float]``) as the rationals
    (Definitions 3.1-3.2), so NaN and +-inf denote no domain value. Admitting them made
    comparison negation unsound (``not (0 <= x <= 1)`` rewritten to two atoms that are both
    false on NaN); they are rejected before any encoding.
    """
    stack: List[Tuple[Any, List[Any]]] = [(tvars, ["tvars"])]
    # Containers already expanded, by identity: an alias cycle (``&d [*d]``) or shared alias
    # is scanned once, so the walk terminates and stays linear in the distinct nodes.
    seen: set = set()
    while stack:
        node, path = stack.pop()
        if isinstance(node, float) and not math.isfinite(node):
            return (
                "Structural satisfiability could not be decided: the TVAR declaration value at "
                f"{'.'.join(str(p) for p in path)} is {node!r}; TVL numeric domains are rationals "
                "(formal semantics Definitions 3.1-3.2), so NaN and infinities are not admitted."
            )
        if isinstance(node, (dict, list, tuple)):
            if id(node) in seen:
                continue
            seen.add(id(node))
        if isinstance(node, dict):
            stack.extend((v, path + [k]) for k, v in node.items())
        elif isinstance(node, (list, tuple)):
            stack.extend((v, path + [i]) for i, v in enumerate(node))
    return None


def _is_empty_enum(domain: Domain) -> bool:
    return domain.kind == "enum" and not domain.values


def _check_value_budget(path: str, domain: Domain) -> None:
    """Raise :class:`_ValueTooLarge` if ``domain``'s members expand past the value budget.

    Each distinct container is sized once (memoised by identity), so the check is linear in
    the objects actually held, not in their expansion; a cycle (``&a [*a]``) or a nesting
    deeper than ``_MAX_VALUE_DEPTH`` is refused rather than recursed into. Every occurrence of
    a member is charged (``[v] * 1000`` costs 1000 times ``v``), because :func:`_atom_key`
    and the witness formatters expand each occurrence.
    """
    if domain.kind != "enum" or not domain.values:
        return
    sizes: Dict[int, int] = {}
    in_progress: set = set()

    def expanded(node: Any, depth: int) -> int:
        if not isinstance(node, (tuple, list)):
            return 1
        known = sizes.get(id(node))
        if known is not None:
            return known
        if depth > _MAX_VALUE_DEPTH or id(node) in in_progress:
            raise _ValueTooLarge(path)
        in_progress.add(id(node))
        total = 1
        for child in node:
            total += expanded(child, depth + 1)
            if total > _MAX_VALUE_NODES:
                raise _ValueTooLarge(path)
        in_progress.discard(id(node))
        sizes[id(node)] = total
        return total

    budget = 0
    for member in domain.values:
        if isinstance(member, (tuple, list)):
            budget += expanded(member, 1)
            if budget > _MAX_VALUE_NODES:
                raise _ValueTooLarge(path)


def _dedupe_enum_values(domain: Domain) -> None:
    """Drop repeated enum members, keeping the first of each exact value (:func:`_atom_key`).

    Definition 3.6 interprets ``[v1, ..., vn]`` and ``{set: [...]}`` as the SET
    ``{v1, ..., vn}``, so repeats carry no meaning; keeping them only multiplied the
    TVAR-equality tables (``[1] * 20000`` on both sides built 4e8 pairs).
    """
    if domain.kind != "enum" or not domain.values:
        return
    seen: set = set()
    unique: List[Any] = []
    for value in domain.values:
        key = _atom_key(value)
        if key not in seen:
            seen.add(key)
            unique.append(value)
    if len(unique) != len(domain.values):
        domain.values = unique


def _element_class(domain: Domain) -> str:
    """Element type class of a domain: ``num``, ``bool``, ``enum`` (non-numeric) or ``unresolved``."""
    if domain.kind in _NUMERIC_KINDS:
        return "num"
    if domain.kind == "bool":
        return "bool"
    # Registry status is declaration provenance (Domain.unresolved), never a value's
    # spelling: an explicit enum member "__registry_unresolved_x" is an ordinary string.
    if domain.unresolved or not domain.values:
        return "unresolved"
    return "num" if _is_numeric_enum(domain) else "enum"


def _typing_problem(domains: Dict[str, Domain], expressions: List[Expression]) -> Optional[Tuple[str, str]]:
    """``(code, message)`` for the first atom the checker must not decide, else None.

    The encoder and the evaluator agree exactly on well-typed atoms (formal semantics
    T-Eq/T-Neq/T-Cmp/T-TVarEq). An ill-typed atom, an unknown identifier, or an atom over an
    unresolved registry domain has no sound truth value to give either backend: fixing it to
    false made its negation false too (e.g. ``not (ghost == 1)`` reported UNSAT), so the
    module is reported undecided instead.
    """
    for expr in expressions:
        for clause in expr.expanded_clauses:
            for cond in clause:
                problem = _atom_problem(cond, domains)
                if problem is not None:
                    code, why = problem
                    return code, (
                        "Structural satisfiability could not be decided: atom "
                        f"'{cond.ident} {cond.operator} {cond.rhs_ident if cond.rhs_ident is not None else cond.value!r}' "
                        f"in '{expr.text}' {why}."
                    )
    return None


def _atom_problem(cond: Condition, domains: Dict[str, Domain]) -> Optional[Tuple[str, str]]:
    domain = domains.get(cond.ident)
    if domain is None:
        return ILL_TYPED_CODE, f"references '{cond.ident}', which is not a declared TVAR"
    cls = _element_class(domain)
    if cls == "unresolved":
        return UNRESOLVED_DOMAIN_CODE, f"references '{cond.ident}', whose registry domain is not resolved"
    op = cond.operator
    if op not in _REIFIED_COMPARISONS:
        return ILL_TYPED_CODE, f"uses unsupported operator '{op}'"
    if cond.rhs_ident is not None:
        rhs = domains.get(cond.rhs_ident)
        if rhs is None:
            return ILL_TYPED_CODE, f"references '{cond.rhs_ident}', which is not a declared TVAR"
        rhs_cls = _element_class(rhs)
        if rhs_cls == "unresolved":
            return UNRESOLVED_DOMAIN_CODE, f"references '{cond.rhs_ident}', whose registry domain is not resolved"
        if op in _ORDERING_OPS:
            return ILL_TYPED_CODE, "orders two TVARs, which T-TVarEq does not type"
        if cls != rhs_cls and not (domain.kind == "enum" and rhs.kind == "enum"):
            return ILL_TYPED_CODE, "compares TVARs of different element types (T-TVarEq)"
        return None
    value = cond.value
    if op in _ORDERING_OPS:
        if cls != "num" or not _is_plain_number(value):
            return ILL_TYPED_CODE, "orders a non-numeric operand (T-Cmp requires int or float)"
        return None
    if cls == "num" and not _is_plain_number(value):
        return ILL_TYPED_CODE, "compares a numeric TVAR with a non-numeric literal (T-Eq/T-Neq)"
    if cls == "bool" and not isinstance(value, bool):
        return ILL_TYPED_CODE, "compares a bool TVAR with a non-bool literal (T-Eq/T-Neq)"
    return None


def _atom_key(value: Any) -> Any:
    """Hashable identity used for equality by BOTH the encoder and the evaluator.

    Numbers compare as exact rationals (never binary64), bools only equal bools, tuples
    compare component-wise by the same rule.
    """
    if isinstance(value, bool):
        return ("b", value)
    if _is_plain_number(value):
        return ("n", _num(value))
    if isinstance(value, (tuple, list)):
        return ("t", tuple(_atom_key(v) for v in value))
    if isinstance(value, str):
        return ("s", value)
    try:
        hash(value)
    except TypeError:
        return ("r", repr(value))
    return ("o", value)


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


def _exact_float(raw: str) -> float:
    return float(raw)


def _literal_exact(raw: Any, value: Any) -> Optional[Fraction]:
    """Exact rational of a numeric literal, read from its SOURCE TEXT (never from binary64)."""
    if not _is_plain_number(value):
        return None
    if isinstance(raw, str):
        try:
            return bounded_fraction(raw.strip())
        except ExactLiteralLimitError as exc:
            raise StructuralParseError(f"numeric literal out of bounds: {exc}") from exc
        except (ValueError, ZeroDivisionError):
            pass
    key = _num(value)
    return key if isinstance(key, Fraction) else None


def _value_condition(ident: str, operator: str, token_type: Optional[str], raw: Any) -> "Condition":
    value = _convert_literal_value(token_type, raw)
    return Condition(ident, operator, value, exact=_literal_exact(raw, value))


def _convert_number_token(raw: str) -> Any:
    if "." in raw or "e" in raw.lower():
        return _exact_float(raw)
    try:
        return int(raw)
    except ValueError:
        return _exact_float(raw)


def _convert_untyped_literal(raw: str) -> Any:
    if raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    try:
        if "." in raw or "e" in raw.lower():
            return _exact_float(raw)
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
    """``int``/``float``/:class:`ExactNumber` for a numeric element, else ``_NOT_A_NUMBER``.

    A float component keeps its exact source value, as scalar literals do: the rational is
    read from the literal TEXT by :func:`bounded_fraction` (never from binary64). When the
    float denotes it exactly the float is returned; otherwise an :class:`ExactNumber` (a
    ``Fraction``, not a ``float``), so :func:`_atom_key` compares ``0.100000000000000001``
    exactly against a domain member with the same lexeme instead of against binary64 ``0.1``.
    """
    try:
        if "." in stripped or "e" in stripped.lower():
            number = float(stripped)
        else:
            return int(stripped)
    except ValueError:
        return _NOT_A_NUMBER
    if not math.isfinite(number):
        return number
    try:
        exact = bounded_fraction(stripped)
    except ExactLiteralLimitError as exc:
        raise StructuralParseError(f"numeric literal out of bounds: {exc}") from exc
    except (ValueError, ZeroDivisionError):
        return number
    if Fraction(repr(number)) == exact:
        return number
    # Not a float at all: an exact rational (a Fraction), so it can never hash or compare as
    # its binary64 neighbour, in sets (fallback candidates) or anywhere else.
    return ExactNumber(exact)


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


def _literal_fanout(literal: Literal) -> int:
    """How many expanded clauses one literal turns each partial clause into (see _integrate_*)."""
    if literal.kind == "membership":
        if literal.negated:
            return 1
        return min(len(literal.values), len(literal.value_types))
    if literal.kind == "interval":
        return 2 if literal.negated else 1
    if literal.kind == "comparison":
        return 1
    return 0


def _clause_expansion_size(clause: List[Literal]) -> int:
    """Expanded clause count of one DNF clause, counted multiplicatively; stops past the limit."""
    size = 1
    for literal in clause:
        size *= _literal_fanout(literal)
        if size == 0 or size > MAX_DNF_CLAUSES:
            return size
    return size


def _expand_dnf(dnf: DNF, tvar_names: set[str]) -> List[List[Condition]]:
    """Expand membership / interval literals into conditions, within ``MAX_DNF_CLAUSES``.

    The parser bounds the DNF it builds, but ``x in {a, b}`` and ``not (lo <= x <= hi)`` each
    expand into several clauses HERE; the total is counted arithmetically BEFORE anything is
    materialised and refused with :class:`_ExpansionTooLarge` above the parser's limit.
    """
    total = 0
    for clause in dnf.clauses:
        total += _clause_expansion_size(clause)
        if total > MAX_DNF_CLAUSES:
            raise _ExpansionTooLarge(total)
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
    values = list(zip(literal.value_types, literal.values))
    if not values:
        if literal.negated:
            return clauses
        return []
    if literal.negated:
        new_clauses: List[List[Condition]] = []
        for clause in clauses:
            extended = list(clause)
            for token_type, raw in values:
                extended.append(_value_condition(literal.ident, "!=", token_type, raw))
            new_clauses.append(extended)
        return new_clauses
    new_clauses = []
    for clause in clauses:
        for token_type, raw in values:
            new_clause = list(clause)
            new_clause.append(_value_condition(literal.ident, "==", token_type, raw))
            new_clauses.append(new_clause)
    return new_clauses


def _integrate_interval(clauses: List[List[Condition]], literal: Literal) -> List[List[Condition]]:
    left, right, op1, op2 = literal.values
    new_clauses: List[List[Condition]] = []
    if literal.negated:
        # not (left op1 x op2 right)  ==  x below the lower bound  or  x above the upper bound,
        # where a strict bound ("<") excludes the endpoint, so its negation includes it.
        below = "<" if op1 == "<=" else "<="
        above = ">" if op2 == "<=" else ">="
        for clause in clauses:
            new_clauses.append(list(clause) + [_value_condition(literal.ident, below, "NUMBER", left)])
            new_clauses.append(list(clause) + [_value_condition(literal.ident, above, "NUMBER", right)])
        return new_clauses
    map_op_left = {"<=": ">=", "<": ">"}
    map_op_right = {"<=": "<=", "<": "<"}
    for clause in clauses:
        new_clause = list(clause)
        new_clause.append(_value_condition(literal.ident, map_op_left.get(op1, ">="), "NUMBER", left))
        new_clause.append(_value_condition(literal.ident, map_op_right.get(op2, "<="), "NUMBER", right))
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
    return [clause + [_value_condition(literal.ident, operator, value_type, raw)] for clause in clauses]


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
    """Encode ``ident ==/!= other_ident`` by exact value equality.

    Pairings check_structural would refuse as ill-typed never reach here from it; for direct
    callers they keep the no-match polarity: ``==`` false, ``!=`` true.
    """
    rhs_var = var_map.get(condition.rhs_ident)
    rhs_domain = domains.get(condition.rhs_ident)
    op = condition.operator
    if rhs_var is None or rhs_domain is None or op not in {"==", "!="}:
        model.Add(bool_var == 0)
    elif domain.kind == "enum" and rhs_domain.kind == "enum":
        _encode_enum_pair(model, var, domain, rhs_var, rhs_domain, op, bool_var)
    elif domain.kind == "enum" and rhs_domain.kind in _NUMERIC_KINDS and _is_numeric_enum(domain):
        pairs = _enum_grid_pairs(domain, rhs_domain)
        _encode_pairs(model, var, rhs_var, pairs, op, bool_var)
    elif rhs_domain.kind == "enum" and domain.kind in _NUMERIC_KINDS and _is_numeric_enum(rhs_domain):
        pairs = [(j, i) for i, j in _enum_grid_pairs(rhs_domain, domain)]
        _encode_pairs(model, var, rhs_var, pairs, op, bool_var)
    elif domain.kind == "bool" and rhs_domain.kind == "bool":
        _reify_comparison(model, var, op, rhs_var, bool_var)
    elif domain.kind in _NUMERIC_KINDS and rhs_domain.kind in _NUMERIC_KINDS:
        # Compare exact values origin + i*step: scale both sides by a common integer L.
        common = _common_scale(domain, rhs_domain)
        left_scaled = _scaled_linear(var, domain, common)
        right_scaled = _scaled_linear(rhs_var, rhs_domain, common)
        _reify_comparison(model, left_scaled, op, right_scaled, bool_var)
    else:
        model.Add(bool_var == (1 if op == "!=" else 0))


def _grid_of(domain: Domain) -> Tuple[Fraction, Fraction]:
    if domain.gridded:
        return domain.grid_origin, domain.grid_step
    return Fraction(0), Fraction(1)


def _common_scale(left: Domain, right: Domain) -> int:
    scale = 1
    for dom in (left, right):
        for q in _grid_of(dom):
            scale = scale * q.denominator // math.gcd(scale, q.denominator)
    return scale


def _scaled_linear(var: Any, domain: Domain, scale: int) -> Any:
    """``(origin + var * step) * scale`` as an integer linear expression."""
    origin, step = _grid_of(domain)
    coef, const = int(step * scale), int(origin * scale)
    lower, upper = _index_bounds(domain)
    if abs(coef) * max(abs(lower), abs(upper)) + abs(const) > _INT_LIMIT:
        raise _EncodingOverflow(domain.path)
    return var * coef + const


def _encode_enum_pair(
    model: cp_model.CpModel,
    var: cp_model.IntVar,
    domain: Domain,
    rhs_var: cp_model.IntVar,
    rhs_domain: Domain,
    op: str,
    bool_var: cp_model.BoolVar,
) -> None:
    """Encode equality between two enum variables: index pairs whose values are EXACTLY equal.

    Values are grouped by :func:`_atom_key` (the evaluator's equality), never by Python
    ``==``/hash on binary64 floats, so 0.1 and 0.100000000000000001 stay distinct.
    """
    left_groups: Dict[Any, List[int]] = {}
    for idx, value in enumerate(domain.values or []):
        left_groups.setdefault(_atom_key(value), []).append(idx)
    # Count the table before building it (members are deduplicated by build_structural_model,
    # but direct callers may pass raw Domains).
    rows = sum(len(left_groups.get(_atom_key(value), ())) for value in rhs_domain.values or [])
    if rows > _MAX_PAIR_TABLE:
        raise _PairTableTooLarge(domain.path, rhs_domain.path, rows)
    pairs = sorted(
        (i, j)
        for j, value in enumerate(rhs_domain.values or [])
        for i in left_groups.get(_atom_key(value), [])
    )
    _encode_pairs(model, var, rhs_var, pairs, op, bool_var)


def _enum_grid_pairs(enum_domain: Domain, num_domain: Domain) -> List[Tuple[int, int]]:
    """(enum index, numeric variable value) pairs whose values are exactly equal."""
    origin, step = _grid_of(num_domain)
    lower, upper = _index_bounds(num_domain)
    pairs: List[Tuple[int, int]] = []
    for i, member in enumerate(enum_domain.values or []):
        idx = (_num(member) - origin) / step
        if idx.denominator == 1 and lower <= idx <= upper:
            pairs.append((i, int(idx)))
    return pairs


def _encode_pairs(
    model: cp_model.CpModel,
    var: cp_model.IntVar,
    rhs_var: cp_model.IntVar,
    pairs: List[Tuple[int, int]],
    op: str,
    bool_var: cp_model.BoolVar,
) -> None:
    """``bool_var`` iff ``(var, rhs_var)`` is (``==``) / is not (``!=``) one of ``pairs``."""
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
    """Encode ``ident <op> literal`` exactly as the evaluator decides it.

    A literal that matches no domain value makes ``==`` false and ``!=`` TRUE (T-Neq types
    the literal against the element type, not against the domain's members). Unencodable
    literals (ill-typed: check_structural refuses them before encoding) keep that same
    no-match polarity for direct callers; ordering on them is false.
    """
    op = condition.operator
    if domain.kind == "enum" and op in _ORDERING_OPS and _is_numeric_enum(domain):
        _encode_enum_ordering(model, var, domain, op, condition, bool_var)
        return
    if domain.kind == "enum" and op in {"==", "!="}:
        target = _atom_key(condition.exact if condition.exact is not None else condition.value)
        matches = [i for i, member in enumerate(domain.values or []) if _atom_key(member) == target]
        _reify_membership(model, var, len(domain.values or []), matches, op, bool_var)
        return
    # Non-numeric enum ordering keeps the legacy index comparison for direct callers
    # (check_structural refuses it as ill-typed, T-Cmp).
    try:
        encoded_value = _encode_literal_value(domain, op, condition)
    except Exception:
        model.Add(bool_var == (1 if op == "!=" else 0))
        return
    if encoded_value is None:
        # Equality against a float that is off the precision grid.
        model.Add(bool_var == (0 if op == "==" else 1))
    elif op in _REIFIED_COMPARISONS:
        # Variable bounds are within +-_INT_LIMIT, so clamping preserves every comparison.
        encoded_value = max(-_INT_LIMIT - 1, min(_INT_LIMIT + 1, encoded_value))
        if domain.kind in _NUMERIC_KINDS and condition.exact is not None and op in {">", "<"}:
            # _encode_grid_literal moved a strict bound to the nearest admissible grid index
            # (floor+1 / ceil-1) of the EXACT rational index, so the comparison is non-strict.
            op = ">=" if op == ">" else "<="
        _reify_comparison(model, var, op, encoded_value, bool_var)
    else:
        model.Add(bool_var == 0)


def _reify_membership(
    model: cp_model.CpModel,
    var: cp_model.IntVar,
    size: int,
    matches: List[int],
    op: str,
    bool_var: cp_model.BoolVar,
) -> None:
    """``bool_var`` iff ``var`` is (``==``) / is not (``!=``) one of the ``matches`` indices."""
    match_set = set(matches)
    others = [i for i in range(size) if i not in match_set]
    holds, fails = (matches, others) if op == "==" else (others, matches)
    if holds:
        model.AddLinearExpressionInDomain(var, cp_model.Domain.FromValues(holds)).OnlyEnforceIf(bool_var)
    else:
        model.Add(bool_var == 0)
    if fails:
        model.AddLinearExpressionInDomain(var, cp_model.Domain.FromValues(fails)).OnlyEnforceIf(bool_var.Not())
    else:
        model.Add(bool_var == 1)


def _is_numeric_enum(domain: Domain) -> bool:
    values = list(domain.values or [])
    return bool(values) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)


def _encode_enum_ordering(
    model: cp_model.CpModel,
    var: cp_model.IntVar,
    domain: Domain,
    op: str,
    condition: "Condition",
    bool_var: cp_model.BoolVar,
) -> None:
    """T-Cmp on a numeric enum: reify membership over the indices whose VALUE satisfies ``op``.

    Values and literal compare as exact rationals. String/bool enums or a non-numeric
    literal cannot be ordered: the atom is false.
    """
    values = list(domain.values or [])
    value = condition.exact

    if value is None or not values or not all(_is_plain_number(v) for v in values):
        model.Add(bool_var == 0)
        return
    test = {
        "<": lambda a: _num(a) < value,
        "<=": lambda a: _num(a) <= value,
        ">": lambda a: _num(a) > value,
        ">=": lambda a: _num(a) >= value,
    }[op]
    allowed = [i for i, v in enumerate(values) if test(v)]
    allowed_set = set(allowed)  # built once: a per-index set(allowed) was quadratic
    others = [i for i in range(len(values)) if i not in allowed_set]
    if allowed:
        model.AddLinearExpressionInDomain(var, cp_model.Domain.FromValues(allowed)).OnlyEnforceIf(bool_var)
    else:
        model.Add(bool_var == 0)
    if others:
        model.AddLinearExpressionInDomain(var, cp_model.Domain.FromValues(others)).OnlyEnforceIf(bool_var.Not())
    else:
        model.Add(bool_var == 1)


def _encode_literal_value(domain: Domain, op: str, condition: "Condition") -> Optional[int]:
    """Encode a literal for comparison; ``None`` means an off-grid numeric equality."""
    value, exact = condition.value, condition.exact
    if domain.kind in _NUMERIC_KINDS and exact is not None:
        return _encode_grid_literal(domain, op, exact)
    return domain.encode(value)


def _encode_grid_literal(domain: Domain, op: str, exact: Fraction) -> Optional[int]:
    """Index bound for ``x <op> exact`` on an int or float grid, computed exactly.

    Floats use the Definition 3.6 grid (or the legacy origin-0 / step-1/precision grid), ints
    the unit grid; both go through the rational index (exact - origin) / step, so ceil/floor
    never see binary64 rounding and an int TVAR compares exactly against ``2.5``.
    """
    origin, step = _grid_of(domain)
    idx = (exact - origin) / step
    if op in {"==", "!="}:
        # Exact: an off-grid value equals no grid point.
        return int(idx) if idx.denominator == 1 else None
    if op == ">=":
        return math.ceil(idx)
    if op == ">":
        return math.floor(idx) + 1
    if op == "<=":
        return math.floor(idx)
    if op == "<":
        return math.ceil(idx) - 1
    raise ValueError(f"{domain.path}: unsupported operator {op!r}")


def _undecided_without_solver() -> "UndecidedStructuralResult":
    return _undecided(UNDECIDED_WITHOUT_SOLVER_CODE, UNDECIDED_WITHOUT_SOLVER_MESSAGE)


class _SearchBudgetExceeded(Exception):
    """The fallback search evaluated its whole budget of complete assignments."""


class _SearchBudget:
    def __init__(self, leaves: int) -> None:
        self.remaining = leaves

    def spend(self) -> None:
        if self.remaining <= 0:
            raise _SearchBudgetExceeded()
        self.remaining -= 1


def _check_structural_bruteforce(domains: Dict[str, Domain], expressions: List[Expression]) -> StructuralResult:
    candidates = _candidate_values(domains, expressions)
    full_grids = _widen_to_full_grids(domains, candidates)
    order = sorted(candidates.keys(), key=lambda name: len(candidates[name]))
    assignment: Dict[str, Any] = {}

    try:
        solution = _search_assignment(
            order, candidates, expressions, assignment, 0, _SearchBudget(_MAX_FALLBACK_PRODUCT)
        )
    except _SearchBudgetExceeded:
        # The product of the candidate lists (2**n for n Booleans) is past the budget and no
        # witness turned up before it ran out: neither SAT nor UNSAT has been shown.
        return _undecided_without_solver()
    if solution is not None:
        return _sat_result(expressions, solution, domains)

    # No witness found. A sampled search only proves UNSAT when every domain was
    # enumerated completely; otherwise fail closed with an explicit undecided result.
    if not _candidates_are_exhaustive(domains, candidates, full_grids):
        return _undecided_without_solver()

    core = _approximate_unsat_core(domains, expressions, candidates)
    return StructuralResult(ok=False, assignment=None, unsat_core=core)


def _candidates_are_exhaustive(
    domains: Dict[str, Domain], candidates: Dict[str, List[Any]], full_grids: Optional[set] = None
) -> bool:
    """True only if every searched variable's candidate list is its entire finite domain."""
    for name, cand in candidates.items():
        domain = domains.get(name)
        if domain is None:
            return False
        if domain.kind in ("bool", "enum"):
            continue
        if domain.kind == "int" and not domain.gridded and domain.minimum is not None and domain.maximum is not None:
            # Arithmetic check (never materialise the range): the candidates are distinct,
            # lie in [min, max] (filtered by contains), so they cover it iff the counts match.
            size = int(domain.index_upper()) - int(domain.index_lower()) + 1
            if size >= 0 and len(set(cand)) == size:
                continue
        if domain.gridded and full_grids and name in full_grids:
            continue
        return False
    return True


def _candidate_values(domains: Dict[str, Domain], expressions: List[Expression]) -> Dict[str, List[Any]]:
    values: Dict[str, set] = {name: _seed_values(domain) for name, domain in domains.items()}
    _collect_condition_values(values, expressions)
    return {name: _candidate_list(domains[name], val_set) for name, val_set in values.items()}


_MAX_FULL_GRID = 2001
_MAX_FALLBACK_PRODUCT = 1_000_000


def _widen_to_full_grids(domains: Dict[str, Domain], candidates: Dict[str, List[Any]]) -> set:
    """Enumerate whole Definition 3.6 float grids (so UNSAT can be proven) when affordable."""
    grids: Dict[str, List[Any]] = {}
    for name, cand in candidates.items():
        domain = domains.get(name)
        count = domain.grid_count() if domain is not None else None
        if domain is None or count is None or count > _MAX_FULL_GRID:
            continue
        lo = int(domain.index_lower())
        grids[name] = [domain.decode_exact(i) for i in range(lo, lo + count)]
    if not grids:
        return set()
    product = 1
    for name, cand in candidates.items():
        product *= len(grids.get(name, cand)) or 1
    if product <= _MAX_FALLBACK_PRODUCT:
        candidates.update(grids)
        return set(grids)
    return set()


def _seed_values(domain: Domain) -> set:
    """Initial candidates implied by the domain declaration alone."""
    base: set = set()
    if domain.kind == "bool":
        base.update({True, False})
    elif domain.kind == "enum":
        base.update(domain.values or [])
    elif domain.kind in _NUMERIC_KINDS:
        # Exact endpoints when known (the binary64 rounding may lie outside the grid).
        for exact, approx in ((domain.exact_minimum, domain.minimum), (domain.exact_maximum, domain.maximum)):
            if exact is not None:
                base.add(exact)
            elif approx is not None:
                base.add(approx)
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
                if cond.exact is not None:
                    vals.add(cond.exact)


def _candidate_list(domain: Domain, val_set: set) -> List[Any]:
    if domain.kind == "bool":
        return [True, False]
    if domain.kind == "enum":
        return list(domain.values or [])
    if domain.kind == "int" and not domain.gridded:
        return _int_candidates(domain, val_set)
    if domain.gridded:
        return _float_candidates(domain, val_set)
    return list(val_set) if val_set else [None]


def _int_candidates(domain: Domain, val_set: set) -> List[Any]:
    valid = sorted(int(v) for v in val_set if isinstance(v, (int, float, Fraction)))
    lower, upper = domain.index_lower(), domain.index_upper()
    if lower is not None and upper is not None:
        if upper - lower <= 10:
            valid = list(range(lower, upper + 1))
    if not valid:
        valid = _fallback_candidates(domain, int)
    return sorted({v for v in valid if domain.contains(v)})


def _float_candidates(domain: Domain, val_set: set) -> List[Any]:
    """Distinct in-bounds grid points among the known values, as exact ``Fraction`` values."""
    valid = [v for v in val_set if _is_plain_number(v)]
    if not valid:
        valid = _fallback_candidates(domain, float)
    lower = domain.index_lower()
    upper = domain.index_upper()
    indices = set()
    for v in valid:
        idx = domain.grid_index(v)  # exact rational index, on both grid forms
        if idx.denominator != 1:
            continue
        i = int(idx)
        if (lower is None or i >= lower) and (upper is None or i <= upper):
            indices.add(i)
    return [domain.decode_exact(i) for i in sorted(indices)]


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
    budget: Optional["_SearchBudget"] = None,
) -> Optional[Dict[str, Any]]:
    if index == len(order):
        if budget is not None:
            budget.spend()
        if all(_evaluate_expression(expr, assignment) for expr in expressions):
            return dict(assignment)
        return None

    name = order[index]
    for value in candidates.get(name, [None]):
        assignment[name] = value
        result = _search_assignment(order, candidates, expressions, assignment, index + 1, budget)
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
    """Evaluate one atom; numeric operands always compare as exact rationals."""
    value = assignment.get(cond.ident)
    if value is None:
        return False
    if cond.rhs_ident is not None:
        target = assignment.get(cond.rhs_ident)
        if target is None:
            return False
    else:
        target = cond.exact if cond.exact is not None else cond.value
    op = cond.operator
    if op == "==":
        return _atom_key(value) == _atom_key(target)
    if op == "!=":
        return _atom_key(value) != _atom_key(target)
    if not (_is_plain_number(value) and _is_plain_number(target)):
        return False  # T-Cmp: ordering is defined on numbers only
    value, target = _num(value), _num(target)
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
