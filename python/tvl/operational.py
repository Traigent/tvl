from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .model import ValidationOptions, extract_validation_options


@dataclass
class BudgetSummary:
    max_trials: Optional[int]
    max_spend_usd: Optional[float]
    max_wallclock_s: Optional[int]


@dataclass
class DerivedConstraint:
    expression: str
    symbol: Optional[list] = None
    operator: Optional[str] = None
    value: Optional[float] = None
    legacy_symbols: list[str] = field(default_factory=list)


@dataclass
class OperationalModel:
    validation_options: ValidationOptions
    budget: BudgetSummary
    derived_constraints: list[DerivedConstraint]


@dataclass
class OperationalResult:
    ok: bool
    binding_budget: Optional[str]
    issues: list[dict[str, Any]]


def build_operational_model(module: dict[str, Any]) -> OperationalModel:
    options = extract_validation_options(module)
    exploration = module.get("exploration") or {}
    budgets = exploration.get("budgets") or {}
    budget = BudgetSummary(
        max_trials=_safe_int(budgets.get("max_trials")),
        max_spend_usd=_safe_float(budgets.get("max_spend_usd")),
        max_wallclock_s=_safe_int(budgets.get("max_wallclock_s")),
    )

    derived_block = (module.get("constraints") or {}).get("derived") or []
    derived_constraints = []
    for entry in derived_block:
        if isinstance(entry, dict) and isinstance(entry.get("require"), str):
            symbol, operator, value, legacy_symbols = _parse_derived_expression(entry["require"])
            derived_constraints.append(
                DerivedConstraint(
                    expression=entry["require"],
                    symbol=symbol,
                    operator=operator,
                    value=value,
                    legacy_symbols=legacy_symbols,
                )
            )

    return OperationalModel(
        validation_options=options,
        budget=budget,
        derived_constraints=derived_constraints,
    )


def check_operational(module: dict[str, Any]) -> OperationalResult:
    model = build_operational_model(module)
    issues: list[dict[str, Any]] = []

    if not model.validation_options.skip_budget_checks:
        budget_issues, binding = _validate_budgets(model.budget)
        issues.extend(budget_issues)
        if binding is not None:
            return OperationalResult(ok=False, binding_budget=binding, issues=issues)

    derived_issues, has_error = _validate_derived_constraints(module, model.derived_constraints)
    issues.extend(derived_issues)
    if has_error:
        return OperationalResult(ok=False, binding_budget=None, issues=issues)

    return OperationalResult(ok=True, binding_budget=None, issues=issues)


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _validate_budgets(budget: BudgetSummary) -> tuple[list[dict[str, Any]], Optional[str]]:
    issues: list[dict[str, Any]] = []
    binding: Optional[str] = None

    if budget.max_trials is not None and budget.max_trials <= 0:
        binding = binding or "max_trials"
        issues.append(
            {
                "code": "invalid_budget_max_trials",
                "message": "exploration.budgets.max_trials must be a positive integer",
                "path": ["exploration", "budgets", "max_trials"],
                "severity": "error",
            }
        )

    if budget.max_spend_usd is not None and budget.max_spend_usd < 0:
        binding = binding or "max_spend_usd"
        issues.append(
            {
                "code": "invalid_budget_max_spend",
                "message": "exploration.budgets.max_spend_usd must be >= 0",
                "path": ["exploration", "budgets", "max_spend_usd"],
                "severity": "error",
            }
        )

    if budget.max_wallclock_s is not None and budget.max_wallclock_s <= 0:
        binding = binding or "max_wallclock_s"
        issues.append(
            {
                "code": "invalid_budget_max_wallclock",
                "message": "exploration.budgets.max_wallclock_s must be positive",
                "path": ["exploration", "budgets", "max_wallclock_s"],
                "severity": "error",
            }
        )

    return issues, binding


def _flatten_prefixed_symbols(prefix: str, value: Any, symbol_table: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                continue
            child_prefix = f"{prefix}.{key}" if prefix else key
            _flatten_prefixed_symbols(child_prefix, child, symbol_table)
        return
    symbol_table[prefix] = value


def _parse_derived_expression(
    expression: str,
) -> tuple[Optional[list], Optional[str], Optional[float], list[str]]:
    # Replace single `=` with `==` to support EBNF `lin_arith_expr` syntax in Python AST
    expression = re.sub(r'(?<![=<>!])=(?![=])', '==', expression)

    # Guard the parse itself as well as the walk below: a sufficiently deep /
    # long chained expression can blow the stack inside ast.parse() before
    # _walk_derived ever runs, not just inside its own recursion. One try
    # spanning both keeps a single graceful "unparseable" exit for either
    # failure mode.
    try:
        tree = ast.parse(expression, mode='eval')
        comparison = _derived_comparison(tree.body)
        if comparison is None:
            return None, None, None, []
        left, op, val = comparison
        walked = _walk_derived(left)
    except SyntaxError:
        return None, None, None, []
    except RecursionError:
        # Defense in depth: the depth guard should prevent this, but never
        # let stack exhaustion escape as an uncaught crash of the CLI check.
        return None, None, None, []
    if walked is None:
        return None, None, None, []
    return _fold_derived_terms(walked, op, val)


_DERIVED_OPERATORS = {ast.LtE: '<=', ast.GtE: '>=', ast.Lt: '<', ast.Gt: '>', ast.Eq: '=='}


# Depth guard: a deeply-nested / long chained expression (e.g. thousands of
# `x+x+...+x` terms) would otherwise recurse until the Python stack is
# exhausted, raising an uncaught RecursionError. Bail to the graceful
# "unparseable" path (return None) well before the real recursion limit.
_DERIVED_MAX_DEPTH = 400


def _is_numeric_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float))


def _derived_symbol_name(node: ast.AST) -> tuple[Optional[str], bool]:
    if isinstance(node, ast.Name):
        return node.id, True
    if isinstance(node, ast.Attribute):
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts)), False
    return None, False


def _scaled_symbol_term(value: Any, symbol_node: ast.AST, negate: bool = False):
    """Return ``coefficient * symbol`` as walked terms, or None if not a symbol.

    The coefficient is converted only after the symbol is recognised.
    """
    name, legacy = _derived_symbol_name(symbol_node)
    if name is None:
        return None
    coefficient = -float(value) if negate else float(value)
    return [(coefficient, name)], [name] if legacy else []


def _walk_derived(node: ast.AST, depth: int = 0):
    if depth > _DERIVED_MAX_DEPTH:
        return None
    if _is_numeric_constant(node):
        return [(float(node.value), None)], []
    if isinstance(node, (ast.Name, ast.Attribute)):
        return _scaled_symbol_term(1.0, node)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _walk_signed(node, depth)
    if isinstance(node, ast.BinOp):
        return _walk_binop(node, depth)
    return None


def _walk_signed(node: ast.UnaryOp, depth: int):
    sign = -1.0 if isinstance(node.op, ast.USub) else 1.0
    child = _walk_derived(node.operand, depth + 1)
    if child is None:
        return None
    child_terms, legacy_symbols = child
    return [(sign * c, s) for c, s in child_terms], legacy_symbols


def _walk_binop(node: ast.BinOp, depth: int):
    if isinstance(node.op, (ast.Add, ast.Sub)):
        left = _walk_derived(node.left, depth + 1)
        right = _walk_derived(node.right, depth + 1)
        if left is None or right is None:
            return None
        left_terms, left_legacy = left
        right_terms, right_legacy = right
        sign = -1.0 if isinstance(node.op, ast.Sub) else 1.0
        return left_terms + [(sign * c, s) for c, s in right_terms], left_legacy + right_legacy
    if isinstance(node.op, ast.Mult):
        return _walk_product(node)
    return None


def _walk_product(node: ast.BinOp):
    if _is_numeric_constant(node.left):
        term = _scaled_symbol_term(node.left.value, node.right)
        if term is not None:
            return term
    if _is_numeric_constant(node.right):
        term = _scaled_symbol_term(node.right.value, node.left)
        if term is not None:
            return term
    left = node.left
    if isinstance(left, ast.UnaryOp) and isinstance(left.op, ast.USub) and _is_numeric_constant(left.operand):
        return _scaled_symbol_term(left.operand.value, node.right, negate=True)
    return None


def _derived_comparison(body: ast.AST) -> Optional[tuple[ast.AST, str, float]]:
    """Split ``<linear expr> OP <number>`` into its parts, or None if unsupported."""
    if not isinstance(body, ast.Compare) or len(body.ops) != 1:
        return None
    op = _DERIVED_OPERATORS.get(type(body.ops[0]))
    if op is None:
        return None
    comp = body.comparators[0]
    if isinstance(comp, ast.UnaryOp) and isinstance(comp.op, ast.USub) and isinstance(comp.operand, ast.Constant):
        val = -float(comp.operand.value)
    elif _is_numeric_constant(comp):
        val = float(comp.value)
    else:
        return None
    return body.left, op, val


def _fold_derived_terms(walked: tuple[list, list[str]], op: str, val: float):
    terms_raw, legacy_symbols = walked
    terms = []
    for c, s in terms_raw:
        if s is None:
            val -= c
        else:
            terms.append((c, s))

    deduped_legacy = list(dict.fromkeys(legacy_symbols))
    return terms, op, val, deduped_legacy


def _validate_derived_constraints(
    module: dict[str, Any], constraints: list[DerivedConstraint]
) -> tuple[list[dict[str, Any]], bool]:
    environment = module.get("environment") or {}
    symbol_table: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []
    has_error = False

    if not constraints:
        return issues, has_error

    context = environment.get("context")
    if isinstance(context, dict):
        _flatten_prefixed_symbols("env.context", context, symbol_table)

    # Each constraint yields at most one issue, and every issue is an error.
    for idx, derived in enumerate(constraints):
        path = ["constraints", "derived", idx, "require"]
        issue = _derived_constraint_issue(derived, path, symbol_table)
        if issue is not None:
            has_error = True
            issues.append(issue)

    return issues, has_error


def _derived_error(code: str, message: str, path: list[Any]) -> dict[str, Any]:
    return {"code": code, "message": message, "path": path, "severity": "error"}


def _derived_shape_issue(derived: DerivedConstraint, path: list[Any]) -> Optional[dict[str, Any]]:
    if "env.bindings." in derived.expression:
        return _derived_error(
            "derived_references_bindings",
            "Operational preconditions must not reference environment.bindings. Bindings are opaque deployment references, not numeric operational symbols.",
            path,
        )
    if derived.legacy_symbols:
        return _derived_error(
            "derived_invalid_symbol_reference",
            (
                "Operational preconditions may reference only env.context.* symbols. "
                f"Found bare symbol(s): {', '.join(derived.legacy_symbols)}."
            ),
            path,
        )
    if derived.symbol is None or derived.operator is None or derived.value is None:
        return _derived_error(
            "unsupported_derived_expression",
            f"Derived constraint '{derived.expression}' must be of the form symbol OP value where OP is <=, >=, <, >, or =",
            path,
        )
    return None


def _sum_derived_terms(
    terms: list, symbol_table: dict[str, Any]
) -> tuple[Optional[str], float, list[str], list[str]]:
    """Sum ``coeff * env value`` over the terms.

    Returns ``(invalid_symbol, total, missing, non_numeric)``; the scan stops at
    the first symbol outside ``env.context.``.
    """
    total_value = 0.0
    missing: list[str] = []
    non_numeric: list[str] = []
    for coeff, sym in terms:
        if not sym.startswith("env.context."):
            return sym, 0.0, [], []
        sym_val = symbol_table.get(sym)
        if sym_val is None:
            missing.append(sym)
            continue
        try:
            total_value += coeff * float(sym_val)
        except (TypeError, ValueError):
            non_numeric.append(sym)
    return None, total_value, missing, non_numeric


_DERIVED_VIOLATIONS = (
    ("<=", lambda observed, bound: observed > bound),
    (">=", lambda observed, bound: observed < bound),
    ("<", lambda observed, bound: observed >= bound),
    (">", lambda observed, bound: observed <= bound),
    ("==", lambda observed, bound: observed != bound),
    ("=", lambda observed, bound: observed != bound),
)


def _derived_violated(op: Any, numeric_value: float, val: Any) -> bool:
    for name, violated in _DERIVED_VIOLATIONS:
        if op == name:
            return violated(numeric_value, val)
    return False


def _derived_constraint_issue(
    derived: DerivedConstraint, path: list[Any], symbol_table: dict[str, Any]
) -> Optional[dict[str, Any]]:
    shape_issue = _derived_shape_issue(derived, path)
    if shape_issue is not None:
        return shape_issue

    invalid_symbol, numeric_value, missing, non_numeric = _sum_derived_terms(derived.symbol, symbol_table)
    if invalid_symbol is not None:
        return _derived_error(
            "derived_invalid_symbol_reference",
            f"Operational preconditions may reference only env.context.* symbols; found '{invalid_symbol}'",
            path,
        )
    if missing:
        return _derived_error(
            "unknown_derived_symbol",
            f"Derived constraint references unknown environment symbol(s): {', '.join(missing)}",
            path,
        )
    if non_numeric:
        return _derived_error(
            "non_numeric_derived_symbol",
            f"Environment symbol(s) '{', '.join(non_numeric)}' must be numeric",
            path,
        )

    op = derived.operator
    val = derived.value
    if _derived_violated(op, numeric_value, val):
        return _derived_error(
            "derived_constraint_violation",
            f"{derived.symbol}={numeric_value} violates constraint {op} {val}",
            path,
        )
    return None
