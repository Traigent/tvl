# RFC 0009 — Optional Objective Weights: a search preference that never reaches the gate

| | |
|---|---|
| **Status** | **DRAFT** — not accepted; syntax, codes and meaning may change before acceptance |
| **Target language version** | TVL 1.6 (conservative extension of 1.5) |
| **Tracking** | to be linked when a pull request exists |
| **Builds on** | the promotion gate of formal semantics §9 (ε-Pareto, Definitions 9.3, 9.5, 9.11) |
| **Companion** | `formalization/tvl-formal-semantics.md` §2.7 (objectives), §9; `docs/reference/language.md` ("Objectives", "Promotion Policy") |
| **Conformance** | `conformance/cases/lint/objective-weight-*.yml`, `conformance/cases/gate/weights-invariance.yml` (§5) |

Existing-text handles are repository paths at `origin/main` commit `674d9aa2a4340115600e837ac28d8538d2b57867`.
Number 0009 is a proposal; the number is confirmed in review.

## 1. Motivation

An `Objective` is closed: `name`, optional `metric_ref`, and either `direction` or `band`, with
`additionalProperties: false` (`spec/grammar/tvl.schema.json`, `$defs/Objective`). A module can say that quality
is maximized and cost is minimized. It cannot say how much one matters against the other.

That omission is deliberate in one place and a missing piece in another. Promotion is ε-Pareto, not a weighted sum:
a candidate is promoted only if it is no worse than the incumbent on any objective beyond that objective's ε and
better on at least one (Definition 9.3, Definition 9.11, `docs/reference/language.md` "Promotion Policy"). Weights
have no role there, and this RFC keeps it so.

But the same module is also read by whoever searches the space. Between exploration and the gate, someone has
to decide which of the candidates seen so far is "best so far", which to explore next, and which to put forward
to the gate. With two or more objectives that ranking needs a statement of relative importance. Today that
statement lives outside the module (in a tool's own configuration), so two tools reading one module can rank the
same trials differently and the module's author cannot write the intent down. Tools that already accept
weights for their own searches cannot express them in a document that validates.

## 2. Design

### 2.1 Syntax

A directional objective gains an optional `weight`:

```yaml
objectives:
  - name: quality
    direction: maximize
    weight: 3
  - name: cost_usd
    direction: minimize
    weight: 1
  - name: reply_length_tokens
    band: {target: [50, 200], test: TOST, alpha: 0.05}   # no weight: a band is an acceptance test
```

`weight` is a positive finite number. The schema adds the key to both `Objective` branches; the banded branch's
presence is rejected by a lint so the diagnostic is specific (§2.4).

### 2.2 Meaning: weights rank, they do not decide

**Weights are used by exploration only. They are not an input of the promotion gate.**

For a module whose directional objectives all carry weights `w_i > 0`, define the **relative weights**
`ŵ_i = w_i / Σ_j w_j` over the directional objectives. A runtime that ranks trials by one scalar during
exploration SHOULD rank by a weighted sum of direction-normalized, dimensionless objective values with these
relative weights. The module does not say how raw values (an accuracy in [0,1], a cost in dollars) are made
dimensionless; that normalisation is a property of the evaluator and the search, and it is the runtime's to
state. A scalar ranking without a stated normalisation is not wrong, but it is not reproducible, so a runtime
that uses weights SHOULD disclose the normalisation it used next to the ranking (RFC 0010's run report has an
optional place for this, if accepted).

Why the gate does not read weights, from TVL's own text:

1. **Non-inferiority is per objective.** Promotion requires that no objective's inferiority test rejects its
   null after adjustment (§9.4, §9.7). A weighted sum lets a large gain on a heavily weighted objective offset a
   regression on another beyond its ε. The module's `min_effect` would no longer bound the regression the author
   accepts, which is the statement the statistical validation guide makes of it.
2. **The tests need per-objective evidence.** A bundle carries one `mean/std/n` or one `samples` list per
   objective (`spec/promotion-evidence-contract.md`). A test of a weighted sum needs the covariance between
   objectives, which the contract does not carry.
3. **`dominance` is a closed enum with one member.** `promotion_policy.dominance` is `epsilon_pareto`
   (`spec/grammar/tvl.schema.json`). Replacing it is a different RFC and a different proof burden.

So a candidate the weights rank first is not thereby promoted, and a candidate the gate promotes need not be the one the
weights rank first. That is the intended separation: weights express taste in search, ε-Pareto expresses what
may be released.

**Weight invariance.** Changing, adding or removing weights changes no gate decision on fixed evidence
(Proposition 9.8, §4). Weights also never break promotion ties: `tie_breakers` is unchanged.

### 2.3 Defaults

- No objective carries a weight: the module means what it meant in 1.5. A runtime that ranks by a scalar
  chooses its own rule, as today.
- Weights are all-or-none over the directional objectives. If some directional objective has a weight and another
  does not, the module is invalid (`partial_objective_weights`). TVL gives no implicit default weight, because a
  default of 1 beside a weight of 3 would silently pick a scale.
- A single directional objective with a weight is valid; its relative weight is 1.
- A banded objective has no weight (`weight_on_banded_objective`). A band is a pass/fail acceptance test, not a
  quantity to trade off.

### 2.4 Validation

| Code | Severity | When |
|---|---|---|
| `objective_weight_invalid` | error | `weight` is not a number, is zero or negative, NaN or an infinity (the schema rejects non-numbers; the lint reports the specific code, as for other numeric fields) |
| `partial_objective_weights` | error | at least one but not all directional objectives have a weight |
| `weight_on_banded_objective` | error | a banded objective has `weight` |
| `construct_version_required` | error | any `weight` present and `tvl_version` absent |
| `declared_version_below_constructs` | error | any `weight` present and `tvl_version` a number or below `"1.6"` (existing code) |

`construct_version_required` is shared with the other RFCs of this series (RFC 0008 §2.7 in this series); the first
one accepted introduces it.

### 2.5 Overlays

Weights are a preference, not a guarantee, so `tvl-compose` does not treat them as narrowing. They join the list
in `docs/reference/language.md` of fields that are "unchanged freely, so review them by hand". An overlay may
change, add or drop weights; dropping them from some objectives only makes the module hit `partial_objective_weights`.

### 2.6 Grammar diff

`spec/grammar/tvl.schema.json`, `$defs/Objective`, both branches of the `oneOf`:

```diff
   {
     "required": ["name", "direction"],
     "additionalProperties": false,
     "properties": {
       "name": { "type": "string" },
       "metric_ref": { "type": "string", "minLength": 1 },
-      "direction": { "enum": ["maximize", "minimize"] }
+      "direction": { "enum": ["maximize", "minimize"] },
+      "weight": {
+        "type": "number",
+        "exclusiveMinimum": 0,
+        "description": "Relative importance in exploration ranking. Not read by the promotion gate."
+      }
     }
   },
   {
     "required": ["name", "band"],
     "additionalProperties": false,
     "properties": {
       "name": { "type": "string" },
       "metric_ref": { "type": "string", "minLength": 1 },
+      "weight": { "type": "number", "description": "Always an error (weight_on_banded_objective); accepted by the schema so the lint can give the specific code." },
       "band": { "...unchanged..." }
     }
   }
```

The cross-objective rule (`partial_objective_weights`) is a lint, as `missing_min_effect` is; JSON Schema cannot
express it. `tvl.ebnf`: `std_objective = rec("name": ident, "direction": direction, ["weight": number], ["metric_ref": string])`.

## 3. Compatibility

A conservative extension. A 1.5 module has no `weight`; its meaning, lints and gate decisions are unchanged. A
1.5 reader meets an unknown key in a closed `Objective` and refuses the module, as it refuses any new construct.
A module that adds weights changes no `Promote`, `Reject`, `NoDecision` or `Error` on any bundle.

## 4. Semantics and proofs

Add to formal semantics §2.7:

```
StdObjective  ::= { name: Ident, direction: Direction, weight?: PosNumber }
BandObjective ::= { name: Ident, band: {...} }              (* no weight *)
Weighted(O)   ⟺  every StdObjective in O has weight
Valid(O)      adds:  ¬(some StdObjective has weight ∧ some StdObjective has none)
```

**Definition 9.14 (Relative weights).** For `Weighted(O)`, `ŵ_i = w_i / Σ_{j ∈ Std(O)} w_j`, so
`Σ ŵ_i = 1` and every `ŵ_i ∈ (0, 1]`.

**Definition 9.15 (Weighted ranking, informative).** Given a normalisation `N` mapping each directional
objective's value into a dimensionless scale, `Rank_{N,ŵ}(y) = Σ_i ŵ_i · σ(d_i) · N_i(y_i)`. TVL defines the form;
`N` belongs to the runtime. Nothing in §§9.4–9.11 refers to `Rank`.

**Proposition 9.8 (Weight invariance of the gate).** For modules `M` and `M'` that differ only in `weight`
fields, and any evidence, `Promote(·, M) = Promote(·, M')` and every other gate decision is equal.
Proof: `weight` is not read by `StatDominates`, `Valid`, `Acceptable` or the decision logic of §9.7; those are
functions of `directions`, `min_effect`, `alpha`, `adjust`, `chance_constraints`, `bands` and the evidence.

**Proposition 9.9 (Soundness of ε-Pareto promotion is preserved).** Every guarantee proved or claimed for §9.11 holds
unchanged for modules with weights, by Proposition 9.8. In particular the non-inferiority guarantee of §9.4 is not
weakened, which a weighted promotion rule would do (§2.2, item 1).

The Lean proofs of the gate are unaffected, since the construct does not enter them. The ranking of §2.2 is
outside the formal semantics and outside the proved subset.

## 5. Conformance

| Case | Input | Expected |
|---|---|---|
| `lint/objective-weight-valid.yml` | two directional objectives with weights 3 and 1, `tvl_version: "1.6"` | no diagnostic |
| `lint/objective-weight-nonpositive.yml` | weight 0; weight -1 | `objective_weight_invalid` |
| `lint/objective-weight-partial.yml` | weight on one of two directional objectives | `partial_objective_weights` |
| `lint/objective-weight-band.yml` | weight on a banded objective | `weight_on_banded_objective` |
| `lint/objective-weight-version.yml` | weight, no `tvl_version`; weight, `"1.5"` | `construct_version_required`; `declared_version_below_constructs` |
| `gate/weights-invariance.yml` | one module with weights 3:1, one with 1:3, one with none; the same incumbent and candidate bundles where the candidate regresses cost beyond ε and improves quality | the same decision in all three (`Reject` or `NoDecision`, never `Promote` through weights) |
| `gate/weights-do-not-promote.yml` | a large weighted gain on one objective and a regression beyond ε on another | the unweighted decision, whatever the weights |

## 6. Alternatives considered

1. **Weights in promotion (a weighted-sum gate).** Rejected for the three reasons in §2.2. It would need a
   different `dominance` value, an evidence contract carrying covariances, and new proofs. It could be a later RFC
   that adds a second `dominance` member and makes its different guarantee explicit; this RFC does not block it.
2. **Weights outside TVL, in the tool.** What happens today. Two tools reading one module cannot agree, and a
   reviewer cannot see the intent.
3. **A scalarisation block (`scalarization: {method: weighted_sum, normalization: ...}`).** More complete, but it
   would put an evaluator concern (normalisation) into the language. The module states importance; the
   runtime states how it made values comparable.
4. **Default weight 1 for omitted weights.** Rejected in §2.3: it picks a scale silently.
5. **Weights on bands.** A band either passes or it does not; a weight would imply a trade-off that the TOST test
   does not offer.

## 7. Open questions

1. Should `weight` be allowed to be an integer-ratio string or a decimal string, to avoid float parsing differences
   across tools? `min_effect` uses plain numbers today, so this RFC does too.
2. Should the module name a normalisation by id (optional `weights_normalization`)? Deferred, §6 item 3.
3. Should weights participate in the identity of a module for evidence reuse (a possible future module-identity proposal)? Proposed: no,
   because the gate ignores them (Proposition 9.8); a digest that changed with weights would invalidate evidence
   that remains valid.
