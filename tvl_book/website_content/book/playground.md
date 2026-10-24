# Traigent Playground

The Traigent Playground is a Streamlit application for exploring optimization problems, managing datasets,
and visualising results in real time. It lives under `Traigent/playground/` and complements Chapters 4 and 5.

## Launching the Control Center

```bash
cd Traigent
pip install -r playground/requirements_streamlit.txt
streamlit run playground/traigent_control_center.py
```

Set `TRAIGENT_MOCK_MODE=true` if you want to experiment without live API keys.

## Key Modules

| Module | Purpose |
|--------|---------|
| `problem_management/` | Create, edit, and analyze optimization problems. |
| `problem_generation/` | Generate new problem suites with Claude-assisted prompts. |
| `optimization_storage.py` | Persists results for later comparison. |
| `optimization_callbacks.py` | Hooks for streaming trials into the UI. |
| `langchain_problems/` | Repository of generated problems and examples. |

## Quickstart Workflow

1. **Generate a problem**
   ```bash
   python playground/problem_manager.py create \
     --description "Customer support ticket classification" \
     --examples 50
   ```
2. **Add examples later**
   ```bash
   python playground/problem_manager.py add-examples customer_support --count 20
   ```
3. **Analyze quality**
   ```bash
   python playground/problem_manager.py analyze customer_support
   ```
4. **Launch the Streamlit UI** and select the problem you just created.

## Connecting Back to TVL

- Exported optimization runs can be kept alongside the artifacts described in Chapter 5.
- The UI’s “Compare Runs” tab helps you compare runs by eye. It does not validate overlays (files that change parts
  of a base module and are merged into it) or decide promotion: compose and validate overlays with
  `tvl-compose --validate` (Chapter 4), and decide promotion with `tvl-ci-gate` from measurement bundles, the files
  that record measured objective values and outcomes for the incumbent and the candidate (Chapter 5).
- Pull generated problems into `examples/` to seed new labs or CI smoke tests.

!!! tip "Capture the UI"
    When you capture screenshots or GIFs of the Playground, store them under
    `tvl_book/figures/` (for example `playground-dashboard.png`). Reference them from
    chapters or case studies to illustrate optimization progress or drift investigations.

## Advanced Tools

- `generate_problem_suite.py` can batch-create numerous scenarios for benchmarking:
  ```bash
  python playground/generate_problem_suite.py --problems 10 --examples 100 --parallel
  ```
- The Playground logs live under `playground/optimization_logs/`; reference them when writing case studies or
  validating reproducibility for TVL specs.
