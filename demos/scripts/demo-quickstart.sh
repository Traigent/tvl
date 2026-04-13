#!/bin/bash
# Demo: TVL Quick Start
# End-to-end workflow from spec to optimization

set -e
cd "$(dirname "$0")/.."
export TERM="${TERM:-xterm-256color}"
export PATH="$PWD/mock-cli:$PATH"

clear
echo "# TVL Quick Start: Spec to Optimization"
echo ""
sleep 1

echo "# Step 1: Define your tuning space"
sleep 0.5
echo ""
echo '$ cat my-agent.tvl.yml'
sleep 0.3

cat << 'EOF'
tvl: { module: 'my.rag.agent' }
tvl_version: '0.9'

environment:
  snapshot_id: '2025-01-01T00:00:00Z'

evaluation_set:
  dataset: 's3://my-bucket/eval.parquet'

tvars:
  - name: model
    type: enum[str]
    domain: ['gpt-4-turbo', 'claude-3-sonnet']
  - name: temperature
    type: float
    domain: { range: [0.0, 1.0] }
  - name: max_tokens
    type: int
    domain: { range: [100, 2000] }

objectives:
  - name: quality
    metric_ref: metrics.quality.v1
    direction: maximize
  - name: cost_usd
    metric_ref: metrics.cost_usd.v1
    direction: minimize

promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  min_effect: { quality: 0.01, cost_usd: 0.001 }

exploration:
  strategy: { type: tpe }
  budgets: { max_trials: 50 }
EOF

echo ""
sleep 2

echo "# Step 2: Validate"
sleep 0.5
echo ""
echo '$ tvl validate my-agent.tvl.yml'
sleep 0.3
tvl validate my-agent.tvl.yml

sleep 1.5
echo ""
echo "# Step 3: Check constraints"
sleep 0.5
echo ""
echo '$ tvl check-sat my-agent.tvl.yml'
sleep 0.3
tvl check-sat my-agent.tvl.yml

sleep 1.5
echo ""
echo "# Step 4: Run optimization"
sleep 0.5
echo ""
echo '$ tvo run my-agent.tvl.yml --dry-run'
sleep 0.3
tvo run my-agent.tvl.yml --dry-run

sleep 2
