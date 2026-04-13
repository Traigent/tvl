# Phase 2 Structural Realisability Examples

These modules illustrate the new `tvl-check-structural` CLI. Run the checker to see SAT/UNSAT results:

| Example | Outcome |
| --- | --- |
| `structural-sat.tvl.yml` | Satisfiable structural constraints with witness assignment |
| `structural-unsat.tvl.yml` | Contradictory constraints producing an UNSAT core |

```bash
tvl-check-structural tvl/spec/examples/validation-phase2/structural-sat.tvl.yml
```
