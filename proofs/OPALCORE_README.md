# OPALCore Lean Mechanization

This document is the authoritative entry point for the OPAL declarative-core mechanization in Lean.

- Source file: `tvl/proofs/TVL/OPALCore.lean`
- Namespace: `TVL.OPALCore`
- Scope: declarative OPAL core (assign/in/when/given/callable templates), not host-language `def` body interpretation

## Scope Boundaries

- Mechanized:
  - snapshot/store state model
  - assignment vs. domain binding semantics
  - `when` lowering equivalence
  - typed callable-domain interface checks
  - `given`-policy snapshot-preservation envelope
  - template argument typing (including nested/compositional templates)
  - argument completeness checks against required parameters
  - progress-style results via `Except EvalError`
- Intentionally abstracted:
  - optimizer learning internals
  - host runtime effects inside opaque function bodies
  - full TVL promotion statistics in Lean

## Theorem Index (OPALCore)

### Declarative Core
- `evalDecl_deterministic`
- `evalDecl_preserves_snapshot`
- `evalDecls_preserves_snapshot`
- `when_lowering_faithful`

### Typed Callable Domains + `given`
- `resolve_callable_interface_sound`
- `evalDecl_preservation_except`
- `evalDecl_given_preserves_snapshot`
- `evalDeclsE_preserves_snapshot`
- `core_progress_except`

### Template-Aware Callable Resolution
- `resolve_template_interface_sound`
- `resolve_template_arguments_sound`
- `core_progress_except_template`

### Nested/Compositional Templates + Completeness
- `resolve_template_choice_sound_nested`
- `resolve_template_interface_sound_nested`
- `resolve_template_arguments_sound_nested`
- `resolve_template_arguments_complete`
- `evalDeclE_template_preservation_except_nested`
- `core_progress_except_template_nested`

## Trusted Assumptions and Design Choices

- Host execution is outside the mechanized core; OPAL/host boundary assumptions remain explicit in manuscript Appendix A.
- Nested template typing uses finite fuel (`templateFuelN`, `templateArgFuelN`) to model finite source trees while keeping proofs tractable.
- Registry well-formedness is captured by `wellFormedRegistryN` and used in completeness lemmas.

## Build and Check

```bash
cd tvl/proofs
lake build
```

For focused iteration:

```bash
cd tvl/proofs
lake build TVL.OPALCore
```

