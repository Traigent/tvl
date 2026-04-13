# Phase 3 Operational Feasibility Examples

| Example | Notes |
| --- | --- |
| `budget-default.tvl.yml` | Uses default validation; budgets are informational and currently pass |
| `budget-skip.tvl.yml` | Demonstrates `tvl.validation.skip_budget_checks: true` |
| `budget-invalid.tvl.yml` | Shows failing budget check (`max_trials: 0`) |
| `derived-violation.tvl.yml` | Environment symbol violates a derived constraint |
