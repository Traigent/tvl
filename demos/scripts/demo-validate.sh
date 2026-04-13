#!/bin/bash
# Demo: TVL Validation
# This script is recorded with asciinema

set -e
cd "$(dirname "$0")/.."

# Set TERM for proper output
export TERM="${TERM:-xterm-256color}"

# Add mock CLI to path
export PATH="$PWD/mock-cli:$PATH"

clear
echo "# TVL Specification Validation Demo"
echo ""
sleep 1

echo "# First, let's look at a TVL spec file:"
sleep 0.5
echo ""
echo '$ cat examples/rag-support-bot.tvl.yml | head -25'
sleep 0.3

# Show a sample spec
cat << 'EOF'
tvl:
  module: corp.rag.support_bot
tvl_version: "1.0"

environment:
  snapshot_id: "2025-01-01T00:00:00Z"

evaluation_set:
  dataset: s3://datasets/support-tickets.parquet

tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4-turbo", "claude-3-sonnet"]
  - name: temperature
    type: float
    domain: { range: [0.0, 1.0] }
  - name: use_rag
    type: bool
    domain: [true, false]

objectives:
  - name: quality
    metric_ref: metrics.quality.v1
    direction: maximize
EOF

echo ""
sleep 2

echo "# Now let's validate it:"
sleep 0.5
echo ""
echo '$ tvl validate examples/rag-support-bot.tvl.yml'
sleep 0.3

# Run mock validation
tvl validate examples/rag-support-bot.tvl.yml

sleep 2
echo ""
echo "# Get more info about the spec:"
sleep 0.5
echo ""
echo '$ tvl info examples/rag-support-bot.tvl.yml'
sleep 0.3

tvl info examples/rag-support-bot.tvl.yml

sleep 2
