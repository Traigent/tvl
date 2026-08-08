from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

try:  # pragma: no cover - optional dependency
    from ortools.sat.python import cp_model  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback path
    cp_model = None  # type: ignore

from .model import Domain, extract_domains, flatten_assignments


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

    constraints_section = module.get("constraints", {}) or {}
    structural = constraints_section.get("structural") or []

    compiled: List[StructuralConstraint] = []
    parse_issues: List[Dict[str, Any]] = []
    for idx, entry in enumerate(structural):
        if not isinstance(entry, dict):
            continue
        when_expr = entry.get("when")
        then_expr = entry.get("then")
        expr_expr = entry.get("expr")

        try:
            if when_expr is not None or then_expr is not None:
                antecedent = parse_expression(when_expr)
                consequent = parse_expression(then_expr)
                compiled.append(StructuralConstraint(antecedent=antecedent, consequent=consequent, raw=entry))
            elif expr_expr is not None:
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
                    antecedent = parse_expression(ante_str)
                    consequent = parse_expression(cons_str)
                    compiled.append(StructuralConstraint(antecedent=antecedent, consequent=consequent, raw=entry))
                else:
                    consequent = parse_expression(expr_expr)
                    compiled.append(StructuralConstraint(antecedent=[[]], consequent=consequent, raw=entry))
        except ConstraintParseError as err:
            parse_issues.append({
                "code": err.code,
                "message": str(err),
                "raw": entry,
                "constraint_index": idx,
            })

    return CompiledConstraints(domains=domains, constraints=compiled, parse_issues=parse_issues)


def parse_expression(expr: Any) -> List[List[Atom]]:
    if expr is None:
        return [[]]
    if isinstance(expr, list):
        disjuncts: List[List[Atom]] = []
        for item in expr:
            disjuncts.extend(parse_expression(item))
        return disjuncts or [[]]
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

    disjuncts: List[List[Atom]] = []
    for disj in _OR_SPLIT.split(text):
        disj = disj.strip()
        if not disj:
            continue
        atoms: List[Atom] = []
        for literal in _AND_SPLIT.split(disj):
            literal = literal.strip()
            if not literal:
                continue
            atoms.append(_parse_literal(literal))
        disjuncts.append(atoms)

    return disjuncts or [[]]


def _parse_literal(text: str) -> Atom:
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
    value = _parse_value(value_raw)
    canonical_op = "==" if op == "=" else op
    return Atom(path=path, op=canonical_op, value=value)


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
        # Evaluate antecedent → consequent
        if not constraint.antecedent:
            antecedent_conjs = [[]]
        else:
            antecedent_conjs = constraint.antecedent

        if not constraint.consequent:
            consequent_conjs = [[]]
        else:
            consequent_conjs = constraint.consequent

        for conj_idx, antecedent_atoms in enumerate(antecedent_conjs):
            cond_literals = [_atom_literal(model, var_map, compiled.domains, atom) for atom in antecedent_atoms]

            effect_literals: List[cp_model.BoolVar] = []
            for eff_idx, effect_atoms in enumerate(consequent_conjs):
                lit = _conjunction_literal(model, [_atom_literal(model, var_map, compiled.domains, atom) for atom in effect_atoms], name=f"cons_{idx}_{conj_idx}_{eff_idx}")
                effect_literals.append(lit)

            if not effect_literals:
                effect_literals.append(_true_literal(model))

            clause = effect_literals + [lit.Not() for lit in cond_literals]
            model.AddBoolOr(clause)

    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        assignment = {
            path: compiled.domains[path].decode(int(solver.Value(var)))
            for path, var in var_map.items()
        }
        return {"ok": True, "assignment": assignment}

    return {"ok": False, "assignment": None}


def evaluate_assignment(compiled: CompiledConstraints, assignments: Dict[str, Any]) -> Dict[str, Any]:
    flat = flatten_assignments(assignments)
    domain_issues: List[Dict[str, Any]] = []
    for path, domain in compiled.domains.items():
        if path not in flat:
            domain_issues.append({"code": "missing_assignment", "path": path, "message": "Missing assignment"})
            continue
        value = flat[path]
        if not domain.contains(value):
            domain_issues.append({"code": "domain_violation", "path": path, "message": f"Value {value!r} outside domain"})

    # Fail closed on constraint atoms that reference an illegal (#51) or
    # undeclared (#52) TVAR path. Without this, atom_true silently returns False
    # for such a path, voiding the guard with no diagnostic (fail-open); the SAT
    # sibling (_atom_literal) already raises "Unknown TVAR in constraint".
    seen_paths: set[str] = set()
    for constraint in compiled.constraints:
        for clause_dnf in (constraint.antecedent, constraint.consequent):
            for conj in clause_dnf:
                for atom in conj:
                    if atom.path in seen_paths:
                        continue
                    seen_paths.add(atom.path)
                    if not _IDENT_RE.match(atom.path):
                        domain_issues.append({
                            "code": "illegal_ident",
                            "path": atom.path,
                            "message": f"Constraint references illegal identifier {atom.path!r}",
                        })
                    elif atom.path not in compiled.domains:
                        domain_issues.append({
                            "code": "unknown_reference",
                            "path": atom.path,
                            "message": f"Constraint references undeclared TVAR '{atom.path}'",
                        })

    def atom_true(atom: Atom) -> bool:
        value = flat.get(atom.path)
        if value is None:
            return False
        if atom.op == "==":
            return value == atom.value
        if atom.op == "!=":
            return value != atom.value
        if atom.op == "<":
            return value < atom.value
        if atom.op == "<=":
            return value <= atom.value
        if atom.op == ">":
            return value > atom.value
        if atom.op == ">=":
            return value >= atom.value
        raise ValueError(f"Unsupported operator {atom.op}")

    constraint_issues: List[Dict[str, Any]] = []
    for idx, constraint in enumerate(compiled.constraints):
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
            all(atom_true(atom) for atom in cond) for cond in antecedent
        )
        if not antecedent_true:
            # antecedent false → constraint vacuously satisfied
            satisfied = True
        else:
            # antecedent holds → consequent must hold
            satisfied = any(
                all(atom_true(atom) for atom in conj) for conj in consequent
            )

        if not satisfied:
            constraint_issues.append({"code": "constraint_failed", "constraint_index": idx, "raw": constraint.raw})

    return {"domains": domain_issues, "constraints": constraint_issues}


def _create_variable(model: cp_model.CpModel, domain: Domain) -> cp_model.IntVar:
    name = domain.path.replace(".", "_")
    if domain.kind == "bool":
        return model.NewBoolVar(name)
    if domain.kind == "enum":
        values = domain.values or []
        if not values:
            # Fallback to a binary selector
            return model.NewIntVar(0, 1, name)
        return model.NewIntVar(0, len(values) - 1, name)
    if domain.kind == "int":
        lb = int(domain.minimum) if domain.minimum is not None else -10_000
        ub = int(domain.maximum) if domain.maximum is not None else 10_000
        return model.NewIntVar(lb, ub, name)
    if domain.kind == "float":
        lb = domain._encode_bound_lower(domain.minimum) if domain.minimum is not None else -1_000_000
        ub = domain._encode_bound_upper(domain.maximum) if domain.maximum is not None else 1_000_000
        return model.NewIntVar(lb, ub, name)
    raise ValueError(f"Unsupported domain type {domain.kind}")


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


def _atom_literal(
    model: cp_model.CpModel,
    var_map: Dict[str, cp_model.IntVar],
    domains: Dict[str, Domain],
    atom: Atom,
) -> cp_model.BoolVar:
    domain = domains.get(atom.path)
    if domain is None:
        raise ValueError(f"Unknown TVAR in constraint: {atom.path}")
    var = var_map[atom.path]

    if domain.kind == "bool":
        bool_var = var
        if atom.op == "==":
            return bool_var if bool(atom.value) else bool_var.Not()
        if atom.op == "!=":
            return bool_var.Not() if bool(atom.value) else bool_var
        raise ValueError(f"Unsupported bool operator {atom.op}")

    if domain.kind == "enum":
        values = domain.values or []
        numeric_values = [v for v in values if isinstance(v, (int, float))]
        is_numeric_enum = len(numeric_values) == len(values) and values

        encoded = None
        if values:
            try:
                encoded = domain.encode(atom.value)
            except ValueError:
                encoded = None

        lit = model.NewBoolVar(f"lit_{atom.path.replace('.', '_')}_{atom.op}_{atom.value}")

        if atom.op == "==":
            if encoded is None:
                model.Add(lit == 0)
            else:
                model.Add(var == encoded).OnlyEnforceIf(lit)
                model.Add(var != encoded).OnlyEnforceIf(lit.Not())
            return lit

        if atom.op == "!=":
            if encoded is None:
                model.Add(lit == 1)
            else:
                model.Add(var != encoded).OnlyEnforceIf(lit)
                model.Add(var == encoded).OnlyEnforceIf(lit.Not())
            return lit

        if is_numeric_enum and atom.op in ("<", "<=", ">", ">="):
            threshold = float(atom.value)
            # Compare enum VALUES against the threshold, not enum indices: the
            # index order is not guaranteed to match value order (legacy
            # dict-form tvars are stored verbatim; only list-form sorts), so we
            # collect the exact set of value-satisfying indices and reify
            # membership over it rather than assuming a contiguous index range.
            if atom.op == "<":
                allowed = [idx for idx, val in enumerate(values) if val < threshold]
            elif atom.op == "<=":
                allowed = [idx for idx, val in enumerate(values) if val <= threshold]
            elif atom.op == ">":
                allowed = [idx for idx, val in enumerate(values) if val > threshold]
            else:  # ">="
                allowed = [idx for idx, val in enumerate(values) if val >= threshold]
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

    encoded = domain.encode(atom.value)
    lit = model.NewBoolVar(f"lit_{atom.path.replace('.', '_')}_{atom.op}_{atom.value}")

    if atom.op == "==":
        model.Add(var == encoded).OnlyEnforceIf(lit)
        model.Add(var != encoded).OnlyEnforceIf(lit.Not())
    elif atom.op == "!=":
        model.Add(var != encoded).OnlyEnforceIf(lit)
        model.Add(var == encoded).OnlyEnforceIf(lit.Not())
    elif atom.op == "<":
        model.Add(var <= encoded - 1).OnlyEnforceIf(lit)
        model.Add(var >= encoded).OnlyEnforceIf(lit.Not())
    elif atom.op == "<=":
        model.Add(var <= encoded).OnlyEnforceIf(lit)
        model.Add(var >= encoded + 1).OnlyEnforceIf(lit.Not())
    elif atom.op == ">":
        model.Add(var >= encoded + 1).OnlyEnforceIf(lit)
        model.Add(var <= encoded).OnlyEnforceIf(lit.Not())
    elif atom.op == ">=":
        model.Add(var >= encoded).OnlyEnforceIf(lit)
        model.Add(var <= encoded - 1).OnlyEnforceIf(lit.Not())
    else:
        raise ValueError(f"Unsupported operator {atom.op}")

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
