# RFC 0008 — Holdout Declaration: an evaluation set kept aside from exploration

| | |
|---|---|
| **Status** | **DRAFT** — not accepted; syntax, codes and meaning may change before acceptance |
| **Target language version** | TVL 1.6 (conservative extension of 1.5) |
| **Tracking** | to be linked when a pull request exists |
| **Builds on** | RFC 0003 (promotion monitors on `evaluation_set` evidence, Accepted); the promotion gate of formal semantics §9 |
| **Companion** | `formalization/tvl-formal-semantics.md` §2.9 (module structure), §9.7 (complete promotion predicate), §12.7 (promotion monitors); `spec/promotion-gate-io.md`; `spec/promotion-evidence-contract.md` |
| **Conformance** | `conformance/cases/gate/holdout-*.yml` and `conformance/cases/lint/holdout-*.yml` (§5) |

Existing-text handles are repository paths at `origin/main` commit `674d9aa2a4340115600e837ac28d8538d2b57867`.
Number 0008 is a proposal: RFC 0006 and RFC 0007 are open drafts, and the number is confirmed in review.

## 1. Motivation

The book teaches a rule the language cannot state. Chapter 6 (`website/client/src/book/chapters/06-evidence.mdx`)
splits 200 tickets once: 60 for tuning and 140 for judging, and says "an evaluation set kept apart from tuning like
this is also called a holdout". It adds that a reused holdout inflates false positives ("choose on the tuning
split, keep the evaluation set for the final comparison"). The statistical validation guide says a measurement
bundle "should bind ... the evaluation-set version or digest".

Today `evaluation_set` is `{dataset, seed?}` (`spec/grammar/tvl.schema.json`, property `evaluation_set`) and the
reference text says it "supplies the evidence for objective measurements and promotion decisions"
(`docs/reference/language.md`, "Evaluation Set"). One name serves two jobs, the data a search looks at and the
data the gate judges on, and nothing in a module, a bundle or the gate tells the two apart. Consequences:

- A module author cannot write down which examples are kept aside. The separation lives in a file convention
  outside the module, so a reviewer cannot check it from the module.
- A bundle measured on the tuning examples is accepted by `tvl-ci-gate` exactly like one measured on a kept-aside
  set. The gate's `n` then counts examples the search has already fitted, which is the flattering score the book
  warns about.
- Nothing lets a tool detect that "the evaluation set" quietly changed between exploration and judgment.

This RFC lets a module declare a holdout, defines what it means for exploration and for the gate, and makes the
gate refuse evidence that is not on it.

## 2. Design

### 2.1 Syntax

`evaluation_set` gains one optional key, `holdout`:

```yaml
tvl_version: "1.6"
evaluation_set:
  dataset: support-tickets/tuning-v3      # what exploration may look at
  seed: 2025
  holdout:
    dataset: support-tickets/holdout-v1   # what the promotion gate judges on
    digest: "sha256:3b5d...(64 hex)"      # optional content identity
```

`holdout` is a closed mapping with:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `dataset` | non-empty string | yes | identifier or URI of the held-aside evaluation data, same form as `evaluation_set.dataset` |
| `seed` | integer | no | seed for reproducible ordering or sampling of the holdout, same meaning as `evaluation_set.seed` |
| `digest` | `sha256:` followed by 64 lowercase hex digits | no | identity of the holdout's content, so a bundle can show it was measured on exactly this data |

A module with no `holdout` is unchanged in meaning (§3).

### 2.2 Roles

Evidence has one of two **roles**:

- `tuning`: observations the search may use to choose candidates. The data named by `evaluation_set.dataset`.
- `holdout`: observations on `evaluation_set.holdout`. Never available to the search.

When `holdout` is declared, `evaluation_set.dataset` is the **tuning set** and `holdout.dataset` is the **gate
set**. When it is not declared, there is one set, no role is checked, and the text of 1.5 applies.

### 2.3 Measurement bundle binding

The measurement bundle (`spec/grammar/tvl-measurement.schema.json`, closed at the root) gains one optional key:

```yaml
evaluation:
  role: holdout                      # tuning | holdout
  dataset: support-tickets/holdout-v1
  digest: "sha256:3b5d..."           # optional
```

### 2.4 Gate behaviour

If the module declares `holdout`, `tvl-ci-gate` evaluates a decision only when both the incumbent bundle and the
candidate bundle satisfy all of:

1. `evaluation` is present (else `evidence_binding_missing`);
2. `evaluation.role` is `holdout` and `evaluation.dataset` equals `holdout.dataset` (else `evidence_not_on_holdout`);
3. if the module declares `holdout.digest`, `evaluation.digest` is present and equal (else `holdout_digest_mismatch`);
   if the module declares none and both bundles carry a digest, the two digests are equal (else
   `holdout_digest_mismatch`).

Failing any condition is **not promotion-ready**: the gate prints the code, returns no decision and exits 2, the
same class as `missing_chance_counts` (`docs/reference/language.md`, "Promotion Policy"). It is never `Promote`.
`Reject` and `NoDecision` keep their meaning for evidence that is on the holdout.

If the module declares no `holdout`, `evaluation` is read when present and has no effect on the decision.

### 2.5 Interaction with `promotion_policy`

- `alpha`, `adjust`, `min_effect`, `tie_breakers`: unchanged. The sample sizes `n` in the tests are the holdout's.
- `chance_constraints`: `chance_outcomes` are counts on the same bundle, hence on the holdout. A chance check on
  tuning counts is never a gate input when a holdout is declared.
- Promotion monitors (RFC 0003, source `evaluation_set`): they read the gate set. With a holdout declared, a
  promotion monitor's evidence is the holdout's. Monitors with other sources are unaffected.
- The incumbent is measured on the same holdout as the candidate. Both are compared on one gate set, which the paired test of §9.4
  already presupposes ("same evaluation instances").

### 2.6 Exploration

A search procedure conforms to a declared holdout only if every observation it consumes has role `tuning`. This
is an obligation on the runtime, outside the static semantics (§4). TVL cannot see inside a search, so the
obligation is testable only through records: a run report that lists the role of each trial's evidence (see RFC 0010
if accepted, §5) is checked for `holdout_used_in_exploration`.

### 2.7 Lints and diagnostics

| Code | Severity | When |
|---|---|---|
| `holdout_same_dataset` | error | `holdout.dataset` equals `evaluation_set.dataset` after trimming whitespace |
| `holdout_digest_malformed` | error | `digest` does not match `^sha256:[0-9a-f]{64}$` (the schema pattern; the lint gives the specific code, as for `tvl_version`) |
| `construct_version_required` | error | `holdout` present and `tvl_version` absent |
| `declared_version_below_constructs` | error | `holdout` present and `tvl_version` is a number, not a string, or below `"1.6"` (existing code) |
| `holdout_removed` | error (`tvl-compose`) | an overlay removes `holdout` that the base declares |
| `evidence_binding_missing`, `evidence_not_on_holdout`, `holdout_digest_mismatch` | gate, not promotion-ready | §2.4 |
| `holdout_used_in_exploration` | run-report check | a trial of the run consumed evidence with role `holdout` |

`construct_version_required` is the code for "a construct of TVL 1.6 appears without a `tvl_version`". Whichever
of the RFCs of this series is accepted first introduces it; the others reuse it.

### 2.8 What TVL does not check

TVL cannot see the content of the two datasets. `holdout_same_dataset` catches the same identifier; it does not
prove the two sets are disjoint. Disjointness is a claim of whoever declares the module, as the existing text
already says of environment bindings ("TVL does not check that"). A `digest` makes the claim auditable: a
different set has a different digest.

### 2.9 Grammar diff

`spec/grammar/tvl.schema.json`, property `evaluation_set` (the mirror in `editor_shared/vscode/schemas/` stays
byte-identical):

```diff
   "evaluation_set": {
     "type": "object",
     "additionalProperties": false,
     "required": ["dataset"],
     "properties": {
       "dataset": { "type": "string" },
-      "seed": { "type": "integer" }
+      "seed": { "type": "integer" },
+      "holdout": {
+        "type": "object",
+        "additionalProperties": false,
+        "required": ["dataset"],
+        "description": "Evaluation data kept aside from exploration; the promotion gate judges on it.",
+        "properties": {
+          "dataset": { "type": "string", "minLength": 1 },
+          "seed": { "type": "integer" },
+          "digest": { "type": "string", "pattern": "^sha256:[0-9a-f]{64}$" }
+        }
+      }
     }
   }
```

`spec/grammar/tvl-measurement.schema.json`, new optional root property:

```diff
+    "evaluation": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["role", "dataset"],
+      "properties": {
+        "role": { "enum": ["tuning", "holdout"] },
+        "dataset": { "type": "string", "minLength": 1 },
+        "digest": { "type": "string", "pattern": "^sha256:[0-9a-f]{64}$" }
+      }
+    },
```

`spec/grammar/tvl.ebnf`: `evaluation_set = rec("dataset": string, ["seed": integer], ["holdout": holdout])`
and `holdout = rec("dataset": string, ["seed": integer], ["digest": digest])` (production names to follow the
file's existing style).

## 3. Compatibility

A conservative extension. Every valid TVL 1.5 module has no `holdout`; its meaning, diagnostics and gate decisions
are unchanged. `evaluation` in a bundle is optional and ignored by modules without a holdout. A 1.5 reader meets an
unknown key under `evaluation_set` or at the bundle root, and the closed schemas reject it (`schema_error`),
so an old reader refuses the new construct instead of silently ignoring a holdout. The overlay table in
`docs/reference/language.md` lists `evaluation_set.dataset` and `seed` as unchecked, "an overlay may point at an
easier evaluation set"; that remains true. Only removing a declared holdout is newly checked.

## 4. Semantics and proofs

Add to formal semantics §2.9:

```
Digest        ::= "sha256:" HexString64
Holdout       ::= { dataset: String, seed?: Integer, digest?: Digest }
EvaluationSet ::= { dataset: String, seed?: Integer, holdout?: Holdout }
```

New paragraph for §9.7 (after Definition 9.11):

**Definition 9.12 (Evidence roles and the gate set).** An evidence record `Y` carries a binding
`ev(Y) = (role, dataset, digest?)` when its bundle has `evaluation`, and no binding otherwise. For a module `M`
with `evaluation_set.holdout = H`, the gate set is `G(M) = H`; `OnGate(Y, M)` holds iff `ev(Y)` is defined, `role = holdout`,
`dataset = H.dataset`, and (`H.digest` defined implies `digest = H.digest`). For a module without a holdout,
`OnGate(Y, M)` holds for every `Y`.

**Definition 9.13 (Promotion with a holdout).**

```
PromoteH(c_cand, c_inc, Y_cand, Y_inc, M) ⟺
    OnGate(Y_cand, M) ∧ OnGate(Y_inc, M) ∧ SameDigest(Y_cand, Y_inc, M)
  ∧ Promote(c_cand, c_inc, Y_cand, Y_inc, M)
```

When `OnGate` or `SameDigest` fails the gate has no decision (the evidence is not promotion-ready), which is not
`Reject`, `NoDecision` or `Error`.

**Proposition 9.5 (Conservative extension).** If `M` has no holdout, `PromoteH = Promote`.
Proof: `OnGate` is true by definition and `SameDigest` is vacuous.

**Proposition 9.6 (No promotion from tuning evidence).** If `M` has a holdout and `ev(Y_cand).role = tuning`, then
`PromoteH` is false. Immediate from Definition 9.12. This is the guarantee that the book's advice becomes checkable.

The exploration obligation of §2.6 is a statement about runtimes, in the same class as §12's evaluator-profile
obligations; it is not a theorem of the static core. The Lean proofs (`proofs/TVL/Gate.lean`) cover the gate
decision on given evidence; Definition 9.13 adds a premise on the evidence's provenance that the proofs do not
model. This RFC states that gap instead of claiming a mechanized result; the existing `outside_proved_subset`
info diagnostic does not need to fire for it, since the gate decision itself is unchanged.

## 5. Conformance

Cases to add, registered in `conformance/expected/results.json`:

| Case | Input | Expected |
|---|---|---|
| `gate/holdout-on-holdout.yml` | module with holdout; both bundles `role: holdout`, matching dataset; a clear win | `Promote` |
| `gate/holdout-tuning-evidence.yml` | same win, candidate bundle `role: tuning` | not promotion-ready, `evidence_not_on_holdout` |
| `gate/holdout-wrong-dataset.yml` | `role: holdout`, a different dataset id | `evidence_not_on_holdout` |
| `gate/holdout-binding-missing.yml` | holdout declared, no `evaluation` in the incumbent bundle | `evidence_binding_missing` |
| `gate/holdout-digest-mismatch.yml` | module digest set; candidate carries another | `holdout_digest_mismatch` |
| `gate/holdout-absent-unchanged.yml` | no holdout; bundles with arbitrary `evaluation` | the same decision as without `evaluation` |
| `lint/holdout-same-dataset.yml` | `holdout.dataset` equals `dataset` | `holdout_same_dataset` |
| `lint/holdout-version.yml` | holdout without `tvl_version`; and with `"1.5"` | `construct_version_required`; `declared_version_below_constructs` |
| `compose/holdout-removed.yml` | overlay removes the base's holdout | `holdout_removed` |
| `runtime/run-report-holdout-use.yml` | (needs RFC 0010) a trial lists role `holdout` | `holdout_used_in_exploration` |

Also: schema sync (`tests/test_editor_schema_sync.py`), `tvl-validate` accepts the book's chapter 6 module unchanged.

## 6. Alternatives considered

1. **`splits` with named roles (`tuning`, `validation`, `holdout`) inside one dataset.** More expressive, but the
   language would have to define how examples are partitioned (by id, by seed, by fraction), and the module could
   not tell whether the partition was honoured. A separately named dataset puts that burden where it already lives
   today, with the dataset's owner, and keeps the check to identifiers and digests.
2. **Rename `evaluation_set` to `tuning_set` and make the holdout the evaluation set.** Cleaner words, but it
   changes the meaning of every existing module. Rejected by the conservative-extension rule.
3. **A lint only, no gate behaviour.** A lint cannot see bundles. The harm happens at the gate, so the gate must
   refuse.
4. **Make the gate return `Error` for tuning evidence.** `Error` is reserved for an undefined check (`zero_trials`).
   Wrong-set evidence is missing evidence, the class of `missing_chance_counts`.

## 7. Open questions

1. Should `evaluation_set` also take a `digest` for the tuning set, so exploration evidence is as bound as holdout
   evidence? (Proposed: yes, later, through the space-and-evidence digest RFC if it is accepted.)
2. Reusing one holdout for many gate looks inflates error (book chapter 6, "A reused holdout"). Should a module be
   able to cap the number of looks (`holdout.max_looks`), with the count carried in the bundle? This needs a
   record that outlives one gate run, so it is deferred here.
3. Is `construct_version_required` the right shape, or should the existing `runtime_version_required` be
   generalised?
4. Should the incumbent be allowed to be measured earlier on the same holdout, or must both bundles come from one
   evaluation pass? This RFC requires only the same dataset and digest.
