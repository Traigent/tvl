# Hands-on Labs

These labs map the narrative chapters to runnable scripts in the `Traigent/examples` directory. Each lab
includes a short brief, how to launch it, and what to inspect afterwards. Enable mock mode (`TRAIGENT_MOCK_MODE=true`)
if you want to run them without API keys.

## Micro Lab · Orientation RAG Circuit

- **Concepts reinforced:** Chapter 2 (configuration anatomy), Chapter 3 (constraint guards), Chapter 5 (promotion evidence).
- **Entry point:** [`microsims/orientation-rag-circuit/index.md`](../microsims/orientation-rag-circuit/index.md)
- **How to explore:** Use the preset buttons to replay incidents, then adjust sliders to recover all constraints.
- **What to inspect:** Latency/cost/quality gauges, constraint badges, and the YAML snapshot that mirrors `params.yaml`.
- **Optional automation:** Regenerate presets with `tvl-microsim-bridge path/to/spec.yml`. In TVL 1.5 the bridge reads
  a legacy `configuration_space` block, not `tvars`, so a current TVL module yields empty presets.

## Lab 1 · Hello World RAG

- **Concepts reinforced:** Chapter 2 (spec anatomy), Chapter 3 (constraints via `use_rag` toggle).
- **Entry point:** `examples/core/hello-world/run.py`
- **Command:**
  ```bash
  cd Traigent
  TRAIGENT_MOCK_MODE=true python examples/core/hello-world/run.py
  ```
- **What to inspect:** The generated `.traigent_local` folder (mock mode) or `TRAIGENT_RESULTS_FOLDER` for
  manifests; the prompt template in `prompt.txt`; the evaluation dataset under `examples/datasets/hello-world/`.

## Lab 2 · Multi-Objective Tradeoff

- **Concepts reinforced:** Chapter 4 (patterns) and Chapter 5 (integration) with Pareto trade-offs.
- **Entry point:** `examples/core/multi-objective-tradeoff/run_openai.py`
- **Command:**
  ```bash
  cd Traigent
  TRAIGENT_MOCK_MODE=true python examples/core/multi-objective-tradeoff/run_openai.py
  ```
- **What to inspect:** Optimization summaries in the console, aggregated dataframes saved in the results
  folder, and the configuration space declared near the top of the file. Try switching to
  `run_openai_optuna.py` to observe concurrency controls.

## Lab 3 · Safety Guardrails

- **Concepts reinforced:** Chapter 3 (structural constraints), Chapter 4 (environment overlays for high-risk paths).
- **Entry point:** `examples/core/safety-guardrails/run.py`
- **Command:**
  ```bash
  cd Traigent
  TRAIGENT_MOCK_MODE=true python examples/core/safety-guardrails/run.py
  ```
- **What to inspect:** The custom metric (`safety_accuracy`) returned in the optimization result, the
  refusal style enumeration in the configuration space, and the `avg_response_time` metric computed from
  metadata.

## Lab 4 · Structured JSON Extraction

- **Concepts reinforced:** Chapter 3 (structural constraints on configuration variables) and Chapter 5
  (validation tooling, including JSON Schema checks of the spec).
- **Entry point:** `examples/core/structured-output-json/run.py`
- **Command:**
  ```bash
  cd Traigent
  TRAIGENT_MOCK_MODE=true python examples/core/structured-output-json/run.py
  ```
- **What to inspect:** The custom `json_score` metric in the aggregated dataframe, the configuration space
  for `schema_rigidity`, and how metadata captures response-time statistics. Note the difference from Chapter 3:
  TVL structural constraints restrict configuration variables such as `schema_rigidity`; checking that an output
  is valid JSON is an evaluation metric (`json_score`), not a TVL constraint.

### Extension Ideas

- Swap in real API keys (remove `TRAIGENT_MOCK_MODE`) to benchmark live services.
- Modify the configuration spaces and rerun; compare manifests and promotion decisions.
- Export a configuration file and a measurement bundle, then check them against the module with
  `tvl-measure-validate module.tvl.yml config.yml measurements.yml`.
- Capture screenshots of interesting runs (console output, Streamlit charts) and drop them into
  `tvl_book/figures/` for inclusion in case studies or the Playground page.
