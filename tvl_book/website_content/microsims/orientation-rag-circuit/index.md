---
hide:
  - toc
---

# Orientation RAG · Analog Circuit Lab

<iframe src="./main.html" height="560px" scrolling="no" style="width: 100%; border: none; overflow: hidden;"></iframe>

[Run the Orientation RAG MicroSim](./main.html){ .md-button .md-button--primary }
[Download the Presets JSON](./microsim_presets.json){ .md-button }

This lab reimagines a TVL spec as an analog circuit. It is a toy model: each slider is a knob of the simulation, in
the spirit of a tuned variable, not a variable read from a TVL module.

- **Retriever Top K** → intake resistor; higher values enrich context but add latency and cost.
- **Rerank Weight** → amplifier gate; raises answer quality and lowers simulated latency. It has no cost term in
  this model.
- **Response Tokens** → output capacitor; longer responses add latency and cost.

The read-outs come from fixed toy formulas in `app.js` (`k` = Top K, `tokens` = Response Tokens, `weight` = Rerank
Weight):

| Meter | Formula |
|-------|---------|
| Latency Gauge (ms) | `480 + 3*k + 0.45*tokens - 50*weight` |
| Cost Meter (USD) | `0.00018*k + 0.00052*tokens + 0.005` |
| Quality Score | `70 + 45*weight + 12*k/64 - penalty(latency)`, clamped to 20–99 |

Warnings light up when violated:

- latency `<= 800 ms`
- cost `<= $0.12`
- `rerank_weight >= 0.3` whenever `retriever_top_k >= 40`

Only the last one has the shape of a TVL structural constraint (a rule over knobs). The first two limit simulated
outcomes; in a TVL module such limits belong in objectives or chance constraints (rules that bound how often a
measured outcome may violate a threshold, checked with stated confidence from evaluation evidence).

Use the preset buttons to replay three scenarios. The bundled `microsim_presets.json` sets the same values as the
built-in presets in `app.js`:

1. **Baseline** – the starting slider positions.
2. **Latency Spike** – Top K 48, Rerank Weight 0.35, Response Tokens 384: latency pressure rises.
3. **Budget Shift** – Top K 24, Rerank Weight 0.55, Response Tokens 512: richer answers, as if the budget had
   relaxed. The cost limit itself stays at $0.12.

To regenerate `microsim_presets.json`, run `tvl-microsim-bridge path/to/spec.yml` (add `-o` to choose another output
file; by default it overwrites this lab's presets file, and `--dry-run` prints instead), then refresh the page. The
page binds three knobs to sliders: `retriever_top_k`, `rerank_weight` and `response_tokens`, also accepted in their
camelCase forms `retrieverTopK`, `rerankWeight` and `responseTokens`. Other keys have no effect. A preset in that
file replaces the built-in preset of the same name, so a preset without any of these keys leaves the sliders
unchanged.

!!! warning "Known gap in TVL 1.5"
    The bridge reads a legacy `configuration_space` block, not `tvars`. On a current TVL module it emits empty
    defaults, sliders, and presets.
