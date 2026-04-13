#!/bin/bash
# Demo: TVL Optimization - From Vague to Precise
# Shows the core value proposition

set -e
cd "$(dirname "$0")/.."

# Set TERM for proper output
export TERM="${TERM:-xterm-256color}"

# Add mock CLI to path
export PATH="$PWD/mock-cli:$PATH"

# Colors
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

clear
echo -e "${CYAN}# The Problem: Vague AI Requirements${NC}"
echo ""
sleep 1

echo -e "${YELLOW}PM:${NC} \"Build me a customer support agent.\""
sleep 1.5

echo -e "${YELLOW}PM:${NC} \"Can you make it cheaper?\""
sleep 1.5

echo -e "${YELLOW}PM:${NC} \"It's not accurate enough...\""
sleep 2

echo ""
echo -e "${CYAN}# The Solution: Precise, Optimizable Specifications${NC}"
echo ""
sleep 1.5

echo '$ cat support-bot.tvl.yml'
sleep 0.5
echo ""

# Show a compelling spec with clear targets
cat << 'EOF'
# support-bot.tvl.yml - A PRD for your AI agent
tvl:
  module: support.qa_bot
tvl_version: "1.0"

objectives:
  - name: accuracy
    metric_ref: metrics.accuracy.v1
    direction: maximize
    target: ">= 0.85"          # 85% accuracy minimum

  - name: latency_ms
    metric_ref: metrics.latency_ms.v1
    direction: minimize
    target: "<= 200"           # Under 200ms

  - name: cost_per_query
    metric_ref: metrics.cost_per_query.v1
    direction: minimize
    target: "<= 0.01"          # Under 1 cent

tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4o", "claude-3-haiku", "claude-3-sonnet"]
  - name: temperature
    type: float
    domain: { range: [0.0, 0.7] }
  - name: rag_k
    type: int
    domain: { range: [3, 10] }
EOF

sleep 3

echo ""
echo -e "${CYAN}# Let the optimizer find the best configuration${NC}"
sleep 1

echo ""
echo '$ tvo run support-bot.tvl.yml --max-trials 50'
sleep 0.5
echo ""

# Run optimization with visual progress
tvo run support-bot.tvl.yml --max-trials 50

sleep 3
