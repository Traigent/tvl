## Scenario

Production latency spikes after a provider-side model change. A candidate hotfix overlay is available, but the team is unsure whether it is safe to promote immediately.

Incident packet:

- provider-side change happened 20 minutes ago
- FAQ latency moved from p95 3.8 seconds to p95 7.2 seconds
- the production budget and rollback manifest still exist
- a hotfix overlay was prepared under pressure and may or may not narrow the surface safely

Base spec fragment:

```yaml
tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4o-mini", "claude-3-haiku"]
  - name: max_tokens
    type: int
    domain:
      set: [256, 384, 512]

constraints:
  structural:
    - expr: "max_tokens <= 512"
  derived:
    - require: env.context.latency_budget_ms <= 4000
```

Candidate hotfix overlay:

```yaml
overrides:
  tvars:
    - name: model
      domain: ["gpt-4o-mini"]
    - name: max_tokens
      domain:
        set: [256, 384, 512, 1024]
```

Mock validation notes:

- `tvl-check-structural` on the base spec still passes
- `tvl-check-operational` reports `env.context.latency_budget_ms <= 4000` is currently false
- the hotfix overlay narrows the model choice but also widens one token limit silently

## Exercise Goals

- Identify the first artifacts you need before touching the rollout.
- Separate “the spec is malformed” from “the environment no longer satisfies the contract.”
- Decide whether to block, defer, hotfix, or roll back.

## Drill Flow

### Step 1. Triage the Failure (10 min)

- Did parsing, linting, or schema validation fail?
- Did structural satisfiability fail?
- Did an operational precondition fail because the environment changed?

<PredictionPrompt prompt="Before you inspect the overlay, predict the most likely failure class here: malformed overlay, structural contradiction, or operational precondition failure.">

The strongest first guess is operational precondition failure, because the incident starts with a provider-side latency
change rather than with a spec edit. The overlay may still be unsafe, but the first signal points to the environment.

</PredictionPrompt>

### Step 2. Inspect the Candidate Overlay (15 min)

- Which knobs are narrowed?
- Which risk bounds are tightened?
- Does anything in the overlay widen exposure silently?

Run the operator checks:

```bash
tvl-compose base-spec.tvl.yml hotfix.overlay.yml
tvl-validate composed-spec.tvl.yml
tvl-check-structural composed-spec.tvl.yml --json
```

What to notice:

- narrowing the model domain is a plausible hotfix move
- widening `max_tokens` to `1024` is not a safe narrowing move
- a hotfix overlay that silently widens exposure should not be promoted under pressure

### Step 3. Check the Audit Trail (10 min)

- Which composed spec and overlay were used?
- Which validation logs exist?
- Is there a promotion manifest with rollback instructions?

## Action Matrix

Use this rule of thumb for the decision:

| Evidence state | Action |
| :--- | :--- |
| overlay is malformed or widens exposure | block or defer |
| base spec is sound, but an operational precondition currently fails and the overlay narrows safely | hotfix may be justified |
| production is degraded and the overlay is unsafe or under-evidenced | roll back to the last approved state |

<KnowledgeCheck prompt="Why is this incident not solved by looking at structural validity alone?">

Because the base spec can remain structurally valid while the current environment no longer satisfies the operational
preconditions. Operators need both signals before deciding whether to hotfix or roll back.

</KnowledgeCheck>

## Debrief

Strong debrief answers should distinguish three things clearly:

- what failed in the environment
- what the overlay changed
- what artifact made the final decision auditable

- What signal should have prevented this surprise earlier?
- Which artifact saved the most time during the drill?
- What additional evidence would make you more confident next time?
