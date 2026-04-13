#!/bin/bash
# Demo: TVL Constraint Checking
# Shows SAT checking and witness generation

set -e
cd "$(dirname "$0")/.."
export TERM="${TERM:-xterm-256color}"
export PATH="$PWD/mock-cli:$PATH"

clear
echo "# TVL Constraint Checking Demo"
echo ""
sleep 1

echo "# Spec with structural constraints:"
sleep 0.5
echo ""

cat << 'EOF'
tvars:
  - name: model
    type: enum[str]
    domain: ['gpt-4', 'claude-3']
  - name: use_cot
    type: bool
    domain: [true, false]
  - name: temperature
    type: float
    domain: { range: [0.0, 2.0] }

constraints:
  structural:
    # If using chain-of-thought, temperature must be low
    - when: 'use_cot = true'
      then: 'temperature <= 0.5'
EOF

echo ""
sleep 2

echo "# Check if constraints are satisfiable:"
sleep 0.5
echo ""
echo '$ tvl check-sat spec.tvl.yml'
sleep 0.3

tvl check-sat spec.tvl.yml

sleep 2
echo ""
echo "# Get a valid configuration (witness):"
sleep 0.5
echo ""
echo '$ tvl witness spec.tvl.yml'
sleep 0.3

tvl witness spec.tvl.yml

sleep 2
