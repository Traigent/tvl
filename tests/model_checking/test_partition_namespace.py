"""Small-scope checks: binding partition (RFC §3.1) and namespaces (§3.7).

Exhaustive enumeration over tiny name universes — every module shape up to
the scope bound is checked, so these are small-scope proofs, not samples.
"""

from __future__ import annotations

import itertools

from .model import (
    CVar,
    Module,
    Policy,
    TVar,
    namespace_diagnostics,
    uses_11_constructs,
)

NAMES = ("a", "b", "a.x")  # includes a dotted name and its strict prefix


def all_modules_up_to_scope():
    """Enumerate all modules with ≤2 tvars, ≤2 cvars, ≤1 policy over NAMES."""
    for n_tvars in range(3):
        for tvar_names in itertools.combinations(NAMES, n_tvars):
            for n_cvars in range(3):
                for cvar_names in itertools.combinations(NAMES, n_cvars):
                    for policy_names in ([], ["a"], ["b"]):
                        yield Module(
                            tvars=tuple(TVar(n, (0, 1)) for n in tvar_names),
                            cvars=tuple(CVar(n, source="s") for n in cvar_names),
                            policies=tuple(
                                Policy(n, "cascade", ("st1",)) for n in policy_names
                            ),
                        )


def test_partition_collision_detected_iff_overlap():
    """P6/§3.1: duplicate_name fires exactly when names collide across blocks."""
    checked = 0
    for module in all_modules_up_to_scope():
        names = module.declared_names
        has_dup = len(names) != len(set(names))
        diags = {code for code, _ in namespace_diagnostics(module)}
        assert ("duplicate_name" in diags) == has_dup, module
        checked += 1
    assert checked > 100  # the scope actually enumerated something substantial


def test_prefix_collision_detected_exactly_for_strict_prefix_pairs():
    """§3.7(5): a.x + a is a prefix collision; a.x alone or a+b is not."""
    with_pair = Module(tvars=(TVar("a", (0,)), TVar("a.x", (0,))))
    without_pair = Module(tvars=(TVar("a.x", (0,)), TVar("b", (0,))))
    assert any(
        code == "namespace_prefix_collision"
        for code, _ in namespace_diagnostics(with_pair)
    )
    assert not any(
        code == "namespace_prefix_collision"
        for code, _ in namespace_diagnostics(without_pair)
    )


def test_prefix_collision_severity_policy():
    """§3.7(5): warning on 1.0-valid modules; error only with 1.1 constructs.

    The model exposes detection; severity is the declared policy — this test
    pins the POLICY function (uses_11_constructs) that Phase 4 lints must use.
    """
    legacy = Module(tvars=(TVar("a", (0,)), TVar("a.x", (0,))))
    modern = Module(
        tvars=(TVar("a", (0,)), TVar("a.x", (0,))),
        cvars=(CVar("c", source="s"),),
    )
    assert not uses_11_constructs(legacy)  # -> warning severity
    assert uses_11_constructs(modern)  # -> error severity


def test_shared_namespace_spans_all_three_blocks():
    """§3.7(3): tvar/cvar/policy name collisions are all detected."""
    cases = [
        Module(tvars=(TVar("x", (0,)),), cvars=(CVar("x", source="s"),)),
        Module(tvars=(TVar("x", (0,)),), policies=(Policy("x", "cascade", ("s1",)),)),
        Module(
            cvars=(CVar("x", source="s"),),
            policies=(Policy("x", "cascade", ("s1",)),),
        ),
    ]
    for module in cases:
        assert any(
            code == "duplicate_name" for code, _ in namespace_diagnostics(module)
        ), module
