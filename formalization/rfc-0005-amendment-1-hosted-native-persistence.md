# RFC 0005 amendment (DRAFT) — Hosted evaluation of persistence on hosted-native monitors

| | |
|---|---|
| **Status** | **Draft**, not accepted; nothing here is normative until accepted |
| **Amends** | RFC 0005 (Accepted 2026-10-23, TVL 1.5.0), §2.3-§2.5 and the hosted-projection table; formal semantics §14 |
| **Target language version** | none; a behavioural clarification within TVL 1.5 (no new construct, no schema change) |
| **Conformance** | case names in §6 below; case files under `conformance/cases/runtime/` |

Handles: `R5` = `formalization/rfc-0005-persistence-and-census-aggregates.md`,
`S` = `formalization/tvl-formal-semantics.md`, both at `origin/main`, reproducible with
`git show origin/main:<path> | nl -ba`. Draft text is marked "Proposed"; quotations are verbatim.

## 1. Motivation

RFC 0005 requires persistence to be evaluated customer-side and gives its results no hosted
projection (`R5:87`, `R5:268`). That is right when the window verdicts are recorded on the
customer side: the hosted service must not learn them through a persistence side channel.

It is needlessly restrictive for one case. When the trigger monitor is *hosted-native* (the hosted
service itself decides that monitor's window verdicts), the hosted service already holds every
verdict that persistence would count. Evaluating persistence there transfers nothing from the customer
side, yet today the only compliant behaviour is to refuse a persisting rule on such a monitor.

This amendment adds one narrow exception for that case. It opens no customer-to-hosted wire.

## 2. Definitions (Proposed)

- **Hosted-native monitor**: a runtime monitor whose declared evidence source and evaluator profile
  make the hosted service the decider of its window verdicts: `profile: backend_v1` with
  `source: backend_trace_metadata` (RFC 0003 T1 and T2, `R3:383-389`; the "metadata monitors" row of
  `R3:1328`). Classification reads only those declared fields.
- **Customer-recorded monitor**: every other monitor, including any whose verdicts derive from a
  customer-side window report (`R3:1329`).

Where the hosted service performs the arithmetic does not classify a monitor. A verdict the hosted
service recomputes from a customer-side count or report is customer-recorded and never hosted-native.
Classification is bound to the registered monitor revision. Deployment placement alone cannot
reclassify a monitor; a change of source or profile is a monitor revision and resets history (§4.4).
If the declared fields do not resolve to exactly one class, the monitor is unclassified and a
hosted evaluator MUST refuse persistence on it with the diagnostic in §6.

## 3. The exception (Proposed normative text)

3.1. Customer-side evaluation remains the baseline. A conforming hosted evaluator MAY evaluate `persist` for a rule whose `trigger.monitor` is
hosted-native. This is the only case in which persistence is evaluated off the customer side.

3.2. No persistence input crosses from the customer side. The evaluator reads only the hosted-native
monitor's own finalized window verdicts, which it already holds. A hosted evaluator MUST NOT accept,
and MUST NOT define a wire shape for, a persistence result, slot identity, B or U count, or
constituent UNKNOWN reason supplied by a customer-side producer.

3.3. For a customer-recorded monitor, RFC 0005 is unchanged: persistence is evaluated customer-side
and its result, slot identities and constituent UNKNOWN reasons have no hosted projection. A hosted
evaluator asked to evaluate persistence for such a monitor MUST refuse (§6, refusal case). It MUST NOT
fall back to evaluating over partial or inferred history.

3.4. The authored `persist` integers keep their existing projection row (`R5:267`). The exception
adds no customer-to-hosted projection field; the hosted-side outputs are in §5.

## 4. Semantics in the exception (Proposed)

The k-of-n semantics are those of `R5:55-95`, unchanged. In particular:

4.1. **Outcomes.** With B BREACHED and U UNKNOWN slots, the result is BREACHED if `B ≥ k`, MET if
`B + U < k`, otherwise UNKNOWN(`inconclusive`). For k=2, n=3: `BBU` is BREACHED, `MMU` is MET,
`BMU` is UNKNOWN. A startup or missing slot can coexist with a definite result.

4.2. **Slot UNKNOWN versus final UNKNOWN.** A gap placeholder is a slot UNKNOWN(`persistence_history_gap`): the
slot is missing, unavailable, not yet active, incompatible, or lacks an identity field. That makes only
that slot UNKNOWN and counting then proceeds; it does not fail the whole history. A finalized source
window may itself be UNKNOWN(`inconclusive`) (`S:1806`, `S:1821`); its slot keeps that source reason.
The final persistence result UNKNOWN(`inconclusive`) is a separate thing: it is the undecided outcome
of counting, not a slot.

4.3. **Identity.** The n counted slots are consecutive tumbling windows ending with the window that
caused the event, ordered by window start, all sharing requirement, monitor, agent, environment,
contract digest, monitor revision and schedule. A slot counts once. Only finalized verdicts count.
A missing slot occupies its position as UNKNOWN; older decided windows are never substituted.

4.4. **Reset.** History starts fresh at a contract digest change or a monitor revision change (this
includes a policy revision that changes the digest, such as tightening a bound, `R5:68-70`). A
statistical horizon boundary alone does not reset history. After a reset the old records contribute nothing,
but their time positions stay inside the n-slot range and are occupied by UNKNOWN placeholders (`S:2249-2257`;
`persist-revision-reset.yml`). With k=2, n=3, two old-revision breaches then one new-revision breach is
`UUB`, which is UNKNOWN(`inconclusive`), never BREACHED.
A revision change that reclassifies a monitor between hosted-native and customer-recorded is a reset.

4.5. **Gaps.** A window the hosted service did not finalize for a hosted-native monitor (outage, a
not-yet-active window, no evaluation record) is a UNKNOWN(`persistence_history_gap`) slot at its
position. Windows are never back-filled after the event they would have affected was decided.

4.6. **Delivery.** Delivered-once semantics are those of `R5:87-95`. The initial trigger is occurrence
0 even when withheld or suppressed. An undelivered occurrence stays reconsiderable: an
`episode_continued` rule re-evaluates at each fresh continuation and may qualify it, with no new
occurrence number (persistence forbids both repeat coordinates, `R5:59`). A delivered occurrence is never redelivered, including
after a process restart. Exact event replays and delivery retries retain their original decision and
occurrence identity. A rule keeps its original trigger (formal semantics §13.9).

4.7. `only_while` and `unless` resolve after qualification exactly as in `R5:97-100`.

## 5. Hosted-side outputs stay closed (Proposed)

This section defines an abstract decision record of the hosted evaluator. It is not an exchanged artifact
and adds no wire shape. If a later contract exchanges the record, that contract must define its own
closed schema. The record has no free text, slot identity, B or U count or constituent reason.

| Field | Values | Presence |
|---|---|---|
| `persistence_verdict` | `BREACHED`, `MET`, `UNKNOWN` | always, for the event evaluated |
| `decision_reason` | `delivered`, `suppressed_met`, `withheld_unknown`, `already_delivered`, `guard_suppressed` | always, exactly one |

Precedence, first match wins: (1) the occurrence was delivered at an earlier event: `already_delivered`
(verdict still recorded); (2) verdict MET: `suppressed_met`; (3) verdict UNKNOWN: `withheld_unknown`;
(4) verdict BREACHED and an `only_while` / `unless` guard suppresses: `guard_suppressed`;
(5) otherwise `delivered`. Qualification is distinct from delivery: BREACHED qualifies, and only (5)
delivers. MET suppression and UNKNOWN withholding stay distinguishable from each other.

## 6. Conformance (Proposed)

Cases are new unless marked "adapted"; the outcome column is what the case MUST assert. Adapted cases
are the existing ones, re-run with a hosted-native trigger monitor.

| Case | Outcome |
|---|---|
| `persist-withheld-continued.yml` (adapted) | undelivered occurrence 0 may qualify at a fresh `episode_continued`; `withheld_unknown` until then |
| `persist-delivered-continued.yml` (adapted) | later continuation gives `already_delivered`; never redelivered, including after restart |
| `persist-startup-definite.yml` (adapted) | two gap slots plus two breaches (k=2, n=4) give BREACHED; gaps stay `persistence_history_gap` |
| `persist-opened-not-redelivered-on-continued.yml` (adapted) | an `episode_opened` rule is not delivered on a later `episode_continued`; original trigger preserved |
| `persist-gap-missing-{digest,monitor-revision,agent,available,schedule}.yml` (adapted) | each missing identity or availability field makes only that slot a `persistence_history_gap` placeholder |
| `persist-replay.yml`, `persist-horizon-crossing.yml` (adapted) | original decision and identity retained; horizon boundary alone does not reset |
| `persist-gap-not-skipped.yml` (adapted) | missing window occupies its slot; older decided windows not substituted |
| `persist-suppressed-opened.yml` (adapted) | k=2, n=3, history `MMB` at `episode_opened` gives MET and `suppressed_met` (an UNKNOWN current window emits no trigger, `S:1866`, so `MMU` is only a counting example, §4.1) |
| `persist-hosted-native-guard-suppressed.yml` | BREACHED then guard suppression gives `guard_suppressed`, not `delivered` |
| `persist-hosted-native-recorded-inconclusive.yml` | a source slot UNKNOWN(`inconclusive`) is kept as that reason, distinct from a gap slot |
| `persist-hosted-native-revision-reset.yml` | old-revision `BB` then new-revision `B` (k=2, n=3) is `UUB`, UNKNOWN(`inconclusive`) |
| `persist-hosted-native-class-from-report.yml` | verdicts recomputed from a customer report are customer-recorded; hosted evaluator refuses |
| `persist-hosted-native-class-change.yml` | source or profile change is a monitor revision and resets history |
| `persist-hosted-native-class-unresolved.yml` | ambiguous declared source or profile refuses; no fallback |
| `persist-customer-recorded-hosted-refused.yml` | persistence on a customer-recorded monitor at a hosted evaluator refuses with the diagnostic below |
| `persist-hosted-no-customer-wire.yml` | no persistence result, slot identity, B or U count or UNKNOWN reason is accepted from, or defined for, a customer-side producer |

The refusal cases expect a new closed diagnostic `runtime_persistence_customer_recorded_hosted` (severity E),
to be added to the RFC 0005 §2.6 diagnostics table. Condition: a hosted evaluator is asked to evaluate
`persist` for a monitor that is customer-recorded or unclassified. The message echoes no client input.
It is distinct from `runtime_invalid_persistence` (`R5:284`). The existing `persist-local-projection.yml`
is unchanged and keeps asserting that customer-recorded results stay local.

## 7. Edits to the formal semantics (Proposed)

### 7.1 `R5` hosted-projection table

Current (`R5:265-268`):

```
| Item | Hosted projection |
|---|---|
| Authored `persist` integers | JSON integers in the contract allowlist |
| Persistence result, slot identities and constituent UNKNOWN reasons | none; customer-side only |
```

Proposed replacement of the last row:

```
| Persistence result, slot identities and constituent UNKNOWN reasons of a customer-recorded monitor | none; customer-side only |
| Persistence of a hosted-native monitor | permitted to be evaluated by the hosted service from verdicts it already holds; only the closed `persistence_verdict` and `decision_reason` (§5 of the amendment) are defined; no customer-side input |
```

### 7.2 `R5:87` customer-side evaluation

Current (`R5:87`):

```
At each fresh allowed source event, evaluate `persist` customer-side: BREACHED qualifies the occurrence,
```

Proposed:

```
At each fresh allowed source event, evaluate `persist` customer-side, except that a hosted-native
monitor's persistence may be evaluated by the hosted service (amendment §3); BREACHED qualifies the occurrence,
```

### 7.3 `R5:94-95` recording

Current (`R5:94-95`):

```
decision and occurrence identity. Record slot identities, the result and
every constituent UNKNOWN reason customer-side only; absent slots use `persistence_history_gap`.
```

Proposed:

```
decision and occurrence identity. For a customer-recorded monitor, record slot identities, the result and
every constituent UNKNOWN reason customer-side only; absent slots use `persistence_history_gap`.
```

### 7.4 Formal semantics §14 projection paragraph

Current (`S:2418-2422`):

```
Default-deny projection adds only closed operator, metric and comparator enums, opaque source
digest, minimal decimal bounds and authored persistence integers. Reports exchange only the closed
numeric summaries, counts, enums, times, commitments and opaque references. Individual values,
unit identifiers, raw traces, prompts, responses, scorer code, free text, persistence results,
slot identities and constituent UNKNOWN reasons remain customer-side. No customer content is routed
```

Proposed (only the last two lines change):

```
unit identifiers, raw traces, prompts, responses, scorer code, free text, and, for customer-recorded
monitors, persistence results, slot identities and constituent UNKNOWN reasons remain customer-side.
Persistence on a hosted-native monitor may be evaluated by the hosted service over verdicts it already
holds and defines only a closed verdict enum and decision reason. No customer content is routed
```

### 7.5 Formal semantics §14.1 recording sentence

Current (`S:2281-2282`):

```
the original decision and identity. Slot identities, result and constituent UNKNOWN reasons stay
customer-side; absent slots carry `persistence_history_gap`.
```

Proposed:

```
the original decision and identity. For a customer-recorded monitor, slot identities, result and
constituent UNKNOWN reasons stay customer-side; absent slots carry `persistence_history_gap`.
```

## 8. Compatibility (Proposed)

No new construct, schema field or format version. Every module valid under the accepted 1.5 text keeps
its meaning; a rule on a customer-recorded monitor behaves exactly as before. A reader that does
not implement the exception keeps refusing persistence at a hosted evaluator, which is conformant
under the unamended text.

## 9. Open questions (resolved in this draft)

1. Guard suppression: kept as its own value, `guard_suppressed`; qualification is distinct from delivery (§5).
2. Diagnostic name: `runtime_persistence_customer_recorded_hosted` is accepted, with an exact condition and no
   echoed input; `runtime_invalid_persistence` has a different condition (§6).
3. Classification: derived from declared source and profile fields, bound to the registered revision;
   deployment placement never reclassifies; ambiguity refuses (§2).
