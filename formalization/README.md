# Formalization and the RFC process

This directory holds the formal semantics of TVL and the RFCs that change the language.

- [`tvl-formal-semantics.md`](tvl-formal-semantics.md) — formal semantics; normative and informative sections are identified.
- [`tvl-formal-roadmap.md`](tvl-formal-roadmap.md) — what is formalized and what is planned.
- [`rfc-template.md`](rfc-template.md) — the template for a new RFC.

## RFC index

| RFC | Title | Status | Target version |
|-----|-------|--------|----------------|
| [0001](rfc-0001-knob-bindings-cvars-policies.md) | Knob Bindings: Calibrated Variables (`cvars`) and `policies` | Accepted (2026-06-05) | TVL 1.1 |
| [0002](rfc-0002-composite-knobs.md) | Composite Knobs: a sealed control-flow algebra and a named pattern catalog | Accepted (2026-06-06) | TVL 1.2 |
| [0003](rfc-0003-runtime-requirements-monitors-responses.md) | Runtime Requirements, Monitors and Responses | Accepted (2026-10-21) | TVL 1.3 |
| [0004](rfc-0004-reactive-outcomes-and-guards.md) | Reactive Outcomes and Guards: telling people when the repair loop needs them | Accepted (2026-10-21) | TVL 1.4 |
| [0005](rfc-0005-persistence-and-census-aggregates.md) | Breach Persistence and Census Aggregates | DRAFT | TVL 1.5 |

The status column is read from each RFC's header; the RFC is the authority if they ever differ.

## When an RFC is needed

A change that alters the language needs an RFC: new syntax or blocks, a change to the meaning of a construct, new or changed diagnostic codes, schema changes, or changes to the promotion contract. Bug fixes, documentation, examples and tooling that do not change the language go through an ordinary pull request.

## Lifecycle

```text
Draft → Proposed → Accepted → Final
              ↘ Rejected      ↘ (superseded by a later RFC)
Draft / Proposed → Withdrawn
```

- **Draft** — being written; open to change. Opened as a pull request.
- **Proposed** — the author considers it complete and asks for a decision. The pull request stays open for review.
- **Accepted** — the maintainers accepted the design. The pull request merges with the status set to Accepted and the date (RFC 0001 and RFC 0002 keep Accepted as their header status).
- **Final** — implemented in the tools, covered by conformance cases, and shipped in a language version (a draft RFC may land on `main` marked Draft while a draft language version is developed, as RFC 0003 did before its acceptance).
- **Rejected** — the maintainers declined it; the reason is recorded in the RFC.
- **Withdrawn** — the author withdrew it.

## Numbering and review

1. Copy [`rfc-template.md`](rfc-template.md) to `rfc-NNNN-short-title.md`, using the next unused four-digit number. Open a pull request; the number is confirmed in review.
2. Discussion happens on the pull request, in the open. Reviewers check motivation, compatibility with the previous language version, precision of the normative text, and conformance coverage.
3. The maintainers listed in [`MAINTAINERS.md`](../MAINTAINERS.md) accept or reject the RFC, as described in [`GOVERNANCE.md`](../GOVERNANCE.md), and record the decision and reason in the RFC's status.

## What an accepted spec change must include

- Conformance cases under [`conformance/cases/`](../conformance/cases/) that exercise the new behaviour, including invalid inputs and their diagnostics.
- Updates to the schemas, grammar and tools where they are affected (keep `vscode-tvl/schemas/` and `editor_shared/vscode/schemas/` byte-identical to `spec/grammar/*.json`, as checked by `tests/test_editor_schema_sync.py`, and run `pnpm --dir website run sync:canonical` when synced `docs/` or `spec/` files change).
- Where the change touches constructs covered by the formal semantics or the Lean proofs, an update to [`tvl-formal-semantics.md`](tvl-formal-semantics.md) and, where applicable, the proofs in [`proofs/`](../proofs/). If a result is not yet formalized, the RFC says so.
- Documentation for each new diagnostic in [`docs/reference/error-codes.md`](../docs/reference/error-codes.md), and a `CHANGELOG.md` entry under `[Unreleased]`.

## License

See [`LICENSE`](LICENSE) in this directory.
