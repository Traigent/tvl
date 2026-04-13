## What You Will Produce

- One working TVL module based on the Chapter 2 starter example.
- One short explanation of how the `tvars`, `objectives`, and `promotion_policy` blocks work together.
- One paragraph connecting a microsim behavior to a structural constraint you would encode in TVL.

## Why This Lab Matters

This lab is meant to make one idea tangible fast: TVL is not just a config format. It is the place where a team
states what may change, how candidates are judged, and what evidence is required before shipping. By the end, you
should be able to read one small TVL file, validate it without guessing, and explain why one runtime trade-off
deserves a structural rule instead of an ad hoc fix later.

## Lab Steps

### Part 1. Read the Contract (~10 min)

Use [Minimal Working Spec](/book/chapter/getting-fluent-in-tvl/section/minimal-working-spec) as the reference page,
but do the first pass here before you leave this material.

Starter shape:

```yaml
tvl:
  module: book.quickstart.simple_rag_qa

environment:
  snapshot_id: "2025-01-20T00:00:00Z" # the snapshot this study is anchored to
  bindings:
    retriever_index: campus-faq-v1
    llm_gateway: us-east-1

evaluation_set:
  dataset: s3://datasets/campus-rag/dev.jsonl # the shared workload used to compare candidates
  seed: 2025

tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4o-mini", "claude-3-haiku"] # what the system may change
  - name: retriever.k
    type: int
    domain:
      set: [3, 5, 8]
  - name: temperature
    type: float
    domain:
      range: [0.0, 0.6]
      resolution: 0.1

constraints:
  structural:
    - when: "retriever.k = 8"
      then: "temperature <= 0.3"

objectives:
  - name: answer_accuracy
    metric_ref: metrics.answer_accuracy.v1
    direction: maximize # what counts as better
  - name: latency_p95_ms
    metric_ref: metrics.latency_p95_ms.v1
    direction: minimize

promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  adjust: holm
  min_effect:
    answer_accuracy: 0.01
    latency_p95_ms: 50 # what evidence is required before shipping
```

- Copy the starter example into a working file.
- Highlight the lines that answer:
  - What can change?
  - What counts as better?
  - What evidence is required before shipping?

Checkpoint: if you cannot point to the exact lines for those three questions, stay with this part before moving on.

### Part 2. Validate the Shape (~15 min)

Use [Validation Warm-Up](/book/chapter/getting-fluent-in-tvl/section/validation-warm-up) while doing this part.

- Run `tvl-validate` on the file.
- Intentionally break one required field, rerun validation, and note what failed.
- Restore the file and rerun until it passes again.

Success signal:

- one run fails for a reason you can name clearly
- the repaired file passes again
- you can explain whether the failure was about missing structure or invalid content

### Part 3. Connect the Spec to System Behavior (~15 min)

Use [Analog Circuit Lab · Explore the Knobs](/book/chapter/getting-fluent-in-tvl/section/analog-circuit-lab-explore-the-knobs).

- Open the Orientation RAG microsim and start from the **Baseline** preset.
- Raise `retriever_top_k` toward `56` and watch the latency gauge.
- Then keep `retriever_top_k >= 40` and drag `rerank_weight` below `0.3`.
- Stop when the red guardrail or warning appears.
- Write one candidate rule that would prevent wasted exploration.

What to look for:

- broader retrieval pushes latency up fast
- some combinations trigger warnings even before you ask whether quality improved
- the useful lesson is not "this slider is bad"; it is "this region of the search space should be ruled out early"

Example deliverable:

> Candidate rule: if `retriever_top_k >= 40`, require `rerank_weight >= 0.3`.
> Justification: in the microsim, broad retrieval with weak reranking made latency worse while also raising the
> warning state, so those trials would waste budget without a good quality story.

## Before You Finish

- Passing validation output.
- A one-page annotated spec.
- One proposed constraint with a short justification.

## Debrief Questions (~5 min)

- Which top-level block felt least intuitive at first?
- What mistake would `tvl-validate` catch quickly, and what mistake would it miss?
- Which microsim observation convinced you that constraints belong in the contract?
