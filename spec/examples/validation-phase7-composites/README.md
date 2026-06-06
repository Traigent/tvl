# Phase 7 Validation Examples — RFC 0002 (composite knobs)

Conformance fixtures for the **composite-knob algebra** (TVL 1.2). They are the
**executable acceptance bar for the validators packet (P4)**: the grammar /
schema / lint changes are done when every fixture below produces exactly its
expected diagnostic through `tvl-validate` and the conformance suite
(`tests/test_composites.py`). One happy + one rejecting fixture per §3.11 error
code, plus the degenerate-acceptance and §4 subsumption fixtures from RFC §9
criterion 3.

> **Status: EXECUTABLE.** The 1.2 composite surface landed in `tvl.schema.json`
> / `tvl.ebnf` / `lints.py` (`_lint_composites`); every fixture below produces
> exactly its expected ERROR code (and nothing else) through the real schema +
> lint pipeline. The §3.11 diagnostics are NORMATIVE LINTS, not `schema_error`:
> the schema checks shape only (the Composite envelope and the arm/signal
> surfaces are deliberately open), so the closed-shape / registry / binding
> diagnostics are the lints' own — the same shape-vs-registry layering RFC 0001
> uses for `policy.strategy`, taken one step further.

## Positive fixtures

| Example | Expected |
| --- | --- |
| `composite-knobs-happy.tvl.yml` | VALID — governed post-cascade + sampling ensemble (tuned `k`) + signal_accept loop; signal binding + `signal_inputs` coverage + parent coverage all satisfied |
| `composite-knobs-happy-pre-cascade.tvl.yml` | VALID — pre-cascade (dispatch) with a `signal_below` gate |
| `composite-knobs-happy-m1-cascade.tvl.yml` | VALID — degenerate `m=1` cascade (no gates) |
| `composite-knobs-happy-sampling-k1-ensemble.tvl.yml` | VALID — sampling-form `\|arms\|=1` ensemble with tuned cardinality |
| `composite-knobs-happy-committee-majority.tvl.yml` | VALID — committee-form `\|arms\|>1` ensemble (no cardinality) |
| `composite-knobs-happy-loop-max-iters-one.tvl.yml` | VALID — loop at `max_iters=1` |
| `composite-knobs-happy-tagged-nesting-under-judge.tvl.yml` | VALID — tagged `{composite: ...}` nesting in a `judge_max` judge |
| `composite-cascade-subsumes-policy.tvl.yml` | VALID — the composite form of the legacy cascade, with both ratchets satisfied |
| `legacy-policy-cascade-unchanged.tvl.yml` | VALID — a legacy `policies:` cascade is unchanged (the two composite-only ratchets do NOT fire) |
| `legacy-cvar-missing-signal-remains-valid.tvl.yml` | VALID — a CVAR with no `calibration.signal` is well-formed in isolation |
| `invalid_cardinality_value-zero-resolved-k.tvl.yml` | VALID statically — `invalid_cardinality_value` (R9) is a RESOLUTION-TIME rejection (see boundary note) |

## Rejecting fixtures — one per §3.11 code

| Example | Expected ERROR |
| --- | --- |
| `unknown_composite_kind-fourth-kind.tvl.yml` | `unknown_composite_kind` (§3.2 item 1) |
| `unknown_composite_field-cross-kind-field.tvl.yml` | `unknown_composite_field` (§3.2 item 1) |
| `cascade_arity-no-gate-for-two-arms.tvl.yml` | `cascade_arity` — reused RFC 0001 (§3.2 item 2) |
| `unknown_gate_kind-unregistered-gate.tvl.yml` | `unknown_gate_kind` — reused RFC 0001 (GateDecl) |
| `composite_binds_value-value-field.tvl.yml` | `composite_binds_value` (§3.1) |
| `composite_shadows_name-tvar-collision.tvl.yml` | `composite_shadows_name` (§3.1) |
| `duplicate_composite-same-name.tvl.yml` | `duplicate_composite` (§3.1) |
| `empty_arms-cascade-no-arms.tvl.yml` | `empty_arms` (§3.2 item 2) |
| `ambiguous_arm-bare-collides-composite.tvl.yml` | `ambiguous_arm` (§3.2 item 3) |
| `missing_composite_ref-tagged-nesting-ghost.tvl.yml` | `missing_composite_ref` (§3.2 item 3) |
| `composite_cycle-two-node-cycle.tvl.yml` | `composite_cycle` (§3.2 item 4) |
| `gate_arm_incompatible-margin-on-judge-max.tvl.yml` | `gate_arm_incompatible` (§3.2 item 5) |
| `gate_kind_placement_mismatch-signal-below-post.tvl.yml` | `gate_kind_placement_mismatch` (§3.2 item 5) |
| `missing_gate_signal-signal-below-no-signal.tvl.yml` | `missing_gate_signal` (§3.2 item 5) |
| `duplicate_stage-stage-repeat.tvl.yml` | `duplicate_stage` — extended scope (§3.2 item 6) |
| `cardinality_arity_mismatch-committee-has-cardinality.tvl.yml` | `cardinality_arity_mismatch` (§3.2 item 7) |
| `invalid_cardinality_type-float-cardinality.tvl.yml` | `invalid_cardinality_type` (§3.2 item 7) |
| `missing_judge-judge-max-without-judge.tvl.yml` | `missing_judge` (AggregateDecl) |
| `unknown_aggregate_kind-weighted-vote.tvl.yml` | `unknown_aggregate_kind` (AggregateDecl) |
| `unknown_stop_kind-unregistered.tvl.yml` | `unknown_stop_kind` (StopDecl) |
| `missing_stop_threshold-signal-accept-no-threshold.tvl.yml` | `missing_stop_threshold` (StopDecl) |
| `missing_stop_signal-signal-accept-no-signal.tvl.yml` | `missing_stop_signal` (StopDecl) |
| `missing_stop_predicate-external-accept-no-predicate.tvl.yml` | `missing_stop_predicate` (StopDecl) |
| `stop_signal_outside_state-undeclared-key.tvl.yml` | `stop_signal_outside_state` (§3.2 item 8) |
| `invalid_max_iters-zero.tvl.yml` | `invalid_max_iters` (§3.2 item 8) |
| `invalid_tuned_param-cvar-parent.tvl.yml` | `invalid_tuned_param` (§3.2 item 9) |
| `invalid_threshold_type-enum-cvar.tvl.yml` | `invalid_threshold_type` (§3.2 item 10) |
| `missing_calibration_signal-no-signal.tvl.yml` | `missing_calibration_signal` (§3.2 item 11) |
| `signal_mismatch-wrong-signal.tvl.yml` | `signal_mismatch` (§3.2 item 11) |
| `unbound_signal_inputs-not-covered.tvl.yml` | `unbound_signal_inputs` (§3.2 item 11) |
| `missing_composite_parent-post-gate-omits-arm-tvar.tvl.yml` | `missing_composite_parent` (§3.5) |
| `invalid_arm_shape-unknown-arm-key.tvl.yml` | `invalid_arm_shape` (§3.9) |
| `invalid_signal_use-nonlist-inputs.tvl.yml` | `invalid_signal_use` (§3.2 / §3.9) |
| `missing_ref-threshold-unknown-cvar.tvl.yml` | `missing_ref` — reused (gate threshold → no CVAR) |
| `missing_ref-threshold-tvar-kind-mismatch.tvl.yml` | `missing_ref` — reused (gate threshold → TVAR, kind mismatch) |

## R9 boundary — `invalid_cardinality_value`

`invalid_cardinality_value` (R9, §3.2 item 7) is a **resolution-time** rejection:
it fires when an ensemble cardinality reference resolves to `k < 1`, which is not
knowable from the static module (the module declares only the namespace
reference). The static lints own the two static cardinality checks
(`cardinality_arity_mismatch`, `invalid_cardinality_type`); R9 itself is
surfaced **exactly as R1–R8 are** — by the resolver / small-scope model-checking
suite (`tests/model_checking/`, `R9_INVALID_CARDINALITY_VALUE`), which extends
RFC 0001's acceptance algebra to
`Accept₁.₂ ⟺ ¬(R1 ∨ … ∨ R8 ∨ R9) ∧ calibrators ≠ ⊥`. The static fixture
`invalid_cardinality_value-zero-resolved-k.tvl.yml` is the statically-well-formed
companion documenting this boundary (it has NO static error).

This mirrors the phase-6 convention: dynamic resolver rejections are not
expressible as static module fixtures and are verified by the model suite.
