---
hide:
  - toc
---

# Orientation RAG · Analog Circuit Lab

<iframe src="./main.html" height="560px" scrolling="no" style="width: 100%; border: none; overflow: hidden;"></iframe>

[Run the Orientation RAG MicroSim](./main.html){ .md-button .md-button--primary }
[Download the Presets JSON](./microsim_presets.json){ .md-button }

This lab reimagines a TVL spec as an analog circuit. Each slider changes a “component” that maps directly to a
governed tuning variable:

- **Retriever Top K** → intake resistor; higher values enrich context but add load.
- **Rerank Weight** → amplifier gate; boosts answer quality at a cost.
- **Response Tokens** → output capacitor; longer responses draw more energy.

The circuit read-outs mirror the objectives of the example TVL module:

| Meter | TVL Metric | Formula |
|-------|------------|---------|
| Latency Gauge | `latency` (minimize) | `base + k*3 + tokens*0.5 - weight*40` |
| Cost Meter | `cost_usd` (minimize) | `0.0002*k + 0.0005*tokens` |
| Quality Score | `faithfulness` (maximize) | `base + weight*45 - penalty(latency)` |

Constraints light up when violated:

- `latency <= 800 ms`
- `cost_usd <= 0.12`
- `rerank_weight >= 0.3` whenever `retriever_top_k >= 40`

Use the preset buttons to replay three scenarios:

1. **Baseline** – The starting configuration.
2. **Latency Spike** – A latency increase that pushes the circuit toward a constraint violation.
3. **Budget Shift** – A change of cost budget that shifts the trade-off between objectives.

The `microsim_presets.json` file matches the format emitted by
`python -m tvl_tools.microsim_bridge`. Drop updated specs in your repo, run the bridge,
and the page reloads with fresh scenarios.
