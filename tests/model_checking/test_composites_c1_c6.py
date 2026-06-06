"""Small-scope model checking for RFC 0002 "Composite Knobs", claims C1–C6.

House convention (RFC 0001's 272 checks, ``test_partition_namespace.py`` /
``test_promotion_cascade.py``): tiny finite universes, exhaustive ``itertools``
enumeration, plain pytest, no new deps. Each claim is one class. Every
UNSAT-style assertion ("no bad instance exists in the universe") is paired with
its TEETH twin ("the deliberately-broken instance/variant EXISTS and is
detected") — named ``test_*_teeth_*`` — so no check passes vacuously.

The algebra under test lives in ``composites_model.py``; the derived functions
(``leaf_t_*``, ``required_parents``, ``cal_*``, ``roots``, ``loop_execute`` vs.
``kchain_execute``) transcribe RFC 0002 v7 §3.2–§3.8 one-to-one.
"""

from __future__ import annotations

import itertools

from .composites_model import (
    NO_ACCEPT,
    AcceptDecl,
    AcceptStat,
    AggregateDecl,
    AggregateKind,
    Arm,
    ArmResult,
    ArmResultKind,
    Cascade,
    Composite,
    CompositeKind,
    CostForm,
    Ensemble,
    Env,
    ERROR,
    GateDecl,
    GateKind,
    IterStep,
    Loop,
    Placement,
    SignalUse,
    StopDecl,
    StopKind,
    arm_is_margin_bearing,
    body_fields,
    cal_composite,
    cal_composite_drop_judge,
    cal_roots,
    calibration_pass,
    child_refs,
    composite_arm,
    cost_is_closed,
    cost_of_arm,
    cost_of_composite,
    gate_typing_diagnostics,
    has_cycle,
    kchain_execute,
    leaf_t_composite,
    loop_execute,
    member_walk_cal,
    missing_composite_parent,
    missing_composite_refs,
    output,
    required_parents,
    result_well_formed,
    roots,
    signal_accept_unrollable,
    stage_arm,
    well_formed_kind,
)

# Tiny universes (2–4 atoms per sort), per the house scope discipline.
ALL_KINDS = list(CompositeKind)
BODY_FIELDS = ["cascade", "ensemble", "loop"]


def _body(field_name: str):
    """A minimal well-formed body object for the named field."""
    if field_name == "cascade":
        return Cascade(arms=(stage_arm("s"),))
    if field_name == "ensemble":
        return Ensemble(arms=(stage_arm("s"),), cardinality="k")
    return Loop(
        body=stage_arm("s"),
        stop=StopDecl(StopKind.EXHAUSTED),
        max_iters=1,
    )


def _make(kind: CompositeKind, present_fields, binds_value=False) -> Composite:
    kw = {f: _body(f) for f in present_fields}
    return Composite(name="c", kind=kind, binds_value=binds_value, **kw)


# ===========================================================================
# C1 — Constructor disjointness (kind partition) + closed result algebra.
# §3.2 item 1, §3.1, §3.2.1.
# ===========================================================================


class TestC1KindPartition:
    def test_exactly_one_kind_well_formed_iff_matching_single_body(self):
        """Exhaustive: over every (kind × subset-of-body-fields), the node is
        well-formed iff exactly the one body matching the kind is present and
        no value is bound. This is the partition: one kind ⟺ one body."""
        checked = 0
        for kind in ALL_KINDS:
            for r in range(len(BODY_FIELDS) + 1):
                for subset in itertools.combinations(BODY_FIELDS, r):
                    c = _make(kind, subset)
                    expected = list(subset) == [
                        {
                            CompositeKind.CASCADE: "cascade",
                            CompositeKind.ENSEMBLE: "ensemble",
                            CompositeKind.LOOP: "loop",
                        }[kind]
                    ]
                    assert well_formed_kind(c) == expected, (kind, subset)
                    checked += 1
        assert checked == len(ALL_KINDS) * (2 ** len(BODY_FIELDS))

    def test_well_formed_node_has_exactly_one_body_field(self):
        """No well-formed node carries a cross-kind or multi-body shape."""
        kind_to_field = {
            CompositeKind.CASCADE: "cascade",
            CompositeKind.ENSEMBLE: "ensemble",
            CompositeKind.LOOP: "loop",
        }
        for kind in ALL_KINDS:
            c = _make(kind, [kind_to_field[kind]])
            assert well_formed_kind(c)
            assert len(body_fields(c)) == 1

    def test_result_algebra_closed_disjoint_exhaustive(self):
        """§3.2.1: every result lands in exactly one of output/no_accept/error;
        ``out`` present iff OUTPUT. Exhaustive over the result-shape space."""
        outs = [None, "o"]
        margins = [None, 0.5]
        checked = 0
        for kind in ArmResultKind:
            for o in outs:
                for m in margins:
                    r = ArmResult(kind, out=o, vote_stats=m)
                    wf = result_well_formed(r)
                    if kind == ArmResultKind.OUTPUT:
                        assert wf == (o is not None)
                    else:
                        assert wf == (o is None and m is None)
                    checked += 1
        assert checked == len(ArmResultKind) * len(outs) * len(margins)

    # --- TEETH ---------------------------------------------------------------

    def test_c1_teeth_two_bodies_rejected(self):
        """A cross-kind body (two bodies present) EXISTS and is flagged."""
        bad = _make(CompositeKind.CASCADE, ["cascade", "ensemble"])
        assert not well_formed_kind(bad)
        assert len(body_fields(bad)) == 2

    def test_c1_teeth_kind_without_matching_body_rejected(self):
        """A kind whose matching body is absent (a different body present)."""
        bad = _make(CompositeKind.LOOP, ["cascade"])
        assert not well_formed_kind(bad)

    def test_c1_teeth_composite_binds_value_rejected(self):
        """§3.1: a value bound on a composite EXISTS and is rejected."""
        bad = _make(CompositeKind.CASCADE, ["cascade"], binds_value=True)
        assert not well_formed_kind(bad)

    def test_c1_teeth_bad_result_no_accept_with_output_detected(self):
        """A no_accept carrying an output is a broken result and is caught."""
        bad = ArmResult(ArmResultKind.NO_ACCEPT, out="leaked")
        assert not result_well_formed(bad)


# ===========================================================================
# C2 — Nesting well-formedness: acyclicity, finite expansion, tag resolution.
# §3.2 item 4 + item 3.
# ===========================================================================

C2_NAMES = ("a", "b", "c")


def _ref_composite(name: str, refs) -> Composite:
    """A cascade composite whose arms reference the given composite names."""
    arms = tuple(composite_arm(r) for r in refs) or (stage_arm("s"),)
    return Composite(name=name, kind=CompositeKind.CASCADE, cascade=Cascade(arms=arms))


def _enumerate_ref_graphs():
    """All directed graphs over 3 composite nodes where each node references a
    subset of the others (size ≤ 2) — the small-scope graph universe."""
    nodes = C2_NAMES
    others = {n: tuple(x for x in nodes if x != n) for n in nodes}
    per_node_choices = {
        n: [
            subset
            for k in range(3)
            for subset in itertools.combinations(others[n], k)
        ]
        for n in nodes
    }
    for ca in per_node_choices["a"]:
        for cb in per_node_choices["b"]:
            for cc in per_node_choices["c"]:
                yield {"a": ca, "b": cb, "c": cc}


def _graph_has_cycle_groundtruth(adj):
    """Independent reachability oracle for cycle presence."""
    def reaches(start, target, seen):
        for nxt in adj.get(start, ()):  # over edges
            if nxt == target:
                return True
            if nxt not in seen:
                seen.add(nxt)
                if reaches(nxt, target, seen):
                    return True
        return False

    return any(reaches(n, n, set()) for n in adj)


class TestC2Nesting:
    def test_acyclicity_matches_ground_truth_and_expansion_terminates(self):
        """Exhaustive over the small ref-graph universe: ``has_cycle`` agrees
        with an independent reachability oracle, AND when acyclic, transitive
        expansion (reachable set) is finite & irreflexive (terminates)."""
        checked = 0
        for adj in _enumerate_ref_graphs():
            comps = tuple(_ref_composite(n, adj[n]) for n in C2_NAMES)
            env = Env(composites=comps)
            gt_cycle = _graph_has_cycle_groundtruth(adj)
            assert has_cycle(env) == gt_cycle, adj
            if not gt_cycle:
                # acyclic ⇒ no node reaches itself; expansion is finite.
                from .composites_model import reachable

                for n in C2_NAMES:
                    assert n not in reachable(env, n), (adj, n)
            checked += 1
        # Each node references a subset (size 0/1/2) of the 2 OTHER nodes:
        # C(2,0)+C(2,1)+C(2,2) = 4 choices per node, 3 nodes.
        assert checked == 4 ** 3

    def test_tag_resolution_is_unambiguous(self):
        """§3.2 item 3: a stage arm never consults N_X; a composite arm always
        does. The two tags are disjoint by construction."""
        s = stage_arm("opaque", ["t1"])
        x = composite_arm("inner")
        assert s.is_stage and not s.is_composite
        assert x.is_composite and not x.is_stage
        env = Env(
            composites=(
                Composite("inner", CompositeKind.CASCADE, cascade=Cascade((stage_arm("y"),))),
                Composite(
                    "outer",
                    CompositeKind.CASCADE,
                    cascade=Cascade((s, x)),
                ),
            )
        )
        # child_refs reports ONLY the composite-tagged arm, never the stage.
        assert child_refs(env.n_x["outer"]) == ["inner"]

    # --- TEETH ---------------------------------------------------------------

    def test_c2_teeth_two_cycle_detected(self):
        """A 2-cycle instance EXISTS and is flagged (not silently accepted)."""
        env = Env(
            composites=(
                _ref_composite("a", ["b"]),
                _ref_composite("b", ["a"]),
            )
        )
        assert has_cycle(env)

    def test_c2_teeth_self_cycle_detected(self):
        env = Env(composites=(_ref_composite("a", ["a"]),))
        assert has_cycle(env)

    def test_c2_teeth_three_cycle_detected(self):
        env = Env(
            composites=(
                _ref_composite("a", ["b"]),
                _ref_composite("b", ["c"]),
                _ref_composite("c", ["a"]),
            )
        )
        assert has_cycle(env)

    def test_c2_teeth_dangling_composite_ref_detected(self):
        """§3.2 item 3: a composite(x) resolving to no N_X member is caught by
        ``missing_composite_refs`` (and does not crash cycle detection)."""
        env = Env(composites=(_ref_composite("a", ["ghost"]),))
        assert ("a", "ghost") in missing_composite_refs(env)
        assert not has_cycle(env)  # dangling != cyclic


# ===========================================================================
# C3 — Coverage-fold soundness (PER-MEMBER). §3.6.
# ===========================================================================

# A small set of composites we nest to depth 2–3 for the fold cross-check.
def _depth2_env():
    """root(loop) -> ensemble(judge_max w/ composite judge + accept) ->
    cascade(post, margin gate). Exercises judge arms + nested levels."""
    inner_cascade = Composite(
        "leaf_casc",
        CompositeKind.CASCADE,
        cascade=Cascade(
            arms=(stage_arm("a", ["t1"]), stage_arm("b", ["t2"])),
            gates=(GateDecl(GateKind.MARGIN_BELOW, "theta_casc"),),
            placement=Placement.POST,
        ),
    )
    judge = composite_arm("leaf_casc")
    mid_ensemble = Composite(
        "mid_ens",
        CompositeKind.ENSEMBLE,
        ensemble=Ensemble(
            arms=(stage_arm("e", ["t3"]),),
            cardinality="k_cal",  # calibrated cardinality -> in Cal
            aggregate=AggregateDecl(
                AggregateKind.JUDGE_MAX,
                judge=judge,
                accept=AcceptDecl(AcceptStat.VOTE_MARGIN, "theta_acc"),
            ),
        ),
    )
    root_loop = Composite(
        "root_loop",
        CompositeKind.LOOP,
        loop=Loop(
            body=composite_arm("mid_ens"),
            stop=StopDecl(
                StopKind.SIGNAL_ACCEPT,
                threshold="theta_stop",
                signal=SignalUse("sig"),
            ),
            max_iters=2,
            state_keys=(),
        ),
    )
    return Env(
        n_t=frozenset({"t1", "t2", "t3"}),
        n_c=frozenset({"theta_casc", "theta_acc", "theta_stop", "k_cal"}),
        composites=(inner_cascade, mid_ensemble, root_loop),
    )


def _enumerate_small_composite_envs():
    """Enumerate depth 2–3 composite shapes by toggling structural choices:
    judge present/absent, accept present/absent, calibrated-vs-tuned k. Each
    env is single-root so the fold has a clean target."""
    for has_judge in (False, True):
        for has_accept in (False, True):
            for k_calibrated in (False, True):
                leaf = Composite(
                    "leaf",
                    CompositeKind.CASCADE,
                    cascade=Cascade(
                        arms=(stage_arm("a", ["t1"]), stage_arm("b", ["t2"])),
                        gates=(GateDecl(GateKind.MARGIN_BELOW, "theta_leaf"),),
                    ),
                )
                agg = AggregateDecl(
                    AggregateKind.JUDGE_MAX if has_judge else AggregateKind.MAJORITY_VOTE,
                    judge=composite_arm("leaf") if has_judge else None,
                    accept=AcceptDecl(AcceptStat.VOTE_MARGIN, "theta_acc")
                    if has_accept
                    else None,
                )
                k_name = "k_cal" if k_calibrated else "k_tuned"
                root = Composite(
                    "root",
                    CompositeKind.ENSEMBLE,
                    ensemble=Ensemble(
                        arms=(stage_arm("e", ["t3"]),),
                        cardinality=k_name,
                        aggregate=agg,
                    ),
                )
                env = Env(
                    n_t=frozenset({"t1", "t2", "t3", "k_tuned"}),
                    n_c=frozenset({"theta_leaf", "theta_acc", "k_cal"}),
                    composites=(leaf, root),
                )
                yield env


class TestC3CoverageFold:
    def test_fold_equals_ground_truth_member_walk(self):
        """C3: ``cal_composite`` over each root equals an INDEPENDENT member
        walk that collects every gate/accept/stop threshold + calibrated
        cardinality through nesting incl. judge arms. Exhaustive over the
        small structural universe + the hand-built depth-2 env."""
        envs = list(_enumerate_small_composite_envs()) + [_depth2_env()]
        checked = 0
        for env in envs:
            for r in roots(env):
                fold = cal_composite(env, r)
                walk = member_walk_cal(env, r)
                assert fold == walk, (r.name, fold, walk)
                checked += 1
        assert checked >= len(list(_enumerate_small_composite_envs()))

    def test_cal_roots_collects_all_calibratable_members_depth2(self):
        """The depth-2 env's root fold collects EXACTLY the expected members:
        nested cascade gate, ensemble accept, calibrated k, loop stop."""
        env = _depth2_env()
        assert cal_roots(env) == frozenset(
            {"theta_casc", "theta_acc", "k_cal", "theta_stop"}
        )

    def test_strict_selection_passes_iff_every_member_certified(self):
        """§3.6 fail-closed: strict selection passes iff ALL Cal members are
        certified-fresh. Exhaustive over every subset of the coverage set."""
        env = _depth2_env()
        coverage = cal_roots(env)
        members = sorted(coverage)
        checked = 0
        for r in range(len(members) + 1):
            for subset in itertools.combinations(members, r):
                certified = frozenset(subset)
                expected = coverage <= certified
                assert calibration_pass(certified, coverage) == expected
                checked += 1
        assert checked == 2 ** len(members)

    # --- TEETH ---------------------------------------------------------------

    def test_c3_teeth_uncertified_gate_yields_coverage_gap(self):
        """An instance with one uncertified gate: strict selection REFUSES
        (the fold is fail-closed — never a partial pass)."""
        env = _depth2_env()
        coverage = cal_roots(env)
        # certify everyone EXCEPT one gate -> must refuse.
        certified = coverage - {"theta_casc"}
        assert not calibration_pass(certified, coverage)
        # and certifying all -> passes (sanity, so the teeth aren't vacuous).
        assert calibration_pass(coverage, coverage)

    def test_c3_teeth_broken_fold_dropping_judge_is_caught(self):
        """A deliberately-broken fold variant that drops judge arms is CAUGHT
        by the ground-truth member walk: it under-collects on a judge-bearing
        nested composite."""
        env = _depth2_env()
        root = env.n_x["root_loop"]
        good = cal_composite(env, root)
        broken = cal_composite_drop_judge(env, root)
        walk = member_walk_cal(env, root)
        assert good == walk
        assert broken != walk  # the bug is detectable
        assert "theta_casc" in (walk - broken)  # the judge's gate is what was lost


# ===========================================================================
# C4 — Cost compositionality (FORM closure only). §3.4.
# ===========================================================================


def _all_five_form_env():
    """One env exhibiting all five §3.4 cost forms as roots/arms."""
    post = Composite(
        "post",
        CompositeKind.CASCADE,
        cascade=Cascade((stage_arm("a"), stage_arm("b")), (GateDecl(GateKind.MARGIN_BELOW, "th"),)),
    )
    pre = Composite(
        "pre",
        CompositeKind.CASCADE,
        cascade=Cascade(
            (stage_arm("a"), stage_arm("b")),
            (GateDecl(GateKind.SIGNAL_BELOW, "th", SignalUse("sig")),),
            placement=Placement.PRE,
        ),
    )
    sampling = Composite(
        "sampling",
        CompositeKind.ENSEMBLE,
        ensemble=Ensemble((stage_arm("a"),), cardinality="k"),
    )
    committee = Composite(
        "committee",
        CompositeKind.ENSEMBLE,
        ensemble=Ensemble((stage_arm("a"), stage_arm("b"))),
    )
    loopc = Composite(
        "loopc",
        CompositeKind.LOOP,
        loop=Loop(stage_arm("a"), StopDecl(StopKind.EXHAUSTED), 2),
    )
    return Env(
        n_t=frozenset({"k"}),
        n_c=frozenset({"th"}),
        composites=(post, pre, sampling, committee, loopc),
    )


class TestC4CostClosure:
    def test_all_five_forms_reachable_and_closed(self):
        """C4: each of the five §3.4 cost forms appears, and every composite's
        cost term is CLOSED — substituting an arm's form yields the parent's,
        with no unexpanded composite reference. (Structural FORM closure.)"""
        env = _all_five_form_env()
        forms_seen = set()
        for c in env.composites:
            term = cost_of_composite(env, c)
            assert cost_is_closed(term), c.name
            forms_seen.add(term.form)
        assert forms_seen == {
            CostForm.CASCADE_POST,
            CostForm.CASCADE_PRE,
            CostForm.ENSEMBLE_SAMPLING,
            CostForm.ENSEMBLE_COMMITTEE,
            CostForm.LOOP,
        }

    def test_nested_arm_cost_is_arms_own_form(self):
        """§3.4 compositionality: a composite arm's cost term IS the referenced
        composite's cost form (the equations close over the algebra)."""
        env = Env(
            n_t=frozenset(),
            n_c=frozenset({"th"}),
            composites=(
                Composite(
                    "inner",
                    CompositeKind.CASCADE,
                    cascade=Cascade((stage_arm("a"), stage_arm("b")), (GateDecl(GateKind.MARGIN_BELOW, "th"),)),
                ),
                Composite(
                    "outer",
                    CompositeKind.LOOP,
                    loop=Loop(composite_arm("inner"), StopDecl(StopKind.EXHAUSTED), 1),
                ),
            ),
        )
        outer_term = cost_of_composite(env, env.n_x["outer"])
        assert outer_term.form == CostForm.LOOP
        # the loop body's cost form is the inner cascade's own form.
        assert outer_term.kids[0].form == CostForm.CASCADE_POST
        assert cost_is_closed(outer_term)

    def test_nesting_to_depth_three_stays_closed(self):
        """Exhaustive small trees: nest loop->ensemble->cascade and confirm the
        whole cost term is closed (no leaked composite reference)."""
        env = _depth2_env()
        for c in env.composites:
            assert cost_is_closed(cost_of_composite(env, c)), c.name

    # --- TEETH ---------------------------------------------------------------

    def test_c4_teeth_unexpanded_composite_ref_is_not_closed(self):
        """A cost term carrying an UNEXPANDED composite reference (a dangling
        arm whose form was never substituted) is NOT closed — the closure
        property has teeth."""
        env = Env(composites=())  # 'ghost' unresolved
        term = cost_of_arm(env, composite_arm("ghost"))
        assert term.composite_ref == "ghost"
        assert not cost_is_closed(term)
        # ... and a closed term passes (non-vacuous).
        assert cost_is_closed(cost_of_arm(env, stage_arm("s")))


# ===========================================================================
# C5 — Loop → K-chain semantic compilation (signal_accept only). §3.8.
# ===========================================================================

# A small finite space of per-iteration outcomes for K ≤ 4.
STEP_BODIES = [output("o"), NO_ACCEPT, ERROR]
STEP_STOPS = [False, True]


def _signal_accept_loop(k: int) -> Loop:
    return Loop(
        body=stage_arm("a"),
        stop=StopDecl(StopKind.SIGNAL_ACCEPT, threshold="th", signal=SignalUse("s")),
        max_iters=k,
        state_keys=(),
    )


def _enumerate_step_traces(k: int):
    """All length-k iteration traces over (body_result × stop_accepts),
    with no ambient mutation (condition 1 holds)."""
    cell = [
        IterStep(body, stop)
        for body in STEP_BODIES
        for stop in STEP_STOPS
    ]
    for combo in itertools.product(cell, repeat=k):
        yield list(combo)


class TestC5LoopKChain:
    def test_signal_accept_loop_and_kchain_outputs_coincide(self):
        """C5: for signal_accept loops with K ≤ 4, pure/threaded bodies,
        deterministic stop, the Loop execution and the unrolled K-chain
        selection coincide on BOTH the final result kind/output AND the
        selected iteration index. Exhaustive over all step traces for K=1..4."""
        total = 0
        for k in (1, 2, 3, 4):
            loop = _signal_accept_loop(k)
            assert signal_accept_unrollable(loop)
            for steps in _enumerate_step_traces(k):
                loop_res, loop_sel = loop_execute(loop, steps)
                chain_res, chain_sel = kchain_execute(loop, steps)
                assert loop_res.kind == chain_res.kind, steps
                if loop_res.kind == ArmResultKind.OUTPUT:
                    assert loop_res.out == chain_res.out, steps
                assert loop_sel == chain_sel, steps
                total += 1
        # 6 cells per iteration; Σ_{k=1..4} 6^k traces.
        assert total == sum(6 ** k for k in (1, 2, 3, 4))

    def test_non_signal_accept_loops_offer_no_unroll(self):
        """§3.8: external_accept and exhausted loops are NOT unrollable."""
        for stop in (
            StopDecl(StopKind.EXTERNAL_ACCEPT, predicate="p"),
            StopDecl(StopKind.EXHAUSTED),
        ):
            loop = Loop(stage_arm("a"), stop, max_iters=2)
            assert not signal_accept_unrollable(loop)

    def test_k_above_four_not_unrollable_in_this_scope(self):
        loop = _signal_accept_loop(5)
        assert not signal_accept_unrollable(loop)

    # --- TEETH ---------------------------------------------------------------

    def test_c5_teeth_hidden_state_mutation_diverges_and_is_detectable(self):
        """Violate §3.8 condition 1 (hidden ambient state mutation): construct
        a trace where the loop's reference semantics and a mutation-corrupted
        K-chain DISAGREE, and show the divergence IS detectable.

        We model the corruption concretely: ambient mutation makes the chain's
        escalation decision read a STALE stop bit (the chain still sees the old
        ``stop_accepts`` while the loop, threading only declared state, sees the
        true one). With state flowing only through declared keys the two agree;
        once ambient flips a stop bit, they part."""
        loop = _signal_accept_loop(2)

        # Honest trace (condition 1 holds): both accept on iter 0.
        honest = [IterStep(output("o"), stop_accepts=True),
                  IterStep(output("p"), stop_accepts=True)]
        lr, ls = loop_execute(loop, honest)
        cr, cs = kchain_execute(loop, honest)
        assert (lr.kind, lr.out, ls) == (cr.kind, cr.out, cs)  # agree -> non-vacuous

        # Corrupted: the true loop semantics (declared state only) sees iter-0
        # stop = False (no acceptance yet); but an ambient mutation made the
        # chain's compiled escalation predicate read stop = True at iter 0.
        loop_view = [IterStep(output("o"), stop_accepts=False, ambient=True),
                     IterStep(output("p"), stop_accepts=True)]
        chain_view = [IterStep(output("o"), stop_accepts=True, ambient=True),
                      IterStep(output("p"), stop_accepts=True)]
        # Condition 1 is violated -> the two views differ.
        assert any(s.ambient for s in loop_view)
        lr2, ls2 = loop_execute(loop, loop_view)
        cr2, cs2 = kchain_execute(loop, chain_view)
        # Loop selects iter 1 ("p"); corrupted chain selects iter 0 ("o").
        assert (lr2.out, ls2) == ("p", 1)
        assert (cr2.out, cs2) == ("o", 0)
        assert (lr2.out, ls2) != (cr2.out, cs2)  # divergence IS detectable

    def test_c5_teeth_error_absorbing_in_both(self):
        """An error at any iteration fails BOTH the loop and the chain — the
        absorbing rule (§3.2.1) holds in both implementations (so a divergence
        here would be a real bug, not noise)."""
        loop = _signal_accept_loop(3)
        steps = [
            IterStep(NO_ACCEPT, stop_accepts=False),  # iter 0: no_accept
            IterStep(ERROR, stop_accepts=False),  # iter 1: error -> absorbing
            IterStep(output("late"), stop_accepts=True),  # never reached
        ]
        lr, _ = loop_execute(loop, steps)
        cr, _ = kchain_execute(loop, steps)
        assert lr.kind == ArmResultKind.ERROR
        assert cr.kind == ArmResultKind.ERROR


# ===========================================================================
# C6 — Dependency-compilation soundness (TVAR-ONLY obligations). §3.5.
# ===========================================================================


def _enumerate_c6_envs():
    """Composite shapes whose required_parents we check land in N_T only:
    post-cascade, pre-cascade, ensemble-accept (judge present/absent), loop
    signal_accept — with tuned/calibrated cardinality toggled."""
    n_t = frozenset({"t1", "t2", "t3", "k_tuned"})
    n_c = frozenset({"theta", "theta_acc", "theta_stop", "k_cal"})
    envs = []

    post = Composite(
        "post",
        CompositeKind.CASCADE,
        cascade=Cascade(
            (stage_arm("a", ["t1"]), stage_arm("b", ["t2"]), stage_arm("c", ["t3"])),
            (GateDecl(GateKind.MARGIN_BELOW, "theta"), GateDecl(GateKind.MARGIN_BELOW, "theta_acc")),
        ),
    )
    envs.append(Env(n_t, n_c, (post,)))

    pre = Composite(
        "pre",
        CompositeKind.CASCADE,
        cascade=Cascade(
            (stage_arm("a", ["t1"]), stage_arm("b", ["t2"])),
            (GateDecl(GateKind.SIGNAL_BELOW, "theta", SignalUse("s")),),
            placement=Placement.PRE,
        ),
    )
    envs.append(Env(n_t, n_c, (pre,)))

    for has_judge in (False, True):
        for k_tuned in (False, True):
            ens = Composite(
                "ens",
                CompositeKind.ENSEMBLE,
                ensemble=Ensemble(
                    (stage_arm("e", ["t1"]),),
                    cardinality="k_tuned" if k_tuned else "k_cal",
                    aggregate=AggregateDecl(
                        AggregateKind.JUDGE_MAX if has_judge else AggregateKind.MAJORITY_VOTE,
                        judge=stage_arm("j", ["t3"]) if has_judge else None,
                        accept=AcceptDecl(AcceptStat.VOTE_MARGIN, "theta_acc"),
                    ),
                ),
            )
            envs.append(Env(n_t, n_c, (ens,)))

    loop = Composite(
        "loop",
        CompositeKind.LOOP,
        loop=Loop(
            stage_arm("b", ["t1", "t2"]),
            StopDecl(StopKind.SIGNAL_ACCEPT, threshold="theta_stop", signal=SignalUse("s")),
            max_iters=2,
        ),
    )
    envs.append(Env(n_t, n_c, (loop,)))
    return envs


class TestC6RequiredParents:
    def test_required_parents_land_in_NT_only(self):
        """C6: for every enumerated instance (incl. tuned cardinality + judge
        arms), every threshold's required_parents ⊆ N_T. No CVAR ever appears
        as a parent."""
        checked = 0
        for env in _enumerate_c6_envs():
            for r in roots(env):
                for theta, parents in required_parents(env, r).items():
                    assert parents <= env.n_t, (r.name, theta, parents)
                    assert not (parents & env.n_c), (theta, parents)
                    checked += 1
        assert checked > 0

    def test_tuned_cardinality_in_leafT(self):
        """§3.5: a sampling ensemble whose tuned cardinality is a TVAR includes
        that TVAR in its leaf set (and in the accept threshold's parents)."""
        env = Env(
            n_t=frozenset({"t1", "k_tuned"}),
            n_c=frozenset({"theta_acc"}),
            composites=(
                Composite(
                    "ens",
                    CompositeKind.ENSEMBLE,
                    ensemble=Ensemble(
                        (stage_arm("e", ["t1"]),),
                        cardinality="k_tuned",
                        aggregate=AggregateDecl(
                            AggregateKind.MAJORITY_VOTE,
                            accept=AcceptDecl(AcceptStat.VOTE_MARGIN, "theta_acc"),
                        ),
                    ),
                ),
            ),
        )
        leaf = leaf_t_composite(env, env.n_x["ens"])
        assert "k_tuned" in leaf and "t1" in leaf
        parents = required_parents(env, env.n_x["ens"])["theta_acc"]
        assert "k_tuned" in parents

    def test_calibrated_cardinality_not_in_leafT(self):
        """§3.5: a CALIBRATED cardinality contributes nothing to leafT (it is a
        member of Cal instead). Keeps the codomain TVAR-only."""
        env = Env(
            n_t=frozenset({"t1"}),
            n_c=frozenset({"k_cal", "theta_acc"}),
            composites=(
                Composite(
                    "ens",
                    CompositeKind.ENSEMBLE,
                    ensemble=Ensemble(
                        (stage_arm("e", ["t1"]),),
                        cardinality="k_cal",
                        aggregate=AggregateDecl(
                            AggregateKind.MAJORITY_VOTE,
                            accept=AcceptDecl(AcceptStat.VOTE_MARGIN, "theta_acc"),
                        ),
                    ),
                ),
            ),
        )
        leaf = leaf_t_composite(env, env.n_x["ens"])
        assert "k_cal" not in leaf

    def test_missing_composite_parent_lint_exact_gap(self):
        """§3.5: ``missing_composite_parent`` fires exactly when
        required_parents(θ) ⊄ depends_on(θ). Exhaustive over depends_on
        subsets for a post-cascade with a known required set."""
        env = Env(
            n_t=frozenset({"t1", "t2"}),
            n_c=frozenset({"theta"}),
            composites=(
                Composite(
                    "post",
                    CompositeKind.CASCADE,
                    cascade=Cascade(
                        (stage_arm("a", ["t1"]), stage_arm("b", ["t2"])),
                        (GateDecl(GateKind.MARGIN_BELOW, "theta"),),
                    ),
                ),
            ),
        )
        required = required_parents(env, env.n_x["post"])["theta"]
        tvars = sorted(env.n_t)
        checked = 0
        for r in range(len(tvars) + 1):
            for subset in itertools.combinations(tvars, r):
                depends_on = {"theta": frozenset(subset)}
                gaps = missing_composite_parent(env, depends_on)
                expected_gap = bool(required - frozenset(subset))
                assert bool(gaps) == expected_gap, subset
                checked += 1
        assert checked == 2 ** len(tvars)

    # --- TEETH ---------------------------------------------------------------

    def test_c6_teeth_broken_variant_emitting_cvar_parent_is_caught(self):
        """A deliberately-broken required_parents variant that emits a CVAR
        parent (e.g. a calibrated cardinality leaking in) is CAUGHT by the
        TVAR-only codomain check."""
        env = Env(
            n_t=frozenset({"t1"}),
            n_c=frozenset({"k_cal", "theta_acc"}),
            composites=(
                Composite(
                    "ens",
                    CompositeKind.ENSEMBLE,
                    ensemble=Ensemble(
                        (stage_arm("e", ["t1"]),),
                        cardinality="k_cal",
                        aggregate=AggregateDecl(
                            AggregateKind.MAJORITY_VOTE,
                            accept=AcceptDecl(AcceptStat.VOTE_MARGIN, "theta_acc"),
                        ),
                    ),
                ),
            ),
        )

        # Broken variant: include the cardinality WITHOUT the §3.5 N_T filter.
        def broken_required(env, c):
            parents = set()
            for a in c.ensemble.arms:
                parents |= set(a.tuned_params)
            if c.ensemble.cardinality is not None:
                parents.add(c.ensemble.cardinality)  # BUG: no ∩ N_T
            return frozenset(parents)

        good = required_parents(env, env.n_x["ens"])["theta_acc"]
        bad = broken_required(env, env.n_x["ens"])
        assert good <= env.n_t  # the real fn stays TVAR-only
        assert not (bad <= env.n_t)  # the broken variant leaks a CVAR
        assert "k_cal" in (bad & env.n_c)  # exactly the leaked CVAR

    def test_c6_teeth_missing_parent_gap_detected(self):
        """A post-cascade gate whose depends_on omits an arm's TVAR yields a
        ``missing_composite_parent`` gap (the obligation has teeth)."""
        env = Env(
            n_t=frozenset({"t1", "t2"}),
            n_c=frozenset({"theta"}),
            composites=(
                Composite(
                    "post",
                    CompositeKind.CASCADE,
                    cascade=Cascade(
                        (stage_arm("a", ["t1"]), stage_arm("b", ["t2"])),
                        (GateDecl(GateKind.MARGIN_BELOW, "theta"),),
                    ),
                ),
            ),
        )
        gaps = missing_composite_parent(env, {"theta": frozenset({"t1"})})
        assert ("theta", frozenset({"t2"})) in gaps


# ===========================================================================
# Cross-claim: gate typing (§3.2 item 5) — supports C1/C3/C6 well-formedness.
# Kept here as a paired UNSAT/teeth block since the C-tests rely on it.
# ===========================================================================


class TestGateTypingSupport:
    def test_well_typed_gates_have_no_diagnostics(self):
        env = Env(
            n_c=frozenset({"th"}),
            composites=(
                Composite(
                    "ok_post",
                    CompositeKind.CASCADE,
                    cascade=Cascade(
                        (stage_arm("a"), stage_arm("b")),
                        (GateDecl(GateKind.MARGIN_BELOW, "th"),),
                    ),
                ),
            ),
        )
        assert gate_typing_diagnostics(env, env.n_x["ok_post"]) == []

    def test_margin_bearing_classification(self):
        env = Env(
            composites=(
                Composite("mv", CompositeKind.ENSEMBLE, ensemble=Ensemble((stage_arm("a"), stage_arm("b")), AggregateDecl(AggregateKind.MAJORITY_VOTE))),
                Composite("jm", CompositeKind.ENSEMBLE, ensemble=Ensemble((stage_arm("a"),), AggregateDecl(AggregateKind.JUDGE_MAX, judge=stage_arm("j")), cardinality="k")),
            )
        )
        assert arm_is_margin_bearing(env, stage_arm("s"))
        assert arm_is_margin_bearing(env, composite_arm("mv"))
        assert not arm_is_margin_bearing(env, composite_arm("jm"))

    def test_gate_typing_teeth_margin_on_judge_max_rejected(self):
        """§3.2 item 5: margin_below gating a judge_max ensemble arm rejects."""
        env = Env(
            n_c=frozenset({"th"}),
            composites=(
                Composite("jm", CompositeKind.ENSEMBLE, ensemble=Ensemble((stage_arm("a"),), AggregateDecl(AggregateKind.JUDGE_MAX, judge=stage_arm("j")), cardinality="k")),
                Composite(
                    "bad",
                    CompositeKind.CASCADE,
                    cascade=Cascade(
                        (stage_arm("a"), composite_arm("jm")),
                        (GateDecl(GateKind.MARGIN_BELOW, "th"),),
                    ),
                ),
            ),
        )
        codes = {c for c, _ in gate_typing_diagnostics(env, env.n_x["bad"])}
        assert "gate_arm_incompatible" in codes

    def test_gate_typing_teeth_placement_mismatch_rejected(self):
        """§3.2 item 5: signal_below in a POST cascade rejects (both-direction
        ``gate_kind_placement_mismatch``)."""
        env = Env(
            n_c=frozenset({"th"}),
            composites=(
                Composite(
                    "bad",
                    CompositeKind.CASCADE,
                    cascade=Cascade(
                        (stage_arm("a"), stage_arm("b")),
                        (GateDecl(GateKind.SIGNAL_BELOW, "th", SignalUse("s")),),
                        placement=Placement.POST,
                    ),
                ),
            ),
        )
        codes = {c for c, _ in gate_typing_diagnostics(env, env.n_x["bad"])}
        assert "gate_kind_placement_mismatch" in codes

    def test_gate_typing_teeth_signal_below_missing_signal_rejected(self):
        env = Env(
            n_c=frozenset({"th"}),
            composites=(
                Composite(
                    "bad",
                    CompositeKind.CASCADE,
                    cascade=Cascade(
                        (stage_arm("a"), stage_arm("b")),
                        (GateDecl(GateKind.SIGNAL_BELOW, "th"),),
                        placement=Placement.PRE,
                    ),
                ),
            ),
        )
        codes = {c for c, _ in gate_typing_diagnostics(env, env.n_x["bad"])}
        assert "missing_gate_signal" in codes
