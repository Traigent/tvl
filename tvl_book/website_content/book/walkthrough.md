# Guided Walkthrough

The `Traigent/walkthrough` directory ships with a scripted journey through the SDK. We adapted it into a
linear walkthrough so you can follow along while reading Chapters 1–3.

## Prerequisites

- Clone the Traigent repository and create a virtual environment.
- Optional: set `TRAIGENT_MOCK_MODE=true` to exercise the flow without API keys.

```bash
git clone https://github.com/nimrodbusany/Traigent.git
cd Traigent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/requirements.txt
pip install -r requirements/requirements-integrations.txt
pip install -e .
```

## Chapter Highlights

### 1. What Traigent Optimizes
- Read `walkthrough/README.md` section “Chapter 1”.
- Run the first example to see parameter injection in action:
  ```bash
  TRAIGENT_MOCK_MODE=true python examples/core/hello-world/run.py
  ```
- Note how adaptive variables (model, temperature, retrieval depth) map directly to Chapter 2’s configuration space.

### 2. Zero-Code-Change Integration
- Inspect the decorator pattern in the walkthrough and compare it with your existing code.
- Create a sample evaluation dataset (e.g., `questions.jsonl`) and run the optimization snippet provided.

### 3. Seamless vs Parameter Modes
- Experiment with `injection_mode="seamless"` vs `"parameter"` by editing the walkthrough sample.
- Observe how TVL specs capture the same ranges when you translate these modes into static files.

### 4. Multi-Objective Runs
- Reuse the walkthrough’s multi-objective example or jump to Lab 2 for the full multi-objective tradeoff script.
- Compare results with Triagent’s output manifests described in Chapter 5.

### 5. Privacy Modes and Execution
- Toggle `execution_mode="edge_analytics"` to experience local-only runs.
- Record findings in a `provenance.json` file as shown in Chapter 5.

## Automation Script

Prefer a scripted tour? Run:

```bash
cd Traigent/walkthrough
bash walkthrough.sh
```

This walks through the same milestones, creating datasets and running optimizations automatically. Keep the
terminal output handy; several book chapters reference these logs when explaining promotion decisions.
