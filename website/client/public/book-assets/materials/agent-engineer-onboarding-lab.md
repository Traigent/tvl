## Why This Lab Matters

This lab trains the move that most teams skip. They can name a pattern, but they cannot yet turn that pattern into a
small governed surface that another engineer can review, tune, and promote safely.

## What You Will Produce

- One candidate agent workflow described as a tuned-variable surface.
- A short rationale for which variables were included and which were excluded.
- A draft promotion loop describing budget, feedback, and evidence.

## Starter Scenario

You are reviewing a campus support assistant that currently uses a simple RAG flow:

1. retrieve FAQ passages
2. answer with one small model
3. return the final response

The team wants to make the workflow more agentic, but not by adding uncontrolled complexity. Your job is to restate
one candidate scaffold as a governed surface that a reviewer could tune, evaluate, and approve.

Pick one starting scaffold:

- contextual batching for repeated FAQ requests if you want the simplest first surface
- routed expertise with a lightweight judge if you want the clearest judge-and-aggregation example
- one reflection round before the final answer if you want a depth-scaling example

## Before You Start

Use the related lessons to refresh three distinctions:

- a pattern name is not yet a governed surface
- TVARs are the variables the system may actually tune
- promotion requires an explicit evidence story, not just a better demo

## Step 1: Translate The Pattern (~20 min)

Write 3-5 candidate TVARs for the scaffold you chose.

Good candidates usually change behavior in a meaningful way:

- number of experts or branches
- judge policy
- batching size
- reflection rounds

Bad candidates are often cosmetic or too implementation-specific:

- log level
- internal cache label
- variable names that never change system behavior

Running example at this step:

- routed expertise: `experts_to_run`, `judge_policy`, `reflection_rounds`, `prompt_style`
- contextual batching: `items_per_batch`, `ordering_policy`, `dedup_threshold`
- reflection: `reflection_rounds`, `critique_mode`, `stop_rule`

### Checkpoint

If you remove one TVAR and nothing important changes about quality, latency, cost, or reviewer confidence, it probably
does not belong in the surface.

## Step 2: Narrow The Surface (~15 min)

Cut your candidate list down to the smallest useful surface.

Use this remove-and-check protocol for each candidate TVAR:

1. Pretend this TVAR is locked to a default.
2. Write one sentence answering: what important trade-off disappears from the reviewer’s decision?
3. If you cannot answer clearly, cut the TVAR.
4. If two TVARs always move together, merge them or encode the relationship later with a structural rule.

Secondary check:

1. Which variables actually drive trade-offs?
2. Which variables can a reviewer explain and justify?
3. Which variables would be dangerous to expose without clear evidence?

Running example at this step:

- routed expertise: keep `experts_to_run`, `judge_policy`, `reflection_rounds`; cut `prompt_style`
- contextual batching: keep `items_per_batch`, cut cosmetic ordering variants unless they clearly change quality or latency
- reflection: keep `reflection_rounds` and `stop_rule`; cut critique variants you cannot yet justify

## Step 3: Add One Structural Rule And One Operational Precondition (~20 min)

Add:

- one structural rule over TVARs
- one operational precondition checked through `constraints.derived`

In TVL, operational preconditions are written under `constraints.derived` and reference the declared
numeric operating assumptions through `env.context.*`.

Example shape:

```yaml
tvars:
  - name: experts_to_run
    type: int
    domain:
      set: [1, 2, 3]
  - name: judge_policy
    type: enum[str]
    domain: ["best_score", "pairwise_compare"]

constraints:
  structural:
    - when: "experts_to_run = 3"
      then: "judge_policy = 'pairwise_compare'"
  derived:
    - require: env.context.daily_token_budget_remaining >= 5000
```

Running example at this step:

- routed expertise: if `experts_to_run = 3`, require a stronger judge policy
- contextual batching: if `items_per_batch >= 8`, require an ordering policy that preserves urgent items
- reflection: if `reflection_rounds = 2`, require a strict stop rule so depth stays bounded

### Checkpoint

The structural rule should restrict the search space. The operational precondition should check whether the current
environment snapshot makes the study or rollout feasible.

### Self-Check Before You Continue

- Can you point to one real trade-off for every remaining TVAR?
- Does your structural rule restrict the search space rather than describe a wish?
- Does your operational precondition depend on `env.context.*` rather than on observed runtime results?

## Step 4: Sketch The Evaluation And Promotion Loop (~15 min)

Write short answers to these prompts:

1. What evaluation set will compare candidate configurations fairly?
2. Which two outcomes matter most?
3. What evidence would make a reviewer comfortable promoting a new configuration?
4. What would trigger rollback?

Running example at this step:

- evaluation set: campus FAQ tasks where routing quality matters
- outcomes: answer accuracy and latency
- promotion evidence: manifest plus budget and rollback notes
- rollback trigger: quality gain disappears or latency budget breaks on the target slice

## Review Rubric

A strong submission:

- exposes a small surface with meaningful TVARs
- distinguishes structural rules from operational preconditions
- names an evaluation set instead of hand-waving “we would test it”
- gives a promotion and rollback story that another engineer could review
