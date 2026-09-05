from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from fractions import Fraction
from math import lcm
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
    cvar_names: Set[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.cvar_names is None:
            self.cvar_names = set()


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
# TVL 1.1 normative identifier (RFC 0001 §3.7(2)): ASCII dotted segments, no
# empty segments, no leading/trailing dots, no hyphens. Enforced on the NEW
# surfaces (cvars/policies/scope) as errors; legacy tvar names are untouched.
_NORMATIVE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_CTX_EXT_KEYS = {
    "stage_versions",
    "model_versions",
    "budget_assumptions",
    "cost_assumptions",
    # TVL 1.2 (RFC 0002 §3.2 item 11): use-site SignalUse.inputs freshness.
    "signal_inputs",
}
_CVAR_TYPE_RE = re.compile(r"^(bool|int|float|enum\[(str|int|float)\])$")
# Normative integer literal grammar (spec/grammar/tvl.ebnf:258): -?[0-9]+.
# int() is deliberately NOT used to validate here — it also accepts
# underscore-grouped ('1_000') and surrounding-whitespace (' 5 ') forms that
# strict grammar-conformant consumers (e.g. tvl-check-structural) reject.
_INT_LITERAL_RE = re.compile(r"^-?[0-9]+$")
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
    _lint_cvars(doc, issues)
    _lint_policies(doc, issues)
    _lint_composites(doc, issues)
    _lint_namespace(doc, issues)
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


def _uses_11_constructs(doc: Dict[str, Any]) -> bool:
    """RFC 0001 §3.7(5): the new-surface opt-in that escalates prefix
    collisions from warning to error. PRESENCE-based: an explicit empty
    `cvars: []`, `policies: []`, `require_calibration: {...}`, or
    `scope: {}` is still an opt-in to the 1.1 surface."""
    if "cvars" in doc or "policies" in doc:
        return True
    promotion = doc.get("promotion_policy")
    if isinstance(promotion, dict) and "require_calibration" in promotion:
        return True
    tvars = doc.get("tvars") or []
    if isinstance(tvars, list) and any(
        isinstance(d, dict) and "scope" in d for d in tvars
    ):
        return True
    return False


def _check_scope(decl: Dict[str, Any], path: List[Any], name: Any, issues: List[Issue]) -> None:
    """Validate the optional ownership-scope metadata (RFC 0001 §3.7(6))."""
    scope = decl.get("scope")
    if scope is None:
        return
    if not isinstance(scope, dict):
        issues.append(
            {
                "code": "invalid_scope",
                "message": "scope must be an object with node/agent/workflow fields",
                "path": path + ["scope"],
                "severity": "error",
            }
        )
        return
    for key, value in scope.items():
        if key not in {"node", "agent", "workflow"}:
            issues.append(
                {
                    "code": "invalid_scope",
                    "message": f"scope field '{key}' is not one of node/agent/workflow",
                    "path": path + ["scope", key],
                    "severity": "error",
                }
            )
        elif not isinstance(value, str) or not _NORMATIVE_IDENT_RE.match(value):
            issues.append(
                {
                    "code": "invalid_scope",
                    "message": f"scope.{key} must be a valid identifier",
                    "path": path + ["scope", key],
                    "severity": "error",
                }
            )
    node = scope.get("node")
    if isinstance(name, str) and isinstance(node, str) and "." in name:
        if name.split(".", 1)[0] != node:
            issues.append(
                {
                    "code": "scope_prefix_mismatch",
                    "message": (
                        f"declaration '{name}' has dotted prefix "
                        f"'{name.split('.', 1)[0]}' but scope.node is '{node}'"
                    ),
                    "path": path + ["scope", "node"],
                    "severity": "warning",
                }
            )


def _lint_cvars(doc: Dict[str, Any], issues: List[Issue]) -> None:
    """RFC 0001 §3.3 — calibrated-variable declarations (governed, NOT searched)."""
    cvars = doc.get("cvars")
    if cvars is None:
        return
    if not isinstance(cvars, list):
        issues.append(
            {
                "code": "invalid_cvars",
                "message": "cvars must be a list of declarations",
                "path": ["cvars"],
                "severity": "error",
            }
        )
        return
    tvar_names = {
        d.get("name")
        for d in (doc.get("tvars") or [])
        if isinstance(d, dict) and isinstance(d.get("name"), str)
    }
    seen: Set[str] = set()
    for idx, decl in enumerate(cvars):
        if not isinstance(decl, dict):
            issues.append(
                {
                    "code": "invalid_cvar_decl",
                    "message": "cvar declarations must be objects",
                    "path": ["cvars", idx],
                    "severity": "error",
                }
            )
            continue
        name = decl.get("name")
        if not isinstance(name, str) or not _NORMATIVE_IDENT_RE.match(name):
            issues.append(
                {
                    "code": "invalid_cvar_name",
                    "message": "cvar declarations require a valid identifier name",
                    "path": ["cvars", idx, "name"],
                    "severity": "error",
                }
            )
            continue
        if name in seen:
            issues.append(
                {
                    "code": "duplicate_cvar",
                    "message": f"CVAR '{name}' is declared multiple times",
                    "path": ["cvars", idx, "name"],
                    "severity": "error",
                }
            )
        seen.add(name)
        raw_type = decl.get("type")
        if not isinstance(raw_type, str) or not _CVAR_TYPE_RE.match(raw_type):
            issues.append(
                {
                    "code": "unsupported_cvar_type",
                    "message": (
                        f"CVAR '{name}' type must be bool, int, float, or enum[...]"
                        " (tuple/callable deferred)"
                    ),
                    "path": ["cvars", idx, "type"],
                    "severity": "error",
                }
            )
        calibration = decl.get("calibration")
        if not isinstance(calibration, dict) or not isinstance(
            calibration.get("source"), str
        ):
            issues.append(
                {
                    "code": "cvar_missing_source",
                    "message": f"CVAR '{name}' requires calibration.source",
                    "path": ["cvars", idx, "calibration"],
                    "severity": "error",
                }
            )
            calibration = {}
        depends_on = calibration.get("depends_on") or []
        if isinstance(depends_on, list):
            for ref_idx, ref in enumerate(depends_on):
                if ref not in tvar_names:
                    issues.append(
                        {
                            "code": "missing_ref",
                            "message": (
                                f"CVAR '{name}' depends_on '{ref}' which does not "
                                "resolve to a declared TVAR (exact match; CVAR/policy "
                                "parents are deferred in v1)"
                            ),
                            "path": ["cvars", idx, "calibration", "depends_on", ref_idx],
                            "severity": "error",
                        }
                    )
        governance = decl.get("governance")
        if governance is not None and (
            not isinstance(governance, dict)
            or not isinstance(governance.get("require_calibration", False), bool)
        ):
            issues.append(
                {
                    "code": "invalid_cvar_governance",
                    "message": f"CVAR '{name}' governance.require_calibration must be a boolean",
                    "path": ["cvars", idx, "governance"],
                    "severity": "error",
                }
            )
        _check_scope(decl, ["cvars", idx], name, issues)


def _lint_policies(doc: Dict[str, Any], issues: List[Issue]) -> None:
    """RFC 0001 §3.8 — operational policy declarations (cascade strategy)."""
    policies = doc.get("policies")
    if policies is None:
        return
    if not isinstance(policies, list):
        issues.append(
            {
                "code": "invalid_policies",
                "message": "policies must be a list of declarations",
                "path": ["policies"],
                "severity": "error",
            }
        )
        return
    cvar_names = {
        d.get("name")
        for d in (doc.get("cvars") or [])
        if isinstance(d, dict) and isinstance(d.get("name"), str)
    }
    seen: Set[str] = set()
    for idx, decl in enumerate(policies):
        if not isinstance(decl, dict):
            issues.append(
                {
                    "code": "invalid_policy_decl",
                    "message": "policy declarations must be objects",
                    "path": ["policies", idx],
                    "severity": "error",
                }
            )
            continue
        name = decl.get("name")
        if not isinstance(name, str) or not _NORMATIVE_IDENT_RE.match(name):
            issues.append(
                {
                    "code": "invalid_policy_name",
                    "message": "policy declarations require a valid identifier name",
                    "path": ["policies", idx, "name"],
                    "severity": "error",
                }
            )
            continue
        if name in seen:
            issues.append(
                {
                    "code": "duplicate_policy",
                    "message": f"policy '{name}' is declared multiple times",
                    "path": ["policies", idx, "name"],
                    "severity": "error",
                }
            )
        seen.add(name)
        if decl.get("kind") != "policy":
            issues.append(
                {
                    "code": "invalid_policy_kind",
                    "message": f"policy '{name}' kind must be the literal 'policy'",
                    "path": ["policies", idx, "kind"],
                    "severity": "error",
                }
            )
        strategy = decl.get("strategy")
        if strategy != "cascade":
            issues.append(
                {
                    "code": "unknown_policy_strategy",
                    "message": f"policy '{name}' strategy '{strategy}' is not in the v1 registry (cascade)",
                    "path": ["policies", idx, "strategy"],
                    "severity": "error",
                }
            )
        stages = decl.get("stages")
        if not isinstance(stages, list) or len(stages) < 1:
            issues.append(
                {
                    "code": "cascade_arity",
                    "message": f"policy '{name}' requires stages with at least one entry",
                    "path": ["policies", idx, "stages"],
                    "severity": "error",
                }
            )
            stages = []
        if len(stages) != len(set(stages)):
            issues.append(
                {
                    "code": "duplicate_stage",
                    "message": f"policy '{name}' declares duplicate stage identifiers",
                    "path": ["policies", idx, "stages"],
                    "severity": "error",
                }
            )
        gates = decl.get("gates") or []
        if stages and isinstance(gates, list) and len(gates) != max(len(stages) - 1, 0):
            issues.append(
                {
                    "code": "cascade_arity",
                    "message": (
                        f"policy '{name}' declares {len(gates)} gate(s) for "
                        f"{len(stages)} stage(s); |gates| must equal |stages| - 1"
                    ),
                    "path": ["policies", idx, "gates"],
                    "severity": "error",
                }
            )
        if isinstance(gates, list):
            for gate_idx, gate in enumerate(gates):
                if not isinstance(gate, dict):
                    continue
                if gate.get("kind") != "margin_below":
                    issues.append(
                        {
                            "code": "unknown_gate_kind",
                            "message": f"policy '{name}' gate kind must be 'margin_below' in v1",
                            "path": ["policies", idx, "gates", gate_idx, "kind"],
                            "severity": "error",
                        }
                    )
                threshold = gate.get("threshold")
                if threshold not in cvar_names:
                    issues.append(
                        {
                            "code": "missing_ref",
                            "message": (
                                f"policy '{name}' gate threshold '{threshold}' must "
                                "resolve to a declared CVAR (kind-checked namespace ref)"
                            ),
                            "path": ["policies", idx, "gates", gate_idx, "threshold"],
                            "severity": "error",
                        }
                    )
        _check_scope(decl, ["policies", idx], name, issues)


# ---------------------------------------------------------------------------
# TVL 1.2 (RFC 0002) — the sealed composite-knob algebra.
#
# Sealed registries (§3.2). A fourth member is a NEW RFC, not a registry entry.
# ---------------------------------------------------------------------------
_COMPOSITE_KINDS = {"cascade", "ensemble", "loop"}
_GATE_KINDS = {"margin_below", "signal_below"}
_AGGREGATE_KINDS = {"majority_vote", "judge_max"}
_ACCEPT_STATS = {"vote_margin", "vote_agreement"}
_STOP_KINDS = {"signal_accept", "external_accept", "exhausted"}
_NUMERIC_CVAR_TYPES = {"int", "float"}

# The canonical vote-statistic ids that live in the SAME registry namespace as
# named signals (§3.2 item 11): sig(margin_below) = "vote_margin".
_CANONICAL_VOTE_MARGIN = "vote_margin"

# Exactly the body fields admissible per kind (§3.2 item 1: closed shapes).
# 'name'/'kind' and the universal optional keys are allowed for every kind.
_COMPOSITE_COMMON_FIELDS = {"name", "kind", "pattern", "parameters", "scope"}
_COMPOSITE_KIND_FIELDS = {
    "cascade": {"placement", "arms", "gates"},
    "ensemble": {"arms", "cardinality", "aggregate"},
    "loop": {"body", "state_keys", "stop", "max_iters"},
}


def _is_arm_object(arm: Any, key: str) -> bool:
    return isinstance(arm, dict) and key in arm


def _lint_composites(doc: Dict[str, Any], issues: List[Issue]) -> None:
    """RFC 0002 §3 — the composite-knob algebra (cascade | ensemble | loop).

    Implements the §3.11 1:1 code↔rule table. Every rejection here fires at the
    composite USE SITE only — a 1.1 module declares no composites, so none of
    these lints can fire on it (P1 preserved, §4). The reused RFC 0001 codes
    (``cascade_arity``, ``unknown_gate_kind``, ``missing_ref``) carry identical
    semantics onto the composite construct.
    """
    composites = doc.get("composites")
    if composites is None:
        return
    if not isinstance(composites, list):
        issues.append(
            {
                "code": "invalid_composites",
                "message": "composites must be a list of declarations",
                "path": ["composites"],
                "severity": "error",
            }
        )
        return

    # Declared identifiers from the other namespace classes (§3.1: composites
    # join the SAME scoped namespace). Types are tracked for the threshold /
    # cardinality kind-and-type checks (items 6, 7, 10).
    tvar_types: Dict[str, str] = {}
    for d in (doc.get("tvars") or []):
        if isinstance(d, dict) and isinstance(d.get("name"), str):
            kind = _normalize_kind(d.get("type")) if isinstance(d.get("type"), str) else None
            tvar_types[d["name"]] = kind if kind is not None else ""
    tvar_names = set(tvar_types)
    cvar_decls: Dict[str, Dict[str, Any]] = {
        d["name"]: d
        for d in (doc.get("cvars") or [])
        if isinstance(d, dict) and isinstance(d.get("name"), str)
    }
    cvar_names = set(cvar_decls)
    other_class_names = set(tvar_names) | cvar_names | {
        d.get("name")
        for d in (doc.get("policies") or [])
        if isinstance(d, dict) and isinstance(d.get("name"), str)
    }

    # Pass 1: the N_X membership + duplicate/shadow discipline (§3.1).
    composite_names: Set[str] = set()
    seen: Set[str] = set()
    for idx, decl in enumerate(composites):
        if not isinstance(decl, dict):
            issues.append(
                {
                    "code": "invalid_composite_decl",
                    "message": "composite declarations must be objects",
                    "path": ["composites", idx],
                    "severity": "error",
                }
            )
            continue
        name = decl.get("name")
        if not isinstance(name, str) or not _NORMATIVE_IDENT_RE.match(name):
            issues.append(
                {
                    "code": "invalid_composite_name",
                    "message": "composite declarations require a valid identifier name",
                    "path": ["composites", idx, "name"],
                    "severity": "error",
                }
            )
            continue
        if name in seen:
            issues.append(
                {
                    "code": "duplicate_composite",
                    "message": f"composite '{name}' is declared multiple times",
                    "path": ["composites", idx, "name"],
                    "severity": "error",
                }
            )
        seen.add(name)
        if name in other_class_names:
            issues.append(
                {
                    "code": "composite_shadows_name",
                    "message": (
                        f"composite '{name}' shadows a name already declared as a "
                        "tvar/cvar/policy — tvars, cvars, policies, and composites "
                        "share one namespace (N_X)"
                    ),
                    "path": ["composites", idx, "name"],
                    "severity": "error",
                }
            )
        composite_names.add(name)

    composites_by_name: Dict[str, Dict[str, Any]] = {
        d["name"]: d
        for d in composites
        if isinstance(d, dict) and isinstance(d.get("name"), str)
    }

    # The N_X reference DAG over composite(·) arms, for acyclicity (item 4) and
    # the leafT/Cal recursive folds (§3.5 / §3.6). Built once over all decls.
    child_refs = _composite_child_refs(composites, composite_names)
    cyclic_nodes = _composite_cyclic_nodes(child_refs)

    # Module-level freshness coverage for the §3.2 item-11 signal_inputs rule.
    ctx_keys, covered_signal_inputs = _doc_calibration_coverage(doc)

    # Pass 2: per-composite well-formedness.
    for idx, decl in enumerate(composites):
        if not isinstance(decl, dict) or not isinstance(decl.get("name"), str):
            continue
        _lint_one_composite(
            decl,
            idx,
            issues,
            composite_names=composite_names,
            composites_by_name=composites_by_name,
            tvar_names=tvar_names,
            tvar_types=tvar_types,
            cvar_decls=cvar_decls,
            cyclic_nodes=cyclic_nodes,
            ctx_keys=ctx_keys,
            covered_signal_inputs=covered_signal_inputs,
        )


def _doc_calibration_coverage(doc: Dict[str, Any]) -> Tuple[Set[str], Optional[List[Any]]]:
    """The module's freshness-context coverage (RFC 0001 §3.5 / RFC 0002 §3.2
    item 11). Returns (a) the set of hash_covered_context EXTENSION keys and
    (b) the ordered value covered under 'signal_inputs'
    (``require_calibration.signal_inputs``). The item-11 ``unbound_signal_inputs``
    check is static — both the use-site inputs list and this covered value are
    declared identifier lists."""
    policy = doc.get("promotion_policy")
    if not isinstance(policy, dict):
        return set(), None
    spec = policy.get("require_calibration")
    if not isinstance(spec, dict):
        return set(), None
    keys = spec.get("hash_covered_context")
    if not isinstance(keys, list):
        return set(), None
    ctx_keys = {k for k in keys if isinstance(k, str)}
    covered = spec.get("signal_inputs") if "signal_inputs" in spec else None
    return ctx_keys, covered if isinstance(covered, list) else None


def _composite_child_refs(
    composites: List[Any], composite_names: Set[str]
) -> Dict[str, Set[str]]:
    """The N_X reference graph: composite name → set of composite names it
    references via tagged ``composite(x)`` arms (in arms / body / judge)."""
    refs: Dict[str, Set[str]] = {}
    for decl in composites:
        if not isinstance(decl, dict) or not isinstance(decl.get("name"), str):
            continue
        name = decl["name"]
        out: Set[str] = refs.setdefault(name, set())
        for arm in _all_arms_of(decl):
            if isinstance(arm, dict) and isinstance(arm.get("composite"), str):
                ref = arm["composite"]
                if ref in composite_names:
                    out.add(ref)
    return refs


def _all_arms_of(decl: Dict[str, Any]) -> List[Any]:
    """Every arm surface a composite carries: cascade/ensemble arms, the loop
    body, and the ensemble judge — the positions an ``Arm`` may appear (§3.9)."""
    arms: List[Any] = []
    raw_arms = decl.get("arms")
    if isinstance(raw_arms, list):
        arms.extend(raw_arms)
    body = decl.get("body")
    if body is not None:
        arms.append(body)
    aggregate = decl.get("aggregate")
    if isinstance(aggregate, dict):
        judge = aggregate.get("judge")
        if judge is not None:
            arms.append(judge)
    return arms


def _composite_cyclic_nodes(child_refs: Dict[str, Set[str]]) -> Set[str]:
    """Names that participate in any cycle of the N_X reference graph (item 4).

    Returns every node on a cycle OR reaching one, so the ``composite_cycle``
    diagnostic fires on each declaration whose expansion would not terminate.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    color: Dict[str, int] = {n: WHITE for n in child_refs}
    on_cycle: Set[str] = set()

    def visit(node: str, stack: List[str]) -> bool:
        color[node] = GREY
        stack.append(node)
        hit = False
        for nxt in child_refs.get(node, set()):
            if color.get(nxt, WHITE) == GREY:
                # Back-edge: every node from nxt's stack position onward is on a cycle.
                start = stack.index(nxt)
                on_cycle.update(stack[start:])
                hit = True
            elif color.get(nxt, WHITE) == WHITE:
                if visit(nxt, stack):
                    on_cycle.add(node)
                    hit = True
            elif nxt in on_cycle:
                on_cycle.add(node)
                hit = True
        stack.pop()
        color[node] = BLACK
        return hit

    for n in list(child_refs):
        if color.get(n, WHITE) == WHITE:
            visit(n, [])
    return on_cycle


def _lint_one_composite(
    decl: Dict[str, Any],
    idx: int,
    issues: List[Issue],
    *,
    composite_names: Set[str],
    composites_by_name: Dict[str, Dict[str, Any]],
    tvar_names: Set[str],
    tvar_types: Dict[str, str],
    cvar_decls: Dict[str, Dict[str, Any]],
    cyclic_nodes: Set[str],
    ctx_keys: Set[str],
    covered_signal_inputs: Optional[List[Any]],
) -> None:
    name = decl["name"]
    base = ["composites", idx]

    # §3.1 — a composite never binds a value. These value-binding keys carry the
    # PRECISE composite_binds_value diagnostic (not the generic unknown field one).
    value_keys = [k for k in ("value", "default", "binding") if k in decl]
    for offending in value_keys:
        issues.append(
            {
                "code": "composite_binds_value",
                "message": (
                    f"composite '{name}' binds a value ('{offending}') — a composite "
                    "is a namespace/expansion unit, never a binding kind (§3.1)"
                ),
                "path": base + [offending],
                "severity": "error",
            }
        )

    # Item 1 — kind registry.
    kind = decl.get("kind")
    if kind not in _COMPOSITE_KINDS:
        issues.append(
            {
                "code": "unknown_composite_kind",
                "message": (
                    f"composite '{name}' kind '{kind}' is not in the sealed v1 "
                    "registry (cascade | ensemble | loop)"
                ),
                "path": base + ["kind"],
                "severity": "error",
            }
        )
        # Without a known kind the body fields cannot be checked further.
        return

    # Item 1 — closed shapes: exactly the body fields of the declared kind.
    # Value-binding keys are excluded here (carried by composite_binds_value).
    allowed = _COMPOSITE_COMMON_FIELDS | _COMPOSITE_KIND_FIELDS[kind] | set(value_keys)
    for field_name in decl:
        if field_name not in allowed:
            issues.append(
                {
                    "code": "unknown_composite_field",
                    "message": (
                        f"composite '{name}' (kind '{kind}') has field '{field_name}' "
                        "which is unknown or belongs to another constructor (closed shapes)"
                    ),
                    "path": base + [field_name],
                    "severity": "error",
                }
            )

    # Item 4 — acyclic N_X reference graph.
    if name in cyclic_nodes:
        issues.append(
            {
                "code": "composite_cycle",
                "message": (
                    f"composite '{name}' participates in a cycle of the composite "
                    "reference graph; nesting must be acyclic so expansion terminates (§3.2 item 4)"
                ),
                "path": base + ["name"],
                "severity": "error",
            }
        )

    ctx = _CompositeCtx(
        name=name,
        base=base,
        issues=issues,
        composite_names=composite_names,
        composites_by_name=composites_by_name,
        tvar_names=tvar_names,
        tvar_types=tvar_types,
        cvar_decls=cvar_decls,
        ctx_keys=ctx_keys,
        covered_signal_inputs=covered_signal_inputs,
    )

    # Items 3, 6, 9 — arm resolution + stage-duplicate + tuned_params, over
    # EVERY arm position (arms / body / judge). Shared so duplicate_stage spans
    # the whole composite (extended scope, §3.11).
    _check_arms(decl, kind, ctx)

    if kind == "cascade":
        _check_cascade(decl, ctx)
    elif kind == "ensemble":
        _check_ensemble(decl, ctx)
    elif kind == "loop":
        _check_loop(decl, ctx)

    # §3.5 — required_parents(θ) ⊆ depends_on(θ) for every threshold CVAR
    # (missing_composite_parent). Skip cyclic composites: leafT would not
    # terminate and the cycle is already reported.
    if name not in cyclic_nodes:
        _check_composite_parents(decl, kind, ctx)


@dataclass
class _CompositeCtx:
    name: str
    base: List[Any]
    issues: List[Issue]
    composite_names: Set[str]
    composites_by_name: Dict[str, Dict[str, Any]]
    tvar_names: Set[str]
    tvar_types: Dict[str, str]
    cvar_decls: Dict[str, Dict[str, Any]]
    # Module-level freshness-context coverage (§3.2 item 11 / RFC 0001 §3.5):
    # the promotion_policy.require_calibration.hash_covered_context keys and the
    # value covered under 'signal_inputs', resolved once for the whole module.
    ctx_keys: Set[str] = field(default_factory=set)
    covered_signal_inputs: Optional[List[Any]] = None

    def add(self, code: str, message: str, path: List[Any], severity: str = "error") -> None:
        self.issues.append(
            {"code": code, "message": message, "path": path, "severity": severity}
        )


def _check_arms(decl: Dict[str, Any], kind: str, ctx: _CompositeCtx) -> None:
    """Items 3/6/9 — arm shape, resolution, stage duplicates, tuned_params,
    over every arm position in the composite (§3.9 one-shape rule)."""
    stage_paths: Dict[str, List[Any]] = {}

    def visit_arm(arm: Any, path: List[Any]) -> None:
        if isinstance(arm, str):
            # Bare identifier is ALWAYS a stage (§3.2 item 3). A bare id that
            # collides with a composite name is ambiguous_arm (not silent resolve).
            if arm in ctx.composite_names:
                ctx.add(
                    "ambiguous_arm",
                    f"composite '{ctx.name}' bare arm '{arm}' collides with a declared "
                    "composite name; use the tagged {{composite: ...}} form to nest, or "
                    "rename the stage",
                    path,
                )
            else:
                _record_stage(arm, path, stage_paths, ctx)
            return
        if not isinstance(arm, dict):
            ctx.add(
                "invalid_arm_shape",
                f"composite '{ctx.name}' arm must be a bare stage identifier, "
                "{{stage, tuned_params?}}, or {{composite}}",
                path,
            )
            return
        has_stage = "stage" in arm
        has_composite = "composite" in arm
        # §3.9 ArmSurface: the stage form allows {stage, tuned_params?}; the
        # nesting form allows {composite} ONLY — tuned_params on a
        # composite-tagged arm is a closure bypass (codex P4 round 1).
        allowed = {"stage", "tuned_params"} if has_stage and not has_composite else {"composite"}
        unknown = set(arm) - allowed
        if unknown or (has_stage and has_composite) or not (has_stage or has_composite):
            ctx.add(
                "invalid_arm_shape",
                f"composite '{ctx.name}' arm has an unknown or ambiguous shape; expected "
                "exactly one of a stage form {{stage, tuned_params?}} or a nesting form "
                "{{composite}}",
                path,
            )
            return
        if has_stage:
            stage_id = arm.get("stage")
            if isinstance(stage_id, str):
                _record_stage(stage_id, path + ["stage"], stage_paths, ctx)
            tuned = arm.get("tuned_params")
            if tuned is None:
                tuned = []
            if isinstance(tuned, list):
                for tp_idx, tp in enumerate(tuned):
                    if tp not in ctx.tvar_names:
                        ctx.add(
                            "invalid_tuned_param",
                            f"composite '{ctx.name}' tuned_params entry '{tp}' does not "
                            "resolve to a declared TVAR (exact match; cvars/policies/"
                            "composites are not tuned parents)",
                            path + ["tuned_params", tp_idx],
                        )
        else:  # has_composite
            ref = arm.get("composite")
            if not isinstance(ref, str) or ref not in ctx.composite_names:
                ctx.add(
                    "missing_composite_ref",
                    f"composite '{ctx.name}' nests composite('{ref}') which does not "
                    "resolve to any declared composite (exact match into N_X)",
                    path + ["composite"],
                )

    # cascade/ensemble arms
    raw_arms = decl.get("arms")
    if isinstance(raw_arms, list):
        for a_idx, arm in enumerate(raw_arms):
            visit_arm(arm, ctx.base + ["arms", a_idx])
    # loop body
    if kind == "loop" and decl.get("body") is not None:
        visit_arm(decl.get("body"), ctx.base + ["body"])
    # ensemble judge
    aggregate = decl.get("aggregate")
    if isinstance(aggregate, dict) and aggregate.get("judge") is not None:
        visit_arm(aggregate.get("judge"), ctx.base + ["aggregate", "judge"])


def _record_stage(
    stage_id: str, path: List[Any], stage_paths: Dict[str, List[Any]], ctx: _CompositeCtx
) -> None:
    if stage_id in stage_paths:
        ctx.add(
            "duplicate_stage",
            f"composite '{ctx.name}' declares duplicate stage '{stage_id}'",
            path,
        )
    else:
        stage_paths[stage_id] = path


def _threshold_cvar_checks(
    threshold: Any,
    path: List[Any],
    ctx: _CompositeCtx,
    *,
    sig_expected: Optional[str],
    sig_inputs: Sequence[str],
) -> None:
    """Items 6, 10, 11 — a gate/accept/stop threshold reference.

    - resolves to a declared CVAR (item 6, reused ``missing_ref``);
    - that CVAR is int/float-typed (item 10, ``invalid_threshold_type``);
    - the composite-use-site signal binding (item 11): the CVAR's
      ``calibration.signal`` MUST equal ``sig_expected``
      (``missing_calibration_signal`` / ``signal_mismatch``); when the governing
      ``SignalUse.inputs`` is non-empty the CVAR's promotion-policy
      ``hash_covered_context`` MUST include ``signal_inputs`` and its covered
      value MUST equal the use-site list (``unbound_signal_inputs``).
    """
    if not isinstance(threshold, str) or threshold not in ctx.cvar_decls:
        ctx.add(
            "missing_ref",
            f"composite '{ctx.name}' threshold '{threshold}' must resolve to a declared "
            "CVAR (kind-checked namespace ref)",
            path,
        )
        return
    cvar = ctx.cvar_decls[threshold]
    cvar_type = cvar.get("type")
    if cvar_type not in _NUMERIC_CVAR_TYPES:
        ctx.add(
            "invalid_threshold_type",
            f"composite '{ctx.name}' threshold CVAR '{threshold}' has type "
            f"'{cvar_type}'; gate/accept/stop thresholds must be int or float (§3.2 item 10)",
            path,
        )

    # Item 11 — signal/threshold calibration binding (composite use site only).
    if sig_expected is not None:
        calibration = cvar.get("calibration")
        declared_signal = (
            calibration.get("signal") if isinstance(calibration, dict) else None
        )
        if declared_signal is None:
            ctx.add(
                "missing_calibration_signal",
                f"composite '{ctx.name}' uses CVAR '{threshold}' as a threshold but it "
                f"declares no calibration.signal; the composite obliges it to declare "
                f"calibration.signal = '{sig_expected}' (§3.2 item 11)",
                path,
            )
        elif declared_signal != sig_expected:
            ctx.add(
                "signal_mismatch",
                f"composite '{ctx.name}' threshold CVAR '{threshold}' is calibrated "
                f"against signal '{declared_signal}' but the construct measures "
                f"'{sig_expected}'; a threshold calibrated against one signal gating "
                "another is vacuously fresh (§3.2 item 11)",
                path,
            )

        # Item 11 (cont.) — use-site signal-inputs freshness coverage.
        if sig_inputs:
            covered = ctx.covered_signal_inputs
            covered_list = covered if isinstance(covered, list) else []
            if "signal_inputs" not in ctx.ctx_keys or list(covered_list) != list(sig_inputs):
                ctx.add(
                    "unbound_signal_inputs",
                    f"composite '{ctx.name}' threshold CVAR '{threshold}' has a governing "
                    f"SignalUse.inputs {list(sig_inputs)} that is not freshness-bound: its "
                    "promotion_policy.require_calibration.hash_covered_context must include "
                    "'signal_inputs' AND the covered value must equal the use-site input "
                    "list (§3.2 item 11)",
                    path,
                )


def _check_cascade(decl: Dict[str, Any], ctx: _CompositeCtx) -> None:
    arms = decl.get("arms")
    arms_list = arms if isinstance(arms, list) else []
    if not arms_list:
        ctx.add("empty_arms", f"composite '{ctx.name}' cascade has no arms", ctx.base + ["arms"])
    gates = decl.get("gates") or []
    gates_list = gates if isinstance(gates, list) else []

    # Item 2 — cascade arity |gates| = |arms| − 1 (reused code).
    if arms_list and len(gates_list) != max(len(arms_list) - 1, 0):
        ctx.add(
            "cascade_arity",
            f"composite '{ctx.name}' declares {len(gates_list)} gate(s) for "
            f"{len(arms_list)} arm(s); |gates| must equal |arms| - 1",
            ctx.base + ["gates"],
        )

    placement = decl.get("placement", "post")  # DEFAULT post
    for g_idx, gate in enumerate(gates_list):
        if not isinstance(gate, dict):
            continue
        gpath = ctx.base + ["gates", g_idx]
        _check_gate(gate, g_idx, gpath, placement, arms_list, ctx)


def _arm_is_margin_bearing(arm: Any, composites_by_name: Dict[str, Dict[str, Any]]) -> bool:
    """§3.2 item 5: the gated arm must be margin-bearing — either a stage arm
    (RFC 0001 vote semantics) or an ensemble arm whose aggregate.kind =
    majority_vote (committee vote statistics). A loop arm, a judge_max ensemble,
    or any nested cascade (pre OR post) is NOT margin-bearing."""
    if isinstance(arm, str):
        return True  # bare = stage
    if not isinstance(arm, dict):
        return False
    if "stage" in arm:
        return True
    if "composite" in arm:
        ref = arm.get("composite")
        target = composites_by_name.get(ref) if isinstance(ref, str) else None
        if not isinstance(target, dict):
            return False  # unresolved — missing_composite_ref already fired
        if target.get("kind") != "ensemble":
            return False
        aggregate = target.get("aggregate")
        return (
            isinstance(aggregate, dict)
            and aggregate.get("kind") == "majority_vote"
        )
    return False


def _check_gate(
    gate: Dict[str, Any],
    g_idx: int,
    gpath: List[Any],
    placement: Any,
    arms_list: List[Any],
    ctx: _CompositeCtx,
) -> None:
    """Items 5, 6, 10, 11 — a composite cascade gate."""
    gkind = gate.get("kind")
    if gkind not in _GATE_KINDS:
        ctx.add(
            "unknown_gate_kind",
            f"composite '{ctx.name}' gate kind '{gkind}' is not in the v1 registry "
            "(margin_below | signal_below)",
            gpath + ["kind"],
        )
        # Unknown kind: still kind-check the threshold ref below, but skip the
        # placement/typing rules that are keyed on the (now unknown) kind.

    signal_use = gate.get("signal")
    sig_inputs: Sequence[str] = ()
    sig_expected: Optional[str] = None

    if gkind == "margin_below":
        # margin_below is POST-only and gates a margin-bearing arm.
        if placement == "pre":
            ctx.add(
                "gate_kind_placement_mismatch",
                f"composite '{ctx.name}' uses a margin_below gate under placement 'pre'; "
                "margin_below is POST-only (§3.2 item 5)",
                gpath + ["kind"],
            )
        else:
            # The gated arm of g_i (1-indexed gate i) is arm i, i.e. arms_list[g_idx].
            gated = arms_list[g_idx] if g_idx < len(arms_list) else None
            if gated is not None and not _arm_is_margin_bearing(gated, ctx.composites_by_name):
                ctx.add(
                    "gate_arm_incompatible",
                    f"composite '{ctx.name}' margin_below gate {g_idx} reads vote statistics "
                    "from a non-margin-bearing arm; the gated arm must be a stage or a "
                    "majority_vote ensemble (§3.2 item 5)",
                    gpath,
                )
        sig_expected = _CANONICAL_VOTE_MARGIN  # sig(margin_below) = vote_margin
    elif gkind == "signal_below":
        # signal_below is PRE-only and requires a declared signal.
        if placement != "pre":
            ctx.add(
                "gate_kind_placement_mismatch",
                f"composite '{ctx.name}' uses a signal_below gate under placement 'post'; "
                "signal_below is PRE-only (§3.2 item 5)",
                gpath + ["kind"],
            )
        ok, sig_name, sig_inputs = _check_signal_use(
            signal_use, gpath + ["signal"], ctx, required=True, in_state=None
        )
        if not ok and signal_use is None:
            ctx.add(
                "missing_gate_signal",
                f"composite '{ctx.name}' signal_below gate {g_idx} is missing its required "
                "signal field (§3.2 item 5)",
                gpath,
            )
        sig_expected = sig_name  # sig(signal_below g) = g.signal.signal

    _threshold_cvar_checks(
        gate.get("threshold"),
        gpath + ["threshold"],
        ctx,
        sig_expected=sig_expected,
        sig_inputs=sig_inputs,
    )


def _check_signal_use(
    signal_use: Any,
    path: List[Any],
    ctx: _CompositeCtx,
    *,
    required: bool,
    in_state: Optional[Set[str]],
) -> Tuple[bool, Optional[str], Sequence[str]]:
    """§3.2/§3.9 SignalUse. Returns (well_formed, signal_name, inputs).

    A malformed SignalUse object (missing signal, unknown keys, non-list inputs)
    rejects ``invalid_signal_use``. When ``in_state`` is provided (loop stop),
    ``inputs ⊄ state_keys`` rejects ``stop_signal_outside_state`` (item 8).
    """
    if signal_use is None:
        return (False, None, ())
    if not isinstance(signal_use, dict):
        ctx.add(
            "invalid_signal_use",
            f"composite '{ctx.name}' signal use must be an object {{signal, inputs?}}",
            path,
        )
        return (False, None, ())
    unknown = set(signal_use) - {"signal", "inputs"}
    signal_name = signal_use.get("signal")
    inputs = signal_use.get("inputs", [])
    malformed = (
        unknown
        or not isinstance(signal_name, str)
        or not isinstance(inputs, list)
    )
    if malformed:
        ctx.add(
            "invalid_signal_use",
            f"composite '{ctx.name}' signal use is malformed (missing 'signal', unknown "
            "keys, or non-list 'inputs')",
            path,
        )
        return (False, signal_name if isinstance(signal_name, str) else None, ())
    # §3.9 SignalSurface: inputs is Ident* — a non-string or non-Ident
    # element REJECTS (silent filtering would also suppress
    # unbound_signal_inputs by emptying the effective list — codex P4
    # round 1).
    bad_inputs = [
        i for i in inputs
        if not isinstance(i, str) or not _NORMATIVE_IDENT_RE.match(i)
    ]
    if bad_inputs:
        ctx.add(
            "invalid_signal_use",
            f"composite '{ctx.name}' signal use has non-Ident 'inputs' "
            f"elements (inputs is Ident*)",
            path + ["inputs"],
        )
        return (False, signal_name, ())
    inputs_list = list(inputs)
    if in_state is not None:
        outside = [i for i in inputs_list if i not in in_state]
        if outside:
            ctx.add(
                "stop_signal_outside_state",
                f"composite '{ctx.name}' stop signal reads input keys {outside} that are "
                "not declared in the loop's state_keys (§3.2 item 8)",
                path + ["inputs"],
            )
    return (True, signal_name, tuple(inputs_list))


def _check_ensemble(decl: Dict[str, Any], ctx: _CompositeCtx) -> None:
    arms = decl.get("arms")
    arms_list = arms if isinstance(arms, list) else []
    if not arms_list:
        ctx.add("empty_arms", f"composite '{ctx.name}' ensemble has no arms", ctx.base + ["arms"])

    cardinality = decl.get("cardinality")
    # Item 7 — cardinality present iff |arms| = 1.
    if len(arms_list) == 1 and cardinality is None:
        ctx.add(
            "cardinality_arity_mismatch",
            f"composite '{ctx.name}' sampling-form ensemble (|arms| = 1) requires a "
            "cardinality reference (§3.2 item 7)",
            ctx.base + ["arms"],
        )
    elif len(arms_list) > 1 and cardinality is not None:
        ctx.add(
            "cardinality_arity_mismatch",
            f"composite '{ctx.name}' committee-form ensemble (|arms| > 1) must NOT declare "
            "a cardinality (§3.2 item 7)",
            ctx.base + ["cardinality"],
        )
    if cardinality is not None:
        # Cardinality must reference a TVAR or CVAR of TVL type int.
        card_type = _ref_type(cardinality, ctx)
        if card_type is None:
            ctx.add(
                "missing_ref",
                f"composite '{ctx.name}' cardinality '{cardinality}' must resolve to a "
                "declared TVAR or CVAR (kind-checked namespace ref)",
                ctx.base + ["cardinality"],
            )
        elif card_type != "int":
            ctx.add(
                "invalid_cardinality_type",
                f"composite '{ctx.name}' cardinality '{cardinality}' has TVL type "
                f"'{card_type}'; the sample count must be int-typed (§3.2 item 7)",
                ctx.base + ["cardinality"],
            )

    aggregate = decl.get("aggregate")
    if not isinstance(aggregate, dict):
        return
    apath = ctx.base + ["aggregate"]
    akind = aggregate.get("kind")
    if akind not in _AGGREGATE_KINDS:
        ctx.add(
            "unknown_aggregate_kind",
            f"composite '{ctx.name}' aggregate kind '{akind}' is not in the v1 registry "
            "(majority_vote | judge_max)",
            apath + ["kind"],
        )
    if akind == "judge_max" and aggregate.get("judge") is None:
        ctx.add(
            "missing_judge",
            f"composite '{ctx.name}' judge_max aggregate is missing its required judge arm "
            "(§3.2)",
            apath,
        )

    accept = aggregate.get("accept")
    if isinstance(accept, dict):
        cpath = apath + ["accept"]
        stat = accept.get("stat")
        if stat not in _ACCEPT_STATS:
            ctx.add(
                "unknown_aggregate_kind",
                f"composite '{ctx.name}' accept stat '{stat}' is not in the v1 registry "
                "(vote_margin | vote_agreement)",
                cpath + ["stat"],
            )
        # sig(stat_at_least a) = a.stat (canonical vote-statistic id).
        sig_expected = stat if stat in _ACCEPT_STATS else None
        _threshold_cvar_checks(
            accept.get("threshold"),
            cpath + ["threshold"],
            ctx,
            sig_expected=sig_expected,
            sig_inputs=(),  # accept carries no SignalUse; no use-site inputs
        )


def _check_loop(decl: Dict[str, Any], ctx: _CompositeCtx) -> None:
    # Item 8 — max_iters ≥ 1 (totality). The schema pins it to an integer.
    max_iters = decl.get("max_iters")
    if isinstance(max_iters, bool) or not isinstance(max_iters, int) or max_iters < 1:
        ctx.add(
            "invalid_max_iters",
            f"composite '{ctx.name}' loop max_iters must be an integer ≥ 1 (totality, §3.2 item 8)",
            ctx.base + ["max_iters"],
        )

    state_keys_raw = decl.get("state_keys") or []
    state_keys = {k for k in state_keys_raw if isinstance(k, str)}

    stop = decl.get("stop")
    if not isinstance(stop, dict):
        return
    spath = ctx.base + ["stop"]
    skind = stop.get("kind")
    if skind not in _STOP_KINDS:
        ctx.add(
            "unknown_stop_kind",
            f"composite '{ctx.name}' stop kind '{skind}' is not in the v1 registry "
            "(signal_accept | external_accept | exhausted)",
            spath + ["kind"],
        )

    if skind == "signal_accept":
        if stop.get("threshold") is None:
            ctx.add(
                "missing_stop_threshold",
                f"composite '{ctx.name}' signal_accept stop is missing its required threshold "
                "(§3.2)",
                spath,
            )
        signal_use = stop.get("signal")
        ok, sig_name, sig_inputs = _check_signal_use(
            signal_use, spath + ["signal"], ctx, required=True, in_state=state_keys
        )
        if signal_use is None:
            ctx.add(
                "missing_stop_signal",
                f"composite '{ctx.name}' signal_accept stop is missing its required signal "
                "(§3.2)",
                spath,
            )
        # sig(signal_accept stop) = stop.signal.signal.
        if stop.get("threshold") is not None:
            _threshold_cvar_checks(
                stop.get("threshold"),
                spath + ["threshold"],
                ctx,
                sig_expected=sig_name,
                sig_inputs=sig_inputs,
            )
    elif skind == "external_accept":
        if stop.get("predicate") is None:
            ctx.add(
                "missing_stop_predicate",
                f"composite '{ctx.name}' external_accept stop is missing its required "
                "predicate (§3.2)",
                spath,
            )


def _ref_type(ref: Any, ctx: _CompositeCtx) -> Optional[str]:
    """The declared TVL type of a TVAR/CVAR namespace reference, or None if it
    resolves to neither. CVAR types carry through verbatim; TVAR types are
    normalized to the base kind (int/float/bool/enum)."""
    if not isinstance(ref, str):
        return None
    if ref in ctx.cvar_decls:
        return ctx.cvar_decls[ref].get("type")
    if ref in ctx.tvar_names:
        return ctx.tvar_types.get(ref)
    return None


def _arm_leaf_tvars(
    arm: Any, ctx: _CompositeCtx, seen: Set[str]
) -> Set[str]:
    """leafT over a single arm (§3.5). stage → its tuned_params ∩ N_T;
    composite(x) → ⋃ leafT(arms/body/judge(x)) ∪ ({cardinality(x)} ∩ N_T),
    recursively. Only TVAR-resolving identifiers are kept (C6 codomain)."""
    if isinstance(arm, str):
        return set()  # bare stage, empty tuned_params
    if not isinstance(arm, dict):
        return set()
    if "stage" in arm:
        tuned = arm.get("tuned_params") or []
        return {t for t in tuned if isinstance(t, str) and t in ctx.tvar_names}
    if "composite" in arm:
        ref = arm.get("composite")
        if not isinstance(ref, str) or ref in seen:
            return set()
        target = ctx.composites_by_name.get(ref)
        if not isinstance(target, dict):
            return set()
        return _composite_leaf_tvars(target, ctx, seen | {ref})
    return set()


def _composite_leaf_tvars(
    decl: Dict[str, Any], ctx: _CompositeCtx, seen: Set[str]
) -> Set[str]:
    """leafT(composite) — the union over its arms/body/judge plus a sampling
    ensemble's Tuned cardinality (§3.5: ({cardinality} ∩ N_T))."""
    leaves: Set[str] = set()
    for arm in _all_arms_of(decl):
        leaves |= _arm_leaf_tvars(arm, ctx, seen)
    card = decl.get("cardinality")
    if isinstance(card, str) and card in ctx.tvar_names:
        leaves.add(card)
    return leaves


def _depends_on(threshold: Any, ctx: _CompositeCtx) -> Set[str]:
    if not isinstance(threshold, str) or threshold not in ctx.cvar_decls:
        return set()
    calibration = ctx.cvar_decls[threshold].get("calibration")
    if not isinstance(calibration, dict):
        return set()
    deps = calibration.get("depends_on") or []
    return {d for d in deps if isinstance(d, str)}


def _check_composite_parents(decl: Dict[str, Any], kind: str, ctx: _CompositeCtx) -> None:
    """§3.5 — required_parents(θ) ⊆ depends_on(θ) for every threshold CVAR
    (missing_composite_parent). Purely static: both sides are declared
    TVAR-only identifier sets. Skipped for thresholds that do not resolve to a
    CVAR (already reported by missing_ref)."""

    def emit(threshold: Any, required: Set[str], path: List[Any]) -> None:
        if not isinstance(threshold, str) or threshold not in ctx.cvar_decls:
            return
        missing = required - _depends_on(threshold, ctx)
        if missing:
            ctx.add(
                "missing_composite_parent",
                f"composite '{ctx.name}' threshold CVAR '{threshold}' omits required parent "
                f"TVAR(s) {sorted(missing)} from its calibration.depends_on; the arm(s) the "
                "gate observes are parameterized by them (§3.5)",
                path,
            )

    if kind == "cascade":
        arms = decl.get("arms")
        arms_list = arms if isinstance(arms, list) else []
        gates = decl.get("gates") or []
        gates_list = gates if isinstance(gates, list) else []
        placement = decl.get("placement", "post")
        # leafT per arm (index-aligned).
        arm_leaves = [_arm_leaf_tvars(a, ctx, set()) for a in arms_list]
        for g_idx, gate in enumerate(gates_list):
            if not isinstance(gate, dict):
                continue
            if placement == "pre":
                # required_parents(θ_i) = leafT(a_i) — the arm the gate admits.
                required = arm_leaves[g_idx] if g_idx < len(arm_leaves) else set()
            else:
                # required_parents(θ_i) = leafT(a₁) ∪ … ∪ leafT(a_i) — the
                # observed prefix (gate g_i reads a_i and prior arms).
                required = set().union(*arm_leaves[: g_idx + 1]) if arm_leaves else set()
            emit(gate.get("threshold"), required, ctx.base + ["gates", g_idx, "threshold"])
    elif kind == "ensemble":
        aggregate = decl.get("aggregate")
        if not isinstance(aggregate, dict):
            return
        accept = aggregate.get("accept")
        if not isinstance(accept, dict):
            return
        # required_parents(θ) = ⋃_j leafT(a_j) ∪ leafT(judge) ∪ ({cardinality} ∩ N_T).
        required = _composite_leaf_tvars(decl, ctx, set())
        emit(
            accept.get("threshold"),
            required,
            ctx.base + ["aggregate", "accept", "threshold"],
        )
    elif kind == "loop":
        stop = decl.get("stop")
        if not isinstance(stop, dict) or stop.get("kind") != "signal_accept":
            return
        # required_parents(θ in Loop.stop) = leafT(body).
        required = _arm_leaf_tvars(decl.get("body"), ctx, set())
        emit(stop.get("threshold"), required, ctx.base + ["stop", "threshold"])


def _lint_namespace(doc: Dict[str, Any], issues: List[Issue]) -> None:
    """RFC 0001 §3.7 — ONE shared declaration namespace + prefix collisions."""
    entries: List[Tuple[str, str, List[Any]]] = []  # (name, block, path)
    for block in ("tvars", "cvars", "policies"):
        decls = doc.get(block) or []
        if not isinstance(decls, list):
            continue
        for idx, decl in enumerate(decls):
            if isinstance(decl, dict) and isinstance(decl.get("name"), str):
                entries.append((decl["name"], block, [block, idx, "name"]))

    by_name: Dict[str, List[Tuple[str, List[Any]]]] = {}
    for name, block, path in entries:
        by_name.setdefault(name, []).append((block, path))
    for name, occurrences in by_name.items():
        blocks = {block for block, _ in occurrences}
        if len(occurrences) > 1 and len(blocks) > 1:
            code = (
                "cvar_shadows_tvar"
                if blocks >= {"tvars", "cvars"}
                else "policy_name_conflict"
            )
            issues.append(
                {
                    "code": code,
                    "message": (
                        f"'{name}' is declared in multiple blocks "
                        f"({', '.join(sorted(blocks))}) — tvars, cvars, and policies "
                        "share one namespace"
                    ),
                    "path": occurrences[-1][1],
                    "severity": "error",
                }
            )

    severity = "error" if _uses_11_constructs(doc) else "warning"
    unique_names = sorted(by_name)
    for shorter in unique_names:
        prefix = shorter + "."
        if any(longer.startswith(prefix) for longer in unique_names):
            issues.append(
                {
                    "code": "namespace_prefix_collision",
                    "message": (
                        f"'{shorter}' is a strict dotted prefix of another declared "
                        "name; attribute-style access becomes ambiguous"
                    ),
                    "path": by_name[shorter][0][1],
                    "severity": severity,
                }
            )


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
    cvar_names = {
        d.get("name")
        for d in (doc.get("cvars") or [])
        if isinstance(d, dict) and isinstance(d.get("name"), str)
    }
    return TypeContext(
        gamma=gamma,
        environment_symbols=environment_symbols,
        issues=issues,
        clause_ids={},
        cvar_names=cvar_names,
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
        if isinstance(value, str):
            # str.isdigit() is False for signed integers ('-5'), wrongly rejecting
            # negative int-domain values while the float branch accepts them
            # (issue #50). Validate against the normative -?[0-9]+ grammar
            # (not bare int(), which also admits '1_000' and ' 5 ') before
            # parsing the sign.
            if not _INT_LITERAL_RE.fullmatch(value):
                raise ValueError("not an int")
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
        if literal.ident in context.cvar_names:
            # RFC 0001 §3.2/P5: cvars are governed but NOT searched — they
            # never enter Γ or the SAT encoding. Precise diagnostic, not the
            # generic undeclared_tvar.
            add(
                {
                    "code": "cvar_in_structural_constraint",
                    "message": (
                        f"Structural constraint references CVAR '{literal.ident}' — "
                        "calibrated variables are governed but not searched; "
                        "substitute as a constant if intended"
                    ),
                    "path": path,
                    "severity": "error",
                }
            )
            return
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
            if other is None and rhs_raw in context.cvar_names:
                # RFC 0001 §3.2/P5: CVAR referenced on the RHS of a TVAR
                # equality — same precise diagnostic as the LHS path.
                add(
                    {
                        "code": "cvar_in_structural_constraint",
                        "message": (
                            f"Structural constraint references CVAR '{rhs_raw}' — "
                            "calibrated variables are governed but not searched; "
                            "substitute as a constant if intended"
                        ),
                        "path": path,
                        "severity": "error",
                    }
                )
                return
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

    _lint_require_calibration(policy, issues)

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


def _lint_require_calibration(policy: Dict[str, Any], issues: List[Issue]) -> None:
    """RFC 0001 §3.5 — strict evidence mode declaration. The mandatory
    ctx_core is implicit and immutable; hash_covered_context selects
    EXTENSION keys only (a key outside the enum is an error)."""
    spec = policy.get("require_calibration")
    if spec is None:
        return
    if not isinstance(spec, dict) or not isinstance(spec.get("enabled"), bool):
        issues.append(
            {
                "code": "invalid_require_calibration",
                "message": "promotion_policy.require_calibration requires a boolean 'enabled'",
                "path": ["promotion_policy", "require_calibration"],
                "severity": "error",
            }
        )
        return
    context_keys = spec.get("hash_covered_context")
    if context_keys is None:
        return
    if not isinstance(context_keys, list):
        issues.append(
            {
                "code": "invalid_calibration_context",
                "message": "hash_covered_context must be a list of extension keys",
                "path": ["promotion_policy", "require_calibration", "hash_covered_context"],
                "severity": "error",
            }
        )
        return
    for idx, key in enumerate(context_keys):
        if key not in _CTX_EXT_KEYS:
            issues.append(
                {
                    "code": "invalid_calibration_context",
                    "message": (
                        f"'{key}' is not a freshness-context EXTENSION key; the "
                        "mandatory core is implicit and not module-configurable"
                    ),
                    "path": [
                        "promotion_policy",
                        "require_calibration",
                        "hash_covered_context",
                        idx,
                    ],
                    "severity": "error",
                }
            )
    if len(context_keys) != len(set(context_keys)):
        issues.append(
            {
                "code": "invalid_calibration_context",
                "message": "hash_covered_context keys must be unique",
                "path": ["promotion_policy", "require_calibration", "hash_covered_context"],
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

    exact_alignment_precision = _compute_exact_alignment_precision([resolution])
    suggestion = (
        f" Suggested exact-alignment precision: P={exact_alignment_precision}."
        if exact_alignment_precision is not None
        else " Use exact rational or index encoding because an aligned integer precision could not be established."
    )
    return {
        "code": "inadequate_precision",
        "severity": "warning",
        "message": (
            f"TVAR '{name}' has resolution {resolution} which is not "
            f"aligned to precision P={precision}. SMT encoding "
            f"soundness (Theorem 8.1) may not hold."
            f"{suggestion}"
        ),
        "path": ["tvars", idx, "domain"],
        "formal_property": "Domain is not precision-aligned per Definition 8.5",
        "current_precision": precision,
        # Retained for diagnostic-output compatibility; the value now means the
        # least integer factor that exactly aligns the parsed decimal values.
        "minimum_precision": exact_alignment_precision,
        "suggested_precision": exact_alignment_precision,
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

    exact_alignment_precision = _compute_exact_alignment_precision(values)
    suggestion = (
        f" Suggested exact-alignment precision: P={exact_alignment_precision}."
        if exact_alignment_precision is not None
        else " Use exact rational or index encoding because an aligned integer precision could not be established."
    )

    return {
        "code": "inadequate_precision",
        "severity": "warning",
        "message": (
            f"TVAR '{name}' has domain values that collide under "
            f"precision P={precision}. Values {collision[0]} and "
            f"{collision[1]} both map to {collision[2]}. "
            f"SMT encoding soundness (Theorem 8.1) does not hold."
            f"{suggestion}"
        ),
        "path": ["tvars", idx, "domain"],
        "formal_property": "Domain is not precision-aligned per Definition 8.5",
        "current_precision": precision,
        # Retained for diagnostic-output compatibility; see the resolution
        # diagnostic above.
        "minimum_precision": exact_alignment_precision,
        "suggested_precision": exact_alignment_precision,
        "collision_example": {
            "value1": collision[0],
            "value2": collision[1],
            "scaled": collision[2],
        },
    }


def _compute_exact_alignment_precision(values: Sequence[float]) -> Optional[int]:
    """Return the least integer factor that aligns parsed decimal values exactly.

    The values arrive from YAML as Python numbers, so ``str(value)`` is used to
    recover their shortest decimal representation. The least common multiple of
    those exact decimal denominators aligns every value. A smallest-gap rule is
    insufficient because separating adjacent values does not make them integers
    after scaling.
    """
    precision = 1
    try:
        for value in values:
            precision = lcm(precision, Fraction(str(value)).denominator)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    return precision
