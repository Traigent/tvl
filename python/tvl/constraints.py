from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

try:  # pragma: no cover - optional dependency
    from ortools.sat.python import cp_model  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback path
    cp_model = None  # type: ignore

from .model import Domain, extract_domains, flatten_assignments


_OR_SPLIT = re.compile(r"\s+or\s+", re.IGNORECASE)
_AND_SPLIT = re.compile(r"\s+and\s+", re.IGNORECASE)
_LITERAL_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*(<=|>=|!=|=|<|>)\s*(.+?)\s*$")

_TRUE_COUNTER = 0


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


def compile_constraints(module: Dict[str, Any]) -> CompiledConstraints:
    domains = extract_domains(module.get("tvars", {}))

    constraints_section = module.get("constraints", {}) or {}
    structural = constraints_section.get("structural") or []

    compiled: List[StructuralConstraint] = []
    for entry in structural:
        if not isinstance(entry, dict):
            continue
        when_expr = entry.get("when")
        then_expr = entry.get("then")
        expr_expr = entry.get("expr")

        if when_expr is not None or then_expr is not None:
            antecedent = parse_expression(when_expr)
            consequent = parse_expression(then_expr)
            compiled.append(StructuralConstraint(antecedent=antecedent, consequent=consequent, raw=entry))
        elif expr_expr is not None:
            consequent = parse_expression(expr_expr)
            compiled.append(StructuralConstraint(antecedent=[[]], consequent=consequent, raw=entry))

    return CompiledConstraints(domains=domains, constraints=compiled)


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
        return [[]]

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
    match = _LITERAL_RE.match(text)
    if not match:
        raise ValueError(f"Could not parse constraint literal: {text!r}")
    path, op, value_raw = match.groups()
    value = _parse_value(value_raw.strip())
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

        satisfied = False
        for cond in antecedent:
            cond_true = all(atom_true(atom) for atom in cond)
            if not cond_true:
                satisfied = True
                break

            # antecedent holds → consequent must hold
            conseq_ok = any(all(atom_true(atom) for atom in conj) for conj in consequent)
            if conseq_ok:
                satisfied = True
                break

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
        lb = domain._encode_bound(domain.minimum) if domain.minimum is not None else -1_000_000
        ub = domain._encode_bound(domain.maximum) if domain.maximum is not None else 1_000_000
        return model.NewIntVar(lb, ub, name)
    raise ValueError(f"Unsupported domain type {domain.kind}")


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

        if is_numeric_enum:
            threshold = float(atom.value)
            if atom.op == "<":
                allowed = [idx for idx, val in enumerate(values) if val < threshold]
                if not allowed:
                    model.Add(lit == 0)
                else:
                    model.Add(var <= max(allowed)).OnlyEnforceIf(lit)
                    model.Add(var >= max(allowed) + 1).OnlyEnforceIf(lit.Not())
                return lit
            if atom.op == "<=":
                allowed = [idx for idx, val in enumerate(values) if val <= threshold]
                if not allowed:
                    model.Add(lit == 0)
                else:
                    model.Add(var <= max(allowed)).OnlyEnforceIf(lit)
                    model.Add(var >= max(allowed) + 1).OnlyEnforceIf(lit.Not())
                return lit
            if atom.op == ">":
                allowed = [idx for idx, val in enumerate(values) if val > threshold]
                if not allowed:
                    model.Add(lit == 0)
                else:
                    model.Add(var >= min(allowed)).OnlyEnforceIf(lit)
                    model.Add(var <= min(allowed) - 1).OnlyEnforceIf(lit.Not())
                return lit
            if atom.op == ">=":
                allowed = [idx for idx, val in enumerate(values) if val >= threshold]
                if not allowed:
                    model.Add(lit == 0)
                else:
                    model.Add(var >= min(allowed)).OnlyEnforceIf(lit)
                    model.Add(var <= min(allowed) - 1).OnlyEnforceIf(lit.Not())
                return lit

        # Unsupported comparison on symbolic enum; fall back to conservative true.
        model.Add(lit == 1)
        return lit

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
