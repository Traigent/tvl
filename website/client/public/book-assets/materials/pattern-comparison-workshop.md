## Shared Scenario

Your team wants to improve a support workflow that currently answers one request at a time with a single model pass.
You have budget for only one serious next experiment. The choice is between:

- a breadth pattern such as contextual batching
- a depth pattern such as reflection
- a committee pattern such as routed expertise plus judge

The goal of this workshop is not to pick the flashiest pattern. The goal is to choose the one that deserves evidence
next.

## Why This Workshop Matters

Teams often argue about patterns by vibe, novelty, or whoever has the strongest opinion in the room. This workshop
forces the discussion back onto one shared decision plane: governed TVARs, concrete failure modes, and evidence worth
paying for.

## Workshop Output

- One comparison table covering at least three candidate patterns.
- A ranked shortlist of which scaffolds deserve budget on the next study plane.
- A failure-mode note describing what would make the leading choice non-deployable.

## Before You Start

Pre-work:

- skim the relevant pattern pages before the meeting if possible
- keep one shared decision plane for the whole workshop

Suggested group size:

- 3-5 people per group
- if the team is larger, split into groups and compare rankings in the debrief

Ground rule:

- if two patterns are being compared against different goals, stop and realign before continuing

Suggested timing:

- Step 1: 20 min
- Step 2: 10 min
- Step 3: 15 min
- Step 4: 15 min

## Step 1: Build The Comparison Table

Create one table with these columns:

| Pattern | Key TVARs (2-3) | Quality upside | Latency impact | Cost impact | Complexity | Explainability |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |

Use at least three pattern pages from the atlas.

To identify TVARs, list only the small set of variables the team would actually need to tune, not every field shown on
the pattern page.

## Step 2: Record The First Blocker

For each pattern, name the first failure mode that would stop you from promoting it even if the quality upside looked
promising.

Examples:

- batching harms tail latency for urgent requests
- reflection improves quality but breaks the latency budget
- judge-based committees are too expensive to evaluate at required volume

### Checkpoint

If two patterns are being compared on different goals, the workshop is drifting. Put them back on one shared decision
plane before ranking them.

## Step 3: Rank The Next Experiment

End with a short decision memo:

1. Which pattern should get budget first?
2. Which pattern is second choice?
3. What evidence would change your ranking?

## Step 4: Debrief The Ranking

Each group should answer:

1. Where did we disagree first?
2. Which blocker changed the ranking most?
3. Which pattern had the highest upside but the weakest evidence story?

## Facilitator Prompt

If the discussion becomes abstract, force the group back to TVL language:

- Which TVARs are we actually exposing?
- Which structural rules would we need?
- Which operational preconditions would block the study?
- Which promotion evidence would justify rollout?

## Worked Example

Suppose the team compares contextual batching, reflection, and routed expertise for a support workflow handling
roughly 2,000 requests per day.

Table excerpt:

| Pattern | Key TVARs | Quality upside | First blocker |
| :--- | :--- | :--- | :--- |
| Contextual batching | `items_per_batch`, `ordering_policy`, `dedup_threshold` | better shared context for repeated tickets | urgent tickets may violate tail-latency expectations |
| Reflection | `reflection_rounds`, `critique_mode`, `stop_rule` | better answers on hard cases | latency doubles too easily |
| Routed expertise + judge | `experts_to_run`, `routing_policy`, `judge_policy` | highest upside on specialist tickets | evaluation cost grows too fast at real traffic volume |

Ranking reasoning:

- contextual batching ranks first not because it has the highest upside, but because its blocker is cheap to measure
- reflection ranks second because the latency blocker is real but still testable
- routed expertise ranks third because the team cannot yet afford the evidence it would need
