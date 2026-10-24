# RFC 0005 — Breach Persistence and Census Aggregates

| | |
|---|---|
| **Status** | **Accepted** 2026-10-23 (TVL 1.5.0) |
| **Target language version** | TVL 1.5 (conservative extension of 1.4) |
| **Tracking** | PRs #186 and #187 |
| **Builds on** | RFC 0003 (Accepted, TVL 1.3); RFC 0004 (Accepted, TVL 1.4) |
| **Companion** | [formal semantics §14](tvl-formal-semantics.md#14-breach-persistence-and-census-aggregates-tvl-15); existing §§12–13 remain the baseline |
| **Conformance** | case names in §5; case files under `conformance/cases/runtime/` |

All additions below are normative as of acceptance on 2026-10-23 as TVL 1.5.0.
Existing-text handles use repository paths at `098bcdfba0b7347eda9cdbad2e351aad39d25f95`:
`R3` = `formalization/rfc-0003-runtime-requirements-monitors-responses.md`;
`R4` = `formalization/rfc-0004-reactive-outcomes-and-guards.md`;
`S` = `formalization/tvl-formal-semantics.md`; `J` = `spec/grammar/tvl.schema.json`.
Thus `S:1682` is a file:line handle, reproducible with `git show <revision>:<path> | nl -ba`.
The accepted statuses above are recorded at `R3:5` and `R4:5`.
## 1. Motivation

TVL Reactive Contracts need two additional statements: “notify when this requirement breached in three of
the last four windows” and “daily observed spend is at most USD 50”, with days aligned to UTC midnight
(`S:1682`). A third example uses the same aggregate
construct: “the mean recorded score over every member of a closed window is at least 0.8”.

The existing catalogue has rate, zero-tolerance, recovery and liveness requirements (`S:1576`); notifications
can have episode or attempt guards (`R4:42–55`). Neither is a census sum or mean. RFC 0004 explicitly defers
k-of-n persistence (`R4:351`). This RFC adds only finite breach persistence and census `sum`/`mean` bounds.
It adds no response action. The response policy and its approval rules remain those of `S:1842–1858`.

## 2. Design

### 2.1 Grammar and version

Productions not shown retain RFC 0003/0004 meanings. `rec` is closed; `number` follows `R3:258–262`.

```ebnf
rule          = rec(…RFC 0003/0004 fields…, ["persist": persistence]) ;
persistence   = rec("breached_in": integer, "of_last": integer) ;
req           = …RFC 0003 variants… | aggregate_req ;
aggregate_req = rec("name": ident, "kind": "aggregate_bound", "unit": unit_kind,
                    ["among": checker_pred], "aggregate": aggregate, "bound": bound) ;
aggregate     = rec("op": "sum" | "mean", "metric": "cost_usd" | "score", "source_digest": fp) ;
bound         = rec("lte": number) | rec("gte": number) ;
decision      = …RFC 0003 variants… | rec("method": "exact_aggregate_v1") ;
```

`unit_kind` remains `trace | invocation`. The new kind, operators, metrics, bound directions and method are
sealed. `score` is a new numeric observation, distinct from categorical checker labels (`R3:204–205`).
Every module or pack using either addition declares `tvl_version: "1.5"`. Omission is
`runtime_version_required`; a lower or incompatible declaration is `declared_version_below_constructs`.

### 2.2 Breach persistence on notifications

`persist` filters a notification; it never replaces the source monitor's verdict. Write k = `breached_in`,
n = `of_last`. Require integers `1 ≤ k ≤ n ≤ 168`; 168 bounds stored window slots (one week only if W=1h).
It applies only to `do: notify`, with `episode_opened` or `episode_continued` from one primary runtime
monitor. This RFC extends primary monitors to include `aggregate_bound`. Burn, promotion and obligation
monitors are not eligible. Neither repeat coordinate (`repeat_after_hours`, `max_repeats`) is allowed.

The source is exactly `trigger.monitor`, not a requirement lookup or a list. The counted slots are n
consecutive tumbling windows ending with the window that caused the event, ordered by window start.
All records must have the same requirement, monitor, agent, environment, contract digest, monitor revision
and schedule. A missing contract digest, monitor revision, agent, environment or schedule identity,
or an absent `available` field, makes the slot UNKNOWN(`persistence_history_gap`). A slot counts once.
Use finalized verdicts only. Missing, unavailable, not-yet-active or incompatible slots occupy their
position as UNKNOWN; never skip them for older decided windows.
A contract or monitor revision starts fresh history; a statistical horizon boundary alone does not.
Tightening a bound changes the contract digest (`R3:1663,1675–1680`) and resets history: conservative
safety under the new bound takes priority over notification continuity across revisions.

Let B be the number of BREACHED slots and U the number of UNKNOWN slots. The persistence result is:

| Condition | Result |
|---|---|
| `B ≥ k` | `BREACHED` — the historical condition holds |
| `B + U < k` | `MET` — the historical condition does not hold |
| otherwise | `UNKNOWN(inconclusive)` |

These labels describe only the historical condition, not present quality or source MET.
For k=2, n=3, `BBU → BREACHED`, `MMU → MET`, `BMU → UNKNOWN`. A startup or missing slot can therefore coexist
with a definite result. `BBM` also satisfies the historical condition, but its current MET window emits
neither allowed breach event (`S:1805`), so it produces no persistence notification.
k=n requires consecutive breaches; k=n=1 leaves eligibility at an allowed trigger unchanged.

At each fresh allowed source event, evaluate `persist` customer-side: BREACHED qualifies the occurrence,
MET suppresses it, UNKNOWN withholds it. The initial trigger counts as occurrence 0 even when withheld
or suppressed. No delivery is queued merely for a later state change. The rule keeps its original
trigger, as required by formal semantics §13.9: an `episode_opened` rule is not delivered on a later
`episode_continued`. An `episode_continued` rule evaluates at each fresh continuation and may reconsider
its undelivered occurrence; without a repeat, no new occurrence number is allocated. A delivered
occurrence is never delivered again. Exact event replays and delivery retries retain their original
decision and occurrence identity. Record slot identities, the result and
every constituent UNKNOWN reason customer-side only; absent slots use `persistence_history_gap`.

After qualification, `only_while` and `unless` resolve exactly as before: UNDECIDED never suppresses
(`S:2104–2115`). Persistence UNKNOWN deliberately requires positive evidence to qualify; it does not
change that guard rule. A suppressed notification changes no verdict, episode, obligation or action state.
In particular, source MET windows alone count toward episode closure (`S:1806`).

```yaml
# Response fragment; latency_prod is an existing primary runtime monitor.
responses:
  - name: persistent_latency
    rules:
      - id: later_bad_window
        trigger: {monitor: latency_prod, event: episode_continued}
        persist: {breached_in: 3, of_last: 4}
        do: notify
        severity: critical
```

Counting across requirements is deferred: populations, schedules, allocations and episode scopes need not agree.
### 2.3 Census aggregate requirements

| Metric | One contribution per population unit | Unit of sum; unit of mean |
|---|---|---|
| `cost_usd` | finite, nonnegative exact decimal cost under the declared source contract | USD; USD per unit |
| `score` | finite exact decimal recorded score in `[0,1]` | dimensionless score total; dimensionless mean score |

The source contract fixes the observed unit universe, cost accounting or scorer version, handling of all
terminal statuses, numeric encoding and finite resource bounds. Its immutable `source_digest` is required
in the authored and compiled requirement and in registration. The local evaluator profile must resolve it
to exactly that versioned contract before activation; no default scorer or source is chosen. The digest
is an opaque commitment, not scorer text. Changing the source requires a different requirement identity.
The profile's procedure remains outside TVL, as with existing evaluator profiles (`S:1665`).

`bound` has exactly one comparator. Equality meets either bound. Bounds are nonnegative; a mean-score
bound is additionally at most 1. A score sum may exceed 1. No weights, expressions or unit conversions
are implied. A recorded score measures the declared scorer's output, not independently established quality.

```yaml
# Requirement and monitor fragment; the illustrative digest needs a matching local source contract.
requirements:
  - name: daily_spend
    kind: aggregate_bound
    unit: invocation
    aggregate:
      op: sum
      metric: cost_usd
      source_digest: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    bound: {lte: 50}
monitors:
  - name: daily_spend_prod
    requirement: daily_spend
    phase: runtime
    evidence: {source: customer_side, deployment_environment: production}
    window: {tumbling_hours: 24, grace_minutes: 30}
    decision: {method: exact_aggregate_v1}
    episode: {closure_windows: 2, closure_max_age_hours: 72}
```

For mean score, use `op: mean`, `metric: score`, the scorer contract's digest and `bound: {gte: 0.8}`.
These fragments are not complete modules or evidence of an installed contract monitor.

**Monitor compatibility.** Aggregate monitors are runtime primaries with `source: customer_side` only.
Sampling is omitted, meaning census as in `S:1692`. `decision` contains only `method: exact_aggregate_v1`.
`profile: backend_v1`, promotion phase, burn factors, statistical decision fields, `min_samples`,
`max_unresolved_fraction`, `single_producer` and `limits` are forbidden. Source resource bounds are fixed
by its contract. Require `window` and `episode`, with existing fields/ranges (`R3:272–277,452–461`);
environment, attribution and resolution retain the primary defaults (`R3:448–450`).

An aggregate primary emits the existing episode events and may use existing responses under their existing
restrictions. It emits no `unit_violation` and supports no local guard. There is no aggregate promotion
monitor in 1.5: `optimize.deploy: if_promoted` on its episode cannot satisfy the same-requirement promotion
monitor check (`R3:642`); diagnose `response_deploy_without_promotion_monitor`. Other effect authority,
target eligibility, suspend approval and recovery rules remain unchanged (`S:1853–1858,1880–1898`).

### 2.4 Membership, completeness and finalization

Keep attribution, environment and start-time placement from `S:1682`: a unit starting exactly at a window's
end belongs to the next window. Omitted `among` selects all placed in-scope units; otherwise use the existing
checker membership semantics (`S:1659`). Membership must be exactly boolean `true`, boolean `false` or
the string `"unknown"`; any other value, including numeric `1`, is an invalid record and makes the census
incomplete. Known false membership is excluded; unknown membership is unresolved.
Include completed, failed and rejected units; never silently select only successful units.

Deduplicate locally by (agent, environment, unit kind, stable SDK unit identifier). An identical replay
contributes once. Compare contribution values after exact decimal parsing: `"1"` and `"1.0"` are equal
values and do not conflict. Conflicting duplicate histories or values prevent completeness. Every
population member needs one valid contribution; a missing or invalid value is not zero. Unresolved attribution that could
belong to this population prevents completeness; unrelated out-of-scope units do not join it.

Complete means a census of the declared **observed** universe: every selected unit accounted for, membership
and placement resolved, all relevant histories terminal and complete, the producer set and sequences
complete, watermarks through `due(w)`, no dropped units, and one valid contribution per member. Source
attestations must establish this; conservation counts alone do not. Missing or null coverage makes the
census incomplete, yielding `UNKNOWN(incomplete)`. Units arriving after due make the census incomplete
unless coverage attests otherwise; they must not be silently discarded to produce MET. This is not a
claim about unobserved traffic, all invoice charges, scorer correctness or expected future quality.

`due(w) = end(w) + grace` follows `S:1682,1750`. Before due, return `UNKNOWN(aggregate_pending)`.
At due, evidence arriving by due is final. Incompleteness yields `UNKNOWN(incomplete)`, even
if a partial sum already exceeds its upper bound. A complete empty population yields
`UNKNOWN(insufficient)`, never zero-sum MET. Later arrivals cannot change the window's recorded verdict.
Append-only audit corrections can expose contradictions; they cannot rewrite a finalized verdict,
withdraw delivered notifications or create another statistical look. Exact replays do not reevaluate it.

**Arithmetic.** Authored bounds follow exact decimal literal recovery (`R3:258–262`). Source values use
lossless finite decimal encodings. Sum with exact scaled integers or rationals, without intermediate
rounding. For mean, compare the exact sum with `member_count × bound`; never compare a rounded quotient.
NaN, infinity, negative cost and scores outside `[0,1]` are invalid contributions and make coverage
incomplete. Check numeric encoding and precision/resource limits before conversion to exact rationals.
If these limits prevent exact arithmetic on otherwise valid evidence, including overlong numeric strings,
return `UNKNOWN(aggregate_precision_limit)` rather than raising a conversion error.
No tolerance or round-to-pass rule is allowed.

### 2.5 Composition and exchanged documents

Aggregate requirement identity is (kind, unit, canonical among, operator, metric, source_digest, comparator
direction). It excludes the numeric bound. Overlays may decrease `lte` or increase `gte`; meet takes their
minimum or maximum respectively. Other identity changes are `runtime_incompatible_replacement`. Extend
effective monitor keys using this identity and the existing source/environment/method coordinates
(`R3:1435–1443`); source/scorer differences cannot share a floor. Keep schedule compatibility checks.
Both coordinates of `persist`, and its presence, are immutable under overlay/meet; there is no inferred
tightening order. Packs rewrite `trigger.monitor` to its canonical monitor as before (`R3:1460–1461`).
Persistence adds no monitor identity, floor requirement or episode lifecycle.

New projected constructs select `tvl-runtime-contract/3` and `tvl-runtime-local/3`, version
`"1.5"`. A version declaration alone does not select `/3`; without a 1.5 construct keep the existing
construct-based `/1` or `/2` selection (`R4:264–283`). Refuse `/3` without a 1.5 construct. Freeze the old
schemas; refuse unknown format tags rather than dropping fields. Count reports remain `/1`.

Aggregate reports use `tvl-runtime-report/2`, a closed record with exactly these fields:

| Field | Content |
|---|---|
| `format` | `tvl-runtime-report/2` |
| `contract_digest`, `monitor_ref`, `monitor_revision` | existing binding types (`R3:1723–1725`) |
| `window_start_ms`, `window_end_ms`, `source_digest` | aligned window and registered source commitment |
| `counts` | natural numbers: selected, reported, dropped, member_count, contribution_count, unknown_membership, unplaceable, excluded, missing_value, invalid_value |
| `sum` | optional minimal exact decimal string; required for complete nonempty evidence when arithmetic succeeds |
| `unknown_reason` | optional closed enum with the single value `aggregate_precision_limit` |
| `coverage` | existing closed coverage fields/types (`R3:1729`), all flags true and watermark ≥ due for completeness |
| `units_commitment` | lowercase hex HMAC-SHA-256 of the canonical payload defined below, under a customer-held secret |
| `sdk_version`, `evidence_tier` | existing version type; exactly `client_attested` |

The disjoint count partitions satisfy `selected = reported + dropped`,
`reported = member_count + unknown_membership + unplaceable + excluded`, and
`member_count = contribution_count + missing_value + invalid_value`. A member with multiple defects is
counted once: missing value takes precedence over invalid value. Require the source binding and count
identities on every report. A mean is reconstructed from sum/count; no rounded mean field is exported.
For complete nonempty evidence, `sum` may be omitted only with
`unknown_reason: "aggregate_precision_limit"`, yielding `UNKNOWN(aggregate_precision_limit)`;
otherwise its omission is `runtime_report_numeric`. When `member_count` is zero, `sum` must be absent
or `"0"`; a nonzero sum is `runtime_report_numeric`. The entire sum string must match the minimal
decimal encoding; trailing characters, including a newline after `12.5`, are `runtime_report_numeric`.
The commitment payload binds `contract_digest`, `monitor_ref`, `monitor_revision`, both window times
and `source_digest`, plus the deduplicated unit list sorted in ascending order by the UTF-8 bytes of
the canonical JSON of each unit key object `{agent, environment, unit_id, unit_kind}`, with canonical
object key order. Each entry includes the full local key (§2.4), membership, canonical exact value or
missing/invalid state, and source digest.
Use canonical JSON (`R3:1656–1658`) with decimal values as minimal strings and a random 256-bit secret
held only customer-side. This keyed commitment replaces the unkeyed construction only for report/2;
report/1's `{unit_id, class}` digest (`R3:1732`) is unchanged.

Projection permits only these numeric summaries, counts, closed enums, times, commitments and opaque
references. Add closed operator, metric, bound direction, source digest and persistence integers to the
contract allowlist; bounds use minimal decimal strings. Individual values, unit IDs, prompts, responses,
raw traces, scorer code and free text stay customer-side. Exchange closed numeric summaries only, under
the default-deny projection (`R3:1322–1342`); no customer content is routed through observability.
These are projection rules, not additional report fields:

| Item | Hosted projection |
|---|---|
| Authored `persist` integers | JSON integers in the contract allowlist |
| Persistence result, slot identities and constituent UNKNOWN reasons | none; customer-side only |

A summary can itself be sensitive: this RFC makes no anonymization or observability privacy claim.
Customer attestations are not independently verified population or source correctness.

### 2.6 Schemas and diagnostics

The authored schemas extend `RequirementDecl` with `aggregate`/`bound`, and `RuleDecl` with `persist`;
extend the kind/method registries. Follow the existing flat union of variant keys (`J:851–866`) and the
shape-versus-lint split (`R3:520–531`): schemas check closed keys, primitive types and common required keys;
lints check enums, variant presence/absence, domains and references. Every nested record is closed.
Exactly one bound key is a variant rule. The following codes are new or explicitly reused:

| Code | Severity | Condition |
|---|---|---|
| `runtime_persistence_out_of_range` | E | integer k/n outside `1 ≤ k ≤ n ≤ 168` |
| `runtime_invalid_persistence` | E | wrong source role/event, or either repeat coordinate on a persistence rule |
| `runtime_aggregate_bound_out_of_range` | E | bound outside §2.3's numeric domains |
| `runtime_report_numeric` | E | malformed/noncanonical or out-of-domain sum; nonzero sum for zero members; missing sum for complete nonempty evidence without `unknown_reason: "aggregate_precision_limit"` |
| `runtime_notify_only` | E | extends `R4:244` to `persist` on any action other than `notify` |
| `runtime_invalid_profile` | E | aggregate variant field missing/forbidden, both/no bound directions, or incompatible monitor tuple |
| `runtime_unknown_kind` | E | unknown kind, operator, metric or method |
| `runtime_missing_ref`, `runtime_ref_kind_mismatch` | E | missing or wrongly typed trigger/membership reference |
| `runtime_report_conservation` | E | extends `R3:654` to aggregate count identities and window/source binding failures |
| `runtime_incompatible_replacement`, `evaluation_schedule_mismatch` | E | identity/persistence replacement or changed schedule |
| `runtime_version_required`, `declared_version_below_constructs` | E | missing or incompatible language declaration |
| `schema_error`, `unsupported_construct` | E | invalid shape/type/tag, or an entrypoint refusing an unsupported construct |

Verdict reasons are separate closed enums. Reuse `insufficient` for empty aggregates and `inconclusive`
for undecided persistence (`S:1741,1745`). Extend `incomplete` beyond zero tolerance (`S:1746`) to any
incomplete aggregate, including invalid raw contributions. Add only `persistence_history_gap` for a
placeholder slot, `aggregate_pending` before due and `aggregate_precision_limit` for arithmetic limits;
the existing reasons have no equivalent for these conditions. Malformed exchanged summaries are refused.
Codes echo no input. Schemas, lints, compilation and reference conformance relations exist; source profiles,
registration verifiers and an evaluator are not established (§7, question 3).

## 3. Compatibility

Every valid 1.4 module or pack retains its meaning without either opt-in addition. Keep old diagnostics,
verdicts, episodes, obligations, promotion, response authority and formats. For identical inputs and a
fixed toolchain version, old canonical artifacts and digests remain identical. This does not assert that
a future compiler's default toolchain version is unchanged; that field already affects digests (`R4:276–283`).
Older readers refuse new constructs through closed shapes or `unsupported_construct`, never erase them.
No statistical budget, response grant or deployment authority is created by either addition.

## 4. Semantics and proofs

For window slots `w[j−n+1] … w[j]`, let each UNKNOWN range over MET/BREACHED. The completion set contains
every such replacement. Persistence is BREACHED iff every completion has at least k breaches, MET iff
none does, UNKNOWN otherwise. The bounds B and B+U in §2.2 are its minimum and maximum breach counts.

**No new statistical evidence or looks.** Reusing verdicts creates no observations, binomial tests,
independence, confidence amplification or reusable alpha. Keep `m = 24H/W`, `α_w = α_FA/m`, or the finite
allocation `∑ α_w ≤ α_FA` (`S:1750–1756`). Overlapping histories reuse charged verdicts, not unit data.
Revisions cannot replenish alpha; horizon-crossing history retains each window's original charge.

For the same source event stream, rules and guard valuations, removing `persist` gives a superset of
delivered breach-event occurrences. It can only reduce those eligible notifications. This says nothing
about all notification counts under different response policies, future actions or episode counts.
Every qualified event still has a current raw BREACHED window. Thus a notification at a compliant current
window implies a false raw breach there. Under the original rational-test assumptions (`S:1729–1733`),
the chance of any such notification from source windows in the predesignated horizon is at most α_FA,
regardless of delivery time, by the same union bound. No α raised to k or cross-window independence claim
is added. No new bound applies to floating-point `_v1` or unsupported selection (`S:1730–1733,1761`).

For a complete nonempty population P, `C = |P| > 0`, `S = ∑[v∈P] x_v` and `A_sum=S`, `A_mean=S/C`.
Return MET iff the declared comparison holds, BREACHED otherwise. UNKNOWN preconditions in §2.4 take
precedence. This is a deterministic statement about recorded observed values, not a hypothesis test,
expected future quality, a new false-alarm allocation or proof that an attested source reported honestly.

Formal semantics §14 and the Lean work must state: completion soundness; notification-subset and
no-new-look properties under those hypotheses; exact aggregate comparison equivalence; and conservative
1.4 embedding preserving TVAR, structural, promotion and runtime denotations. Lean statements for completion
soundness and exact mean comparison are in `proofs/TVL/Runtime/Persistence.lean`, with scope and build status in
`proofs/PROOF_SUMMARY.md`; the other properties remain proof obligations. None of this claims passing
conformance, controller execution or production enablement.

## 5. Conformance

The following case names and expected outcomes are normative; the case files are under
`conformance/cases/runtime/`. Semantic cases record histories and expected decisions; they do not imply an
evaluator exists.

| Case name(s) | Expected diagnostic or semantic outcome |
|---|---|
| `persist-k1-n1-valid.yml`; `persist-consecutive-valid.yml` | accepted; identity at breach events; k=n requires n breaches |
| `persist-bbu.yml`; `persist-mmu.yml`; `persist-bmu.yml` | k=2,n=3: BREACHED; MET; UNKNOWN(inconclusive) |
| `persist-startup-definite.yml`; `persist-startup-undecided.yml` | missing slots remain UNKNOWN; decide only when completions agree |
| `persist-gap-not-skipped.yml`; `persist-revision-reset.yml` | placeholder persistence_history_gap; never substitute older verdicts |
| `persist-horizon-crossing.yml`; `persist-replay.yml` | original charges retained; no duplicate occurrence or recomputation |
| `persist-withheld-continued.yml`; `persist-delivered-continued.yml` | fresh continuation may qualify undelivered occurrence 0 only for an `episode_continued` rule; delivered occurrence never redelivered |
| `persist-local-projection.yml`; `aggregate-bound-history-reset.yml` | result/reasons stay local; authored integers export; tightening changes digest and resets history |
| `persist-bbm-no-event.yml`; `persist-guards-undecided.yml` | no current breach notification; qualified event keeps 1.4 guard resolution |
| `persist-range-zero.yml`; `persist-k-above-n.yml`; `persist-n169.yml` | runtime_persistence_out_of_range |
| `persist-string-n.yml`; `persist-extra-key.yml` | schema_error |
| `persist-burn.yml`; `persist-timer.yml`; `persist-repeat.yml` | runtime_invalid_persistence |
| `persist-optimize.yml`; `persist-ref-missing.yml` | runtime_notify_only; runtime_missing_ref |
| `aggregate-sum-equality.yml`; `aggregate-mean-score.yml` | sum=50 ≤50 MET; mean of 0.7,0.9 ≥0.8 MET |
| `aggregate-sum-breach.yml`; `aggregate-mean-third.yml` | sum=50.01 ≤50 BREACHED; 1/3 ≥0.333333333333333 MET without rounding |
| `aggregate-empty.yml`; `aggregate-partial-over-budget.yml` | UNKNOWN(insufficient); UNKNOWN(incomplete) |
| `aggregate-before-due.yml`; `aggregate-late-value.yml` | UNKNOWN(aggregate_pending); finalized incomplete verdict unchanged |
| `aggregate-failed-unit.yml`; `aggregate-among-false.yml` | failed unit's declared value included; known nonmember excluded |
| `aggregate-membership-unknown.yml`; `aggregate-nan-source.yml`; `aggregate-missing-value.yml` | UNKNOWN(incomplete), never zero-filled |
| `aggregate-replay.yml`; `aggregate-conflicting-duplicate.yml` | count once; UNKNOWN(incomplete) |
| `aggregate-source-replacement.yml`; `aggregate-direction-change.yml` | runtime_incompatible_replacement |
| `aggregate-sampled-declaration.yml`; `aggregate-promotion.yml` | runtime_invalid_profile |
| `aggregate-sampled-evidence.yml`; `aggregate-precision-limit.yml` | UNKNOWN(incomplete); UNKNOWN(aggregate_precision_limit) |
| `aggregate-report-counts.yml`; `aggregate-report-binding.yml` | runtime_report_conservation |
| `aggregate-keyed-commitment.yml`; `legacy-report1-commitment.yml` | report/2 uses local-secret HMAC over bound canonical payload; report/1 digest unchanged |
| `aggregate-report-nan.yml`; `aggregate-report-negative-sum.yml` | runtime_report_numeric |
| `aggregate-op-unknown.yml`; `aggregate-metric-unknown.yml`; `aggregate-method-unknown.yml` | runtime_unknown_kind |
| `aggregate-extra-key.yml`; `aggregate-wrong-primitive.yml` | schema_error |
| `aggregate-source-missing.yml`; `aggregate-both-bounds.yml` | runtime_invalid_profile |
| `aggregate-negative-bound.yml`; `aggregate-mean-score-bound-two.yml` | runtime_aggregate_bound_out_of_range |
| `aggregate-deploy-if-promoted.yml` | response_deploy_without_promotion_monitor |
| `persist-pack-ref-rewrite.yml`; `aggregate-pack-tightening.yml` | canonical trigger reference; lte decreases/gte increases |
| `version-15-missing.yml`; `version-14-new-construct.yml` | runtime_version_required; declared_version_below_constructs |
| `old-reader-new-construct.yml`; `format-v3-without-new-construct.yml` | schema_error or unsupported_construct by entrypoint; schema_error |
| `legacy-14-meaning.yml`; `legacy-artifact-bytes.yml`; `version-15-alone.yml` | unchanged 1.4 outcomes/bytes at fixed toolchain; prior format selection |

## 6. Alternatives considered

| Alternative | Reason not chosen |
|---|---|
| Replace raw verdicts or episode entry with persistence | Historical MET would be confused with present satisfaction; would change closure or repair timing. |
| Persistence on service effects or timer repeats | Needs new effect-time and repeated-evaluation rules; notification filtering leaves authority intact. |
| Sampled sums or confidence bounds for means | Need new estimands, assumptions and error accounting; these checks concern complete observed populations. |
| Early breach from a partial nonnegative sum | Sound in a narrower case, but would abandon the uniform complete-census rule requested here. |
| General temporal expressions or arbitrary numeric reducers | Enlarges the language beyond these two bounded constructs. |

Design sources: [pure-past finite-trace logic](https://www.ijcai.org/proceedings/2020/690) for a past-only
interpretation, and [RTLola stream aggregation](https://arxiv.org/abs/1711.03829) for aggregate streams.
This RFC borrows those ideas, not their syntax, algorithms, sliding windows or correctness results.
## 7. Open questions

1. Should a later version add census count/min/max? They are not normative operators in 1.5.
2. Is 168 the right history limit? TVL 1.5 fixes it at 168; a later version may change it with updated cases.
3. Which concrete local source profiles and registration verifiers will support these contracts? Their
   implementation and complete document schemas must be reviewed before enablement; none is established here.

Out of scope: maintenance/external events (await a closed event catalogue in a later RFC); sliding windows and site reliability engineering (SRE)
multi-burn alerts (1.6, with full statistical-look accounting); baseline-relative regression; headroom
proposals; synthesis of action-blocking monitors from temporal specifications; change-point detection; any
general linear or signal temporal logic (LTL/STL) language; learned anomaly alerts;
auto-tightening. None is implied by the two additions above.
