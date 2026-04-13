# TVL Quick Start Demo
# End-to-end workflow from spec to optimization

Output output/quick-start.gif
Source tapes/_theme.tape
Set Height 700

Hide
Type "clear"
Enter
Show

Sleep 500ms

# Title
Type "# TVL Quick Start: From Spec to Optimization"
Enter
Sleep 1s

# Step 1: Create a spec
Type "# Step 1: Define your tuning space"
Enter
Sleep 500ms

Type "cat > my-agent.tvl.yml << 'EOF'"
Enter
Type "tvl: { module: 'my.rag.agent' }"
Enter
Type "tvl_version: '0.9'"
Enter
Enter
Type "environment:"
Enter
Type "  snapshot_id: '2025-01-01T00:00:00Z'"
Enter
Enter
Type "evaluation_set:"
Enter
Type "  dataset: 's3://my-bucket/eval.parquet'"
Enter
Enter
Type "tvars:"
Enter
Type "  - name: model"
Enter
Type "    type: enum[str]"
Enter
Type "    domain: ['gpt-4-turbo', 'claude-3-sonnet']"
Enter
Type "  - name: temperature"
Enter
Type "    type: float"
Enter
Type "    domain: { range: [0.0, 1.0] }"
Enter
Type "  - name: max_tokens"
Enter
Type "    type: int"
Enter
Type "    domain: { range: [100, 2000] }"
Enter
Enter
Type "objectives:"
Enter
Type "  - name: quality"
Enter
Type "    metric_ref: metrics.quality.v1"
Enter
Type "    direction: maximize"
Enter
Type "  - name: cost_usd"
Enter
Type "    metric_ref: metrics.cost_usd.v1"
Enter
Type "    direction: minimize"
Enter
Enter
Type "promotion_policy:"
Enter
Type "  dominance: epsilon_pareto"
Enter
Type "  alpha: 0.05"
Enter
Type "  min_effect: { quality: 0.01, cost_usd: 0.001 }"
Enter
Enter
Type "exploration:"
Enter
Type "  strategy: { type: tpe }"
Enter
Type "  budgets: { max_trials: 50 }"
Enter
Type "EOF"
Enter
Sleep 2s

# Step 2: Validate
Type "# Step 2: Validate the spec"
Enter
Sleep 500ms

Type "tvl validate my-agent.tvl.yml"
Enter
Sleep 1.5s

# Step 3: Check SAT
Type "# Step 3: Verify constraints are satisfiable"
Enter
Sleep 500ms

Type "tvl check-sat my-agent.tvl.yml"
Enter
Sleep 1.5s

# Step 4: Run optimization (simulated)
Type "# Step 4: Run optimization"
Enter
Sleep 500ms

Type "tvo run my-agent.tvl.yml --dry-run"
Enter
Sleep 2s

# Clean up
Hide
Type "rm my-agent.tvl.yml"
Enter
Show

Sleep 2s
