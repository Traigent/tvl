from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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
    legacy_symbols: List[str] = field(default_factory=list)


@dataclass
class OperationalModel:
    validation_options: ValidationOptions
    budget: BudgetSummary
    derived_constraints: List[DerivedConstraint]


@dataclass
class OperationalResult:
    ok: bool
    binding_budget: Optional[str]
    issues: List[Dict[str, Any]]


def build_operational_model(module: Dict[str, Any]) -> OperationalModel:
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


def check_operational(module: Dict[str, Any]) -> OperationalResult:
    model = build_operational_model(module)
    issues: List[Dict[str, Any]] = []

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


def _validate_budgets(budget: BudgetSummary) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    issues: List[Dict[str, Any]] = []
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

    if budget.max_spend_usd is not None and budget.max_spend_usd <= 0:
        binding = binding or "max_spend_usd"
        issues.append(
            {
                "code": "invalid_budget_max_spend",
                "message": "exploration.budgets.max_spend_usd must be positive",
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


def _flatten_prefixed_symbols(prefix: str, value: Any, symbol_table: Dict[str, Any]) -> None:
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
) -> Tuple[Optional[list], Optional[str], Optional[float], List[str]]:
    import ast
    import re
    # Replace single `=` with `==` to support EBNF `lin_arith_expr` syntax in Python AST
    expression = re.sub(r'(?<![=<>!])=(?![=])', '==', expression)
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError:
        return None, None, None, []

    def symbol_name(node: ast.AST) -> Tuple[Optional[str], bool]:
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

    def walk_expr(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return [(float(node.value), None)], []
        elif isinstance(node, (ast.Name, ast.Attribute)):
            name, legacy = symbol_name(node)
            if name is None:
                return None
            return [(1.0, name)], [name] if legacy else []
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            sign = -1.0 if isinstance(node.op, ast.USub) else 1.0
            child = walk_expr(node.operand)
            if child is None:
                return None
            child_terms, legacy_symbols = child
            return [(sign * c, s) for c, s in child_terms], legacy_symbols
        elif isinstance(node, ast.BinOp):
            if isinstance(node.op, (ast.Add, ast.Sub)):
                left = walk_expr(node.left)
                right = walk_expr(node.right)
                if left is None or right is None:
                    return None
                left_terms, left_legacy = left
                right_terms, right_legacy = right
                sign = -1.0 if isinstance(node.op, ast.Sub) else 1.0
                return left_terms + [(sign * c, s) for c, s in right_terms], left_legacy + right_legacy
            elif isinstance(node.op, ast.Mult):
                if isinstance(node.left, ast.Constant) and isinstance(node.left.value, (int, float)):
                    name, legacy = symbol_name(node.right)
                    if name is not None:
                        return [(float(node.left.value), name)], [name] if legacy else []
                if isinstance(node.right, ast.Constant) and isinstance(node.right.value, (int, float)):
                    name, legacy = symbol_name(node.left)
                    if name is not None:
                        return [(float(node.right.value), name)], [name] if legacy else []
                if (
                    isinstance(node.left, ast.UnaryOp)
                    and isinstance(node.left.op, ast.USub)
                    and isinstance(node.left.operand, ast.Constant)
                    and isinstance(node.left.operand.value, (int, float))
                ):
                    name, legacy = symbol_name(node.right)
                    if name is not None:
                        return [(-float(node.left.operand.value), name)], [name] if legacy else []
        return None

    if not isinstance(tree.body, ast.Compare) or len(tree.body.ops) != 1:
        return None, None, None, []
    op_node = tree.body.ops[0]
    op_map = {ast.LtE: '<=', ast.GtE: '>=', ast.Lt: '<', ast.Gt: '>', ast.Eq: '=='}
    if type(op_node) not in op_map:
        return None, None, None, []
    op = op_map[type(op_node)]

    comp = tree.body.comparators[0]
    if isinstance(comp, ast.UnaryOp) and isinstance(comp.op, ast.USub) and isinstance(comp.operand, ast.Constant):
        val = -float(comp.operand.value)
    elif isinstance(comp, ast.Constant) and isinstance(comp.value, (int, float)):
        val = float(comp.value)
    else:
        return None, None, None, []

    walked = walk_expr(tree.body.left)
    if walked is None:
        return None, None, None, []
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
    module: Dict[str, Any], constraints: List[DerivedConstraint]
) -> Tuple[List[Dict[str, Any]], bool]:
    environment = module.get("environment") or {}
    symbol_table: Dict[str, Any] = {}
    issues: List[Dict[str, Any]] = []
    has_error = False

    if not constraints:
        return issues, has_error

    context = environment.get("context")
    if isinstance(context, dict):
        _flatten_prefixed_symbols("env.context", context, symbol_table)

    for idx, derived in enumerate(constraints):
        path = ["constraints", "derived", idx, "require"]
        expression = derived.expression
        if "env.bindings." in expression:
            has_error = True
            issues.append(
                {
                    "code": "derived_references_bindings",
                    "message": "Operational preconditions must not reference environment.bindings. Bindings are opaque deployment references, not numeric operational symbols.",
                    "path": path,
                    "severity": "error",
                }
            )
            continue
        if derived.legacy_symbols:
            has_error = True
            issues.append(
                {
                    "code": "derived_invalid_symbol_reference",
                    "message": (
                        "Operational preconditions may reference only env.context.* symbols. "
                        f"Found bare symbol(s): {', '.join(derived.legacy_symbols)}."
                    ),
                    "path": path,
                    "severity": "error",
                }
            )
            continue
        if derived.symbol is None or derived.operator is None or derived.value is None:
            has_error = True
            issues.append(
                {
                    "code": "unsupported_derived_expression",
                    "message": f"Derived constraint '{derived.expression}' must be of the form symbol OP value where OP is <=, >=, <, >, or =",
                    "path": path,
                    "severity": "error",
                }
            )
            continue

        total_value = 0.0
        missing = []
        non_numeric = []
        for coeff, sym in derived.symbol:
            if not sym.startswith("env.context."):
                has_error = True
                issues.append({
                    "code": "derived_invalid_symbol_reference",
                    "message": f"Operational preconditions may reference only env.context.* symbols; found '{sym}'",
                    "path": path,
                    "severity": "error",
                })
                non_numeric = []
                missing = []
                total_value = 0.0
                break
            sym_val = symbol_table.get(sym)
            if sym_val is None:
                missing.append(sym)
                continue
            try:
                total_value += coeff * float(sym_val)
            except (TypeError, ValueError):
                non_numeric.append(sym)

        if any(issue["path"] == path and issue["code"] == "derived_invalid_symbol_reference" for issue in issues):
            continue

        if missing:
            has_error = True
            issues.append({
                "code": "unknown_derived_symbol",
                "message": f"Derived constraint references unknown environment symbol(s): {', '.join(missing)}",
                "path": path,
                "severity": "error",
            })
            continue
            
        if non_numeric:
            has_error = True
            issues.append({
                "code": "non_numeric_derived_symbol",
                "message": f"Environment symbol(s) '{', '.join(non_numeric)}' must be numeric",
                "path": path,
                "severity": "error",
            })
            continue
            
        numeric_value = total_value

        op = derived.operator
        val = derived.value
        violated = False
        if op == "<=" and numeric_value > val: violated = True
        elif op == ">=" and numeric_value < val: violated = True
        elif op == "<" and numeric_value >= val: violated = True
        elif op == ">" and numeric_value <= val: violated = True
        elif op in ("==", "=") and numeric_value != val: violated = True
        
        if violated:
            has_error = True
            issues.append(
                {
                    "code": "derived_constraint_violation",
                    "message": f"{derived.symbol}={numeric_value} violates constraint {op} {val}",
                    "path": path,
                    "severity": "error",
                }
            )

    return issues, has_error
