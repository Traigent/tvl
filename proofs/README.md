# TVL + OPAL Lean Proofs

This public library contains TVL core proofs (typing, the encoding for
satisfiability modulo theories (SMT) solvers, and dominance),
OPAL declarative-core proofs, and Lean models for the runtime extensions: TVL 1.3
(RFC 0003), TVL 1.4 reactive guards (RFC 0004, `Guards.lean`) and TVL 1.5 persistence
(RFC 0005, `Persistence.lean`). All three versions are accepted; TVL 1.5 is the latest.
The Lean models cover only the statements listed in [PROOF_SUMMARY.md](PROOF_SUMMARY.md),
some of which remain OPEN.

The TVL 1.3 modules define complete-history predicate meaning, action/approval and
severity vocabulary, static composition, conservative extension, the promotion
join over supplied verdicts, backend-profile representation and generic binomial
mathematics. How an evaluator decides verdicts and executes responses is outside
TVL (RFC 0003 §3.5) and is not modelled here. Compilation is a
declaration/contract boundary; it does not install, register, enable or execute
monitors.

[PROOF_SUMMARY.md](PROOF_SUMMARY.md#runtime-tvl-13) preserves the
**SUBSTANTIVE**, **BY-CONSTRUCTION**, **WEAKER: what dropped**, and **OPEN** classes.
The static full-contract composition target and the narrower language compiler
normalization/projection target remain OPEN. Product erasure is by construction,
without syntax-level name-exclusion or source-to-SMT preservation. Backend codecs
are supplied equivalences. Building checks a mathematical model, without proving
Python compiler behavior, concrete serialization, population assumptions, deployed
adapters or floating-point/rational numerical equivalence.

## Layout

```text
proofs/
├── lakefile.lean
├── lake-manifest.json
├── lean-toolchain
├── Main.lean
├── PROOF_SUMMARY.md
├── OPALCORE_README.md
└── TVL/
    ├── Basic.lean, Types.lean, TypeSoundness.lean
    ├── SMTEncoding.lean, Dominance.lean, OPALCore.lean
    ├── Gate.lean
    └── Runtime/
        ├── History.lean          # complete-history predicates
        ├── Declarations.lean     # action, approval and severity vocabulary
        ├── Compose.lean          # static orders, numeric meet and OPEN full meet
        ├── Compiler.lean         # normalized declaration/projection OPEN target
        ├── Guards.lean           # TVL 1.4 three-valued notification guards
        ├── Persistence.lean      # TVL 1.5 breach persistence and exact mean comparison
        ├── Extension.lean        # erasure and abstract promotion refinement
        ├── Backend.lean          # representation round trip
        ├── BinomialGeneric.lean  # tails, domination and finite union bound
        └── BinomialLaw.lean      # generic PMF.binomial instantiations
```

`Main.lean` imports every public module. Generic probability results have no
import of count accounting or verdict definitions. Their names stay in the
`TVL.Runtime` namespace. The existing core files and the pinned dependencies
are unchanged.

## Build

Lean `v4.28.0-rc1` and Mathlib
`6a596ab93c06c66333edc70d52d8955648f6669c` are pinned by the existing files.
With dependencies and the Mathlib cache already present, build offline:

```bash
export PATH=$HOME/.elan/toolchains/leanprover--lean4---v4.28.0-rc1/bin:$PATH
cd proofs
timeout 3000 lake build
```

For a new environment with network access, install the pinned dependencies and
obtain their cache with `lake exe cache get` first. This step is unnecessary in
the prepared offline worktree. Do not change the pinned dependency to silence a
manifest warning.

Inspect the public import graph:

```bash
rg -n '^import' Main.lean TVL --glob '*.lean'
```

## Current Status

- `TVL.TypeSoundness`: mechanized
- `TVL.SMTEncoding`: mechanized with documented edge-case assumptions
- `TVL.Dominance`: mechanized
- `TVL.OPALCore`: mechanized declarative core with nested template argument soundness/completeness

CI enforcement:

- `.github/workflows/lean-proofs.yml` builds the proofs with `lake build` on every change under `proofs/`, and fails if any Lean source contains the word `sorry` or `admit`, or a line that starts with `axiom`. This is a text check: it misses an axiom declared after a modifier or an attribute (for example `private axiom` or `@[simp] axiom`).

Focused builds include `lake build TVL.Runtime.BinomialGeneric` and
`lake build TVL.OPALCore`. The existing proof CI enforces a strict source policy.
See [OPALCORE_README.md](OPALCORE_README.md) for the OPAL scope and theorem index.
