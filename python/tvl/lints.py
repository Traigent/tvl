from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .structural_parser import Literal, StructuralParseError, clause_to_string, parse_expression

Issue = Dict[str, Any]


@dataclass
class TypeInfo:
    name: str
    kind: str  # bool, int, float, enum, tuple, callable
    raw_type: str
    path: List[Any]
    domain_values: Optional[Set[Any]] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None


@dataclass
class TypeContext:
    gamma: Dict[str, TypeInfo]
    environment_symbols: Set[str]
    issues: List[Issue]
    clause_ids: Dict[Tuple[Any, ...], str]


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_IDENTIFIER_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
_NON_LINEAR_TOKENS_STRUCTURAL = {"*", "/", "^"}
_NON_LINEAR_TOKENS_DERIVED = {"/", "^"}


def lint_module(doc: Dict[str, Any], precision: int = 1000) -> List[Issue]:
    """Lint a TVL module for errors and warnings.

    Args:
        doc: The TVL module document
        precision: Float precision factor for SMT encoding (default 1000)

    Returns:
        List of issues (errors and warnings)
    """
    issues: List[Issue] = []
    _lint_duplicate_tvars(doc, issues)
    _lint_environment(doc, issues)
    context = _build_type_context(doc)
    issues.extend(context.issues)
    _lint_structural_constraints(doc, issues, context)
    _lint_derived_constraints(doc, issues, context)
    _lint_objectives(doc, issues)
    _lint_promotion_policy(doc, issues)
    _lint_exploration(doc, issues)
    # Add formal verification scope warnings
    issues.extend(check_formal_verification_scope(doc, precision))
    return issues


def _lint_environment(doc: Dict[str, Any], issues: List[Issue]) -> None:
    return


def _lint_duplicate_tvars(doc: Dict[str, Any], issues: List[Issue]) -> None:
    tvars = doc.get("tvars") or []
    seen: Dict[str, int] = {}
    if not isinstance(tvars, list):
        return

    for idx, decl in enumerate(tvars):
        if not isinstance(decl, dict):
            continue
        name = decl.get("name")
        if not isinstance(name, str):
            continue
        if name in seen:
            issues.append(
                {
                    "code": "duplicate_tvar",
                    "message": f"TVAR '{name}' is declared multiple times",
                    "path": ["tvars", idx, "name"],
                    "severity": "error",
                }
            )
        else:
            seen[name] = idx


def _build_type_context(doc: Dict[str, Any]) -> TypeContext:
    gamma: Dict[str, TypeInfo] = {}
    issues: List[Issue] = []

    tvars = doc.get("tvars") or []
    if isinstance(tvars, list):
        for idx, decl in enumerate(tvars):
            if not isinstance(decl, dict):
                continue
            name = decl.get("name")
            raw_type = decl.get("type")
            if not isinstance(name, str) or not name:
                issues.append(
                    {
                        "code": "invalid_tvar_name",
                        "message": "TVAR declarations must provide a non-empty name",
                        "path": ["tvars", idx, "name"],
                        "severity": "error",
                    }
                )
                continue
            if name in gamma:
                # duplicate already reported elsewhere; keep first definition
                continue
            if not isinstance(raw_type, str) or not raw_type.strip():
                issues.append(
                    {
                        "code": "missing_tvar_type",
                        "message": f"TVAR '{name}' must declare a type",
                        "path": ["tvars", idx, "type"],
                        "severity": "error",
                    }
                )
                continue
            normalized = _normalize_kind(raw_type)
            if normalized is None:
                issues.append(
                    {
                        "code": "unsupported_tvar_type",
                        "message": f"TVAR '{name}' has unsupported type '{raw_type}'",
                        "path": ["tvars", idx, "type"],
                        "severity": "error",
                    }
                )
                continue

            domain_spec = decl.get("domain")
            domain_values, minimum, maximum = _parse_domain(name, normalized, domain_spec, ["tvars", idx], issues)
            if domain_values is not None and len(domain_values) == 0:
                issues.append(
                    {
                        "code": "empty_domain",
                        "message": f"TVAR '{name}' domain specialises to an empty set",
                        "path": ["tvars", idx, "domain"],
                        "severity": "error",
                    }
                )
            gamma[name] = TypeInfo(
                name=name,
                kind=normalized,
                raw_type=raw_type,
                path=["tvars", idx],
                domain_values=domain_values,
                minimum=minimum,
                maximum=maximum,
            )

    environment_symbols = _collect_environment_symbols(doc.get("environment"))
    return TypeContext(
        gamma=gamma,
        environment_symbols=environment_symbols,
        issues=issues,
        clause_ids={},
    )


def _normalize_kind(raw_type: str) -> Optional[str]:
    lowered = raw_type.strip().lower()
    if lowered.startswith("enum"):
        return "enum"
    if lowered.startswith("tuple"):
        return "tuple"
    if lowered.startswith("callable"):
        return "callable"
    if lowered in {"bool", "int", "float"}:
        return lowered
    return None


def _parse_domain(
    name: str,
    kind: str,
    spec: Any,
    path: List[Any],
    issues: List[Issue],
) -> Tuple[Optional[Set[Any]], Optional[float], Optional[float]]:
    if kind == "bool":
        values: Set[Any] = {True, False}
        if spec is not None:
            parsed = _parse_collection(spec, allow_scalar=True)
            if parsed is not None:
                bool_values = set()
                for item in parsed:
                    if isinstance(item, bool):
                        bool_values.add(item)
                    elif isinstance(item, str) and item.lower() in {"true", "false"}:
                        bool_values.add(item.lower() == "true")
                    else:
                        issues.append(
                            {
                                "code": "invalid_bool_domain",
                                "message": f"Boolean TVAR '{name}' domain values must be true/false",
                                "path": path + ["domain"],
                                "severity": "error",
                            }
                        )
                if bool_values:
                    values = bool_values
        return values, None, None

    if kind in {"enum", "tuple", "callable"}:
        if isinstance(spec, dict):
            if "registry" in spec:
                # Registry-backed domains are resolved lazily at specialization time.
                return None, None, None
            if kind == "tuple" and "components" in spec:
                components = spec.get("components")
                if not isinstance(components, list) or not components:
                    issues.append(
                        {
                            "code": "invalid_tuple_domain",
                            "message": f"TVAR '{name}' tuple domain must define a non-empty 'components' list",
                            "path": path + ["domain", "components"],
                            "severity": "error",
                        }
                    )
                    return set(), None, None
                # Tuple domains are products; we don't enumerate them during linting.
                return None, None, None
        parsed = _parse_collection(spec, allow_scalar=True)
        if parsed is None:
            issues.append(
                {
                    "code": "missing_domain",
                    "message": f"TVAR '{name}' requires an explicit domain set",
                    "path": path + ["domain"],
                    "severity": "error",
                }
            )
            return set(), None, None
        return set(parsed), None, None

    if kind in {"int", "float"}:
        if spec is None:
            issues.append(
                {
                    "code": "missing_domain",
                    "message": f"TVAR '{name}' requires a domain definition (range or set)",
                    "path": path + ["domain"],
                    "severity": "error",
                }
            )
            return set(), None, None
        if isinstance(spec, dict):
            if "set" in spec:
                parsed = _parse_collection(spec["set"], allow_scalar=True)
                if parsed is None:
                    issues.append(
                        {
                            "code": "invalid_numeric_domain",
                            "message": f"TVAR '{name}' set domain must be a list of numeric literals",
                            "path": path + ["domain"],
                            "severity": "error",
                        }
                    )
                    return set(), None, None
                converted: Set[Any] = set()
                for item in parsed:
                    try:
                        converted.add(_coerce_numeric(item, kind))
                    except ValueError:
                        issues.append(
                            {
                                "code": "invalid_numeric_domain",
                                "message": f"TVAR '{name}' domain value {item!r} is not a valid {kind}",
                                "path": path + ["domain"],
                                "severity": "error",
                            }
                        )
                return converted, None, None
            if "range" in spec:
                range_vals = spec.get("range", [])
                if not isinstance(range_vals, list) or len(range_vals) != 2:
                    issues.append(
                        {
                            "code": "invalid_range_domain",
                            "message": f"TVAR '{name}' range domain must specify [min, max]",
                            "path": path + ["domain"],
                            "severity": "error",
                        }
                    )
                    return set(), None, None
                try:
                    minimum = float(range_vals[0]) if range_vals[0] is not None else None
                    maximum = float(range_vals[1]) if range_vals[1] is not None else None
                except (TypeError, ValueError):
                    issues.append(
                        {
                            "code": "invalid_range_domain",
                            "message": f"TVAR '{name}' range bounds must be numeric",
                            "path": path + ["domain"],
                            "severity": "error",
                        }
                    )
                    return set(), None, None
                if minimum is not None and maximum is not None and minimum > maximum:
                    issues.append(
                        {
                            "code": "invalid_range_domain",
                            "message": f"TVAR '{name}' range has min > max ({minimum} > {maximum})",
                            "path": path + ["domain"],
                            "severity": "error",
                        }
                    )
                if kind == "int":
                    min_val = float(minimum) if minimum is not None else None
                    max_val = float(maximum) if maximum is not None else None
                    return None, min_val, max_val
                return None, minimum, maximum
            if "registry" in spec:
                issues.append(
                    {
                        "code": "unsupported_domain_registry",
                        "message": f"TVAR '{name}' uses registry-backed domain which is not yet supported in lints",
                        "path": path + ["domain", "registry"],
                        "severity": "error",
                    }
                )
                return set(), None, None
        parsed = _parse_collection(spec, allow_scalar=True)
        if parsed is not None:
            converted = set()
            for item in parsed:
                try:
                    converted.add(_coerce_numeric(item, kind))
                except ValueError:
                    issues.append(
                        {
                            "code": "invalid_numeric_domain",
                            "message": f"TVAR '{name}' domain value {item!r} is not a valid {kind}",
                            "path": path + ["domain"],
                            "severity": "error",
                        }
                    )
            return converted, None, None
        issues.append(
            {
                "code": "invalid_numeric_domain",
                "message": f"TVAR '{name}' domain must be specified as a set or range",
                "path": path + ["domain"],
                "severity": "error",
            }
        )
        return set(), None, None

    return set(), None, None


def _collect_environment_symbols(environment: Any) -> Set[str]:
    symbols: Set[str] = set()

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, val in value.items():
                if not isinstance(key, str):
                    continue
                symbols.add(key)
                compound = f"{prefix}.{key}" if prefix else key
                symbols.add(compound)
                walk(compound, val)

    if isinstance(environment, dict):
        walk("", environment)
    return symbols


def _coerce_numeric(value: Any, kind: str) -> float | int:
    if kind == "int":
        if isinstance(value, bool):
            raise ValueError("bool not allowed")
        if isinstance(value, (int, float)) and float(value).is_integer():
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
        raise ValueError("not an int")
    if kind == "float":
        if isinstance(value, bool):
            raise ValueError("bool not allowed")
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError("not a float") from None
    raise ValueError("unsupported kind")


def _parse_collection(spec: Any, allow_scalar: bool = False) -> Optional[List[Any]]:
    if spec is None:
        return None
    if isinstance(spec, list):
        return list(spec)
    if isinstance(spec, tuple):
        return list(spec)
    if allow_scalar and not isinstance(spec, (dict, set)):
        return [spec]
    if isinstance(spec, dict) and "set" in spec:
        return _parse_collection(spec["set"], allow_scalar=allow_scalar)
    if isinstance(spec, str):
        text = spec.strip()
        if len(text) >= 2 and text[0] in "{[" and text[-1] in "}]" and text[0] != text[-1]:
            inner = text[1:-1]
            return _parse_collection(inner, allow_scalar=allow_scalar)
        if len(text) >= 2 and text[0] in "{[" and text[-1] in "}]" and text[0] == text[-1]:
            inner = text[1:-1]
            if not inner.strip():
                return []
            values: List[Any] = []
            current: List[str] = []
            in_string = False
            string_quote = ""
            for char in inner:
                if in_string:
                    current.append(char)
                    if char == string_quote:
                        in_string = False
                    continue
                if char in {"'", '"'}:
                    in_string = True
                    string_quote = char
                    current.append(char)
                    continue
                if char == ",":
                    token = "".join(current).strip()
                    if token:
                        values.append(_parse_value(token))
                    current = []
                else:
                    current.append(char)
            token = "".join(current).strip()
            if token:
                values.append(_parse_value(token))
            return values
    return None


def _parse_value(token: str) -> Any:
    token = token.strip()
    if not token:
        return token
    if token[0] in {'"', "'"} and token[-1] == token[0]:
        return token[1:-1]
    lowered = token.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if "." in token or "e" in token.lower():
            return float(token)
        return int(token)
    except ValueError:
        return token


def _convert_literal_value(token_type: Optional[str], raw: Any) -> Any:
    if token_type == "BOOLEAN" and isinstance(raw, str):
        return raw.lower() == "true"
    if token_type == "NUMBER" and isinstance(raw, str):
        return _parse_value(raw)
    if isinstance(raw, str):
        return _parse_value(raw)
    return raw


def _expr_has_non_linear(expr: Any) -> bool:
    """Check if a structural expression contains non-linear operators.

    Affine terms (coefficient * identifier, e.g. ``2*x``) are permitted
    per the EBNF ``lin_arith_expr`` production.  Only ``/`` and ``^`` are
    unconditionally non-linear; ``*`` is non-linear only when *both*
    operands are identifiers (i.e. ``x * y``).
    """
    if not isinstance(expr, str):
        return False
    # Division and exponentiation are always non-linear
    if any(token in expr for token in ("/", "^")):
        return True
    # For multiplication, check whether every occurrence is affine (number * ident)
    if "*" not in expr:
        return False
    # Pattern: optional sign/number, *, identifier  OR  identifier, *, number
    _AFFINE_MUL = re.compile(
        r'(?:^|(?<=[\s(+\-,]))'           # start or preceded by whitespace/operator
        r'(?:'
        r'[+-]?\d+(?:\.\d+)?\s*\*\s*'     # number * ...
        r'[A-Za-z_][A-Za-z0-9_.]*'         # ... identifier
        r'|'
        r'[A-Za-z_][A-Za-z0-9_.]*'         # identifier * ...
        r'\s*\*\s*[+-]?\d+(?:\.\d+)?'      # ... number
        r')'
    )
    # Strip all affine multiplications, then check if any '*' remains
    stripped = _AFFINE_MUL.sub('', expr)
    return "*" in stripped


def _lint_structural_constraints(doc: Dict[str, Any], issues: List[Issue], context: TypeContext) -> None:
    constraints = doc.get("constraints") or {}
    structural = constraints.get("structural") or []
    if not isinstance(structural, list):
        return

    for idx, clause in enumerate(structural):
        if not isinstance(clause, dict):
            continue
        for field in ("when", "then", "expr"):
            expr = clause.get(field)
            expr_path = ["constraints", "structural", idx, field]
            _check_structural_expression(expr, expr_path, context, issues)


def _check_structural_expression(expr: Any, path: List[Any], context: TypeContext, issues: List[Issue]) -> None:
    if expr is None:
        return
    if isinstance(expr, list):
        for idx, item in enumerate(expr):
            _check_structural_expression(item, path + [idx], context, issues)
        return
    if not isinstance(expr, str):
        issues.append(
            {
                "code": "invalid_constraint_expression",
                "message": "Structural constraint expressions must be strings",
                "path": path,
                "severity": "error",
            }
        )
        return

    text = expr.strip()
    if not text:
        return

    if _expr_has_non_linear(text):
        issues.append(
            {
                "code": "non_linear_structural",
                "message": "Structural constraint contains non-linear operator (*, /, ^)",
                "path": path,
                "severity": "error",
            }
        )
    try:
        dnf = parse_expression(text)
    except StructuralParseError as exc:
        issues.append(
            {
                "code": "invalid_structural_expression",
                "message": f"Unable to parse structural constraint: {exc}",
                "path": path,
                "severity": "error",
            }
        )
        return

    for clause_idx, clause in enumerate(dnf.clauses):
        clause_path = tuple(path + ["literal", clause_idx])
        clause_hash = hashlib.sha1(clause_to_string(clause).encode("utf-8")).hexdigest()[:8]
        context.clause_ids[clause_path] = f"{clause_idx}#{clause_hash}"
        for lit_idx, literal in enumerate(clause):
            literal_path = path + ["literal", clause_idx, lit_idx]
            _typecheck_literal(literal, literal_path, context, issues)


def _typecheck_literal(literal: Literal, path: List[Any], context: TypeContext, issues: List[Issue]) -> None:
    clause_id = context.clause_ids.get(tuple(path[:-1]))

    def add(issue: Issue) -> None:
        if clause_id is not None:
            issue.setdefault("clause_id", clause_id)
        issues.append(issue)

    type_info = context.gamma.get(literal.ident)
    if type_info is None:
        add(
            {
                "code": "undeclared_tvar",
                "message": f"Structural constraint references undeclared TVAR '{literal.ident}'",
                "path": path,
                "severity": "error",
            }
        )
        return

    if literal.kind == "interval":
        lower_raw, upper_raw, left_op, right_op = literal.values
        try:
            lower = float(lower_raw)
            upper = float(upper_raw)
        except ValueError:
            add(
                {
                    "code": "invalid_interval",
                    "message": f"Interval bounds must be numeric; got {lower_raw!r}, {upper_raw!r}",
                    "path": path,
                    "severity": "error",
                }
            )
            return
        if type_info.kind not in {"int", "float"}:
            add(
                {
                    "code": "constraint_operator_type_mismatch",
                    "message": f"Intervals are only valid for numeric TVARs; '{literal.ident}' is {type_info.kind}",
                    "path": path,
                    "severity": "error",
                }
            )
            return
        if left_op == "<" and type_info.kind == "int":
            add(
                {
                    "code": "unsupported_strict_interval",
                    "message": f"Strict '<' bounds are not supported for integer TVAR '{literal.ident}'",
                    "path": path,
                    "severity": "error",
                }
            )
        _check_numeric_bound(lower, type_info, path, add)
        _check_numeric_bound(upper, type_info, path, add)
        return

    if literal.kind == "membership":
        if literal.value_types:
            values = [_convert_literal_value(t, v) for t, v in zip(literal.value_types, literal.values)]
        else:
            values = [_parse_value(token) for token in literal.values]
        for value in values:
            for issue_obj in _check_value_against_type(value, type_info, path):
                add(issue_obj)
        return

    if literal.kind == "comparison":
        op = "==" if literal.operator == "=" else literal.operator
        rhs_raw = literal.values[0]
        value_type = literal.value_types[0] if literal.value_types else None
        if value_type == "IDENT":
            other = context.gamma.get(rhs_raw)
            if other is not None:
                if op not in {"==", "!=", "="}:
                    add(
                        {
                            "code": "constraint_operator_type_mismatch",
                            "message": f"Only equality is supported between TVARs; found operator '{op}'",
                            "path": path,
                            "severity": "error",
                        }
                    )
                    return
                if not _are_types_compatible(type_info, other):
                    add(
                        {
                            "code": "constraint_type_mismatch",
                            "message": f"TVAR '{literal.ident}' ({type_info.kind}) is not compatible with '{rhs_raw}' ({other.kind})",
                            "path": path,
                            "severity": "error",
                        }
                    )
                return
            if type_info.kind in {"enum", "tuple", "callable"}:
                value = rhs_raw
            else:
                add(
                    {
                        "code": "undeclared_tvar",
                        "message": f"Structural constraint references undeclared TVAR '{rhs_raw}'",
                        "path": path,
                        "severity": "error",
                    }
                )
                return
        else:
            value = _convert_literal_value(value_type, rhs_raw)
        if op in {"<", "<=", ">", ">="} and type_info.kind not in {"int", "float"}:
            add(
                {
                    "code": "constraint_operator_type_mismatch",
                    "message": f"Operator '{op}' requires numeric TVAR; '{literal.ident}' is {type_info.kind}",
                    "path": path,
                    "severity": "error",
                }
            )
            return
        if op in {"==", "!=", "="} and type_info.kind == "float" and isinstance(value, (int, float)):
            add(
                {
                    "code": "float_equality",
                    "message": f"Floating-point equality in structural constraint may be unstable (TVAR '{literal.ident}')",
                    "path": path,
                    "severity": "warning",
                }
            )
        for issue_obj in _check_value_against_type(value, type_info, path):
            add(issue_obj)
        return

    add(
        {
            "code": "unsupported_structural_literal",
            "message": "Structural literal could not be analysed",
            "path": path,
            "severity": "error",
        }
    )


def _check_numeric_bound(value: float, type_info: TypeInfo, path: List[Any], add_issue) -> None:
    if type_info.minimum is not None and value < float(type_info.minimum):
        add_issue(
            {
                "code": "constraint_value_out_of_domain",
                "message": f"Value {value} is below minimum {type_info.minimum} for TVAR '{type_info.name}'",
                "path": path,
                "severity": "error",
            }
        )
    if type_info.maximum is not None and value > float(type_info.maximum):
        add_issue(
            {
                "code": "constraint_value_out_of_domain",
                "message": f"Value {value} exceeds maximum {type_info.maximum} for TVAR '{type_info.name}'",
                "path": path,
                "severity": "error",
            }
        )


def _check_value_against_type(value: Any, type_info: TypeInfo, path: List[Any]) -> List[Issue]:
    issues: List[Issue] = []
    kind = type_info.kind
    if kind == "bool":
        if not isinstance(value, bool):
            issues.append(
                {
                    "code": "constraint_type_mismatch",
                    "message": f"Expected boolean literal for TVAR '{type_info.name}', got {value!r}",
                    "path": path,
                    "severity": "error",
                }
            )
        return issues

    if kind in {"enum", "tuple", "callable"}:
        if isinstance(value, (bool, dict, list)):
            issues.append(
                {
                    "code": "constraint_type_mismatch",
                    "message": f"Enumerated TVAR '{type_info.name}' must compare against scalar literals",
                    "path": path,
                    "severity": "error",
                }
            )
            return issues
        if type_info.domain_values and value not in type_info.domain_values:
            issues.append(
                {
                    "code": "constraint_value_out_of_domain",
                    "message": f"Value {value!r} is not in domain for TVAR '{type_info.name}'",
                    "path": path,
                    "severity": "error",
                }
            )
        return issues

    if kind in {"int", "float"}:
        try:
            numeric = _coerce_numeric(value, kind)
        except ValueError:
            issues.append(
                {
                    "code": "constraint_type_mismatch",
                    "message": f"Expected numeric literal for TVAR '{type_info.name}', got {value!r}",
                    "path": path,
                    "severity": "error",
                }
            )
            return issues
        if type_info.minimum is not None and float(numeric) < float(type_info.minimum):
            issues.append(
                {
                    "code": "constraint_value_out_of_domain",
                    "message": f"Value {numeric} is below minimum {type_info.minimum} for TVAR '{type_info.name}'",
                    "path": path,
                    "severity": "error",
                }
            )
        if type_info.maximum is not None and float(numeric) > float(type_info.maximum):
            issues.append(
                {
                    "code": "constraint_value_out_of_domain",
                    "message": f"Value {numeric} exceeds maximum {type_info.maximum} for TVAR '{type_info.name}'",
                    "path": path,
                    "severity": "error",
                }
            )
        if type_info.domain_values and numeric not in type_info.domain_values:
            issues.append(
                {
                    "code": "constraint_value_out_of_domain",
                    "message": f"Value {numeric} is not listed in domain for TVAR '{type_info.name}'",
                    "path": path,
                    "severity": "error",
                }
            )
        return issues

    return issues
def _are_types_compatible(lhs: TypeInfo, rhs: TypeInfo) -> bool:
    if lhs.kind == rhs.kind:
        return True
    if lhs.kind in {"int", "float"} and rhs.kind in {"int", "float"}:
        return True
    return False


def _lint_derived_constraints(doc: Dict[str, Any], issues: List[Issue], context: TypeContext) -> None:
    constraints = doc.get("constraints") or {}
    derived = constraints.get("derived") or []
    if not isinstance(derived, list):
        return

    gamma_names = set(context.gamma.keys())

    for idx, clause in enumerate(derived):
        if not isinstance(clause, dict):
            continue
        expr = clause.get("require")
        path = ["constraints", "derived", idx, "require"]
        if isinstance(expr, str) and any(token in expr for token in _NON_LINEAR_TOKENS_DERIVED):
            issues.append(
                {
                    "code": "non_linear_derived",
                    "message": "Derived constraint contains non-linear operator (/, ^)",
                    "path": path,
                    "severity": "error",
                }
            )
        if isinstance(expr, str):
            if "env.bindings." in expr:
                issues.append(
                    {
                        "code": "derived_references_bindings",
                        "message": "Operational preconditions must not reference environment.bindings. Bindings are opaque deployment references, not numeric operational symbols.",
                        "path": path,
                        "severity": "error",
                    }
                )
            tokens = set(_IDENTIFIER_TOKEN_RE.findall(expr))
            invalid_env_tokens = sorted(
                token for token in tokens if token.startswith("env.") and not token.startswith("env.context.")
            )
            for token in invalid_env_tokens:
                if token.startswith("env.bindings.") or token.startswith("env.components."):
                    continue
                issues.append(
                    {
                        "code": "derived_invalid_symbol_reference",
                        "message": f"Operational preconditions may reference only env.context.* symbols; found '{token}'",
                        "path": path,
                        "severity": "error",
                    }
                )
            offending = sorted(tokens & gamma_names)
            if offending:
                issues.append(
                    {
                        "code": "derived_references_tvar",
                        "message": f"Derived constraint must not reference TVARs; found {', '.join(offending)}",
                        "path": path,
                        "severity": "error",
                    }
                )
            bare_tokens = sorted(
                token for token in tokens if not token.startswith("env.") and token not in gamma_names
            )
            for token in bare_tokens:
                issues.append(
                    {
                        "code": "derived_invalid_symbol_reference",
                        "message": f"Operational preconditions may reference only env.context.* symbols; found '{token}'",
                        "path": path,
                        "severity": "error",
                    }
                )


def _lint_objectives(doc: Dict[str, Any], issues: List[Issue]) -> None:
    objectives = doc.get("objectives") or []
    if not isinstance(objectives, list):
        return
    if not objectives:
        issues.append(
            {
                "code": "empty_objectives",
                "message": "At least one objective is required",
                "path": ["objectives"],
                "severity": "error",
            }
        )
        return

    seen_names: Dict[str, int] = {}

    for idx, objective in enumerate(objectives):
        if not isinstance(objective, dict):
            continue
        name = objective.get("name", f"objective[{idx}]")
        if isinstance(name, str):
            if name in seen_names:
                issues.append(
                    {
                        "code": "duplicate_objective",
                        "message": f"Objective name '{name}' is duplicated",
                        "path": ["objectives", idx, "name"],
                        "severity": "error",
                    }
                )
            else:
                seen_names[name] = idx

        band = objective.get("band") if isinstance(objective.get("band"), dict) else None
        if not band:
            direction = objective.get("direction")
            if direction not in {"maximize", "minimize"}:
                issues.append(
                    {
                        "code": "invalid_direction",
                        "message": f"Objective '{name}' direction must be 'maximize' or 'minimize'",
                        "path": ["objectives", idx, "direction"],
                        "severity": "error",
                    }
                )
        if "epsilon" in objective:
            issues.append(
                {
                    "code": "legacy_objective_epsilon",
                    "message": f"Objective '{name}' uses legacy epsilon; move value to promotion_policy.min_effect['{name}']",
                    "path": ["objectives", idx, "epsilon"],
                    "severity": "warning",
                }
            )
        if band:
            path = ["objectives", idx, "band"]
            target = band.get("target")
            if isinstance(target, list):
                if len(target) != 2 or not all(_is_number(x) for x in target):
                    issues.append(
                        {
                            "code": "invalid_band_target",
                            "message": f"Banded objective '{name}' target must be [low, high] numbers",
                            "path": path + ["target"],
                            "severity": "error",
                        }
                    )
                else:
                    low, high = float(target[0]), float(target[1])
                    if low >= high:
                        issues.append(
                            {
                                "code": "invalid_band_bounds",
                                "message": f"Banded objective '{name}' requires low < high; got [{low}, {high}]",
                                "path": path + ["target"],
                                "severity": "error",
                            }
                        )
            elif isinstance(target, dict):
                center = target.get("center")
                tol = target.get("tol")
                if not _is_number(center) or not _is_number(tol):
                    issues.append(
                        {
                            "code": "invalid_band_center_tol",
                            "message": f"Banded objective '{name}' requires numeric center/tol",
                            "path": path + ["target"],
                            "severity": "error",
                        }
                    )
                elif float(tol) <= 0:
                    issues.append(
                        {
                            "code": "invalid_band_tolerance",
                            "message": f"Banded objective '{name}' requires tol > 0",
                            "path": path + ["target", "tol"],
                            "severity": "error",
                        }
                    )
            else:
                issues.append(
                    {
                        "code": "missing_band_target",
                        "message": f"Banded objective '{name}' must provide a target",
                        "path": path,
                        "severity": "error",
                    }
                )

            alpha = band.get("alpha")
            if not _is_number(alpha) or not (0 < float(alpha) <= 1):
                issues.append(
                    {
                        "code": "invalid_band_alpha",
                        "message": f"Banded objective '{name}' alpha must be in (0, 1]",
                        "path": path + ["alpha"],
                        "severity": "error",
                    }
                )
            test = band.get("test")
            if test is not None and test != "TOST":
                issues.append(
                    {
                        "code": "invalid_band_test",
                        "message": f"Banded objective '{name}' must use TOST",
                        "path": path + ["test"],
                        "severity": "error",
                    }
                )


def _lint_promotion_policy(doc: Dict[str, Any], issues: List[Issue]) -> None:
    policy = doc.get("promotion_policy") or {}
    if not isinstance(policy, dict):
        return

    alpha = policy.get("alpha")
    if not _is_number(alpha) or not (0 < float(alpha) < 1):
        issues.append(
            {
                "code": "invalid_alpha",
                "message": "promotion_policy.alpha must be in (0, 1)",
                "path": ["promotion_policy", "alpha"],
                "severity": "error",
            }
        )

    dominance = policy.get("dominance")
    if dominance not in {"epsilon_pareto", None}:
        issues.append(
            {
                "code": "invalid_dominance",
                "message": "promotion_policy.dominance must be 'epsilon_pareto'",
                "path": ["promotion_policy", "dominance"],
                "severity": "error",
            }
        )

    objectives = doc.get("objectives") or []
    min_effect = policy.get("min_effect") if isinstance(policy.get("min_effect"), dict) else {}

    for idx, objective in enumerate(objectives):
        if not isinstance(objective, dict):
            continue
        name = objective.get("name")
        direction = objective.get("direction")
        if isinstance(name, str) and isinstance(direction, str):
            if name not in min_effect:
                issues.append(
                    {
                        "code": "missing_min_effect",
                        "message": f"promotion_policy.min_effect missing entry for '{name}'",
                        "path": ["promotion_policy", "min_effect"],
                        "severity": "error",
                    }
                )
            else:
                value = min_effect.get(name)
                if not _is_number(value) or float(value) < 0:
                    issues.append(
                        {
                            "code": "invalid_min_effect",
                            "message": f"promotion_policy.min_effect['{name}'] must be >= 0",
                            "path": ["promotion_policy", "min_effect", name],
                            "severity": "error",
                        }
                    )

    chance_constraints = policy.get("chance_constraints") or []
    if not isinstance(chance_constraints, list):
        return

    seen_names: Dict[str, int] = {}
    for idx, entry in enumerate(chance_constraints):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        confidence = entry.get("confidence")
        threshold = entry.get("threshold")
        if isinstance(name, str):
            if name in seen_names:
                issues.append(
                    {
                        "code": "duplicate_chance_constraint",
                        "message": f"chance_constraints contains duplicate name '{name}'",
                        "path": ["promotion_policy", "chance_constraints", idx, "name"],
                        "severity": "error",
                    }
                )
            else:
                seen_names[name] = idx
        if not _is_number(threshold) or not (0 <= float(threshold) <= 1):
            issues.append(
                {
                    "code": "invalid_chance_threshold",
                    "message": "chance constraint threshold must be in [0, 1]",
                    "path": ["promotion_policy", "chance_constraints", idx, "threshold"],
                    "severity": "error",
                }
            )
        if not _is_number(confidence) or not (0 < float(confidence) < 1):
            issues.append(
                {
                    "code": "invalid_chance_confidence",
                    "message": "chance constraint confidence must be in (0, 1)",
                    "path": ["promotion_policy", "chance_constraints", idx, "confidence"],
                    "severity": "error",
                }
            )


def _lint_exploration(doc: Dict[str, Any], issues: List[Issue]) -> None:
    exploration = doc.get("exploration")
    if exploration is None:
        # exploration section is optional
        return
    if not isinstance(exploration, dict):
        return

    strategy = exploration.get("strategy")
    if not isinstance(strategy, dict) or "type" not in strategy:
        issues.append(
            {
                "code": "missing_strategy",
                "message": "exploration.strategy.type is required",
                "path": ["exploration", "strategy"],
                "severity": "error",
            }
        )

    budgets = exploration.get("budgets")
    if isinstance(budgets, dict):
        max_trials = budgets.get("max_trials")
        if max_trials is not None and (not isinstance(max_trials, int) or max_trials <= 0):
            issues.append(
                {
                    "code": "invalid_max_trials",
                    "message": "exploration.budgets.max_trials must be a positive integer",
                    "path": ["exploration", "budgets", "max_trials"],
                    "severity": "error",
                }
            )

    parallelism = exploration.get("parallelism")
    if isinstance(parallelism, dict):
        max_parallel = parallelism.get("max_parallel_trials")
        if max_parallel is not None and (not isinstance(max_parallel, int) or max_parallel <= 0):
            issues.append(
                {
                    "code": "invalid_parallelism",
                    "message": "exploration.parallelism.max_parallel_trials must be a positive integer",
                    "path": ["exploration", "parallelism", "max_parallel_trials"],
                    "severity": "error",
                }
            )

    convergence = exploration.get("convergence")
    if isinstance(convergence, dict):
        metric = convergence.get("metric")
        if metric == "hypervolume_improvement":
            threshold = convergence.get("threshold")
            window = convergence.get("window")
            if threshold is None or not _is_number(threshold) or float(threshold) <= 0:
                issues.append(
                    {
                        "code": "invalid_convergence_threshold",
                        "message": "hypervolume_improvement convergence requires threshold > 0",
                        "path": ["exploration", "convergence", "threshold"],
                        "severity": "error",
                    }
                )
            if window is None or not isinstance(window, int) or window <= 0:
                issues.append(
                    {
                        "code": "invalid_convergence_window",
                        "message": "hypervolume_improvement convergence requires window > 0",
                        "path": ["exploration", "convergence", "window"],
                        "severity": "error",
                    }
                )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# -----------------------------------------------------------------------------
# Formal Verification Warnings (W6xxx)
# -----------------------------------------------------------------------------
# These warnings indicate features outside the formally verified TVL subset.
# The module may still be valid, but formal soundness guarantees do not apply.


def check_formal_verification_scope(doc: Dict[str, Any], precision: int = 1000) -> List[Issue]:
    """Check for features outside the formally verified TVL subset.

    Returns warnings for:
    - W6001: Registry-backed domains (no formal semantics for resolve())
    - W6002: Callable types (protocol implementation not formally defined)
    - W6003: Inadequate float precision (SMT encoding may lose injectivity)

    Args:
        doc: The TVL module document
        precision: The precision factor P for float scaling (default 1000)

    Returns:
        List of warning issues
    """
    issues: List[Issue] = []

    tvars = doc.get("tvars") or []
    if not isinstance(tvars, list):
        return issues

    for idx, decl in enumerate(tvars):
        if not isinstance(decl, dict):
            continue
        name = decl.get("name")
        raw_type = decl.get("type", "")
        domain_spec = decl.get("domain")

        if not isinstance(name, str):
            continue

        # W6001: Registry-backed domains
        if isinstance(domain_spec, dict) and "registry" in domain_spec:
            issues.append({
                "code": "unverifiable_registry_domain",
                "severity": "warning",
                "message": (
                    f"TVAR '{name}' uses a registry domain, which is outside "
                    "the formally verified subset. SMT encoding soundness "
                    "(Theorem 8.1) does not apply."
                ),
                "path": ["tvars", idx, "domain", "registry"],
                "formal_property": "Registry domains have undefined resolve(E_τ, R) semantics",
            })

        # W6002: Callable types
        if isinstance(raw_type, str) and raw_type.strip().lower().startswith("callable"):
            issues.append({
                "code": "unverifiable_callable_type",
                "severity": "warning",
                "message": (
                    f"TVAR '{name}' uses a callable type, which is outside "
                    "the formally verified subset. Type safety theorems "
                    "do not apply to callable-typed TVARs."
                ),
                "path": ["tvars", idx, "type"],
                "formal_property": "'Implements protocol' is not formally defined",
            })

        # W6003: Inadequate precision for float domains
        if isinstance(raw_type, str) and raw_type.strip().lower() == "float":
            precision_issue = _check_float_precision(name, domain_spec, precision, idx)
            if precision_issue is not None:
                issues.append(precision_issue)

    return issues


def _check_float_precision(
    name: str,
    domain_spec: Any,
    precision: int,
    idx: int,
) -> Optional[Issue]:
    """Check if float domain values collide under the given precision.

    A float domain is precision-aligned iff:
        ∀v₁,v₂ ∈ domain: v₁ ≠ v₂ ⟹ scale(v₁,P) ≠ scale(v₂,P)

    where scale(v, P) = round(v × P)
    """
    if domain_spec is None:
        return None

    # Extract domain values and check resolution alignment
    result = _extract_float_domain_values(domain_spec, precision, name, idx)
    if isinstance(result, dict):
        # Early return with resolution misalignment issue
        return result

    values = result
    if len(values) < 2:
        return None

    # Check for collisions
    return _check_value_collisions(values, precision, name, idx)


def _extract_float_domain_values(
    domain_spec: Any,
    precision: int,
    name: str,
    idx: int,
) -> List[float] | Issue:
    """Extract float values from domain spec, or return issue if resolution misaligned."""
    values: List[float] = []

    if isinstance(domain_spec, list):
        return _extract_numeric_list(domain_spec)

    if not isinstance(domain_spec, dict):
        return values

    if "set" in domain_spec:
        return _extract_numeric_list(domain_spec.get("set", []))

    if "range" in domain_spec:
        return _extract_range_values(domain_spec, precision, name, idx)

    return values


def _extract_numeric_list(items: Any) -> List[float]:
    """Extract numeric values from a list."""
    values: List[float] = []
    if not isinstance(items, list):
        return values
    for v in items:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            values.append(float(v))
    return values


def _extract_range_values(
    domain_spec: Dict[str, Any],
    precision: int,
    name: str,
    idx: int,
) -> List[float] | Issue:
    """Extract values from a range domain, checking resolution alignment."""
    range_vals = domain_spec.get("range", [])
    resolution = domain_spec.get("resolution")

    if not isinstance(range_vals, list) or len(range_vals) != 2:
        return []

    try:
        low = float(range_vals[0])
        high = float(range_vals[1])
    except (TypeError, ValueError):
        return []

    if resolution is None:
        return [low, high]

    try:
        res = float(resolution)
    except (TypeError, ValueError):
        return []

    if res <= 0:
        return []

    # Check resolution alignment with precision
    issue = _check_resolution_alignment(res, precision, name, idx)
    if issue is not None:
        return issue

    # Generate values at resolution steps
    values: List[float] = []
    current = low
    while current <= high + res / 2:
        values.append(current)
        current += res
    return values


def _check_resolution_alignment(
    resolution: float,
    precision: int,
    name: str,
    idx: int,
) -> Optional[Issue]:
    """Check if resolution is aligned with precision."""
    scaled_res = resolution * precision
    if abs(scaled_res - round(scaled_res)) <= 1e-9:
        return None

    min_adequate_precision = _compute_minimum_precision(resolution)
    return {
        "code": "inadequate_precision",
        "severity": "warning",
        "message": (
            f"TVAR '{name}' has resolution {resolution} which is not "
            f"aligned to precision P={precision}. SMT encoding "
            f"soundness (Theorem 8.1) may not hold. "
            f"Minimum adequate precision: {min_adequate_precision}."
        ),
        "path": ["tvars", idx, "domain"],
        "formal_property": "Domain is not precision-aligned per Definition 8.5",
        "current_precision": precision,
        "minimum_precision": min_adequate_precision,
    }


def _check_value_collisions(
    values: List[float],
    precision: int,
    name: str,
    idx: int,
) -> Optional[Issue]:
    """Check for collisions when scaling float values to integers."""
    scaled_values: Dict[int, float] = {}
    collision: Optional[Tuple[float, float, int]] = None

    for v in values:
        scaled = int(round(v * precision))
        if scaled in scaled_values:
            existing = scaled_values[scaled]
            if abs(existing - v) > 1e-12:
                collision = (existing, v, scaled)
                break
        else:
            scaled_values[scaled] = v

    if collision is None:
        return None

    sorted_values = sorted(set(values))
    min_gap = min(b - a for a, b in zip(sorted_values, sorted_values[1:]))
    min_adequate_precision = _compute_minimum_precision(min_gap)

    return {
        "code": "inadequate_precision",
        "severity": "warning",
        "message": (
            f"TVAR '{name}' has domain values that collide under "
            f"precision P={precision}. Values {collision[0]} and "
            f"{collision[1]} both map to {collision[2]}. "
            f"SMT encoding soundness (Theorem 8.1) does not hold. "
            f"Minimum adequate precision: {min_adequate_precision}."
        ),
        "path": ["tvars", idx, "domain"],
        "formal_property": "Domain is not precision-aligned per Definition 8.5",
        "current_precision": precision,
        "minimum_precision": min_adequate_precision,
        "collision_example": {
            "value1": collision[0],
            "value2": collision[1],
            "scaled": collision[2],
        },
    }


def _compute_minimum_precision(min_gap: float) -> int:
    """Compute minimum precision P such that all distinct values map to distinct integers.

    For a minimum gap of δ between values, we need P such that:
        δ × P >= 1

    Therefore: P >= ceil(1/δ)
    """
    if min_gap <= 0:
        return 1000000  # Very high precision as fallback

    import math
    return int(math.ceil(1.0 / min_gap))
