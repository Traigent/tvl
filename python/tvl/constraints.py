from __future__ import annotations

import math
import operator
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Dict, List, Optional, Sequence

try:  # pragma: no cover - optional dependency
    from ortools.sat.python import cp_model  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback path
    cp_model = None  # type: ignore

from .model import Domain, _exact, exact_number_or_none, extract_domains, flatten_assignments


_OR_SPLIT = re.compile(r"\s+or\s+", re.IGNORECASE)
_AND_SPLIT = re.compile(r"\s+and\s+", re.IGNORECASE)

# Normative TVAR identifier per spec/grammar/tvl.ebnf:252 and
# spec/grammar/tvl.schema.json:243 — must start with a letter/underscore and
# may only contain [A-Za-z0-9_], dotted-path separated. NO leading digit/'.'/'-'
# and NO mid-ident hyphen (issue #51). Group 1 of _LITERAL_RE is tightened to
# this pattern so config-validate agrees with structural_parser and the grammar.
_IDENT_PATTERN = r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
_IDENT_RE = re.compile(rf"^{_IDENT_PATTERN}$")
# Operator alternation lists '==' before '=' so 'a == 1' matches the two-char
# equality operator instead of the parser matching a bare '=' and leaving a
# residual '= 1' in the value (issue #37). Group 1 stays _IDENT_PATTERN — the
# #51 hardening — this only widens the *operator* set, never the identifier
# set; a hyphenated/illegal identifier is rejected before the operator is
# even considered (see test_hardened_identifier_regex_* in
# tests/test_constraints_fail_open_regression.py).
_LITERAL_RE = re.compile(rf"^\s*({_IDENT_PATTERN})\s*(<=|>=|!=|==|=|<|>)\s*(.+?)\s*$")
# Permissive lexer retained only to produce a precise "illegal identifier"
# diagnostic when the strict pattern rejects an atom that the old regex accepted.
_PERMISSIVE_LITERAL_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(<=|>=|!=|==|=|<|>)\s*(.+?)\s*$")
_COMPARISON_OP_RE = re.compile(r"(<=|>=|!=|==|=|<|>)")

_TRUE_COUNTER = 0


class ConstraintParseError(ValueError):
    """A constraint literal/expression could not be parsed (fail-closed).

    Carries a machine-readable ``code`` so ``compile_constraints`` can surface it
    as a validation issue instead of crashing the CLI or silently swallowing the
    unenforced constraint (issues #49/#51).
    """

    def __init__(self, message: str, code: str = "constraint_parse_error", text: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.text = text


@dataclass
class Atom:
    path: str
    op: str
    value: Any
    # ``x = y`` / ``x != y`` between two TVARs (T-TVarEq): the right-hand TVAR path; ``value`` is unused.
    rhs_path: Optional[str] = None
    # Exact rational of a numeric literal, from its source text; comparisons use it, never the
    # binary64 ``value`` (semantics: numeric atoms are exact).
    exact: Optional[Fraction] = field(default=None, compare=False)


@dataclass
class StructuralConstraint:
    antecedent: List[List[Atom]]  # DNF (antecedent == [[]] → True)
    consequent: List[List[Atom]]  # DNF
    raw: Any


@dataclass
class CompiledConstraints:
    domains: Dict[str, Domain]
    constraints: List[StructuralConstraint]
    # Constraints that could not be parsed (unsupported/illegal construct). Kept
    # as issues so callers fail *closed* — an unparseable constraint must not be
    # silently dropped (which would be fail-open, issues #49/#51).
    parse_issues: List[Dict[str, Any]] = field(default_factory=list)


def _split_top_level_implication(text: str) -> Optional[tuple[str, str]]:
    """Split ``A => B`` on the first top-level ``=>`` (paren-balanced, outside
    quotes). Returns ``None`` when there is no top-level implication.

    This lets an ``expr`` form carry the ``=>`` sugar (tvl.ebnf:216) and have its
    consequent actually enforced, instead of the whole ``=>`` clause being
    swallowed into a single atom's value (issue #49)."""
    depth = 0
    quote: Optional[str] = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and text.startswith("=>", i):
            return text[:i], text[i + 2:]
        i += 1
    return None


def compile_constraints(module: Dict[str, Any]) -> CompiledConstraints:
    domains = extract_domains(module.get("tvars", {}))
    tvar_names = frozenset(domains)

    constraints_section = module.get("constraints", {}) or {}
    structural = constraints_section.get("structural") or []

    compiled: List[StructuralConstraint] = []
    parse_issues: List[Dict[str, Any]] = []
    for idx, entry in enumerate(structural):
        try:
            if not isinstance(entry, dict):
                raise ConstraintParseError(
                    f"Structural constraint at index {idx} must be an object, got {entry!r}",
                    code="malformed_structural_constraint",
                    text=repr(entry),
                )
            when_expr = entry.get("when")
            then_expr = entry.get("then")
            expr_expr = entry.get("expr")
            extra_keys = set(entry.keys()) - {"when", "then", "expr"}
            has_when_then = when_expr is not None and then_expr is not None
            has_expr = expr_expr is not None
            # Mirror the grammar's oneOf({when,then} | {expr}) + additionalProperties:
            # false (spec/grammar/tvl.schema.json, constraints.structural items): an
            # entry that is missing one side of when/then, carries both when/then AND
            # expr, has neither shape, or has an unrecognised key must be rejected
            # loudly instead of silently compiling to zero constraints (issue #15).
            if extra_keys or has_when_then == has_expr:
                raise ConstraintParseError(
                    f"Structural constraint at index {idx} does not match the required "
                    f"{{when, then}} or {{expr}} shape (extra keys: {sorted(extra_keys)!r}): {entry!r}",
                    code="malformed_structural_constraint",
                    text=repr(entry),
                )
            if has_when_then:
                antecedent = parse_expression(when_expr, tvar_names)
                consequent = parse_expression(then_expr, tvar_names)
                compiled.append(StructuralConstraint(antecedent=antecedent, consequent=consequent, raw=entry))
            elif has_expr:
                split = _split_top_level_implication(expr_expr) if isinstance(expr_expr, str) else None
                if split is not None:
                    ante_str, cons_str = split
                    if not ante_str.strip() or not cons_str.strip():
                        # Grammar-invalid: '=>' requires a non-empty antecedent and
                        # consequent (tvl.ebnf:216). Without this, a truncated
                        # 'x = 1 =>' silently compiled to a vacuous-true or
                        # unconditional constraint instead of being rejected —
                        # the exact fail-open class this PR closes (#49/#51).
                        raise ConstraintParseError(
                            f"Malformed implication (empty antecedent/consequent): {expr_expr!r}",
                            code="malformed_implication",
                            text=expr_expr,
                        )
                    antecedent = parse_expression(ante_str, tvar_names)
                    consequent = parse_expression(cons_str, tvar_names)
                    compiled.append(StructuralConstraint(antecedent=antecedent, consequent=consequent, raw=entry))
                else:
                    consequent = parse_expression(expr_expr, tvar_names)
                    compiled.append(StructuralConstraint(antecedent=[[]], consequent=consequent, raw=entry))
        except ConstraintParseError as err:
            parse_issues.append({
                "code": err.code,
                "message": str(err),
                "raw": entry,
                "constraint_index": idx,
            })

    return CompiledConstraints(domains=domains, constraints=compiled, parse_issues=parse_issues)


def parse_expression(expr: Any, tvar_names: frozenset = frozenset()) -> List[List[Atom]]:
    if expr is None:
        return [[]]
    if isinstance(expr, list):
        return _parse_expression_list(expr, tvar_names)
    if not isinstance(expr, str):
        raise ValueError(f"Expression must be a string; got {expr!r}")

    text = expr.strip()
    if not text:
        # Grammar-invalid: 'formula' requires at least one atom (tvl.ebnf).
        # Silently mapping an empty/whitespace formula to [[]] (vacuous truth)
        # would void a schema-valid 'when'/'then'/'expr': "" with no diagnostic —
        # the same silent-void class this PR closes for #49/#51. The only
        # callers of this function are compile_constraints (this module) and
        # its own list recursion above; neither relies on empty-string->[[]].
        raise ConstraintParseError(
            "Empty or whitespace-only formula is not a valid constraint expression",
            code="empty_formula",
            text=expr,
        )

    try:
        disjuncts: List[List[Atom]] = []
        for disj in _OR_SPLIT.split(text):
            disj = disj.strip()
            if not disj:
                continue
            disjuncts.append(_parse_conjunction(disj, tvar_names))
    except ConstraintParseError as err:
        if err.code not in _GRAMMAR_FALLBACK_CODES:
            raise
        # A grammar-valid construct the flat regex parser cannot represent (chained
        # comparison, ``not``, ``in {...}``, parentheses): parse it with the structural parser
        # the linter and the checker use, then reduce it to the same flat atoms.
        return _parse_with_structural_parser(text, err, tvar_names)

    return disjuncts or [[]]


# Codes of the regex parser that mean "construct not representable", not "illegal text".
_GRAMMAR_FALLBACK_CODES = frozenset(
    {"unsupported_negation", "unsupported_interval", "constraint_parse_error", "illegal_ident"}
)


def _parse_with_structural_parser(
    text: str, original: "ConstraintParseError", tvar_names: frozenset = frozenset()
) -> List[List[Atom]]:
    from .structural_parser import StructuralParseError, parse_expression as parse_structural
    from .structural_sat import _expand_dnf

    try:
        conditions = _expand_dnf(parse_structural(text), set(tvar_names))
    except (StructuralParseError, ValueError):
        raise original from None
    if not conditions:
        # No clause at all (an empty ``in {}``): not representable, and never vacuously true.
        raise original
    disjuncts: List[List[Atom]] = []
    for clause in conditions:
        atoms: List[Atom] = []
        for cond in clause:
            atoms.append(
                Atom(path=cond.ident, op=cond.operator, value=cond.value, rhs_path=cond.rhs_ident, exact=cond.exact)
            )
        disjuncts.append(atoms)
    return disjuncts


def _parse_expression_list(expr: List[Any], tvar_names: frozenset = frozenset()) -> List[List[Atom]]:
    disjuncts: List[List[Atom]] = []
    for item in expr:
        disjuncts.extend(parse_expression(item, tvar_names))
    return disjuncts or [[]]


def _parse_conjunction(disj: str, tvar_names: frozenset = frozenset()) -> List[Atom]:
    atoms: List[Atom] = []
    for literal in _AND_SPLIT.split(disj):
        literal = literal.strip()
        if not literal:
            continue
        atoms.append(_parse_literal(literal, tvar_names))
    return atoms


def _parse_literal(text: str, tvar_names: frozenset = frozenset()) -> Atom:
    # Fail closed on valid-grammar constructs the regex parser cannot represent
    # as a single flat Atom (issue #49). The structural_parser tokenizer handles
    # these; here we reject them with a diagnostic rather than mis-parse/swallow.
    # Use the quote/depth-aware splitter (not a naive substring test) so a
    # quoted value containing '=>' (e.g. mode = "a=>b") isn't mistaken for an
    # inline implication.
    if _split_top_level_implication(text) is not None:
        raise ConstraintParseError(
            f"Inline implication '=>' is not supported in this position: {text!r}; "
            "use a when/then constraint or a top-level expr.",
            code="unsupported_implication",
            text=text,
        )
    stripped = text.lstrip()
    if stripped.lower() == "not" or stripped[:4].lower() == "not ":
        raise ConstraintParseError(
            f"Negation ('not') is not supported by config-validate: {text!r}",
            code="unsupported_negation",
            text=text,
        )

    match = _LITERAL_RE.match(text)
    if not match:
        # Distinguish an illegal identifier (accepted by the old permissive regex,
        # forbidden by the normative grammar — issue #51) from generic garbage.
        permissive = _PERMISSIVE_LITERAL_RE.match(text)
        if permissive is not None:
            raise ConstraintParseError(
                f"Illegal identifier {permissive.group(1)!r} in constraint literal "
                f"{text!r}; identifiers must match {_IDENT_PATTERN}.",
                code="illegal_ident",
                text=text,
            )
        raise ConstraintParseError(f"Could not parse constraint literal: {text!r}", text=text)

    path, op, value_raw = match.groups()
    value_raw = value_raw.strip()
    # A residual comparison operator in an unquoted value means a compound/interval
    # atom (e.g. ``a <= t <= b``) the flat Atom model cannot represent (issue #49).
    if value_raw[:1] not in {'"', "'"} and _COMPARISON_OP_RE.search(value_raw):
        raise ConstraintParseError(
            f"Unsupported compound/interval atom: {text!r}",
            code="unsupported_interval",
            text=text,
        )
    canonical_op = "==" if op == "=" else op
    if canonical_op in ("==", "!=") and value_raw in tvar_names:
        return Atom(path=path, op=canonical_op, value=None, rhs_path=value_raw)  # T-TVarEq
    value = _parse_value(value_raw)
    exact = None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        exact = exact_number_or_none(value_raw)
    return Atom(path=path, op=canonical_op, value=value, exact=exact)


def _parse_value(token: str) -> Any:
    if not token:
        return token

    if token[0] in {'"', "'"} and token[-1] == token[0]:
        return token[1:-1]

    lowered = token.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"

    try:
        if "." in token or "e" in token.lower():
            return float(token)
        return int(token)
    except ValueError:
        pass

    return token


def check_structural_satisfiable(compiled: CompiledConstraints) -> Dict[str, Any]:
    if cp_model is None:
        raise RuntimeError(
            "OR-Tools is required for structural satisfiability checking. "
            "Install with: pip install ortools"
        )
    model = cp_model.CpModel()
    var_map: Dict[str, cp_model.IntVar] = {}

    for path, domain in compiled.domains.items():
        var_map[path] = _create_variable(model, domain)

    for idx, constraint in enumerate(compiled.constraints):
        _add_implication_clauses(model, var_map, compiled.domains, idx, constraint)

    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        assignment = {
            path: compiled.domains[path].decode(int(solver.Value(var)))
            for path, var in var_map.items()
        }
        return {"ok": True, "assignment": assignment}

    return {"ok": False, "assignment": None}


def _add_implication_clauses(
    model: cp_model.CpModel,
    var_map: Dict[str, cp_model.IntVar],
    domains: Dict[str, Domain],
    idx: int,
    constraint: StructuralConstraint,
) -> None:
    """Add ``antecedent -> consequent`` as one clause per antecedent disjunct."""
    antecedent_conjs = constraint.antecedent or [[]]
    consequent_conjs = constraint.consequent or [[]]

    for conj_idx, antecedent_atoms in enumerate(antecedent_conjs):
        cond_literals = [_atom_literal(model, var_map, domains, atom) for atom in antecedent_atoms]

        effect_literals: List[cp_model.BoolVar] = []
        for eff_idx, effect_atoms in enumerate(consequent_conjs):
            lit = _conjunction_literal(model, [_atom_literal(model, var_map, domains, atom) for atom in effect_atoms], name=f"cons_{idx}_{conj_idx}_{eff_idx}")
            effect_literals.append(lit)

        if not effect_literals:
            effect_literals.append(_true_literal(model))

        clause = effect_literals + [lit.Not() for lit in cond_literals]
        model.AddBoolOr(clause)


def evaluate_assignment(compiled: CompiledConstraints, assignments: Dict[str, Any]) -> Dict[str, Any]:
    flat = flatten_assignments(assignments)
    domain_issues = _assignment_domain_issues(compiled.domains, flat)

    # Fail closed on constraint atoms that reference an illegal (#51) or
    # undeclared (#52) TVAR path. Without this, _atom_true silently returns
    # False for such a path, voiding the guard with no diagnostic (fail-open);
    # the SAT sibling (_atom_literal) already raises "Unknown TVAR in constraint".
    domain_issues.extend(_constraint_reference_issues(compiled))

    constraint_issues: List[Dict[str, Any]] = []
    for idx, constraint in enumerate(compiled.constraints):
        if not _constraint_holds(constraint, flat):
            constraint_issues.append({"code": "constraint_failed", "constraint_index": idx, "raw": constraint.raw})

    return {"domains": domain_issues, "constraints": constraint_issues}


def _assignment_domain_issues(domains: Dict[str, Domain], flat: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for path, domain in domains.items():
        if path not in flat:
            issues.append({"code": "missing_assignment", "path": path, "message": "Missing assignment"})
            continue
        value = flat[path]
        if not domain.contains(value):
            issues.append({"code": "domain_violation", "path": path, "message": f"Value {value!r} outside domain"})
    return issues


def _constraint_atoms(constraint: StructuralConstraint):
    for clause_dnf in (constraint.antecedent, constraint.consequent):
        for conj in clause_dnf:
            yield from conj


def _constraint_reference_issues(compiled: CompiledConstraints) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    seen_paths: set[str] = set()
    for constraint in compiled.constraints:
        for atom in _constraint_atoms(constraint):
            for ref in (atom.path, atom.rhs_path):
                if ref is not None:
                    _check_reference(ref, compiled, seen_paths, issues)
    return issues


def _check_reference(ref: str, compiled: "CompiledConstraints", seen_paths: set, issues: List[Dict[str, Any]]) -> None:
    if ref in seen_paths:
        return
    seen_paths.add(ref)
    if not _IDENT_RE.match(ref):
        issues.append({
            "code": "illegal_ident",
            "path": ref,
            "message": f"Constraint references illegal identifier {ref!r}",
        })
    elif ref not in compiled.domains:
        issues.append({
            "code": "unknown_reference",
            "path": ref,
            "message": f"Constraint references undeclared TVAR '{ref}'",
        })


_ATOM_COMPARISONS = (
    ("==", operator.eq),
    ("!=", operator.ne),
    ("<", operator.lt),
    ("<=", operator.le),
    (">", operator.gt),
    (">=", operator.ge),
)


def _atom_true(atom: Atom, flat: Dict[str, Any]) -> bool:
    value = flat.get(atom.path)
    if value is None:
        return False
    target = atom.value
    if atom.rhs_path is not None:
        target = flat.get(atom.rhs_path)
        if target is None:
            return False
    elif (
        atom.exact is not None
        and isinstance(value, (int, float, Fraction))
        and not isinstance(value, bool)
        and not (isinstance(value, float) and value != value)
    ):
        value, target = _exact(value), atom.exact  # exact rationals, not binary64 roundings
    for op, compare in _ATOM_COMPARISONS:
        if atom.op == op:
            return compare(value, target)
    raise ValueError(f"Unsupported operator {atom.op}")


def _constraint_holds(constraint: StructuralConstraint, flat: Dict[str, Any]) -> bool:
    antecedent = constraint.antecedent or [[]]
    consequent = constraint.consequent or [[]]

    # The antecedent is a DNF (OR of conjunctions); it holds iff ANY
    # disjunct holds. It is vacuously true only when EVERY disjunct is
    # false. Short-circuiting on the first false disjunct (the previous
    # behaviour) declared the whole constraint satisfied as soon as one
    # disjunct was false — a fail-open that mirrored neither the intended
    # semantics nor the SAT encoder, which encodes (d1 ∨ d2) → C as
    # (d1 → C) ∧ (d2 → C) (issue #38).
    antecedent_true = any(
        all(_atom_true(atom, flat) for atom in cond) for cond in antecedent
    )
    if not antecedent_true:
        # antecedent false → constraint vacuously satisfied
        return True
    # antecedent holds → consequent must hold
    return any(
        all(_atom_true(atom, flat) for atom in conj) for conj in consequent
    )


def _create_variable(model: cp_model.CpModel, domain: Domain) -> cp_model.IntVar:
    name = domain.path.replace(".", "_")
    if domain.kind == "bool":
        return model.NewBoolVar(name)
    if domain.kind == "enum":
        return _create_enum_variable(model, domain, name)
    if domain.kind == "int" and not domain.gridded:
        return _create_int_variable(model, domain, name)
    if domain.gridded:
        return _create_float_variable(model, domain, name)
    raise ValueError(f"Unsupported domain type {domain.kind}")


def _create_enum_variable(model: cp_model.CpModel, domain: Domain, name: str) -> cp_model.IntVar:
    values = domain.values or []
    if not values:
        # Fallback to a binary selector
        return model.NewIntVar(0, 1, name)
    return model.NewIntVar(0, len(values) - 1, name)


def _create_int_variable(model: cp_model.CpModel, domain: Domain, name: str) -> cp_model.IntVar:
    lb = int(domain.minimum) if domain.minimum is not None else -10_000
    ub = int(domain.maximum) if domain.maximum is not None else 10_000
    return model.NewIntVar(lb, ub, name)


def _create_float_variable(model: cp_model.CpModel, domain: Domain, name: str) -> cp_model.IntVar:
    lower, upper = domain.index_lower(), domain.index_upper()  # exact endpoints when known
    lb = lower if lower is not None else -1_000_000
    ub = upper if upper is not None else 1_000_000
    return model.NewIntVar(lb, ub, name)


def _reify_index_membership(
    model: cp_model.CpModel,
    var: cp_model.IntVar,
    allowed: Sequence[int],
    num_values: int,
    lit: cp_model.BoolVar,
) -> None:
    """Constrain ``lit`` to be true iff ``var`` takes one of the ``allowed`` indices.

    Unlike the previous ``var <= max(allowed)`` encoding, this makes no
    assumption that the enum's index order matches its value order — it reifies
    membership over the exact set of satisfying indices, so it is correct for
    unsorted numeric enums (e.g. legacy dict-form tvars, which are not sorted).
    """
    allowed_set = sorted({idx for idx in allowed if 0 <= idx < num_values})
    if not allowed_set:
        model.Add(lit == 0)
        return
    if len(allowed_set) == num_values:
        model.Add(lit == 1)
        return
    member_lits = []
    for idx in allowed_set:
        member = model.NewBoolVar(f"{var.Name()}_eq_{idx}")
        model.Add(var == idx).OnlyEnforceIf(member)
        model.Add(var != idx).OnlyEnforceIf(member.Not())
        member_lits.append(member)
    # lit <=> OR(member_lits)
    model.AddBoolOr(member_lits).OnlyEnforceIf(lit)
    for member in member_lits:
        model.AddImplication(member, lit)


# Reified atom encodings: (constraint when the literal holds, constraint when it does not).
_ATOM_REIFICATIONS: Dict[str, Any] = {
    "==": (lambda var, enc: var == enc, lambda var, enc: var != enc),
    "!=": (lambda var, enc: var != enc, lambda var, enc: var == enc),
    "<": (lambda var, enc: var <= enc - 1, lambda var, enc: var >= enc),
    "<=": (lambda var, enc: var <= enc, lambda var, enc: var >= enc + 1),
    ">": (lambda var, enc: var >= enc + 1, lambda var, enc: var <= enc),
    ">=": (lambda var, enc: var >= enc, lambda var, enc: var <= enc - 1),
}

# Value comparisons used to select the enum indices satisfying an ordering atom.
_VALUE_ORDERINGS: Dict[str, Any] = {
    "<": lambda val, threshold: val < threshold,
    "<=": lambda val, threshold: val <= threshold,
    ">": lambda val, threshold: val > threshold,
    ">=": lambda val, threshold: val >= threshold,
}


def _atom_literal(
    model: cp_model.CpModel,
    var_map: Dict[str, cp_model.IntVar],
    domains: Dict[str, Domain],
    atom: Atom,
) -> cp_model.BoolVar:
    domain = domains.get(atom.path)
    if domain is None:
        raise ValueError(f"Unknown TVAR in constraint: {atom.path}")
    if atom.rhs_path is not None:
        raise ValueError(f"TVAR-to-TVAR equality is not supported by the satisfiability encoder: {atom.path}")
    var = var_map[atom.path]

    if domain.kind == "bool":
        return _bool_atom_literal(var, atom)
    if domain.kind == "enum":
        return _enum_atom_literal(model, var, domain, atom)
    return _ordered_atom_literal(model, var, domain, atom)


def _atom_literal_name(atom: Atom) -> str:
    return f"lit_{atom.path.replace('.', '_')}_{atom.op}_{atom.value}"


def _reify_atom(model: cp_model.CpModel, var: cp_model.IntVar, op: str, encoded: int, lit: cp_model.BoolVar) -> None:
    holds, fails = _ATOM_REIFICATIONS[op]
    model.Add(holds(var, encoded)).OnlyEnforceIf(lit)
    model.Add(fails(var, encoded)).OnlyEnforceIf(lit.Not())


def _bool_atom_literal(bool_var: cp_model.BoolVar, atom: Atom) -> cp_model.BoolVar:
    if atom.op == "==":
        return bool_var if bool(atom.value) else bool_var.Not()
    if atom.op == "!=":
        return bool_var.Not() if bool(atom.value) else bool_var
    raise ValueError(f"Unsupported bool operator {atom.op}")


def _enum_atom_literal(
    model: cp_model.CpModel,
    var: cp_model.IntVar,
    domain: Domain,
    atom: Atom,
) -> cp_model.BoolVar:
    values = domain.values or []
    encoded = _try_encode_enum(domain, values, atom.value)
    lit = model.NewBoolVar(_atom_literal_name(atom))

    if atom.op in ("==", "!="):
        if encoded is None:
            # A value outside the enum is never equal to the variable.
            model.Add(lit == (0 if atom.op == "==" else 1))
        else:
            _reify_atom(model, var, atom.op, encoded, lit)
        return lit

    if _is_numeric_enum(values) and atom.op in _VALUE_ORDERINGS:
        threshold = float(atom.value)
        # Compare enum VALUES against the threshold, not enum indices: the
        # index order is not guaranteed to match value order (legacy
        # dict-form tvars are stored verbatim; only list-form sorts), so we
        # collect the exact set of value-satisfying indices and reify
        # membership over it rather than assuming a contiguous index range.
        holds = _VALUE_ORDERINGS[atom.op]
        allowed = [idx for idx, val in enumerate(values) if holds(val, threshold)]
        _reify_index_membership(model, var, allowed, len(values), lit)
        return lit

    # Ordering comparison (<, <=, >, >=) on a symbolic (non-numeric) enum
    # has no defined order, so it cannot be encoded soundly. Forcing the
    # literal true (the previous behaviour) made the atom a tautology and
    # the whole clause fail open, letting violating configs pass. Reject it
    # instead — matching the fail-closed `raise` for unsupported operators
    # on ordered domains below (issue #40).
    raise ValueError(
        f"Unsupported ordering operator {atom.op!r} on symbolic enum "
        f"'{atom.path}' (enum values are not ordered)"
    )


def _try_encode_enum(domain: Domain, values: List[Any], value: Any) -> Optional[int]:
    """Index of ``value`` in the enum, or ``None`` if it is not a member."""
    if not values:
        return None
    try:
        return domain.encode(value)
    except ValueError:
        return None


def _is_numeric_enum(values: List[Any]) -> bool:
    return bool(values) and all(isinstance(v, (int, float)) for v in values)


def _ordered_atom_literal(
    model: cp_model.CpModel,
    var: cp_model.IntVar,
    domain: Domain,
    atom: Atom,
) -> cp_model.BoolVar:
    lit = model.NewBoolVar(_atom_literal_name(atom))
    if atom.op not in _ATOM_REIFICATIONS:
        raise ValueError(f"Unsupported operator {atom.op}")
    value = atom.value
    if domain.kind in ("int", "float") and isinstance(value, (int, float)) and not isinstance(value, bool):
        # A threshold need not be a domain member (Definition 3.6 grid ``origin + i*step``):
        # compare through the exact rational grid index, as structural_sat does.
        idx = (_exact(value) - domain.grid_origin) / domain.grid_step
        op = atom.op
        if op in ("==", "!="):
            if idx.denominator != 1:
                model.Add(lit == (0 if op == "==" else 1))
                return lit
            encoded = int(idx)
        elif op == ">=":
            encoded = math.ceil(idx)
        elif op == ">":
            encoded, op = math.floor(idx) + 1, ">="
        elif op == "<=":
            encoded = math.floor(idx)
        else:  # "<"
            encoded, op = math.ceil(idx) - 1, "<="
        _reify_atom(model, var, op, encoded, lit)
        return lit
    _reify_atom(model, var, atom.op, domain.encode(value), lit)
    return lit


def _conjunction_literal(model: cp_model.CpModel, literals: Sequence[cp_model.BoolVar], name: str) -> cp_model.BoolVar:
    if not literals:
        return _true_literal(model)
    if len(literals) == 1:
        return literals[0]
    conj = model.NewBoolVar(name)
    model.AddBoolAnd(literals).OnlyEnforceIf(conj)
    for lit in literals:
        model.AddImplication(conj, lit)
    return conj


def _true_literal(model: cp_model.CpModel) -> cp_model.BoolVar:
    global _TRUE_COUNTER
    _TRUE_COUNTER += 1
    lit = model.NewBoolVar(f"const_true_{_TRUE_COUNTER}")
    model.Add(lit == 1)
    return lit
