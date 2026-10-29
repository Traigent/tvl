from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field as dataclass_field
from fractions import Fraction
from math import lcm
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .model import ExactLiteralLimitError, exact_number_or_none
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
_NON_LINEAR_TOKENS_DERIVED = {"/", "^"}


def lint_module(
    doc: Dict[str, Any],
    precision: int = 1000,
    *,
    floor_provenance: Optional[Sequence[Dict[str, Any]]] = None,
    checker_registry: Optional[Dict[str, Sequence[str]]] = None,
) -> List[Issue]:
    """Lint a TVL module for errors and warnings.

    Args:
        doc: The TVL module document
        precision: Float precision factor for SMT encoding (default 1000)
        floor_provenance: Optional pack floor provenance records from tvl-compose
        checker_registry: Optional customer checker label registry for compile-time checks

    Returns:
        List of issues (errors and warnings)
    """
    from .diagnostics import runtime_syntax_issues

    syntax = runtime_syntax_issues(doc) if _uses_13_constructs(doc) else []
    if syntax:
        return syntax
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
    if _uses_13_constructs(doc):
        runtime_start = len(issues)
        _lint_runtime_version(doc, issues)
        _lint_requirements(doc, issues, checker_registry=checker_registry)
        _lint_monitors(doc, issues, is_pack=False, floor_provenance=floor_provenance)
        _lint_responses(doc, issues)
        _address_runtime_issues(issues, runtime_start)
    # Add formal verification scope warnings
    issues.extend(check_formal_verification_scope(doc, precision))
    return issues


def lint_pack(
    doc: Dict[str, Any],
    *,
    checker_registry: Optional[Dict[str, Sequence[str]]] = None,
) -> List[Issue]:
    """Lint a TVL 1.3 pack document (RFC 0003 §5.1, §11.2)."""
    from .diagnostics import runtime_syntax_issues

    syntax = runtime_syntax_issues(doc)
    if syntax:
        return syntax
    issues: List[Issue] = []
    pack_block = doc.get("pack")
    if not isinstance(pack_block, dict) or not isinstance(pack_block.get("module"), str) or not _NORMATIVE_IDENT_RE.match(pack_block["module"]):
        issues.append(
            {
                "code": "runtime_invalid_profile",
                "message": "pack.module must be a valid TVL module identifier",
                "path": ["pack", "module"],
                "severity": "error",
            }
        )
    if "requirements" not in doc or not isinstance(doc.get("requirements"), list):
        issues.append(
            {
                "code": "runtime_invalid_profile",
                "message": "tvl_pack requires a 'requirements' list",
                "path": ["requirements"],
                "severity": "error",
            }
        )
    if "monitors" not in doc or not isinstance(doc.get("monitors"), list):
        issues.append(
            {
                "code": "runtime_invalid_profile",
                "message": "tvl_pack requires a 'monitors' list",
                "path": ["monitors"],
                "severity": "error",
            }
        )
    _lint_runtime_version(doc, issues)
    _lint_requirements(doc, issues, checker_registry=checker_registry)
    _lint_monitors(doc, issues, is_pack=True)
    _lint_responses(doc, issues)
    _address_runtime_issues(issues)
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
    ctx_keys: Set[str] = dataclass_field(default_factory=set)
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
        # composite-tagged arm is a closure bypass.
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
    # unbound_signal_inputs by emptying the effective list).
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
    if akind == "judge_max" and accept is not None:
        ctx.add(
            "accept_over_judge_max",
            f"composite '{ctx.name}' has an accept block over a judge_max aggregate; "
            "judge_max takes no vote, so there is no vote statistic to read "
            "(RFC 0002 errata 2026-10-25)",
            apath + ["accept"],
        )
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
            non_finite = _first_non_finite(domain_spec)
            if non_finite is not None:
                bad_path, bad_value = non_finite
                issues.append(
                    {
                        "code": "non_finite_domain_value",
                        "message": (
                            f"TVAR '{name}' domain contains {bad_value!r}; numeric domains are "
                            "rationals (formal semantics Definitions 3.1-3.2), so NaN and "
                            "infinities are not admitted"
                        ),
                        "path": ["tvars", idx, "domain"] + bad_path,
                        "severity": "error",
                    }
                )
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


def _first_non_finite(node: Any) -> Optional[Tuple[List[Any], float]]:
    """(relative path, value) of the first NaN/infinite float inside ``node``, else None."""
    stack: List[Tuple[Any, List[Any]]] = [(node, [])]
    # Containers already expanded, by identity, so an alias cycle (``&d [*d]``) terminates.
    seen: set = set()
    while stack:
        current, path = stack.pop()
        if isinstance(current, float) and not math.isfinite(current):
            return path, current
        if isinstance(current, (dict, list, tuple)):
            if id(current) in seen:
                continue
            seen.add(id(current))
        if isinstance(current, dict):
            stack.extend((v, path + [k]) for k, v in current.items())
        elif isinstance(current, (list, tuple)):
            stack.extend((v, path + [i]) for i, v in enumerate(current))
    return None


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


def _report_duplicate_members(
    name: str, values: List[Any], path: List[Any], issues: List[Issue], where: str = ""
) -> None:
    """Append ``duplicate_domain_value`` when ``values`` repeats a member (issues #24, #202)."""
    try:
        has_duplicate = len(values) != len(set(values))
    except TypeError:
        # Unhashable members cannot be compared as a set; the type checks elsewhere report them.
        return
    if has_duplicate:
        counts: Dict[Any, int] = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1
        repeated = sorted({str(v) for v, n in counts.items() if n > 1})
        issues.append(
            {
                "code": "duplicate_domain_value",
                "message": f"TVAR '{name}'{where} domain contains duplicate value(s): {repeated}",
                "path": path,
                "severity": "error",
            }
        )


def _lint_tuple_components(name: str, components: List[Any], path: List[Any], issues: List[Issue]) -> None:
    """Lint each tuple component for empty, duplicate and reversed domains (issues #202, #203).

    Mirrors the key precedence of ``model._resolve_component_values``: ``values``, ``set``,
    ``range``, nested ``components``, then ``registry`` (resolved externally, never linted).

    Nested ``components`` are walked with an explicit stack and each list is visited once, by
    identity: YAML aliases can make a tiny document stand for a cyclic or exponentially shared
    structure, and a deep one would exhaust the interpreter stack if walked recursively.
    """
    seen: Set[int] = set()
    stack: List[Tuple[List[Any], List[Any]]] = [(components, path)]
    while stack:
        current, current_path = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        _lint_tuple_component_list(name, current, current_path, issues, stack, seen)


def _range_component_is_valid(name: str, idx: int, bounds: Any, comp_path: List[Any], issues: List[Issue]) -> bool:
    """Report a malformed or reversed tuple-component ``range``; True when it is usable.

    A usable range always resolves to at least ``lo`` itself (the grid starts at ``lo``), so an
    integer-free range such as ``[1.2, 1.8]`` is never empty here, unlike a bare ``int`` TVAR.
    """
    try:
        if not (isinstance(bounds, list) and len(bounds) == 2):
            raise ValueError("range must specify [min, max]")
        lo, hi = float(bounds[0]), float(bounds[1])
        if not (math.isfinite(lo) and math.isfinite(hi)):
            raise ValueError("range bounds must be finite")
        reversed_range = lo > hi
    except (TypeError, ValueError):
        message = f"TVAR '{name}' component {idx} range must be two finite numeric bounds [min, max]"
    else:
        if not reversed_range:
            return True
        message = f"TVAR '{name}' component {idx} range has min > max ({bounds[0]} > {bounds[1]})"
    issues.append(
        {"code": "invalid_range_domain", "message": message, "path": comp_path + ["range"], "severity": "error"}
    )
    return False


def _queue_nested_components(
    name: str,
    idx: int,
    comp: Dict[str, Any],
    comp_path: List[Any],
    issues: List[Issue],
    stack: List[Tuple[List[Any], List[Any]]],
) -> None:
    if not isinstance(comp["components"], list) or not comp["components"]:
        issues.append(
            {
                "code": "invalid_tuple_domain",
                "message": f"TVAR '{name}' component {idx} tuple domain must define a non-empty 'components' list",
                "path": comp_path + ["components"],
                "severity": "error",
            }
        )
        return
    stack.append((comp["components"], comp_path + ["components"]))


def _lint_tuple_component_list(
    name: str,
    components: List[Any],
    path: List[Any],
    issues: List[Issue],
    stack: List[Tuple[List[Any], List[Any]]],
    seen: Set[int],
) -> None:
    for idx, comp in enumerate(components):
        comp_path = path + [idx]
        members: Any = None
        if isinstance(comp, list):
            members = comp
        elif isinstance(comp, dict):
            if "values" in comp:
                members = comp["values"]
            elif "set" in comp:
                members = comp["set"]
            elif "range" in comp:
                if "registry" in comp and "components" not in comp:
                    # The model resolves an unusable range through ``registry`` (external).
                    continue
                if _range_component_is_valid(name, idx, comp["range"], comp_path, issues):
                    continue
                # An unusable range makes the model fall through to ``components``
                # (``model._resolve_component_values``), so lint them as well.
                if "components" in comp:
                    _queue_nested_components(name, idx, comp, comp_path, issues, stack)
                continue
            elif "components" in comp:
                _queue_nested_components(name, idx, comp, comp_path, issues, stack)
                continue
            # Any other shape (no recognised key, non-list ``values``) is the schema stage's to
            # reject; it is not linted here.
        if not isinstance(members, list):
            continue
        if members and id(members) in seen:
            # The same member list reached through an alias is checked once, so a few
            # aliases of one large list cannot multiply the work.
            continue
        seen.add(id(members))
        if not members:
            issues.append(
                {
                    "code": "empty_domain",
                    "message": f"TVAR '{name}' component {idx} has an empty domain",
                    "path": comp_path,
                    "severity": "error",
                }
            )
            continue
        _report_duplicate_members(name, members, comp_path, issues, f" component {idx}")


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
                # Tuple domains are products; we don't enumerate them during linting, but
                # each component is checked on its own (issues #202, #203).
                _lint_tuple_components(name, components, path + ["domain", "components"], issues)
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
        if len(parsed) != len(set(parsed)):
            # Issue #24: a repeated enum/callable domain member silently
            # collapsed into one arm (inflated cardinality, wasted trial
            # budget, ambiguous encode/decode) with no diagnostic.
            issues.append(
                {
                    "code": "duplicate_domain_value",
                    "message": f"TVAR '{name}' domain contains duplicate value(s): "
                    f"{sorted({str(v) for v in parsed if parsed.count(v) > 1})}",
                    "path": path + ["domain"],
                    "severity": "error",
                }
            )
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
                coerced_values: List[Any] = []
                for item in parsed:
                    try:
                        coerced_values.append(_coerce_numeric(item, kind))
                    except ValueError:
                        issues.append(
                            {
                                "code": "invalid_numeric_domain",
                                "message": f"TVAR '{name}' domain value {item!r} is not a valid {kind}",
                                "path": path + ["domain"],
                                "severity": "error",
                            }
                        )
                _report_duplicate_members(name, coerced_values, path + ["domain"], issues)
                converted.update(coerced_values)
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
                if (
                    kind == "int"
                    and minimum is not None
                    and maximum is not None
                    and minimum <= maximum
                    and math.isfinite(minimum)
                    and math.isfinite(maximum)
                    and math.ceil(minimum) > math.floor(maximum)
                ):
                    # Issue #203: min <= max but no integer lies between them
                    # (e.g. [1.2, 1.8]), so the domain is empty.
                    issues.append(
                        {
                            "code": "empty_domain",
                            "message": f"TVAR '{name}' int range [{minimum}, {maximum}] contains no integer",
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
            coerced_list: List[Any] = []
            for item in parsed:
                try:
                    coerced_list.append(_coerce_numeric(item, kind))
                    converted.add(coerced_list[-1])
                except ValueError:
                    issues.append(
                        {
                            "code": "invalid_numeric_domain",
                            "message": f"TVAR '{name}' domain value {item!r} is not a valid {kind}",
                            "path": path + ["domain"],
                            "severity": "error",
                        }
                    )
            _report_duplicate_members(name, coerced_list, path + ["domain"], issues)
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
            issues.append(
                {
                    "code": "malformed_structural_constraint",
                    "message": f"Structural constraint at index {idx} must be an object, got {clause!r}",
                    "path": ["constraints", "structural", idx],
                    "severity": "error",
                }
            )
            continue

        when_expr = clause.get("when")
        then_expr = clause.get("then")
        expr_expr = clause.get("expr")
        extra_keys = set(clause.keys()) - {"when", "then", "expr"}
        has_when_then = when_expr is not None and then_expr is not None
        has_expr = expr_expr is not None
        # Mirror the schema's oneOf({when,then} | {expr}) + additionalProperties:
        # false: reject a non-dict entry, an entry missing one side of when/then,
        # an entry carrying both when/then AND expr, or an unrecognised key — the
        # exact malformed shape the compilers now raise on (issue #15). Without
        # this, tvl-lint (the one gateless first-class CLI) stayed clean on a
        # module whose declared constraint is never enforced.
        if extra_keys or has_when_then == has_expr:
            issues.append(
                {
                    "code": "malformed_structural_constraint",
                    "message": (
                        f"Structural constraint at index {idx} does not match the required "
                        f"{{when, then}} or {{expr}} shape (extra keys: {sorted(extra_keys)!r}): {clause!r}"
                    ),
                    "path": ["constraints", "structural", idx],
                    "severity": "error",
                }
            )
            continue

        for field in ("when", "then", "expr"):
            expr = clause.get(field)
            expr_path = ["constraints", "structural", idx, field]
            _check_structural_expression(expr, expr_path, context, issues)


def _supports_ordering(type_info: "TypeInfo") -> bool:
    """T-Cmp: ordering needs elem(tau) in {int, float}; numeric enums qualify, string/bool enums do not."""
    if type_info.kind in {"int", "float"}:
        return True
    if type_info.kind == "enum":
        values = type_info.domain_values
        return bool(values) and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in values
        )
    return False


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
        if not _supports_ordering(type_info):
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
                            "message": f"TVAR '{literal.ident}' ({type_info.raw_type}) is not compatible with '{rhs_raw}' ({other.raw_type})",
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
        if op in {"<", "<=", ">", ">="} and not _supports_ordering(type_info):
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
            if kind == "int" and isinstance(value, float) and not isinstance(value, bool):
                # T-Cmp requires the literal to have type elem(int) = int; a fractional
                # literal has type float, so it is the fractionality that is wrong.
                message = (
                    f"Fractional literal {value!r} cannot be compared with int TVAR "
                    f"'{type_info.name}' (T-Cmp requires an integer literal)"
                )
            else:
                message = f"Expected numeric literal for TVAR '{type_info.name}', got {value!r}"
            issues.append(
                {
                    "code": "constraint_type_mismatch",
                    "message": message,
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
def _split_type_args(raw: str) -> Optional[List[str]]:
    """Top-level comma-separated component types of ``tuple[...]``; None if not parseable."""
    text = raw.strip()
    if not text.startswith("tuple[") or not text.endswith("]"):
        return None
    inner = text[len("tuple["):-1]
    parts: List[str] = []
    depth = 0
    cur = ""
    for ch in inner:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _canonical_type(raw: str) -> Optional[str]:
    """Whitespace-free spelling of a declared type, with tuple components canonicalised.

    Returns None when a ``tuple[...]`` cannot be split into components.
    """
    text = "".join(raw.split())
    if text.lower().startswith("tuple["):
        parts = _split_type_args(text)
        if parts is None:
            return None
        canon = [_canonical_type(part) for part in parts]
        if any(part is None for part in canon):
            return None
        return "tuple[" + ",".join(canon) + "]"  # type: ignore[arg-type]
    if text.lower().startswith("callable["):
        return "callable[" + text[len("callable["):]  # the protocol identifier keeps its case
    return text.lower()


def _elem_type(raw: str) -> Optional[str]:
    """Definition 4.2: elem(enum[τ]) = τ; every other type is its own element type."""
    canon = _canonical_type(raw)
    if canon is not None and canon.startswith("enum[") and canon.endswith("]"):
        return canon[len("enum["):-1]
    return canon


def _component_types_compatible(left: str, right: str) -> bool:
    """T-TupleVarEq: both tuples have the same type tuple[τ₁,...,τₙ] (same arity and τᵢ)."""
    lc, rc = _canonical_type(left), _canonical_type(right)
    if lc is None or rc is None:
        return True  # unparseable tuple types are reported elsewhere
    return lc == rc


def _are_types_compatible(lhs: TypeInfo, rhs: TypeInfo) -> bool:
    """Whether ``x = y`` between two TVARs is well-typed (formal semantics §4.6-4.7).

    Scalars follow T-TVarEq, elem(τ) = elem(τ'), so ``int = enum[int]`` is
    well-typed while ``int = float`` and ``enum[str] = enum[int]`` are not: the
    typing rules have no numeric widening. Tuples follow T-TupleVarEq.
    """
    if lhs.kind == "tuple" or rhs.kind == "tuple":
        if lhs.kind != rhs.kind:
            return False
        return _component_types_compatible(lhs.raw_type, rhs.raw_type)
    left, right = _elem_type(lhs.raw_type), _elem_type(rhs.raw_type)
    return left is not None and left == right


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

    # An omitted alpha takes the documented default (0.05); an explicit value,
    # including null, must still be a number in (0, 1).
    alpha = policy.get("alpha", 0.05)
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

    # Issue #24: the forward check above only asserts every objective HAS a
    # min_effect entry; it never checked the reverse — that every min_effect
    # KEY names a real objective. A stale/renamed/typo'd key (e.g.
    # 'ghost_typo') was silently accepted with no effect. Declared names
    # include banded objectives too (their `direction` need not be a plain
    # string), so a min_effect entry for a banded objective is not orphaned.
    declared_names = {
        objective.get("name")
        for objective in objectives
        if isinstance(objective, dict) and isinstance(objective.get("name"), str)
    }
    for key in min_effect:
        if isinstance(key, str) and key not in declared_names:
            issues.append(
                {
                    "code": "unknown_min_effect_objective",
                    "message": f"promotion_policy.min_effect['{key}'] does not name a declared objective",
                    "path": ["promotion_policy", "min_effect", key],
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
    - outside_proved_subset: cvars / policies / composites declarations

    Args:
        doc: The TVL module document
        precision: The precision factor P for float scaling (default 1000)

    Returns:
        List of warning issues
    """
    issues: List[Issue] = []

    # outside_proved_subset: one warning per construct family that the Lean
    # proof tree (proofs/TVL/*.lean) does not model. Callable domains are
    # covered by unverifiable_callable_type below, so they are not repeated.
    issues.extend(_outside_proved_subset_issues(doc))

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

        # W6003: Inadequate precision for float domains (a non-finite domain is already an
        # error, non_finite_domain_value; its grid has no precision to judge).
        if (
            isinstance(raw_type, str)
            and raw_type.strip().lower() == "float"
            and _first_non_finite(domain_spec) is None
        ):
            precision_issue = _check_float_precision(name, domain_spec, precision, idx)
            if precision_issue is not None:
                issues.append(precision_issue)

    return issues


_OUTSIDE_PROVED_SUBSET_FAMILIES = (
    ("cvars", "cvars (RFC 0001 calibrated variables)"),
    ("policies", "policies (RFC 0001)"),
    ("composites", "composites (RFC 0002)"),
)


def _outside_proved_subset_issues(doc: Dict[str, Any]) -> List[Issue]:
    """Warn once per declared construct family absent from the Lean proofs.

    Presence of at least one declaration triggers the warning; an empty or
    absent section does not. See proofs/PROOF_SUMMARY.md (coverage note).
    """
    out: List[Issue] = []
    for key, label in _OUTSIDE_PROVED_SUBSET_FAMILIES:
        value = doc.get(key)
        if not isinstance(value, list) or not value:
            continue
        out.append({
            "code": "outside_proved_subset",
            "severity": "info",
            "message": (
                f"Module uses {label}, which is outside the machine-proved "
                "(Lean) subset. Proved guarantees (type soundness, SMT "
                "encoding soundness) do not cover this construct. See "
                "proofs/PROOF_SUMMARY.md."
            ),
            "path": [key],
            "construct": key,
            "formal_property": f"No Lean model of {key} exists in proofs/TVL",
        })
    return out


def _check_float_precision(
    name: str,
    domain_spec: Any,
    precision: int,
    idx: int,
) -> Optional[Issue]:
    """Check that a float domain is precision-aligned (formal semantics Definition 8.6).

    A float domain D is precision-aligned to P iff every value is an integer
    after scaling, in exact arithmetic:

        ∀v ∈ D: v · P ∈ ℤ

    Values are read as the exact decimals they were written as (``str(v)``),
    not as their binary floating-point approximations. A range domain's
    values are ``a + k·r`` for its effective resolution ``r`` (semantics §2.4:
    the given resolution, or 0.001 for a float range without one), so it is
    aligned iff ``r·P`` and ``a·P`` are integers. Alignment implies that
    scaling is injective (Lemma 8.2), so collisions are reported only as the
    most specific form of a misalignment.
    """
    if domain_spec is None:
        return None
    if isinstance(domain_spec, dict) and "range" in domain_spec:
        return _check_range_alignment(domain_spec, precision, name, idx)
    if isinstance(domain_spec, dict):
        domain_spec = domain_spec.get("set", [])
    return _check_values_alignment(_extract_numeric_list(domain_spec), precision, name, idx)


def _exact_decimal(value: Any) -> Optional[Fraction]:
    """The exact rational a YAML number was written as; None if it has none.

    A float whose YAML source lexeme was retained (one binary64 cannot hold, such as
    ``0.100000000000000001``) is read from that lexeme, never from ``str(value)``.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return exact_number_or_none(value)
    except (ValueError, ZeroDivisionError, OverflowError, ExactLiteralLimitError):
        return None


def _is_aligned(value: Fraction, precision: int) -> bool:
    return (value * precision).denominator == 1


def _extract_numeric_list(items: Any) -> List[float]:
    """Extract numeric values from a list."""
    values: List[float] = []
    if not isinstance(items, list):
        return values
    for v in items:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            values.append(v)
    return values


def _check_values_alignment(
    values: List[float],
    precision: int,
    name: str,
    idx: int,
) -> Optional[Issue]:
    """Definition 8.6 on a finite set of values."""
    misaligned = None
    for v in values:
        exact = _exact_decimal(v)
        if exact is not None and not _is_aligned(exact, precision):
            misaligned = (v, exact)
            break
    if misaligned is None:
        return None

    collision_issue = _check_value_collisions(values, precision, name, idx)
    if collision_issue is not None:
        return collision_issue

    exact_alignment_precision = _compute_exact_alignment_precision(values)
    value, exact = misaligned
    return {
        "code": "inadequate_precision",
        "severity": "warning",
        "message": (
            f"TVAR '{name}' has domain value {value} which is not aligned to "
            f"precision P={precision}: {value} × {precision} = {float(exact * precision)} "
            f"is not an integer. SMT encoding soundness (Theorem 8.1) does not hold."
            f"{_precision_suggestion(exact_alignment_precision)}"
        ),
        "path": ["tvars", idx, "domain"],
        "formal_property": _PRECISION_ALIGNED_PROPERTY,
        "current_precision": precision,
        # Retained for diagnostic-output compatibility; see the resolution
        # diagnostic below.
        "minimum_precision": exact_alignment_precision,
        "suggested_precision": exact_alignment_precision,
        "misaligned_value": value,
    }


_PRECISION_ALIGNED_PROPERTY = "Domain is not precision-aligned per Definition 8.6"
_DEFAULT_FLOAT_RESOLUTION = Fraction(1, 1000)  # formal semantics §2.4, effective resolution


def _precision_suggestion(exact_alignment_precision: Optional[int]) -> str:
    if exact_alignment_precision is not None:
        return f" Suggested exact-alignment precision: P={exact_alignment_precision}."
    return " Use exact rational or index encoding because an aligned integer precision could not be established."


def _check_range_alignment(
    domain_spec: Dict[str, Any],
    precision: int,
    name: str,
    idx: int,
) -> Optional[Issue]:
    """Definition 8.6 on a range domain: its values are a + k·r for k ≥ 0 with a + k·r ≤ b."""
    range_vals = domain_spec.get("range", [])
    if not isinstance(range_vals, list) or len(range_vals) != 2:
        return None
    low, high = _exact_decimal(range_vals[0]), _exact_decimal(range_vals[1])
    if low is None or high is None:
        return None

    raw_resolution = domain_spec.get("resolution")
    if raw_resolution is None:
        res: Optional[Fraction] = _DEFAULT_FLOAT_RESOLUTION
    else:
        res = _exact_decimal(raw_resolution)
    if res is None or res <= 0:
        return None

    if high - low >= res and not _is_aligned(res, precision):
        return _check_resolution_alignment(res, precision, name, idx, implicit=raw_resolution is None)
    if not _is_aligned(low, precision):
        return _check_values_alignment([range_vals[0]], precision, name, idx)
    return None


def _check_resolution_alignment(
    resolution: Fraction,
    precision: int,
    name: str,
    idx: int,
    *,
    implicit: bool = False,
) -> Issue:
    """Issue for a range whose (effective) resolution r has r·P ∉ ℤ."""
    exact_alignment_precision = _compute_exact_alignment_precision([resolution])
    shown = float(resolution)
    described = f"the default resolution {shown} for float ranges" if implicit else f"resolution {shown}"
    return {
        "code": "inadequate_precision",
        "severity": "warning",
        "message": (
            f"TVAR '{name}' has {described} which is not "
            f"aligned to precision P={precision}. SMT encoding "
            f"soundness (Theorem 8.1) may not hold."
            f"{_precision_suggestion(exact_alignment_precision)}"
        ),
        "path": ["tvars", idx, "domain"],
        "formal_property": _PRECISION_ALIGNED_PROPERTY,
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
        "formal_property": _PRECISION_ALIGNED_PROPERTY,
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


def _compute_exact_alignment_precision(values: Sequence[Any]) -> Optional[int]:
    """Return the least integer factor that aligns parsed decimal values exactly.

    A ``Fraction`` is used as is; a YAML number is read as the exact decimal it was written
    as (its retained lexeme when binary64 could not hold it). The least common multiple of
    those exact decimal denominators aligns every value. A smallest-gap rule is
    insufficient because separating adjacent values does not make them integers
    after scaling.
    """
    precision = 1
    try:
        for value in values:
            exact = value if isinstance(value, Fraction) else _exact_decimal(value)
            if exact is None:
                return None
            precision = lcm(precision, exact.denominator)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    return precision


# -----------------------------------------------------------------------------
# TVL 1.3 Runtime Lints (RFC 0003 §4, §5, §7, §9, §10, §11)
# -----------------------------------------------------------------------------

_RUNTIME_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CODE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_CUSTOMER_CHECKER_RE = re.compile(r"^customer:[A-Za-z_][A-Za-z0-9_]*$")

_REQ_KINDS = {"rate_bound", "zero_tolerance", "recovery_time", "evidence_liveness", "aggregate_bound"}
_AGG_OPS = {"sum", "mean"}
_AGG_METRICS = {"cost_usd", "score"}
_AGG_BOUNDS = ("lte", "gte")
_PRIMARY_ROLES = {"primary_rate", "primary_zero", "primary_aggregate"}
_PERSIST_EVENTS = {"episode_opened", "episode_continued"}
_PERSIST_MAX = 168
_UNIT_KINDS = {"trace", "invocation"}
_ALL_UNIT_KINDS = {"trace", "invocation", "episode", "window"}
_METRICS = {"wall_clock_latency_ms", "cost_usd", "total_tokens", "tool_calls"}
_PATTERNS = {"absence", "bounded_existence", "precedence", "bounded_response", "protocol"}
_STATEFUL_PATTERNS = {"precedence", "bounded_response", "protocol"}
_WITNESS_PATTERNS = {"absence", "bounded_existence", "precedence", "protocol"}
_EVENT_TYPES = {
    "unit_start",
    "unit_end",
    "tool_call",
    "tool_result",
    "model_call",
    "handoff",
    "error",
    "authorization_granted",
    "authorization_revoked",
}
_STATUSES = {"running", "completed", "failed", "rejected"}
_CORRELATE_BY = {"unit", "correlation_id", "tool_call_id"}
_PRECEDENCE_MODES = {"single_use", "reusable"}
_UNLISTED_MODES = {"reject", "ignore"}
_CATALOGUE_CHECKERS: Dict[str, Set[str]] = {
    "traigent.refusal.v1": {"must_refuse", "complied"},
}

_PHASES = {"promotion", "runtime"}
_PROFILES = {"backend_v1"}
_APPLIES_TO = {"agent", "tenant_floor"}
_SOURCES = {"backend_trace_metadata", "customer_side", "evaluation_set", "episodes", "windows"}
_ATTRIBUTIONS = {"agent_key_exact_v1"}
_RESOLUTIONS = {"terminal_status_v1"}
_SAMPLING_MODES = {"head_sampled_declared", "hash_bernoulli_committed_v1"}
_METHODS = {"clopper_pearson_exact_v1", "clopper_pearson_rational_v2", "exact_count_v1", "exact_aggregate_v1"}
_MODELS = {"iid_bernoulli_within_window_v1"}
_HOURS_DIVISORS = {1, 2, 3, 4, 6, 8, 12, 24}
_BACKEND_HOURS = {1, 3, 6, 12, 24}
_BACKEND_CONFIDENCES = {Fraction(9, 10), Fraction(95, 100), Fraction(99, 100)}

_OUTCOME_EVENTS = {"optimize_no_candidate", "optimize_failed", "deploy_refused", "deploy_failed"}

_TRIGGER_EVENTS = {
    "unknown_for",
    "episode_opened",
    "episode_continued",
    "episode_open_for",
    "episode_resolved",
    "episode_withdrawn",
    "recovery_overdue",
    "recovery_cancelled",
    "recovery_recovered",
    "burn_breached",
    "stale",
    "live_again",
    "unit_violation",
}
_ACTIONS = {
    "notify",
    "open_next_step",
    "optimize",
    "rollback",
    "throttle",
    "degrade",
    "suspend",
    "block_action",
    "halt_unit",
}
_APPROVALS = {"none", "standing", "human"}
_SEVERITIES = {"info", "warning", "critical"}
_ON_CHECK_ERRORS = {"block", "allow"}
_SUSPEND_FALLBACKS = {"static_unavailable", "route_to_human"}
_SUSPEND_ESCALATION_EVENTS = {"episode_continued", "episode_open_for", "recovery_overdue"}
_DEPLOY_MODES = {"never", "if_promoted"}
# RFC 0003 §7.6: a deploy is a service effect of an episode scope, so only episode events may carry it.
_DEPLOY_EPISODE_EVENTS = {"episode_opened", "episode_continued", "episode_open_for"}


def _address_runtime_issues(issues: List[Issue], start: int = 0) -> None:
    from .diagnostics import field_path

    for issue in issues[start:]:
        issue["message"] = f"{field_path(issue.get('path', []))}: {issue['message']}"


def _uses_13_constructs(doc: Dict[str, Any]) -> bool:
    """RFC 0003 §11.1: presence-based opt-in for TVL 1.3 runtime blocks."""
    if not isinstance(doc, dict):
        return False
    return any(key in doc for key in ("requirements", "monitors", "responses"))


def _is_int_strict(value: Any) -> bool:
    return type(value) is int


def _to_exact_fraction(value: Any) -> Optional[Fraction]:
    """Convert a JSON/YAML number to its exact decimal Fraction if recoverable (§4.2)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, int):
        return Fraction(value)
    if getattr(value, "_unrecoverable_decimal", False):
        return None
    import math
    if not math.isfinite(value):
        return None
    text = repr(value)
    if float(text) != value:
        return None
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None


def _legacy_module_names(doc: Dict[str, Any]) -> Set[str]:
    names: Set[str] = set()
    for block in ("tvars", "cvars", "policies", "composites"):
        entries = doc.get(block) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                names.add(entry["name"])
    return names


def _lint_runtime_version(doc: Dict[str, Any], issues: List[Issue]) -> None:
    """RFC 0003 T17, §5.2, §11.1."""
    if "tvl_version" not in doc or doc.get("tvl_version") is None:
        issues.append(
            {
                "code": "runtime_version_required",
                "message": "Runtime constructs and packs require tvl_version: '1.3' (or '1.4' with RFC 0004 constructs, '1.5' with RFC 0005 constructs)",
                "path": ["tvl_version"],
                "severity": "error",
            }
        )
    elif not isinstance(doc.get("tvl_version"), str) or doc.get("tvl_version") not in {"1.3", "1.4", "1.5"}:
        issues.append(
            {
                "code": "declared_version_below_constructs",
                "message": 'TVL 1.3 constructs require a string version; quote it: "1.3"',
                "path": ["tvl_version"],
                "severity": "error",
            }
        )

    elif doc.get("tvl_version") == "1.3" and _uses_14_constructs(doc):
        issues.append({
            "code": "declared_version_below_constructs",
            "message": 'Reactive outcomes and guards require tvl_version: "1.4"',
            "path": ["tvl_version"], "severity": "error",
        })
    elif doc.get("tvl_version") in {"1.3", "1.4"} and _uses_15_constructs(doc):
        issues.append({
            "code": "declared_version_below_constructs",
            "message": 'Breach persistence and census aggregates require tvl_version: "1.5"',
            "path": ["tvl_version"], "severity": "error",
        })


def _uses_15_constructs(doc: Dict[str, Any]) -> bool:
    """RFC 0005 §2.1: presence-based opt-in for breach persistence and census aggregates."""
    requirements = doc.get("requirements")
    for req in requirements if isinstance(requirements, list) else []:
        if isinstance(req, dict) and (req.get("kind") == "aggregate_bound" or "aggregate" in req or "bound" in req):
            return True
    monitors = doc.get("monitors")
    for mon in monitors if isinstance(monitors, list) else []:
        decision = mon.get("decision") if isinstance(mon, dict) else None
        if isinstance(decision, dict) and decision.get("method") == "exact_aggregate_v1":
            return True
    responses = doc.get("responses")
    for resp in responses if isinstance(responses, list) else []:
        if not isinstance(resp, dict) or not isinstance(resp.get("rules"), list):
            continue
        if any(isinstance(rule, dict) and "persist" in rule for rule in resp["rules"]):
            return True
    return False


def _uses_14_constructs(doc: Dict[str, Any]) -> bool:
    responses = doc.get("responses")
    for resp in responses if isinstance(responses, list) else []:
        if not isinstance(resp, dict) or not isinstance(resp.get("rules"), list):
            continue
        for rule in resp["rules"]:
            if not isinstance(rule, dict):
                continue
            trigger = rule.get("trigger")
            if "only_while" in rule or "unless" in rule or (
                isinstance(trigger, dict) and ("rule" in trigger or trigger.get("event") == "unknown_for")
            ):
                return True
    return False


def _selector_canonical(sel: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        sel.get("event"),
        sel.get("tool"),
        sel.get("status"),
        sel.get("ref"),
    )


def _selectors_can_overlap(s1: Dict[str, Any], s2: Dict[str, Any]) -> bool:
    if s1.get("event") != s2.get("event"):
        return False
    for key in ("tool", "status", "ref"):
        v1, v2 = s1.get(key), s2.get(key)
        if v1 is not None and v2 is not None and v1 != v2:
            return False
    return True


def _lint_selector(sel: Any, path: List[Any], issues: List[Issue]) -> None:
    if not isinstance(sel, dict):
        issues.append(
            {
                "code": "runtime_invalid_profile",
                "message": "Event selector must be a mapping",
                "path": path,
                "severity": "error",
            }
        )
        return
    event = sel.get("event")
    if not isinstance(event, str) or event not in _EVENT_TYPES:
        issues.append(
            {
                "code": "runtime_unknown_kind",
                "message": "Unknown trace event type; expected an agent_trace_v1 event",
                "path": path + ["event"],
                "severity": "error",
            }
        )
        return
    if "tool" in sel:
        tool = sel.get("tool")
        if event not in {"tool_call", "tool_result"}:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Selector tool is allowed only on tool_call / tool_result",
                    "path": path + ["tool"],
                    "severity": "error",
                }
            )
        if not isinstance(tool, str) or len(tool) > 128 or not _CODE_IDENT_RE.match(tool):
            issues.append(
                {
                    "code": "runtime_tool_not_code_identifier",
                    "message": "Selector tool must be a valid code_ident",
                    "path": path + ["tool"],
                    "severity": "error",
                }
            )
    if "status" in sel:
        status = sel.get("status")
        if event not in {"unit_end", "tool_result"}:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Selector status is allowed only on unit_end / tool_result",
                    "path": path + ["status"],
                    "severity": "error",
                }
            )
        if not isinstance(status, str) or status not in _STATUSES:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Expected status: running, completed, failed, rejected",
                    "path": path + ["status"],
                    "severity": "error",
                }
            )
    if "ref" in sel:
        ref = sel.get("ref")
        if event not in {"authorization_granted", "authorization_revoked"}:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Selector ref is allowed only on authorization_granted / authorization_revoked",
                    "path": path + ["ref"],
                    "severity": "error",
                }
            )
        elif not isinstance(ref, str) or not _RUNTIME_IDENT_RE.match(ref):
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Selector ref must be a runtime identifier",
                    "path": path + ["ref"],
                    "severity": "error",
                }
            )


def _lint_predicate(
    pred: Any,
    path: List[Any],
    issues: List[Issue],
    *,
    exact_only: bool = False,
    checker_only: bool = False,
    checker_registry: Optional[Dict[str, Sequence[str]]] = None,
) -> None:
    if not isinstance(pred, dict):
        issues.append(
            {
                "code": "runtime_invalid_profile",
                "message": "Predicate must be an object",
                "path": path,
                "severity": "error",
            }
        )
        return

    has_metric = "metric" in pred
    has_checker = "checker" in pred
    has_pattern = "pattern" in pred
    if sum([has_metric, has_checker, has_pattern]) != 1:
        issues.append(
            {
                "code": "runtime_invalid_profile",
                "message": "Predicate must specify exactly one of metric, checker, or pattern",
                "path": path,
                "severity": "error",
            }
        )
        return

    if checker_only and not has_checker:
        issues.append(
            {
                "code": "runtime_among_not_checker",
                "message": "among must be a checker predicate; 1.3 defines population membership only for checker labels",
                "path": path,
                "severity": "error",
            }
        )
        return

    if exact_only and (has_metric or has_checker):
        issues.append(
            {
                "code": "runtime_zero_tolerance_inexact",
                "message": "zero_tolerance violation must be an exact_pred",
                "path": path,
                "severity": "error",
            }
        )
        return

    if has_metric:
        if set(pred.keys()) != {"metric", "exceeds"}:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Metric predicate requires exactly 'metric' and 'exceeds'",
                    "path": path,
                    "severity": "error",
                }
            )
            return
        metric = pred.get("metric")
        if not isinstance(metric, str) or metric not in _METRICS:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Unknown metric; expected wall_clock_latency_ms, cost_usd, total_tokens, tool_calls",
                    "path": path + ["metric"],
                    "severity": "error",
                }
            )
            return
        exceeds = pred.get("exceeds")
        frac = _to_exact_fraction(exceeds)
        if frac is None:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Metric 'exceeds' must be an exact decimal number",
                    "path": path + ["exceeds"],
                    "severity": "error",
                }
            )
            return
        if metric in {"wall_clock_latency_ms", "total_tokens", "tool_calls"}:
            if not _is_int_strict(exceeds) or exceeds < 1:
                issues.append(
                    {
                        "code": "runtime_exceeds_out_of_range",
                        "message": "Metric exceeds must be an integer >= 1",
                        "path": path + ["exceeds"],
                        "severity": "error",
                    }
                )
        elif metric == "cost_usd":
            if frac <= 0:
                issues.append(
                    {
                        "code": "runtime_exceeds_out_of_range",
                        "message": "Metric 'cost_usd' exceeds must be > 0",
                        "path": path + ["exceeds"],
                        "severity": "error",
                    }
                )
        return

    if has_checker:
        if set(pred.keys()) != {"checker", "label_in"}:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Checker predicate requires 'checker' and 'label_in'",
                    "path": path,
                    "severity": "error",
                }
            )
            return
        checker = pred.get("checker")
        label_in = pred.get("label_in")
        if not isinstance(label_in, list) or not label_in:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "checker label_in must be a non-empty list",
                    "path": path + ["label_in"],
                    "severity": "error",
                }
            )
            return
        if not isinstance(checker, str):
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "checker id must be a string",
                    "path": path + ["checker"],
                    "severity": "error",
                }
            )
            return
        if checker in _CATALOGUE_CHECKERS:
            allowed_labels = _CATALOGUE_CHECKERS[checker]
            for l_idx, label in enumerate(label_in):
                if not isinstance(label, str) or label not in allowed_labels:
                    issues.append(
                        {
                            "code": "runtime_unknown_kind",
                            "message": "Expected catalogue label: must_refuse, complied",
                            "path": path + ["label_in", l_idx],
                            "severity": "error",
                        }
                    )
        elif _CUSTOMER_CHECKER_RE.match(checker):
            for l_idx, label in enumerate(label_in):
                if not isinstance(label, str) or not _RUNTIME_IDENT_RE.match(label):
                    issues.append(
                        {
                            "code": "runtime_unknown_kind",
                            "message": "Expected a customer checker label identifier",
                            "path": path + ["label_in", l_idx],
                            "severity": "error",
                        }
                    )
            if checker_registry is not None:
                if checker not in checker_registry:
                    issues.append(
                        {
                            "code": "runtime_unknown_kind",
                            "message": "Customer checker requires an entry in the checker registry",
                            "path": path + ["checker"],
                            "severity": "error",
                        }
                    )
                else:
                    bound_labels = set(checker_registry[checker])
                    for l_idx, label in enumerate(label_in):
                        if label not in bound_labels:
                            issues.append(
                                {
                                    "code": "runtime_unknown_kind",
                                    "message": "Label requires an entry in the checker registry labels",
                                    "path": path + ["label_in", l_idx],
                                    "severity": "error",
                                }
                            )
        else:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Expected a catalogue checker id or customer:<identifier>",
                    "path": path + ["checker"],
                    "severity": "error",
                }
            )
        return

    # exact_pred
    pattern = pred.get("pattern")
    if not isinstance(pattern, str) or pattern not in _PATTERNS:
        issues.append(
            {
                "code": "runtime_unknown_kind",
                "message": "Unknown exact predicate pattern",
                "path": path + ["pattern"],
                "severity": "error",
            }
        )
        return

    if pattern == "absence":
        if set(pred.keys()) != {"pattern", "a"}:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "absence pattern requires only 'pattern' and 'a'",
                    "path": path,
                    "severity": "error",
                }
            )
            return
        _lint_selector(pred.get("a"), path + ["a"], issues)
    elif pattern == "bounded_existence":
        if "correlate_by" in pred:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "correlate_by is not supported by bounded_existence; max_count applies to the whole unit",
                    "path": path + ["correlate_by"],
                    "severity": "error",
                }
            )
            return
        if set(pred.keys()) != {"pattern", "a", "max_count"}:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "bounded_existence requires 'pattern', 'a', and 'max_count'",
                    "path": path,
                    "severity": "error",
                }
            )
            return
        _lint_selector(pred.get("a"), path + ["a"], issues)
        max_count = pred.get("max_count")
        if not _is_int_strict(max_count) or max_count < 0:
            issues.append(
                {
                    "code": "runtime_max_count_out_of_range",
                    "message": "max_count must be an integer >= 0",
                    "path": path + ["max_count"],
                    "severity": "error",
                }
            )
    elif pattern == "precedence":
        allowed = {"pattern", "a", "b", "mode", "correlate_by"}
        if not {"pattern", "a", "b"} <= set(pred.keys()) <= allowed:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "precedence has invalid or missing fields",
                    "path": path,
                    "severity": "error",
                }
            )
            return
        _lint_selector(pred.get("a"), path + ["a"], issues)
        _lint_selector(pred.get("b"), path + ["b"], issues)
        if "mode" in pred and pred.get("mode") not in _PRECEDENCE_MODES:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Expected precedence mode: single_use, reusable",
                    "path": path + ["mode"],
                    "severity": "error",
                }
            )
        if "correlate_by" in pred and pred.get("correlate_by") not in _CORRELATE_BY:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Expected correlate_by: unit, correlation_id, tool_call_id",
                    "path": path + ["correlate_by"],
                    "severity": "error",
                }
            )
    elif pattern == "bounded_response":
        allowed = {"pattern", "a", "b", "within_ms", "correlate_by"}
        if not {"pattern", "a", "b", "within_ms"} <= set(pred.keys()) <= allowed:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "bounded_response has invalid or missing fields",
                    "path": path,
                    "severity": "error",
                }
            )
            return
        _lint_selector(pred.get("a"), path + ["a"], issues)
        _lint_selector(pred.get("b"), path + ["b"], issues)
        within_ms = pred.get("within_ms")
        if not _is_int_strict(within_ms) or within_ms < 1:
            issues.append(
                {
                    "code": "runtime_within_ms_out_of_range",
                    "message": "within_ms must be an integer >= 1",
                    "path": path + ["within_ms"],
                    "severity": "error",
                }
            )
        if "correlate_by" in pred and pred.get("correlate_by") not in _CORRELATE_BY:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Expected correlate_by: unit, correlation_id, tool_call_id",
                    "path": path + ["correlate_by"],
                    "severity": "error",
                }
            )
    elif pattern == "protocol":
        req_keys = {"pattern", "alphabet", "states", "start", "transitions", "accepting", "rejecting"}
        allowed = req_keys | {"unlisted"}
        if not req_keys <= set(pred.keys()) <= allowed:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "protocol predicate has invalid or missing fields",
                    "path": path,
                    "severity": "error",
                }
            )
            return
        if "unlisted" in pred and pred.get("unlisted") not in _UNLISTED_MODES:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Expected unlisted: reject, ignore",
                    "path": path + ["unlisted"],
                    "severity": "error",
                }
            )
        alphabet = pred.get("alphabet")
        states = pred.get("states")
        start = pred.get("start")
        transitions = pred.get("transitions")
        accepting = pred.get("accepting")
        rejecting = pred.get("rejecting")
        if (
            not isinstance(alphabet, list)
            or not alphabet
            or not isinstance(states, list)
            or not states
            or not isinstance(transitions, list)
            or not isinstance(accepting, list)
            or not isinstance(rejecting, list)
        ):
            issues.append(
                {
                    "code": "runtime_protocol_nondeterministic",
                    "message": "protocol lists must be valid",
                    "path": path,
                    "severity": "error",
                }
            )
            return
        for a_idx, sel in enumerate(alphabet):
            _lint_selector(sel, path + ["alphabet", a_idx], issues)
        state_set = set(states)
        nondet = False
        if len(state_set) != len(states) or start not in state_set:
            nondet = True
        if not set(accepting) <= state_set or not set(rejecting) <= state_set:
            nondet = True
        if set(accepting) & set(rejecting):
            nondet = True
        alphabet_canon = [
            _selector_canonical(s) for s in alphabet if isinstance(s, dict)
        ]
        if len(alphabet_canon) != len(alphabet):
            nondet = True
        for i in range(len(alphabet)):
            for j in range(i + 1, len(alphabet)):
                if isinstance(alphabet[i], dict) and isinstance(alphabet[j], dict):
                    if _selectors_can_overlap(alphabet[i], alphabet[j]):
                        nondet = True
        seen_trans: Set[Tuple[Any, Any]] = set()
        alphabet_set = set(alphabet_canon)
        for tr in transitions:
            if not isinstance(tr, dict):
                nondet = True
                continue
            fr = tr.get("from")
            wh = tr.get("when")
            to = tr.get("to")
            if fr not in state_set or to not in state_set or not isinstance(wh, dict):
                nondet = True
                continue
            wh_c = _selector_canonical(wh)
            if wh_c not in alphabet_set or (fr, wh_c) in seen_trans:
                nondet = True
            seen_trans.add((fr, wh_c))
        if nondet:
            issues.append(
                {
                    "code": "runtime_protocol_nondeterministic",
                    "message": "Protocol automaton must be deterministic and well-scoped (T12)",
                    "path": path,
                    "severity": "error",
                }
            )


def _lint_requirements(
    doc: Dict[str, Any],
    issues: List[Issue],
    *,
    checker_registry: Optional[Dict[str, Sequence[str]]] = None,
) -> None:
    reqs = doc.get("requirements")
    if reqs is None:
        return
    if not isinstance(reqs, list):
        issues.append(
            {
                "code": "runtime_invalid_profile",
                "message": "requirements must be a list",
                "path": ["requirements"],
                "severity": "error",
            }
        )
        return

    legacy_names = _legacy_module_names(doc)
    seen_names: Set[str] = set()

    for idx, req in enumerate(reqs):
        path = ["requirements", idx]
        if not isinstance(req, dict):
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Requirement declaration must be an object",
                    "path": path,
                    "severity": "error",
                }
            )
            continue

        name = req.get("name")
        if not isinstance(name, str) or not _RUNTIME_IDENT_RE.match(name):
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Requirement name must be a runtime identifier",
                    "path": path + ["name"],
                    "severity": "error",
                }
            )
        else:
            if name in seen_names or name in legacy_names:
                issues.append(
                    {
                        "code": "runtime_name_collision",
                        "message": "Requirement name collides with an existing declaration",
                        "path": path + ["name"],
                        "severity": "error",
                    }
                )
            seen_names.add(name)

        kind = req.get("kind")
        if not isinstance(kind, str) or kind not in _REQ_KINDS:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Unknown requirement kind",
                    "path": path + ["kind"],
                    "severity": "error",
                }
            )
            continue

        unit = req.get("unit")
        if not isinstance(unit, str) or unit not in _ALL_UNIT_KINDS:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Unknown requirement unit",
                    "path": path + ["unit"],
                    "severity": "error",
                }
            )
            continue

        if kind == "rate_bound":
            if unit not in _UNIT_KINDS:
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "rate_bound unit must be 'trace' or 'invocation'",
                        "path": path + ["unit"],
                        "severity": "error",
                    }
                )
            req_keys = {"name", "kind", "unit", "violation", "max_rate"}
            allowed = req_keys | {"among"}
            if not req_keys <= set(req.keys()) <= allowed:
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "rate_bound has missing or forbidden fields",
                        "path": path,
                        "severity": "error",
                    }
                )
            if "violation" in req:
                _lint_predicate(
                    req["violation"],
                    path + ["violation"],
                    issues,
                    exact_only=False,
                    checker_registry=checker_registry,
                )
            if "among" in req:
                _lint_predicate(
                    req["among"],
                    path + ["among"],
                    issues,
                    checker_only=True,
                    checker_registry=checker_registry,
                )
            if "max_rate" in req:
                rate_frac = _to_exact_fraction(req.get("max_rate"))
                if rate_frac is None:
                    issues.append(
                        {
                            "code": "runtime_invalid_profile",
                            "message": "max_rate must be an exact decimal number",
                            "path": path + ["max_rate"],
                            "severity": "error",
                        }
                    )
                elif not (0 < rate_frac < 1):
                    issues.append(
                        {
                            "code": "runtime_rate_out_of_range",
                            "message": "max_rate must satisfy 0 < max_rate < 1",
                            "path": path + ["max_rate"],
                            "severity": "error",
                        }
                    )
        elif kind == "zero_tolerance":
            if unit not in _UNIT_KINDS:
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "zero_tolerance unit must be 'trace' or 'invocation'",
                        "path": path + ["unit"],
                        "severity": "error",
                    }
                )
            req_keys = {"name", "kind", "unit", "violation"}
            allowed = req_keys | {"among"}
            if not req_keys <= set(req.keys()) <= allowed:
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "zero_tolerance has missing or forbidden fields",
                        "path": path,
                        "severity": "error",
                    }
                )
            if "violation" in req:
                _lint_predicate(
                    req["violation"],
                    path + ["violation"],
                    issues,
                    exact_only=True,
                    checker_registry=checker_registry,
                )
            if "among" in req:
                _lint_predicate(
                    req["among"],
                    path + ["among"],
                    issues,
                    checker_only=True,
                    checker_registry=checker_registry,
                )
        elif kind == "recovery_time":
            if unit != "episode":
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "recovery_time unit must be 'episode'",
                        "path": path + ["unit"],
                        "severity": "error",
                    }
                )
            if set(req.keys()) != {"name", "kind", "unit", "of", "within_hours"}:
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "recovery_time requires 'of' and 'within_hours'",
                        "path": path,
                        "severity": "error",
                    }
                )
            within_hours = req.get("within_hours")
            if within_hours is not None and (not _is_int_strict(within_hours) or within_hours < 1):
                issues.append(
                    {
                        "code": "runtime_within_hours_out_of_range",
                        "message": "within_hours must be an integer >= 1",
                        "path": path + ["within_hours"],
                        "severity": "error",
                    }
                )
        elif kind == "evidence_liveness":
            if unit != "window":
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "evidence_liveness unit must be 'window'",
                        "path": path + ["unit"],
                        "severity": "error",
                    }
                )
            if set(req.keys()) != {"name", "kind", "unit", "of", "max_stale_windows"}:
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "evidence_liveness requires 'of' and 'max_stale_windows'",
                        "path": path,
                        "severity": "error",
                    }
                )
            max_stale = req.get("max_stale_windows")
            if max_stale is not None and (not _is_int_strict(max_stale) or max_stale < 1):
                issues.append(
                    {
                        "code": "runtime_max_stale_windows_out_of_range",
                        "message": "max_stale_windows must be an integer >= 1",
                        "path": path + ["max_stale_windows"],
                        "severity": "error",
                    }
                )
        elif kind == "aggregate_bound":
            _lint_aggregate_requirement(req, path, issues, checker_registry=checker_registry)


def _lint_aggregate_requirement(
    req: Dict[str, Any],
    path: List[Any],
    issues: List[Issue],
    *,
    checker_registry: Optional[Dict[str, Sequence[str]]] = None,
) -> None:
    """RFC 0005 §2.3: census aggregate requirement variant checks."""

    def error(code: str, message: str, subpath: List[Any]) -> None:
        issues.append({"code": code, "message": message, "path": path + subpath, "severity": "error"})

    if req.get("unit") not in _UNIT_KINDS:
        error("runtime_invalid_profile", "aggregate_bound unit must be 'trace' or 'invocation'", ["unit"])
    req_keys = {"name", "kind", "unit", "aggregate", "bound"}
    if not req_keys <= set(req) <= req_keys | {"among"}:
        error("runtime_invalid_profile", "aggregate_bound has missing or forbidden fields", [])
    if "among" in req:
        _lint_predicate(req["among"], path + ["among"], issues, checker_only=True, checker_registry=checker_registry)
    aggregate = req.get("aggregate")
    op = metric = None
    if "aggregate" in req:
        if not isinstance(aggregate, dict) or "source_digest" not in aggregate or not {"op", "metric"} <= set(aggregate):
            error("runtime_invalid_profile", "aggregate requires op, metric and source_digest", ["aggregate"])
        else:
            op, metric = aggregate.get("op"), aggregate.get("metric")
            if not isinstance(op, str) or op not in _AGG_OPS:
                error("runtime_unknown_kind", "Unknown aggregate operator", ["aggregate", "op"])
                op = None
            if not isinstance(metric, str) or metric not in _AGG_METRICS:
                error("runtime_unknown_kind", "Unknown aggregate metric", ["aggregate", "metric"])
                metric = None
            digest = aggregate.get("source_digest")
            if not isinstance(digest, str) or not _FINGERPRINT_RE.match(digest):
                error("runtime_invalid_profile", "source_digest must be a 64-character lowercase hexadecimal digest", ["aggregate", "source_digest"])
    if "bound" in req:
        bound = req.get("bound")
        if not isinstance(bound, dict) or sum(key in bound for key in _AGG_BOUNDS) != 1 or set(bound) - set(_AGG_BOUNDS):
            error("runtime_invalid_profile", "bound requires exactly one of lte or gte", ["bound"])
        else:
            direction = next(key for key in _AGG_BOUNDS if key in bound)
            value = _to_exact_fraction(bound[direction])
            if value is None:
                error("runtime_invalid_profile", "bound must be an exact decimal number", ["bound", direction])
            elif value < 0 or (op == "mean" and metric == "score" and value > 1):
                error("runtime_aggregate_bound_out_of_range", "bound is outside its numeric domain", ["bound", direction])


def _predicate_canonical(pred: Optional[Dict[str, Any]]) -> Any:
    if not isinstance(pred, dict):
        return None
    if "metric" in pred:
        exceeds = pred.get("exceeds")
        frac = _to_exact_fraction(exceeds)
        return ("metric", pred.get("metric"), frac if frac is not None else exceeds)
    if "checker" in pred:
        labels = tuple(sorted(set(pred.get("label_in") or [])))
        return ("checker", pred.get("checker"), labels)
    pattern = pred.get("pattern")
    if pattern == "absence":
        return ("absence", _selector_canonical(pred.get("a") or {}))
    if pattern == "bounded_existence":
        return ("bounded_existence", _selector_canonical(pred.get("a") or {}), pred.get("max_count"))
    if pattern == "precedence":
        return (
            "precedence",
            _selector_canonical(pred.get("a") or {}),
            _selector_canonical(pred.get("b") or {}),
            pred.get("mode", "single_use"),
            pred.get("correlate_by", "unit"),
        )
    if pattern == "bounded_response":
        return (
            "bounded_response",
            _selector_canonical(pred.get("a") or {}),
            _selector_canonical(pred.get("b") or {}),
            pred.get("within_ms"),
            pred.get("correlate_by", "unit"),
        )
    if pattern == "protocol":
        alphabet = tuple(sorted(_selector_canonical(s) for s in (pred.get("alphabet") or []) if isinstance(s, dict)))
        states = tuple(sorted(set(pred.get("states") or [])))
        accepting = tuple(sorted(set(pred.get("accepting") or [])))
        rejecting = tuple(sorted(set(pred.get("rejecting") or [])))
        transitions = tuple(
            sorted(
                (t.get("from"), _selector_canonical(t.get("when") or {}), t.get("to"))
                for t in (pred.get("transitions") or [])
                if isinstance(t, dict)
            )
        )
        return (
            "protocol",
            alphabet,
            states,
            pred.get("start"),
            transitions,
            accepting,
            rejecting,
            pred.get("unlisted", "reject"),
        )
    return None


def _requirement_identity(req: Dict[str, Any]) -> Any:
    kind = req.get("kind")
    if kind in {"rate_bound", "zero_tolerance"}:
        return (
            kind,
            req.get("unit"),
            _predicate_canonical(req.get("among")),
            _predicate_canonical(req.get("violation")),
        )
    if kind == "aggregate_bound":
        aggregate = req.get("aggregate") if isinstance(req.get("aggregate"), dict) else {}
        bound = req.get("bound") if isinstance(req.get("bound"), dict) else {}
        # The numeric bound is excluded: overlays may tighten it (RFC 0005 §2.5).
        direction = next((key for key in _AGG_BOUNDS if key in bound), None)
        return (
            kind,
            req.get("unit"),
            _predicate_canonical(req.get("among")),
            aggregate.get("op"),
            aggregate.get("metric"),
            aggregate.get("source_digest"),
            direction,
        )
    return (kind, req.get("unit"), req.get("of"))


def _monitor_effective_key(mon: Dict[str, Any], req: Dict[str, Any]) -> Any:
    kind = req.get("kind")
    evidence = mon.get("evidence") or {}
    decision = mon.get("decision") or {}
    env_raw = evidence.get("deployment_environment", "production")
    env_norm = env_raw.strip().lower() if isinstance(env_raw, str) else "production"
    if mon.get("profile") == "backend_v1":
        viol = req.get("violation") or {}
        return ("backend_v1", "latency_violation_rate", viol.get("exceeds"), env_norm)
    if kind in {"recovery_time", "evidence_liveness"}:
        return ("obligation", _requirement_identity(req))
    tf = _to_exact_fraction(decision.get("threshold_factor")) if "threshold_factor" in decision else None
    return (
        "primary_or_burn",
        _requirement_identity(req),
        evidence.get("source"),
        env_norm,
        evidence.get("attribution", "agent_key_exact_v1"),
        decision.get("method"),
        tf,
    )


def _monitor_role(mon: Dict[str, Any], req: Optional[Dict[str, Any]]) -> str:
    if mon.get("phase") == "promotion":
        return "promotion"
    kind = (req or {}).get("kind")
    if kind == "recovery_time":
        return "recovery"
    if kind == "evidence_liveness":
        return "liveness"
    if kind == "aggregate_bound":
        return "primary_aggregate"
    decision = mon.get("decision") or {}
    if isinstance(decision, dict) and "threshold_factor" in decision:
        return "burn"
    if kind == "zero_tolerance":
        return "primary_zero"
    return "primary_rate"


def _lint_monitors(
    doc: Dict[str, Any],
    issues: List[Issue],
    *,
    is_pack: bool = False,
    floor_provenance: Optional[Sequence[Dict[str, Any]]] = None,
) -> None:
    mons = doc.get("monitors")
    if mons is None:
        return
    if not isinstance(mons, list):
        issues.append(
            {
                "code": "runtime_invalid_profile",
                "message": "monitors must be a list",
                "path": ["monitors"],
                "severity": "error",
            }
        )
        return

    reqs_list = doc.get("requirements") or []
    reqs_by_name: Dict[str, Dict[str, Any]] = {
        r["name"]: r
        for r in reqs_list
        if isinstance(r, dict) and isinstance(r.get("name"), str)
    }
    legacy_names = _legacy_module_names(doc)
    seen_names: Set[str] = set()
    mons_by_name: Dict[str, Dict[str, Any]] = {}
    provenance_monitors = {
        entry.get("monitor")
        for entry in (floor_provenance or [])
        if isinstance(entry, dict) and isinstance(entry.get("monitor"), str)
    }
    chance_names = {
        c.get("name")
        for c in ((doc.get("promotion_policy") or {}).get("chance_constraints") or [])
        if isinstance(c, dict) and isinstance(c.get("name"), str)
    }
    seen_effective_keys: Set[Any] = set()

    for idx, mon in enumerate(mons):
        path = ["monitors", idx]
        if not isinstance(mon, dict):
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Monitor declaration must be an object",
                    "path": path,
                    "severity": "error",
                }
            )
            continue

        name = mon.get("name")
        if not isinstance(name, str) or not _RUNTIME_IDENT_RE.match(name):
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Monitor name must be a runtime identifier",
                    "path": path + ["name"],
                    "severity": "error",
                }
            )
        else:
            if name in seen_names or name in legacy_names:
                issues.append(
                    {
                        "code": "runtime_name_collision",
                        "message": "Monitor name collides with an existing declaration",
                        "path": path + ["name"],
                        "severity": "error",
                    }
                )
            seen_names.add(name)
            mons_by_name[name] = mon

        phase = mon.get("phase")
        if not isinstance(phase, str) or phase not in _PHASES:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Expected monitor phase: promotion, runtime",
                    "path": path + ["phase"],
                    "severity": "error",
                }
            )
            continue

        profile = mon.get("profile")
        if profile is not None and (not isinstance(profile, str) or profile not in _PROFILES):
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Expected monitor profile: backend_v1",
                    "path": path + ["profile"],
                    "severity": "error",
                }
            )
            continue

        applies_to = mon.get("applies_to")
        if applies_to is not None and (not isinstance(applies_to, str) or applies_to not in _APPLIES_TO):
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Expected applies_to: agent, tenant_floor",
                    "path": path + ["applies_to"],
                    "severity": "error",
                }
            )
            continue

        if is_pack:
            if applies_to != "tenant_floor" or phase != "runtime":
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "Pack monitors must explicitly declare applies_to: 'tenant_floor' and phase: 'runtime'",
                        "path": path,
                        "severity": "error",
                    }
                )
        else:
            if applies_to == "tenant_floor" and name not in provenance_monitors:
                issues.append(
                    {
                        "code": "tenant_floor_outside_pack",
                        "message": "applies_to: 'tenant_floor' is only permitted inside a tvl_pack",
                        "path": path + ["applies_to"],
                        "severity": "error",
                    }
                )

        req_name = mon.get("requirement")
        req = reqs_by_name.get(req_name) if isinstance(req_name, str) else None
        if req is None:
            issues.append(
                {
                    "code": "runtime_missing_ref",
                    "message": "Monitor requirement references an undeclared requirement",
                    "path": path + ["requirement"],
                    "severity": "error",
                }
            )
            continue

        req_kind = req.get("kind")
        if req_kind not in _REQ_KINDS:
            continue

        evidence = mon.get("evidence")
        decision = mon.get("decision")
        if not isinstance(evidence, dict) or not isinstance(decision, dict):
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Monitor requires 'evidence' and 'decision' mappings",
                    "path": path,
                    "severity": "error",
                }
            )
            continue

        source = evidence.get("source")
        if not isinstance(source, str) or source not in _SOURCES:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Unknown evidence source",
                    "path": path + ["evidence", "source"],
                    "severity": "error",
                }
            )
            continue

        if "attribution" in evidence and evidence.get("attribution") not in _ATTRIBUTIONS:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Expected attribution: agent_key_exact_v1",
                    "path": path + ["evidence", "attribution"],
                    "severity": "error",
                }
            )
            continue

        if "resolution" in evidence and evidence.get("resolution") not in _RESOLUTIONS:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Expected resolution: terminal_status_v1",
                    "path": path + ["evidence", "resolution"],
                    "severity": "error",
                }
            )
            continue

        sampling = evidence.get("sampling")
        if sampling is not None:
            if isinstance(sampling, str):
                if sampling != "unverified":
                    issues.append(
                        {
                            "code": "runtime_unknown_kind",
                            "message": "Unknown sampling mode",
                            "path": path + ["evidence", "sampling"],
                            "severity": "error",
                        }
                    )
                    continue
            elif isinstance(sampling, dict):
                s_mode = sampling.get("mode")
                if not isinstance(s_mode, str) or s_mode not in _SAMPLING_MODES:
                    issues.append(
                        {
                            "code": "runtime_unknown_kind",
                            "message": "Unknown sampling mode",
                            "path": path + ["evidence", "sampling", "mode"],
                            "severity": "error",
                        }
                    )
                    continue
                s_rate = _to_exact_fraction(sampling.get("rate"))
                if s_rate is None:
                    issues.append(
                        {
                            "code": "runtime_invalid_profile",
                            "message": "sampling.rate must be an exact decimal number",
                            "path": path + ["evidence", "sampling", "rate"],
                            "severity": "error",
                        }
                    )
                elif not (0 < s_rate < 1):
                    issues.append(
                        {
                            "code": "runtime_sampling_rate_out_of_range",
                            "message": "sampling.rate must satisfy 0 < rate < 1",
                            "path": path + ["evidence", "sampling", "rate"],
                            "severity": "error",
                        }
                    )
            else:
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "Invalid sampling specification",
                        "path": path + ["evidence", "sampling"],
                        "severity": "error",
                    }
                )
                continue

        method = decision.get("method")
        if not isinstance(method, str) or method not in _METHODS:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Unknown decision method",
                    "path": path + ["decision", "method"],
                    "severity": "error",
                }
            )
            continue

        if "model" in decision and decision.get("model") not in _MODELS:
            issues.append(
                {
                    "code": "runtime_unknown_kind",
                    "message": "Expected model: iid_bernoulli_within_window_v1",
                    "path": path + ["decision", "model"],
                    "severity": "error",
                }
            )
            continue

        # T4: content checker on backend source
        viol = req.get("violation") if isinstance(req.get("violation"), dict) else {}
        among = req.get("among") if isinstance(req.get("among"), dict) else {}
        has_checker_pred = "checker" in viol or "checker" in among
        if has_checker_pred and source == "backend_trace_metadata":
            issues.append(
                {
                    "code": "runtime_content_on_backend_source",
                    "message": "Checker predicates cannot run on backend_trace_metadata",
                    "path": path + ["evidence", "source"],
                    "severity": "error",
                }
            )

        # T5: zero_tolerance sampling forbidden
        if req_kind == "zero_tolerance" and "sampling" in evidence:
            issues.append(
                {
                    "code": "runtime_zero_tolerance_incomplete",
                    "message": "zero_tolerance monitors cannot declare sampling",
                    "path": path + ["evidence", "sampling"],
                    "severity": "error",
                }
            )

        is_backend = profile == "backend_v1"
        if is_backend:
            # T1: backend_v1 frozen fields
            env_val = evidence.get("deployment_environment", "production")
            env_ok = isinstance(env_val, str) and 1 <= len(env_val.strip()) <= 64
            legacy_ok = (
                req_kind == "rate_bound"
                and req.get("unit") == "trace"
                and "among" not in req
                and viol.get("metric") == "wall_clock_latency_ms"
                and phase == "runtime"
                and source == "backend_trace_metadata"
                and method == "clopper_pearson_exact_v1"
                and evidence.get("sampling", "unverified") == "unverified"
                and evidence.get("attribution", "agent_key_exact_v1") == "agent_key_exact_v1"
                and evidence.get("resolution", "terminal_status_v1") == "terminal_status_v1"
                and decision.get("model", "iid_bernoulli_within_window_v1") == "iid_bernoulli_within_window_v1"
                and "threshold_factor" not in decision
                and "limits" not in mon
                and "single_producer" not in mon
                and env_ok
            )
            if not legacy_ok:
                issues.append(
                    {
                        "code": "runtime_legacy_profile_override",
                        "message": "profile: backend_v1 freezes requirement, evidence, and decision fields (T1)",
                        "path": path,
                        "severity": "error",
                    }
                )
            exceeds_val = viol.get("exceeds")
            if _is_int_strict(exceeds_val) and exceeds_val > 600_000:
                issues.append(
                    {
                        "code": "runtime_exceeds_out_of_range",
                        "message": "Under backend_v1, wall_clock_latency_ms exceeds must be in 1..600000",
                        "path": ["requirements", reqs_list.index(req), "violation", "exceeds"],
                        "severity": "error",
                    }
                )
        else:
            # T2: backend_trace_metadata requires profile: backend_v1
            if source == "backend_trace_metadata" and not has_checker_pred:
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "source: backend_trace_metadata requires profile: backend_v1",
                        "path": path + ["evidence", "source"],
                        "severity": "error",
                    }
                )
            if method == "clopper_pearson_exact_v1":
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "clopper_pearson_exact_v1 requires profile: backend_v1",
                        "path": path + ["decision", "method"],
                        "severity": "error",
                    }
                )

        # T3: kind compatibility (§4.3)
        compat_ok = True
        if req_kind == "rate_bound":
            if source not in {"backend_trace_metadata", "customer_side", "evaluation_set"}:
                compat_ok = False
            if (phase == "promotion") != (source == "evaluation_set"):
                compat_ok = False
            if method not in {"clopper_pearson_exact_v1", "clopper_pearson_rational_v2"}:
                compat_ok = False
        elif req_kind == "zero_tolerance":
            if source not in {"customer_side", "evaluation_set"}:
                compat_ok = False
            if (phase == "promotion") != (source == "evaluation_set"):
                compat_ok = False
            if method != "exact_count_v1":
                compat_ok = False
        elif req_kind == "recovery_time":
            if source != "episodes" or phase != "runtime" or method != "exact_count_v1":
                compat_ok = False
        elif req_kind == "evidence_liveness":
            if source != "windows" or phase != "runtime" or method != "exact_count_v1":
                compat_ok = False
        elif req_kind == "aggregate_bound":
            if source != "customer_side" or phase != "runtime" or method != "exact_aggregate_v1":
                compat_ok = False
        if req_kind == "aggregate_bound" and is_backend:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "aggregate_bound monitors cannot declare a profile",
                    "path": path + ["profile"],
                    "severity": "error",
                }
            )
        if not compat_ok and not is_backend:
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Incompatible requirement kind, evidence source, phase, or decision method (§4.3)",
                    "path": path,
                    "severity": "error",
                }
            )

        # T6: sampling compatibility
        if sampling is not None and req_kind != "zero_tolerance":
            if sampling == "unverified" and source != "backend_trace_metadata":
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "sampling: unverified is only permitted with backend_trace_metadata",
                        "path": path + ["evidence", "sampling"],
                        "severity": "error",
                    }
                )
            elif isinstance(sampling, dict) and (source != "customer_side" or req_kind != "rate_bound"):
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "Declared sampling modes are only permitted with customer_side rate_bound monitors",
                        "path": path + ["evidence", "sampling"],
                        "severity": "error",
                    }
                )

        # Role-specific required and forbidden fields (§4.5)
        role = _monitor_role(mon, req)
        window = mon.get("window")
        episode = mon.get("episode")
        limits = mon.get("limits")
        has_exact_pred = "pattern" in viol or "pattern" in among
        has_stateful_pred = (
            viol.get("pattern") in _STATEFUL_PATTERNS or among.get("pattern") in _STATEFUL_PATTERNS
        )

        role_fields: List[Tuple[List[Any], str]] = []

        def forbid_fields(obj: Dict[str, Any], prefix: List[Any], keys: Sequence[str]) -> None:
            for key in keys:
                if key in obj:
                    role_fields.append((prefix + [key], "field is forbidden"))

        def require_fields(obj: Any, prefix: List[Any], keys: Sequence[str]) -> None:
            if not isinstance(obj, dict):
                role_fields.append((prefix, "required object is missing"))
                return
            for key in keys:
                if key not in obj:
                    role_fields.append((prefix + [key], "required field is missing"))

        if role in {"promotion", "recovery", "liveness"}:
            forbid_fields(evidence, ["evidence"], ("deployment_environment", "attribution"))
            for key, value in (("window", window), ("episode", episode)):
                if value is not None:
                    role_fields.append(([key], "field is forbidden"))
            forbid_fields(decision, ["decision"], ("horizon_days", "model", "threshold_factor"))
        if role in {"recovery", "liveness"}:
            forbid_fields(evidence, ["evidence"], ("resolution", "sampling"))
            forbid_fields(decision, ["decision"], ("confidence", "false_alarm_budget", "min_samples", "max_unresolved_fraction"))
            if limits is not None:
                role_fields.append((["limits"], "field is forbidden"))
            forbid_fields(mon, [], ("single_producer",))
        elif role == "promotion":
            if req_kind == "rate_bound":
                require_fields(decision, ["decision"], ("confidence", "false_alarm_budget"))
            elif req_kind == "zero_tolerance":
                forbid_fields(decision, ["decision"], ("confidence", "false_alarm_budget", "max_unresolved_fraction"))
        elif role == "burn":
            if episode is not None:
                role_fields.append((["episode"], "field is forbidden"))
            forbid_fields(decision, ["decision"], ("confidence",))
            require_fields(window, ["window"], ("tumbling_hours", "grace_minutes"))
            require_fields(decision, ["decision"], ("false_alarm_budget", "horizon_days", "min_samples", "max_unresolved_fraction", "threshold_factor"))
        elif role == "primary_aggregate":
            require_fields(window, ["window"], ("tumbling_hours", "grace_minutes"))
            require_fields(episode, ["episode"], ("closure_windows", "closure_max_age_hours"))
            forbid_fields(decision, ["decision"], ("model", "confidence", "false_alarm_budget", "horizon_days", "min_samples", "max_unresolved_fraction", "threshold_factor"))
            forbid_fields(evidence, ["evidence"], ("sampling",))
            forbid_fields(mon, [], ("profile", "limits", "single_producer"))
        elif role == "primary_zero":
            require_fields(window, ["window"], ("tumbling_hours", "grace_minutes"))
            require_fields(episode, ["episode"], ("closure_windows", "closure_max_age_hours"))
            forbid_fields(decision, ["decision"], ("model", "confidence", "false_alarm_budget", "horizon_days", "max_unresolved_fraction", "threshold_factor"))
        elif role == "primary_rate" and not is_backend:
            require_fields(window, ["window"], ("tumbling_hours", "grace_minutes"))
            require_fields(episode, ["episode"], ("closure_windows", "closure_max_age_hours"))
            require_fields(decision, ["decision"], ("confidence", "false_alarm_budget", "horizon_days", "min_samples", "max_unresolved_fraction"))

        if "single_producer" in mon and not has_exact_pred and not is_backend:
            role_fields.append((["single_producer"], "field requires an exact predicate"))

        if source in {"customer_side", "evaluation_set"} and has_stateful_pred:
            require_fields(limits, ["limits"], ("max_active_obligations", "max_tracked_correlations"))

        if not is_backend:
            for subpath, reason in role_fields:
                issues.append({
                    "code": "runtime_invalid_profile",
                    "message": f"{reason} for role '{role}' (§4.5)",
                    "path": path + subpath,
                    "severity": "error",
                })

        # Numeric domains for monitor fields (§4.2, §5.4)
        w_hours: Optional[int] = None
        grace_min: Optional[int] = None
        if isinstance(window, dict):
            if "tumbling_hours" in window:
                wh = window.get("tumbling_hours")
                allowed_hours = _BACKEND_HOURS if is_backend else _HOURS_DIVISORS
                if not _is_int_strict(wh) or wh not in allowed_hours:
                    issues.append(
                        {
                            "code": "runtime_window_out_of_range",
                            "message": "tumbling_hours is outside its allowed domain",
                            "path": path + ["window", "tumbling_hours"],
                            "severity": "error",
                        }
                    )
                else:
                    w_hours = wh
            elif is_backend:
                w_hours = 6

            if "grace_minutes" in window:
                gm = window.get("grace_minutes")
                if not _is_int_strict(gm) or not (0 <= gm <= 360):
                    issues.append(
                        {
                            "code": "runtime_grace_out_of_range",
                            "message": "grace_minutes must be in 0..360",
                            "path": path + ["window", "grace_minutes"],
                            "severity": "error",
                        }
                    )
                else:
                    grace_min = gm
            elif is_backend:
                grace_min = 30
        elif is_backend:
            w_hours = 6
            grace_min = 30

        conf_frac: Optional[Fraction] = None
        if "confidence" in decision:
            cf = _to_exact_fraction(decision.get("confidence"))
            if cf is None:
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "confidence must be an exact decimal number",
                        "path": path + ["decision", "confidence"],
                        "severity": "error",
                    }
                )
            elif (is_backend and cf not in _BACKEND_CONFIDENCES) or (not is_backend and not (0 < cf < 1)):
                issues.append(
                    {
                        "code": "runtime_confidence_out_of_range",
                        "message": "confidence is outside its allowed domain",
                        "path": path + ["decision", "confidence"],
                        "severity": "error",
                    }
                )
            else:
                conf_frac = cf
        elif is_backend:
            conf_frac = Fraction(95, 100)

        budget_frac: Optional[Fraction] = None
        if "false_alarm_budget" in decision:
            bf = _to_exact_fraction(decision.get("false_alarm_budget"))
            if bf is None:
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "false_alarm_budget must be an exact decimal number",
                        "path": path + ["decision", "false_alarm_budget"],
                        "severity": "error",
                    }
                )
            elif not (0 < bf <= Fraction(1, 2)):
                issues.append(
                    {
                        "code": "runtime_false_alarm_budget_out_of_range",
                        "message": "false_alarm_budget must satisfy 0 < false_alarm_budget <= 0.5",
                        "path": path + ["decision", "false_alarm_budget"],
                        "severity": "error",
                    }
                )
            else:
                budget_frac = bf
        elif is_backend:
            budget_frac = Fraction(5, 100)

        horizon_val: Optional[int] = None
        if "horizon_days" in decision:
            hd = decision.get("horizon_days")
            if not _is_int_strict(hd) or not (1 <= hd <= 365):
                issues.append(
                    {
                        "code": "runtime_horizon_out_of_range",
                        "message": "horizon_days must be in 1..365",
                        "path": path + ["decision", "horizon_days"],
                        "severity": "error",
                    }
                )
            else:
                horizon_val = hd
        elif is_backend:
            horizon_val = 30

        min_samples_val: Optional[int] = None
        if "min_samples" in decision:
            ms = decision.get("min_samples")
            if not _is_int_strict(ms) or not (1 <= ms <= 10_000_000):
                issues.append(
                    {
                        "code": "runtime_min_samples_out_of_range",
                        "message": "min_samples must be in 1..10000000",
                        "path": path + ["decision", "min_samples"],
                        "severity": "error",
                    }
                )
            else:
                min_samples_val = ms
        elif is_backend:
            min_samples_val = 200
        elif role in {"primary_zero", "promotion"}:
            min_samples_val = 1

        if "max_unresolved_fraction" in decision:
            uf = _to_exact_fraction(decision.get("max_unresolved_fraction"))
            if uf is None:
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "max_unresolved_fraction must be an exact decimal number",
                        "path": path + ["decision", "max_unresolved_fraction"],
                        "severity": "error",
                    }
                )
            elif not (0 <= uf <= Fraction(1, 2)):
                issues.append(
                    {
                        "code": "runtime_unresolved_fraction_out_of_range",
                        "message": "max_unresolved_fraction must satisfy 0 <= f <= 0.5",
                        "path": path + ["decision", "max_unresolved_fraction"],
                        "severity": "error",
                    }
                )

        c_windows: Optional[int] = None
        c_age: Optional[int] = None
        if isinstance(episode, dict):
            if "closure_windows" in episode:
                cw = episode.get("closure_windows")
                if not _is_int_strict(cw) or not (1 <= cw <= 24):
                    issues.append(
                        {
                            "code": "runtime_closure_windows_out_of_range",
                            "message": "closure_windows must be in 1..24",
                            "path": path + ["episode", "closure_windows"],
                            "severity": "error",
                        }
                    )
                else:
                    c_windows = cw
            elif is_backend:
                c_windows = 2

            if "closure_max_age_hours" in episode:
                ca = episode.get("closure_max_age_hours")
                if not _is_int_strict(ca) or not (1 <= ca <= 720):
                    issues.append(
                        {
                            "code": "runtime_closure_age_out_of_range",
                            "message": "closure_max_age_hours must be in 1..720",
                            "path": path + ["episode", "closure_max_age_hours"],
                            "severity": "error",
                        }
                    )
                else:
                    c_age = ca
            elif is_backend:
                c_age = 24
        elif is_backend:
            c_windows = 2
            c_age = 24

        if isinstance(limits, dict):
            if "max_active_obligations" in limits:
                mao = limits.get("max_active_obligations")
                if not _is_int_strict(mao) or mao < 1:
                    issues.append(
                        {
                            "code": "runtime_max_active_obligations_out_of_range",
                            "message": "max_active_obligations must be >= 1",
                            "path": path + ["limits", "max_active_obligations"],
                            "severity": "error",
                        }
                    )
            if "max_tracked_correlations" in limits:
                mtc = limits.get("max_tracked_correlations")
                if not _is_int_strict(mtc) or mtc < 1:
                    issues.append(
                        {
                            "code": "runtime_max_tracked_correlations_out_of_range",
                            "message": "max_tracked_correlations must be >= 1",
                            "path": path + ["limits", "max_tracked_correlations"],
                            "severity": "error",
                        }
                    )

        # Closure reachability (§5.6)
        if (
            role in _PRIMARY_ROLES
            and w_hours is not None
            and grace_min is not None
            and c_windows is not None
            and c_age is not None
        ):
            if c_age * 60 < c_windows * w_hours * 60 + grace_min + 60:
                issues.append(
                    {
                        "code": "closure_unreachable",
                        "message": "closure_max_age_hours cannot accommodate closure_windows + grace + 1h",
                        "path": path + ["episode"],
                        "severity": "error",
                    }
                )

        # Burn threshold and power check (§5.4)
        theta_frac = _to_exact_fraction(req.get("max_rate")) if req_kind == "rate_bound" else None
        if role == "burn" and not is_backend:
            tf_frac = _to_exact_fraction(decision.get("threshold_factor"))
            if tf_frac is None:
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "threshold_factor must be an exact decimal number",
                        "path": path + ["decision", "threshold_factor"],
                        "severity": "error",
                    }
                )
            elif (
                theta_frac is not None
                and 0 < theta_frac < 1
                and budget_frac is not None
                and horizon_val is not None
                and w_hours is not None
                and min_samples_val is not None
            ):
                b_theta = tf_frac * theta_frac
                m_windows = (24 * horizon_val) // w_hours
                alpha_w = budget_frac / m_windows
                if tf_frac <= 1 or b_theta >= 1 or (b_theta ** min_samples_val) >= alpha_w:
                    issues.append(
                        {
                            "code": "runtime_burn_out_of_range",
                            "message": "burn monitor requires b > 1, b*theta < 1, and breach reachable at min_samples",
                            "path": path + ["decision", "threshold_factor"],
                            "severity": "error",
                        }
                    )

        # Primary rate_bound power checks (§5.5)
        if (
            role == "primary_rate"
            and theta_frac is not None
            and 0 < theta_frac < 1
            and conf_frac is not None
            and budget_frac is not None
            and horizon_val is not None
            and w_hours is not None
            and min_samples_val is not None
        ):
            m_windows = (24 * horizon_val) // w_hours
            met_unreachable = False
            breach_unreachable = False
            if method == "clopper_pearson_rational_v2":
                met_unreachable = ((1 - theta_frac) ** min_samples_val) > (1 - conf_frac)
                alpha_w = budget_frac / m_windows
                breach_unreachable = (theta_frac ** min_samples_val) >= alpha_w
            else:
                try:
                    import math
                    from scipy.stats import beta  # type: ignore

                    up = float(beta.ppf(float(conf_frac), 1, min_samples_val))
                    alpha_w_f = float(budget_frac) / m_windows
                    lo = float(beta.ppf(alpha_w_f, min_samples_val, 1))
                    if math.isnan(up) or math.isnan(lo):
                        raise ValueError("scipy.stats.beta.ppf returned NaN")
                    met_unreachable = up > float(theta_frac)
                    breach_unreachable = lo <= float(theta_frac)
                except Exception:  # noqa: BLE001
                    issues.append(
                        {
                            "code": "runtime_invalid_profile",
                            # RFC 0003 §5.10: a fixed message that echoes no input; the
                            # path locates the monitor.
                            "message": (
                                "Monitor uses clopper_pearson_exact_v1, "
                                "whose power bounds could not be evaluated with scipy.stats.beta"
                            ),
                            "path": path + ["decision", "method"],
                            "severity": "error",
                        }
                    )

            if met_unreachable:
                issues.append(
                    {
                        "code": "runtime_met_unreachable_at_min_samples",
                        "message": "Monitor cannot establish MET at decision.min_samples",
                        "path": path + ["decision", "min_samples"],
                        "severity": "warning" if is_backend else "error",
                    }
                )
            if breach_unreachable:
                issues.append(
                    {
                        "code": "runtime_breach_unreachable_at_min_samples",
                        "message": "Monitor cannot establish BREACHED at decision.min_samples",
                        "path": path + ["decision", "min_samples"],
                        "severity": "warning",
                    }
                )

        # Promotion monitor shadowing chance constraint (§5.5)
        if role == "promotion" and (name in chance_names or req_name in chance_names):
            issues.append(
                {
                    "code": "chance_constraint_shadowed",
                    "message": "Promotion monitor shadows chance_constraint of the same name",
                    "path": path + ["name"],
                    "severity": "warning",
                }
            )

        # Effective key duplicate check (§5.6)
        if phase == "runtime":
            eff_scope = applies_to or ("tenant_floor" if is_pack else "agent")
            eff_key = (eff_scope, _monitor_effective_key(mon, req))
            if eff_key in seen_effective_keys:
                issues.append(
                    {
                        "code": "runtime_duplicate_key",
                        "message": "Monitor duplicates the effective key of another monitor",
                        "path": path,
                        "severity": "error",
                    }
                )
            seen_effective_keys.add(eff_key)

    # Obligation requirement references (`of`), deadline feasibility, and cycle detection
    liveness_covered_monitors: Set[str] = set()
    for r_idx, req in enumerate(reqs_list):
        if not isinstance(req, dict):
            continue
        r_kind = req.get("kind")
        if r_kind not in {"recovery_time", "evidence_liveness"}:
            continue
        of_name = req.get("of")
        path = ["requirements", r_idx, "of"]
        target_mon = mons_by_name.get(of_name) if isinstance(of_name, str) else None
        if target_mon is None:
            issues.append(
                {
                    "code": "runtime_missing_ref",
                    "message": "Requirement of references an undeclared monitor",
                    "path": path,
                    "severity": "error",
                }
            )
            continue
        target_req = reqs_by_name.get(target_mon.get("requirement", ""))
        target_role = _monitor_role(target_mon, target_req)
        if r_kind == "recovery_time":
            if target_role not in _PRIMARY_ROLES:
                issues.append(
                    {
                        "code": "runtime_ref_kind_mismatch",
                        "message": "recovery_time of must reference a primary runtime monitor with an episode",
                        "path": path,
                        "severity": "error",
                    }
                )
            else:
                within_hours = req.get("within_hours")
                t_win = target_mon.get("window") or {}
                t_ep = target_mon.get("episode") or {}
                w_h = t_win.get("tumbling_hours", 6 if target_mon.get("profile") == "backend_v1" else None)
                k_c = t_ep.get("closure_windows", 2 if target_mon.get("profile") == "backend_v1" else None)
                if _is_int_strict(within_hours) and within_hours >= 1 and _is_int_strict(w_h) and _is_int_strict(k_c):
                    if within_hours < k_c * w_h:
                        issues.append(
                            {
                                "code": "recovery_deadline_impossible",
                                "message": "within_hours must be >= closure_windows * tumbling_hours",
                                "path": ["requirements", r_idx, "within_hours"],
                                "severity": "error",
                            }
                        )
        elif r_kind == "evidence_liveness":
            if target_role not in _PRIMARY_ROLES | {"burn"}:
                issues.append(
                    {
                        "code": "runtime_ref_kind_mismatch",
                        "message": "evidence_liveness 'of' must reference a runtime window monitor",
                        "path": path,
                        "severity": "error",
                    }
                )
            else:
                liveness_covered_monitors.add(of_name)

    # Dependency cycle check: requirement -> of -> monitor -> requirement
    for r_idx, req in enumerate(reqs_list):
        if not isinstance(req, dict):
            continue
        start_name = req.get("name")
        if not isinstance(start_name, str):
            continue
        curr_req = req
        visited: Set[str] = {start_name}
        while curr_req.get("kind") in {"recovery_time", "evidence_liveness"}:
            of_mon_name = curr_req.get("of")
            if not isinstance(of_mon_name, str) or of_mon_name not in mons_by_name:
                break
            next_req_name = mons_by_name[of_mon_name].get("requirement")
            if not isinstance(next_req_name, str) or next_req_name not in reqs_by_name:
                break
            if next_req_name in visited:
                issues.append(
                    {
                        "code": "runtime_dependency_cycle",
                        "message": "Cyclic dependency involving requirement",
                        "path": ["requirements", r_idx],
                        "severity": "error",
                    }
                )
                break
            visited.add(next_req_name)
            curr_req = reqs_by_name[next_req_name]

    # runtime_liveness_missing warning (§5.5)
    for m_idx, mon in enumerate(mons):
        if not isinstance(mon, dict):
            continue
        m_name = mon.get("name")
        if not isinstance(m_name, str):
            continue
        req = reqs_by_name.get(mon.get("requirement", ""))
        if req is None:
            continue
        role = _monitor_role(mon, req)
        if role in _PRIMARY_ROLES and m_name not in liveness_covered_monitors:
            issues.append(
                {
                    "code": "runtime_liveness_missing",
                    "message": "Primary runtime monitor is not covered by an evidence_liveness requirement",
                    "path": ["monitors", m_idx, "name"],
                    "severity": "warning",
                }
            )


def _emitted_events_for_monitor(mon: Dict[str, Any], req: Optional[Dict[str, Any]]) -> Set[str]:
    role = _monitor_role(mon, req)
    if role in _PRIMARY_ROLES:
        events = {
            "unknown_for",
            "episode_opened",
            "episode_continued",
            "episode_open_for",
            "episode_resolved",
            "episode_withdrawn",
        }
        source = (mon.get("evidence") or {}).get("source")
        if source == "customer_side" and role != "primary_aggregate":
            events.add("unit_violation")
        return events
    if role == "burn":
        return {"burn_breached"}
    if role == "recovery":
        return {"recovery_overdue", "recovery_cancelled", "recovery_recovered"}
    if role == "liveness":
        return {"stale", "live_again"}
    return set()


def _lint_responses(doc: Dict[str, Any], issues: List[Issue]) -> None:
    resps = doc.get("responses")
    if resps is None:
        return
    if not isinstance(resps, list):
        issues.append(
            {
                "code": "runtime_invalid_profile",
                "message": "responses must be a list",
                "path": ["responses"],
                "severity": "error",
            }
        )
        return

    reqs_by_name: Dict[str, Dict[str, Any]] = {
        r["name"]: r
        for r in (doc.get("requirements") or [])
        if isinstance(r, dict) and isinstance(r.get("name"), str)
    }
    mons_by_name: Dict[str, Dict[str, Any]] = {
        m["name"]: m
        for m in (doc.get("monitors") or [])
        if isinstance(m, dict) and isinstance(m.get("name"), str)
    }
    legacy_names = _legacy_module_names(doc)
    guard_edges: List[Tuple[str, str, List[Any]]] = []
    seen_resp_names: Set[str] = set()

    for r_idx, resp in enumerate(resps):
        r_path = ["responses", r_idx]
        if not isinstance(resp, dict):
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Response declaration must be an object",
                    "path": r_path,
                    "severity": "error",
                }
            )
            continue

        r_name = resp.get("name")
        if not isinstance(r_name, str) or not _RUNTIME_IDENT_RE.match(r_name):
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Response name must be a runtime identifier",
                    "path": r_path + ["name"],
                    "severity": "error",
                }
            )
        else:
            if r_name in seen_resp_names or r_name in legacy_names:
                issues.append(
                    {
                        "code": "runtime_name_collision",
                        "message": "Response name collides with an existing declaration",
                        "path": r_path + ["name"],
                        "severity": "error",
                    }
                )
            seen_resp_names.add(r_name)

        rules = resp.get("rules")
        if not isinstance(rules, list):
            issues.append(
                {
                    "code": "runtime_invalid_profile",
                    "message": "Response 'rules' must be a list",
                    "path": r_path + ["rules"],
                    "severity": "error",
                }
            )
            continue

        rules_by_id = {r.get("id"): r for r in rules if isinstance(r, dict) and isinstance(r.get("id"), str)}
        seen_rule_ids: Set[str] = set()
        for rule_idx, rule in enumerate(rules):
            path = r_path + ["rules", rule_idx]
            if not isinstance(rule, dict):
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "Response rule must be an object",
                        "path": path,
                        "severity": "error",
                    }
                )
                continue

            rule_id = rule.get("id")
            if not isinstance(rule_id, str) or not _RUNTIME_IDENT_RE.match(rule_id):
                issues.append(
                    {
                        "code": "runtime_invalid_profile",
                        "message": "Rule id must be a runtime identifier",
                        "path": path + ["id"],
                        "severity": "error",
                    }
                )
            else:
                if rule_id in seen_rule_ids:
                    issues.append(
                        {
                            "code": "response_rule_id_duplicate",
                            "message": "Rule id duplicates another rule in this response",
                            "path": path + ["id"],
                            "severity": "error",
                        }
                    )
                seen_rule_ids.add(rule_id)

            trigger = rule.get("trigger")
            t_mon: Optional[Dict[str, Any]] = None
            t_req: Optional[Dict[str, Any]] = None
            t_event: Optional[str] = None
            if not isinstance(trigger, dict):
                issues.append(
                    {
                        "code": "runtime_invalid_ladder",
                        "message": "Rule 'trigger' must be an object",
                        "path": path + ["trigger"],
                        "severity": "error",
                    }
                )
            elif "rule" in trigger:
                t_event = trigger.get("event")
                _lint_outcome_trigger(doc, rule, rules_by_id, path, issues)
            else:
                mon_name = trigger.get("monitor")
                t_event = trigger.get("event")
                if not isinstance(t_event, str) or t_event not in _TRIGGER_EVENTS:
                    issues.append(
                        {
                            "code": "runtime_unknown_kind",
                            "message": "Unknown trigger event",
                            "path": path + ["trigger", "event"],
                            "severity": "error",
                        }
                    )
                t_mon = mons_by_name.get(mon_name) if isinstance(mon_name, str) else None
                if t_mon is None:
                    issues.append(
                        {
                            "code": "runtime_missing_ref",
                            "message": "Trigger monitor references an undeclared monitor",
                            "path": path + ["trigger", "monitor"],
                            "severity": "error",
                        }
                    )
                else:
                    t_req = reqs_by_name.get(t_mon.get("requirement", ""))
                    if isinstance(t_event, str) and t_event in _TRIGGER_EVENTS:
                        if t_event == "unknown_for" and _monitor_role(t_mon, t_req) not in _PRIMARY_ROLES:
                            issues.append({"code": "runtime_invalid_ladder", "message": "unknown_for requires a primary runtime monitor",
                                           "path": path + ["trigger", "event"], "severity": "error"})
                        elif t_event not in _emitted_events_for_monitor(t_mon, t_req):
                            issues.append(
                                {
                                    "code": "runtime_ref_kind_mismatch",
                                    "message": "Monitor does not emit this trigger event",
                                    "path": path + ["trigger", "event"],
                                    "severity": "error",
                                }
                            )
                if "hours" in trigger:
                    t_hours = trigger.get("hours")
                    if not _is_int_strict(t_hours) or t_hours < 1:
                        issues.append(
                            {
                                "code": "runtime_trigger_hours_out_of_range",
                                "message": "trigger.hours must be >= 1",
                                "path": path + ["trigger", "hours"],
                                "severity": "error",
                            }
                        )
                    if t_event not in {"episode_open_for", "unknown_for"}:
                        issues.append(
                            {
                                "code": "runtime_invalid_ladder",
                                "message": "trigger.hours is only permitted with episode_open_for or unknown_for",
                                "path": path + ["trigger", "hours"],
                                "severity": "error",
                            }
                        )
                elif t_event in {"episode_open_for", "unknown_for"}:
                    issues.append(
                        {
                            "code": "runtime_invalid_ladder",
                            "message": "This event requires trigger.hours",
                            "path": path + ["trigger"],
                            "severity": "error",
                        }
                    )

            if isinstance(trigger, dict) and trigger.get("event") == "unknown_for" and t_mon is not None:
                window = t_mon.get("window")
                window_hours = window.get("tumbling_hours") if isinstance(window, dict) else (6 if t_mon.get("profile") == "backend_v1" else None)
                hours = trigger.get("hours")
                if _is_int_strict(hours) and _is_int_strict(window_hours) and hours < window_hours:
                    issues.append({"code": "runtime_trigger_hours_out_of_range", "message": "unknown_for hours must be at least tumbling_hours",
                                   "path": path + ["trigger", "hours"], "severity": "error"})
            _lint_reactive_guards(doc, rule, rules_by_id, mons_by_name, reqs_by_name, path, issues, guard_edges)
            _lint_persistence(rule, mons_by_name, reqs_by_name, path, issues)

            action = rule.get("do")
            if not isinstance(action, str) or action not in _ACTIONS:
                issues.append(
                    {
                        "code": "response_unknown_action",
                        "message": "Unknown response action",
                        "path": path + ["do"],
                        "severity": "error",
                    }
                )
                continue

            approval = rule.get("approval")
            if approval is not None and (not isinstance(approval, str) or approval not in _APPROVALS):
                issues.append(
                    {
                        "code": "runtime_unknown_kind",
                        "message": "Expected approval: none, standing, human",
                        "path": path + ["approval"],
                        "severity": "error",
                    }
                )
                continue

            default_approval = (
                "none"
                if action in {"notify", "open_next_step", "block_action", "halt_unit"}
                else "human"
            )
            eff_approval = approval if approval is not None else default_approval

            if action == "suspend":
                if approval != "human":
                    issues.append(
                        {
                            "code": "response_suspend_without_human",
                            "message": "suspend requires approval: human",
                            "path": path + ["approval"],
                            "severity": "error",
                        }
                    )
                if t_event not in _SUSPEND_ESCALATION_EVENTS:
                    issues.append(
                        {
                            "code": "response_suspend_unconfirmed",
                            "message": "suspend requires an escalation trigger event (episode_continued, episode_open_for, or recovery_overdue)",
                            "path": path + ["trigger", "event"],
                            "severity": "error",
                        }
                    )
            elif action in {"optimize", "rollback", "throttle", "degrade"}:
                if eff_approval == "none":
                    issues.append(
                        {
                            "code": "response_irreversible_without_approval",
                            "message": f"Action '{action}' requires 'standing' or 'human' approval",
                            "path": path + ["approval"],
                            "severity": "error",
                        }
                    )
            elif action in {"notify", "open_next_step", "block_action", "halt_unit"}:
                if eff_approval != "none":
                    issues.append(
                        {
                            "code": "runtime_invalid_ladder",
                            "message": f"Action '{action}' only permits approval: none",
                            "path": path + ["approval"],
                            "severity": "error",
                        }
                    )

            if action in {"open_next_step", "optimize", "rollback", "throttle", "degrade", "suspend"} and t_event in {
                "episode_resolved", "episode_withdrawn", "recovery_cancelled", "recovery_recovered", "live_again", "unit_violation"
            }:
                issues.append({
                    "code": "runtime_invalid_ladder",
                    "message": "Service action requires an active originating scope; this event cannot authorize it (§7.4)",
                    "path": path + ["trigger", "event"],
                    "severity": "error",
                })

            # Action-specific parameter rules (§5.8, §7.2)
            def invalid_parameter(field: str, expected: str) -> None:
                issues.append({
                    "code": "runtime_invalid_ladder",
                    "message": expected,
                    "path": path + [field],
                    "severity": "error",
                })
            if action == "rollback":
                target = rule.get("target")
                if not isinstance(target, str) or (target != "last_certified" and not _FINGERPRINT_RE.match(target)):
                    invalid_parameter("target", "target requires last_certified or 64 lowercase hex characters")
            elif "target" in rule:
                invalid_parameter("target", "target is permitted only on rollback")

            if action == "suspend":
                fb = rule.get("fallback")
                if not isinstance(fb, str) or fb not in _SUSPEND_FALLBACKS:
                    invalid_parameter("fallback", "fallback requires static_unavailable or route_to_human")
            elif action == "degrade":
                fb = rule.get("fallback")
                if not isinstance(fb, str) or not _FINGERPRINT_RE.match(fb):
                    invalid_parameter("fallback", "fallback requires 64 lowercase hex characters")
            elif "fallback" in rule:
                invalid_parameter("fallback", "fallback is permitted only on suspend or degrade")

            if action == "throttle":
                if "rate_floor" not in rule:
                    invalid_parameter("rate_floor", "rate_floor requires an exact decimal number satisfying 0 < rate_floor < 1")
                else:
                    rf_frac = _to_exact_fraction(rule.get("rate_floor"))
                    if rf_frac is None:
                        issues.append(
                            {
                                "code": "runtime_invalid_profile",
                                "message": "rate_floor must be an exact decimal number",
                                "path": path + ["rate_floor"],
                                "severity": "error",
                            }
                        )
                    elif not (0 < rf_frac < 1):
                        issues.append(
                            {
                                "code": "runtime_rate_floor_out_of_range",
                                "message": "rate_floor must satisfy 0 < rate_floor < 1",
                                "path": path + ["rate_floor"],
                                "severity": "error",
                            }
                        )
            elif "rate_floor" in rule:
                invalid_parameter("rate_floor", "rate_floor is permitted only on throttle")

            if "severity" in rule:
                if action != "notify":
                    invalid_parameter("severity", "severity is permitted only on notify")
                else:
                    sev = rule.get("severity")
                    if not isinstance(sev, str) or sev not in _SEVERITIES:
                        issues.append(
                            {
                                "code": "runtime_unknown_kind",
                                "message": "Expected severity: info, warning, critical",
                                "path": path + ["severity"],
                                "severity": "error",
                            }
                        )

            if action in {"block_action", "halt_unit"}:
                if "on_check_error" not in rule:
                    issues.append(
                        {
                            "code": "response_on_check_error_missing",
                            "message": f"Local guard '{action}' requires on_check_error",
                            "path": path,
                            "severity": "error",
                        }
                    )
                else:
                    oce = rule.get("on_check_error")
                    if not isinstance(oce, str) or oce not in _ON_CHECK_ERRORS:
                        issues.append(
                            {
                                "code": "runtime_unknown_kind",
                                "message": "Expected on_check_error: block, allow",
                                "path": path + ["on_check_error"],
                                "severity": "error",
                            }
                        )
                if t_mon is not None and t_req is not None:
                    t_source = (t_mon.get("evidence") or {}).get("source")
                    t_pattern = (t_req.get("violation") or {}).get("pattern")
                    if t_event != "unit_violation" or t_source != "customer_side" or t_pattern not in _WITNESS_PATTERNS:
                        issues.append(
                            {
                                "code": "response_guard_not_enforceable",
                                "message": f"Local guard '{action}' requires customer_side unit_violation with a pattern whose violation is fixed by a prefix (absence, bounded_existence, precedence, protocol)",
                                "path": path,
                                "severity": "error",
                            }
                        )
            elif "on_check_error" in rule:
                invalid_parameter("on_check_error", "on_check_error is permitted only on block_action or halt_unit")

            if "deploy" in rule:
                deploy = rule.get("deploy")
                if action != "optimize":
                    invalid_parameter("deploy", "deploy is permitted only on optimize")
                elif not isinstance(deploy, str) or deploy not in _DEPLOY_MODES:
                    issues.append(
                        {
                            "code": "runtime_unknown_kind",
                            "message": "Expected deploy: never, if_promoted",
                            "path": path + ["deploy"],
                            "severity": "error",
                        }
                    )
                elif deploy == "if_promoted":
                    if t_event not in _DEPLOY_EPISODE_EVENTS:
                        issues.append(
                            {
                                "code": "runtime_invalid_ladder",
                                "message": "deploy: if_promoted requires an episode trigger (episode_opened, episode_continued, or episode_open_for)",
                                "path": path + ["trigger", "event"],
                                "severity": "error",
                            }
                        )
                    gate_req = t_mon.get("requirement") if t_mon is not None else None
                    has_gate = isinstance(gate_req, str) and any(
                        isinstance(m, dict) and m.get("phase") == "promotion" and m.get("requirement") == gate_req
                        for m in mons_by_name.values()
                    )
                    if t_mon is not None and not has_gate:
                        issues.append(
                            {
                                "code": "response_deploy_without_promotion_monitor",
                                "message": "deploy: if_promoted requires a promotion monitor on the trigger monitor's requirement",
                                "path": path + ["deploy"],
                                "severity": "error",
                            }
                        )

            has_repeat_after = "repeat_after_hours" in rule
            has_max_repeats = "max_repeats" in rule
            if has_repeat_after:
                rah = rule.get("repeat_after_hours")
                if not _is_int_strict(rah) or rah < 1:
                    issues.append(
                        {
                            "code": "runtime_repeat_after_hours_out_of_range",
                            "message": "repeat_after_hours must be >= 1",
                            "path": path + ["repeat_after_hours"],
                            "severity": "error",
                        }
                    )
            if has_max_repeats:
                mr = rule.get("max_repeats")
                if not _is_int_strict(mr) or mr < 1:
                    issues.append(
                        {
                            "code": "runtime_max_repeats_out_of_range",
                            "message": "max_repeats must be >= 1",
                            "path": path + ["max_repeats"],
                            "severity": "error",
                        }
                    )
                if not has_repeat_after:
                    invalid_parameter("max_repeats", "max_repeats requires repeat_after_hours")
            if has_repeat_after and not has_max_repeats and action != "notify":
                issues.append(
                    {
                        "code": "response_rule_repeat_unbounded",
                        "message": f"Action '{action}' with repeat_after_hours requires max_repeats",
                        "path": path,
                        "severity": "error",
                    }
                )


    _lint_guard_cycles(guard_edges, issues)


def _rule_source_monitor(rule: Dict[str, Any], rules: Dict[str, Any]) -> Optional[str]:
    trigger = rule.get("trigger")
    if not isinstance(trigger, dict):
        return None
    if "rule" in trigger:
        target = rules.get(trigger["rule"]) if isinstance(trigger["rule"], str) else None
        trigger = target.get("trigger") if isinstance(target, dict) and target.get("do") == "optimize" else None
    return trigger.get("monitor") if isinstance(trigger, dict) and isinstance(trigger.get("monitor"), str) else None


def _lint_outcome_trigger(doc: Dict[str, Any], rule: Dict[str, Any], rules: Dict[str, Any],
                          path: List[Any], issues: List[Issue]) -> None:
    trigger = rule["trigger"]
    def error(code: str, message: str, field: str = "trigger") -> None:
        issues.append({"code": code, "message": message, "path": path + [field], "severity": "error"})
    event = trigger.get("event")
    if not isinstance(event, str) or event not in _OUTCOME_EVENTS:
        error("runtime_unknown_kind", "Unknown outcome event")
    if set(trigger) != {"rule", "event"}:
        error("runtime_invalid_ladder", "An outcome trigger has only rule and event")
    target = rules.get(trigger.get("rule")) if isinstance(trigger.get("rule"), str) else None
    if target is None:
        error("runtime_missing_ref", "Outcome trigger requires a rule in the same response")
    elif target is rule or target.get("do") != "optimize":
        error("runtime_ref_kind_mismatch", "Outcome trigger must name another optimize rule")
    elif event in {"deploy_refused", "deploy_failed"} and target.get("deploy", "never") != "if_promoted":
        error("runtime_invalid_ladder", "Deploy outcomes require deploy: if_promoted")
    if "repeat_after_hours" in rule or "max_repeats" in rule:
        error("runtime_invalid_ladder", "Outcome triggers cannot repeat")
    if "pack" in doc and "tvl" not in doc:
        error("runtime_invalid_ladder", "Packs cannot declare outcome triggers")


def _lint_reactive_guards(doc: Dict[str, Any], rule: Dict[str, Any], rules: Dict[str, Any],
                          monitors: Dict[str, Any], requirements: Dict[str, Any], path: List[Any],
                          issues: List[Issue], edges: List[Tuple[str, str, List[Any]]]) -> None:
    trigger = rule.get("trigger")
    reactive = "only_while" in rule or "unless" in rule or "persist" in rule or (
        isinstance(trigger, dict) and ("rule" in trigger or trigger.get("event") == "unknown_for"))
    if reactive and rule.get("do") != "notify":
        issues.append({"code": "runtime_notify_only", "message": "Reactive outcomes and guards are notify-only",
                       "path": path + ["do"], "severity": "error"})
    source = _rule_source_monitor(rule, rules)
    for field in ("only_while", "unless"):
        if field not in rule:
            continue
        guards = rule[field]
        if not isinstance(guards, list):
            issues.append({"code": "runtime_invalid_profile", "message": "Guards must be a list",
                           "path": path + [field], "severity": "error"})
            continue
        for idx, guard in enumerate(guards):
            gpath = path + [field, idx]
            def issue(code: str, message: str, severity: str = "error") -> None:
                issues.append({"code": code, "message": message, "path": gpath, "severity": severity})
            if not isinstance(guard, dict) or set(guard) not in ({"monitor", "state"}, {"rule", "state"}):
                issue("runtime_unknown_kind", "Expected a sealed episode_open or attempt_open guard")
                continue
            key, state = ("monitor", "episode_open") if "monitor" in guard else ("rule", "attempt_open")
            if guard.get("state") != state:
                issue("runtime_unknown_kind", "Unknown guard state for this reference kind")
                continue
            name = guard[key]
            target = (monitors if key == "monitor" else rules).get(name) if isinstance(name, str) else None
            if key == "rule" and "pack" in doc and "tvl" not in doc:
                issue("runtime_invalid_ladder", "Packs cannot declare attempt_open guards")
            if target is None:
                issue("runtime_missing_ref", "Guard reference is not declared in its scope")
            elif key == "rule" and target.get("do") != "optimize":
                issue("runtime_ref_kind_mismatch", "attempt_open requires an optimize rule in the same response")
            elif key == "monitor" and _monitor_role(target, requirements.get(target.get("requirement"))) not in _PRIMARY_ROLES:
                issue("runtime_ref_kind_mismatch", "episode_open requires a primary runtime monitor")
            if key == "monitor" and source is not None and isinstance(name, str):
                if field == "unless":
                    edges.append((source, name, gpath))
                elif source == name:
                    issue("runtime_guard_redundant", "only_while on the source monitor is redundant", "warning")


def _lint_persistence(rule: Dict[str, Any], monitors: Dict[str, Any], requirements: Dict[str, Any],
                      path: List[Any], issues: List[Issue]) -> None:
    """RFC 0005 §2.2: breach persistence on a notification."""
    if "persist" not in rule:
        return
    persist = rule["persist"]

    def error(code: str, message: str, subpath: List[Any]) -> None:
        issues.append({"code": code, "message": message, "path": path + subpath, "severity": "error"})

    if not isinstance(persist, dict) or set(persist) != {"breached_in", "of_last"}:
        error("runtime_invalid_profile", "persist requires exactly breached_in and of_last", ["persist"])
    else:
        k, n = persist["breached_in"], persist["of_last"]
        if not _is_int_strict(k) or not _is_int_strict(n):
            error("runtime_invalid_profile", "persist coordinates must be integers", ["persist"])
        elif not 1 <= k <= n <= _PERSIST_MAX:
            error("runtime_persistence_out_of_range", "persist requires 1 <= breached_in <= of_last <= 168", ["persist"])
    trigger = rule.get("trigger")
    if "repeat_after_hours" in rule or "max_repeats" in rule:
        error("runtime_invalid_persistence", "persist cannot be combined with repeat_after_hours or max_repeats", ["persist"])
    if not isinstance(trigger, dict):
        return
    if "monitor" not in trigger or not isinstance(trigger.get("event"), str) or trigger["event"] not in _PERSIST_EVENTS:
        error("runtime_invalid_persistence", "persist requires an episode_opened or episode_continued monitor trigger", ["trigger"])
        return
    monitor = monitors.get(trigger["monitor"]) if isinstance(trigger["monitor"], str) else None
    if monitor is not None and _monitor_role(monitor, requirements.get(monitor.get("requirement"))) not in _PRIMARY_ROLES:
        error("runtime_invalid_persistence", "persist requires a primary runtime monitor source", ["trigger", "monitor"])


def _lint_guard_cycles(edges: List[Tuple[str, str, List[Any]]], issues: List[Issue]) -> None:
    graph: Dict[str, Set[str]] = {}
    for source, target, _ in edges:
        graph.setdefault(source, set()).add(target)
    # Each edge is cyclic iff its target can reach its source (including self-loops).
    for source, target, path in edges:
        pending, visited = [target], set()
        while pending:
            node = pending.pop()
            if node == source:
                issues.append({"code": "runtime_guard_cycle", "message": "Cycle in notification unless monitor graph",
                               "path": path, "severity": "error"})
                break
            if node not in visited:
                visited.add(node)
                pending.extend(graph.get(node, ()))
