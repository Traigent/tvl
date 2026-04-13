# Phase 1B Validation Examples

These specs demonstrate the Phase 1B grammar enhancements (parentheses, negation, implication sugar) and the canonical literal hashing exposed by the linter.

| Example | Highlights |
| --- | --- |
| `negated-parentheses.tvl.yml` | Nested parentheses with `not`, ensures typed DNF + literal ordering |
| `implication-sugar.tvl.yml` | Uses implication syntax (`when`/`then` equivalent) that is canonicalised to `¬A ∨ B` |

Run the linter to inspect canonical paths and warnings:

```bash
tvl-lint tvl/spec/examples/validation-phase1b/negated-parentheses.tvl.yml
```
