# Phase 4 IDE Integration Examples

These fixtures exercise the IDE-focused workflow from Phase 4 of the validation roadmap. Open them in VS Code with the TVL extension to see on-save diagnostics, quick fixes, and command-triggered solver feedback.

| Example | Highlights |
| --- | --- |
| `on-save-typo-diagnostics.tvl.yml` | Introduces misspelled identifiers and type mismatches so the Problems panel can surface quick-fixable lint errors as soon as the file is saved. |
| `structural-core-preview.tvl.yml` | Contains contradictory structural clauses; running `TVL: Check Structural Realisability` shows the unsat core with stable spans and a witness preview. |

Quick reference for the commands that drive these walkthroughs:

```text
TVL: Check Structural Realisability
TVL: Check Operational Realisability
```
