# TVL Conformance Suite (Minimal)

This suite captures a minimal set of black-box cases that the loader and validators should pass.

- `cases/satisfiable/minimal.yml` — smallest valid module
- `cases/satisfiable/banded-target.yml` — banded targets (hard/soft)
- `cases/unsatisfiable/conflicting-implications.yml` — conflicting DNF implications (unsat)
- `cases/gate/chance-constraint-pass-fail.yml` — synthetic incumbent vs candidate gate outcomes
- `cases/configurations/valid.yml` — configuration valid for example module
- `cases/measurements/valid.yml` — measurement bundle satisfying objectives

`expected/results.json` contains placeholders until the SMT and statistical tests are implemented.
