# TVL 1.3 language conformance (DRAFT)

These self-contained `tvl-runtime-case/1` cases check declarations, lint diagnostics,
static composition, codecs, compilation, hosted projection, measurement normalization,
and promotion joins over supplied verdicts. Run `python -m pytest tests/test_conformance_suite.py -q`.

`python/tvl/runtime_conformance.py` owns the public language registry. Fixture integrity
is checked by `python conformance/tools/check_runtime_cases.py`. Unknown kinds and
expected assertion keys fail closed, including under Python optimization.

Passing a language family does not enable an evaluator or authorize a response action.
Runtime evidence interpretation and execution require a separately supplied engine.
Compiled local artifacts contain declarations, token joins, and checker bindings.
