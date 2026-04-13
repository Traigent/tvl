# TVL + OPAL Lean Proofs

This directory contains Lean 4 mechanizations for both:

- TVL core theorems (typing, SMT encoding soundness, dominance composition)
- OPAL declarative-core theorems (snapshot semantics, callable/interface soundness, `given`, template typing/completeness)

## Layout

```text
tvl/proofs/
├── lakefile.lean
├── lean-toolchain
├── Main.lean
├── PROOF_SUMMARY.md
├── OPALCORE_README.md
└── TVL/
    ├── Basic.lean
    ├── Types.lean
    ├── TypeSoundness.lean
    ├── SMTEncoding.lean
    ├── Dominance.lean
    └── OPALCore.lean
```

## Primary References

- TVL theorem summary and proof notes: [`PROOF_SUMMARY.md`](PROOF_SUMMARY.md)
- OPAL mechanization scope and theorem index: [`OPALCORE_README.md`](OPALCORE_README.md)

## Build

Requires Lean `4.28.0-rc1` (pinned in `lean-toolchain`) and Mathlib from Lake manifest.

```bash
cd tvl/proofs
lake exe cache get
lake build
```

Focused module builds:

```bash
cd tvl/proofs
lake build TVL.OPALCore
lake build TVL.SMTEncoding
```

## Current Status

- `TVL.TypeSoundness`: mechanized
- `TVL.SMTEncoding`: mechanized with documented edge-case assumptions
- `TVL.Dominance`: mechanized
- `TVL.OPALCore`: mechanized declarative core with nested template argument soundness/completeness

CI enforcement:

- `.github/workflows/proofs-ci.yml` enforces a strict zero-`sorry` policy for Lean sources.
