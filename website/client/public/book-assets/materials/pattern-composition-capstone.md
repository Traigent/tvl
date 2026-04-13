## Capstone Scenario

Design a governed workflow for a customer-support agent that must:

- answer ordinary FAQ requests cheaply
- escalate harder requests to a stronger reasoning path
- stay within a clear latency and budget story

You may combine patterns, but every added controller must earn its place.

## Scenario Constraints

Use these numbers when justifying your scaffold choice, TVAR ranges, and narrowing plan:

| Dimension | Value |
| :--- | :--- |
| daily ticket volume | ~2,000 requests |
| FAQ fraction | ~70% answerable from a known knowledge base |
| FAQ latency ceiling | `p95 <= 4 seconds` |
| escalation latency ceiling | `p95 <= 12 seconds` |
| monthly model budget | $800 |
| escalation fallback | human review within 30 minutes when the agent is uncertain |

## Why This Capstone Matters

This capstone checks whether you can move past isolated pattern pages and compose a bundle that still behaves like a
governed system. The real test is not whether the workflow sounds sophisticated. The test is whether another engineer
could explain, evaluate, narrow, and safely ship it under explicit traffic, latency, and budget conditions.

## Capstone Output

- One multi-pattern workflow proposal with explicit tuned variables.
- One production-safe narrowing plan for staging, production, and rollback.
- One release brief describing the evidence bundle and manifest shape required for promotion.

## Step 1: Choose The Base Scaffold (~10 min)

Start from one scaffold that already works on its own.

Examples:

- contextual batching for repeated FAQ traffic
- routed expertise for specialist escalation
- map-reduce synthesis for multi-document answers

Write one sentence explaining why this scaffold is the base rather than an add-on.

## Step 2: Add At Most One Controller (~10 min)

Add one bounded controller only if it solves a real weakness in the base scaffold.

Good reasons:

- reduce obvious failure cases
- improve quality on a known hard slice
- make the system more reviewable at promotion time

Weak reasons:

- the pattern sounds advanced
- another team used it
- it improved a demo without a clear mechanism

## Step 3: Describe The Governed Surface (~15 min)

List:

- the TVARs exposed by the bundle
- one structural rule that keeps the bundle coherent
- one operational precondition that must hold before the study or rollout proceeds

A structural rule constrains how TVARs relate to each other.
An operational precondition constrains what must be true of the environment before the bundle runs.

## Step 4: Write The Safe Narrowing Plan (~25 min)

Describe the difference between:

1. exploratory bundle
2. staging bundle
3. production bundle
4. rollback bundle

This extends the safe-narrowing idea from the composition lessons: the production version should normally expose a
smaller, easier-to-review surface than the exploratory one. For the rollback tier, describe the configuration state
the system returns to, not just the act of reverting.

## Step 5: Draft The Release Brief (~25 min)

Your release brief should answer:

- what changed
- which evaluation set was used
- which outcomes justified promotion
- which manifest fields would help replay the decision later
- what condition would trigger rollback

## Worked Example

Different domain, same reasoning pattern. Do not copy it directly.

**Domain:** internal code-review assistant.

1. **Base scaffold:** routed expertise. Fast reviews go to a cheaper model; hard logic reviews go to a stronger one.
2. **Added controller:** confidence-gated escalation to human review when the strong model is uncertain.
3. **TVARs:** `routing_threshold`, `confidence_gate`, `fast_model_id`, `strong_model_id`.
   **Structural rule:** `confidence_gate` must be `>= routing_threshold`.
   **Operational precondition:** the evaluation slice must contain at least 50 logic-review samples.
4. **Narrowing:** exploratory exposes all four TVARs; staging locks model IDs and narrows `routing_threshold`;
   production locks `confidence_gate`; rollback returns to the last promoted staging snapshot.
5. **Promotion evidence:** logic-review success rate `>= 85%`, false escalation rate `<= 10%`, latency `p95 <= 8 seconds`.

## Reviewer Checklist

A strong submission should meet each of these:

- Is the scaffold-versus-controller split clear?
- Does each exposed TVAR have a reason to exist?
- Is the production surface narrower than the exploratory one?
- Are promotion evidence and rollback conditions explicit?
- Could another engineer replay the decision from the brief?

## Final Check

Before you submit, ask:

1. Did I justify this design against the actual scenario constraints?
2. Could another engineer reject one of my TVARs as unjustified?
3. Is my rollback state concrete enough to execute without rethinking the whole design?
