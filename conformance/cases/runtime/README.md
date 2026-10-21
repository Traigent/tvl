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

## RFC 0004 recorded semantic traces

`semantic_traces/*.yml` extends the same case envelope with `input.kind: trace`,
an inline `module`, `input.history`, and `expected.notifications`. The conformance
runner compares the **entire ordered notification list**, including empty lists;
missing, extra, duplicate, reordered, or mistimed events fail. Each notification
has `response`, `rule` (the notifying rule id), `event`, and `instant`.

This is a pure reference relation in `python/tvl/runtime_trace.py`, not an engine:
it never starts a repair, writes a deployment, reads live state, or supplies a
clock. All instants and window bounds are nonnegative integer lifecycle hours
from an origin aligned with the declared tumbling windows.
A history names one `agent` and `environment`, then strictly increasing
`evaluations`. Each evaluation has `instant` and optional lists of:

- `windows`: `{monitor, start, end, verdict: MET|BREACHED|UNKNOWN, usable: bool}`.
  Window width is the declared `tumbling_hours`. Re-recording a start corrects
  that window. Runs use window-start order, span their first/last counted windows,
  and retain fired notifications after corrections. Nonusable UNKNOWN windows
  neither count nor end a run. MET/BREACHED ends it; a decided window marked
  nonusable is rejected as inconsistent.
- `episodes`: `{monitor, scope, event: opened|continued|closed}`; a closure also
  has `reason: resolved|withdrawn`. These are recorded RFC 0003 episode facts,
  not episode decisions recomputed from verdicts. A window evaluates its monitor;
  an otherwise unevaluated monitor guard is UNDECIDED.
- `liveness`: `{monitor, scope, event: stale|live_again}`. These are recorded
  RFC 0003 evidence-liveness transitions, not liveness recomputed by this checker.
- `revisions`: `{kind: response|monitor, name, value}`. Initial revision/effective
  key is the string `"1"`. A changed monitor key clears its window history and
  episode state; a response revision closes its pending attempts. An already
  started optimization records its outcome, but cannot yield a later deploy
  after its scope/revision closes (RFC 0003 §7.2; RFC 0004 §2.2).
- `optimizations`: each record has `response`, `revision`, `rule`, `scope`,
  `occurrence` (a nonnegative integer), and `fact`. `fired` records an occurrence
  in an open episode; `started` records its effect starting. `finished` adds
  `completion: normal|error|cancelled|cost_limit` and `candidates`. A valid
  candidate has `{evidence_valid: true, legacy_decision, monitor_verdicts}`; the
  existing RFC 0003 promotion join computes its gate. Invalid evidence is
  `{evidence_valid: false}` and cannot claim a gate decision. `approval` adds
  `effect: optimize|deploy` and `state: granted|declined|expired`; `authority`
  adds `state: reachable|unreachable`. `deploy_started` records the deploy effect
  starting. `deploy_result` adds `checks: passed|refused|unreachable`,
  `write: succeeded|failed|not_attempted`, and `retries_exhausted: bool`. A failed
  write emits `deploy_failed` only at the recorded finite retry bound. Facts
  arriving after attempt closure cannot create outcomes.

Within an evaluation, revisions, windows, episode/liveness facts, then optimize
facts are applied in that order. All notification guards then see the resulting
state, including optimize occurrences recorded in the same evaluation, regardless
of rule declaration order. Notifications are ordered by evaluation, then module
response/rule order. Only delivered notifications appear. The closed vocabulary
rejects unknown fields and facts. It models a complete attempt ledger for the
named agent/environment; absence of any open attempt means FALSE. Monitor state
without evaluation or in another environment is UNDECIDED.

The supported notification triggers are the four episode boundary/continuation
events above, the four RFC 0004 failure outcomes, `unknown_for`, `stale`, and
`live_again`. Repeats are supported on `unknown_for` and `episode_opened`, and
re-evaluate guards for each occurrence while their scope persists, including
after a suppressed first occurrence. Each repeat's due instant must appear as an
evaluation; missing repeat evaluations fail rather than inventing a catch-up
policy. Batched continuation facts each yield their own occurrence. Other trigger or
repeat combinations fail explicitly rather than silently claiming conformance.

Run the executable traces and reference-function probes with
`.venv/bin/pytest -q tests/test_runtime_trace.py tests/test_conformance_suite.py`.
Passing these cases establishes the recorded-history relation only; it does not
establish controller execution, scheduling, retry policy, or effect authority.
