# Chapter 2 · Getting Fluent in TVL

TVL encodes the answers to three questions:

1. **What are we tuning?** (`tvars` — tuned variables with typed domains)
2. **How do we measure success?** (`objectives` and `evaluation_set`)
3. **What rules govern promotion?** (`constraints`, `promotion_policy`)

The table below maps each TVL section to its responsibilities.

| Section | Responsibilities |
|---------|------------------|
| `tvl` | Module namespace identifier |
| `environment` | Snapshot ID plus optional `bindings` and `context` anchoring the spec |
| `evaluation_set` | Dataset URI and optional seed for reproducibility |
| `tvars` | Tuned variables with explicit types (`bool`, `int`, `float`, `enum[str]`) and domains |
| `constraints` | Structural rules and operational preconditions |
| `objectives` | Metrics to maximize/minimize, including banded targets |
| `promotion_policy` | ε-Pareto dominance settings, α-level, min effects, chance constraints |
| `exploration` | Search strategy, budgets, and convergence criteria |

## Minimal Working Spec

Here is the smallest useful TVL module. Read it top to bottom and notice how every field supports the
optimizer.

```yaml
# Minimal TVL Spec - Chapter 2
tvl:
  module: book.quickstart.simple_rag_qa

environment:
  snapshot_id: "2025-01-20T00:00:00Z"
  bindings:
    retriever_index: campus-faq-v1
    llm_gateway: us-east-1

evaluation_set:
  dataset: s3://datasets/campus-rag/dev.jsonl
  seed: 2025

tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4o-mini", "claude-3-haiku"]

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
    direction: maximize
  - name: latency_p95_ms
    metric_ref: metrics.latency_p95_ms.v1
    direction: minimize

promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  adjust: holm
  min_effect:
    answer_accuracy: 0.01
    latency_p95_ms: 50

exploration:
  strategy:
    type: grid
  budgets:
    max_trials: 24
    max_wallclock_s: 900
```

!!! tip "Checklist Before You Commit"
    - Every TVAR has an explicit `type` and `domain`?
    - Objectives declared with `direction: maximize` or `minimize`?
    - `promotion_policy` includes `min_effect` for each objective?
    - `environment.snapshot_id` is an RFC3339 timestamp?

## Validation Warm-Up

Use `tvl-validate` to check your spec against the TVL schema:

```bash
cd tvl_book/examples
tvl-validate ch2_hello_tvl.tvl.yml
```

For deeper inspection, use this helper script to print the TVARs and their domains:

```python
"""Quick helper for Chapter 2 to inspect a TVL spec and print the knobs."""
from pathlib import Path
import textwrap

import yaml


def load_spec(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def ensure_sections(spec: dict, required: list[str]) -> list[str]:
    missing = [section for section in required if section not in spec]
    return missing


def _format_domain(domain: object) -> str:
    if isinstance(domain, list):
        return f"choices={domain}"
    if isinstance(domain, dict):
        if "range" in domain:
            resolution = domain.get("resolution")
            if resolution is not None:
                return f"range={domain['range']}, resolution={resolution}"
            return f"range={domain['range']}"
        if "set" in domain:
            return f"set={domain['set']}"
        return "domain=<object>"
    return "domain=<unknown>"


def print_tvars(tvars: list[dict]) -> None:
    print("Tuned Variables (tvars)")
    print("----------------------")
    for entry in tvars:
        name = entry.get("name", "<unnamed>")
        type_ = entry.get("type", "<untyped>")
        domain = _format_domain(entry.get("domain"))
        print(f"- {name} [{type_}]: {domain}")


def main() -> None:
    spec_path = Path(__file__).with_name("ch2_hello_tvl.tvl.yml")
    spec = load_spec(spec_path)

    required_sections = ["tvl", "environment", "evaluation_set", "tvars", "objectives", "promotion_policy"]
    missing = ensure_sections(spec, required_sections)
    if missing:
        print("Missing sections:", ", ".join(missing))
        return

    print(textwrap.dedent(
        """\
        Spec loaded successfully.
        module    : {module}
        snapshot  : {snapshot}
        dataset   : {dataset}
        """
    ).format(
        module=(spec.get("tvl") or {}).get("module", "<unknown>"),
        snapshot=(spec.get("environment") or {}).get("snapshot_id", "<unknown>"),
        dataset=(spec.get("evaluation_set") or {}).get("dataset", "<unknown>"),
    ))

    print_tvars(spec["tvars"])


if __name__ == "__main__":
    main()
```

!!! info "Run It Yourself"
    ```bash
    cd tvl_book/examples
    python ch2_validate_spec.py
    ```

## TVL Type System

TVL enforces explicit typing on all tuned variables:

| Type | Description | Domain Examples |
|------|-------------|-----------------|
| `bool` | Boolean flag | `[true, false]` |
| `int` | Integer value | `range: [1, 10]` or `set: [1, 2, 4, 8]` |
| `float` | Floating-point | `range: [0.0, 1.0]` with optional `resolution` |
| `enum[str]` | Finite set of strings | `["gpt-4o", "claude-3"]` |
| `enum[int]` | Finite set of integers | `[100, 500, 1000]` |
| `tuple[...]` | Product type | Cartesian product of component domains |
| `callable[Proto]` | Protocol reference | Registry-backed function lookup |

## Common Pitfalls

1. Using wrong type names — it's `enum[str]` not `categorical`, `float` not `continuous`.
2. Mixing deployment bindings with numeric operating assumptions instead of separating `bindings` and `context`.
3. Missing `promotion_policy` — this is required in TVL (no implicit defaults).
4. Constraint syntax errors — use `=` for equality (not `==`), `and`/`or` (not `&&`/`||`).

## Analog Circuit Lab · Explore the Knobs

Try the Orientation RAG micro simulation to feel each tuning variable. The sliders map directly to the spec above;
latency, cost, and quality update in real time, and constraint warnings match the rules we enforce in Chapter 3.

<iframe src="../../sims/orientation-rag-circuit/main.html" height="640px" scrolling="no" style="width: 100%; border: none;"></iframe>

[Open the lab in a new tab](../sims/orientation-rag-circuit/index.md){ .md-button .md-button--primary }

**Suggested Prompts**

- Start from the **Baseline** preset, bump `retriever_top_k` to 56, and observe the latency gauge. When does the red
  guardrail trigger?
- Move the `rerank_weight` slider below 0.3 while `retriever_top_k` ≥ 40. What warning do you see? Why does the
  constraint exist?
- Hold `retriever_top_k` steady and stretch `response_tokens`. What trade-off emerges between cost and quality?
