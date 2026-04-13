#!/bin/bash
# Demo: TVL Error Diagnostics
# Shows helpful error messages

set -e
cd "$(dirname "$0")/.."
export TERM="${TERM:-xterm-256color}"
export PATH="$PWD/mock-cli:$PATH"

clear
echo "# TVL Error Diagnostics Demo"
echo ""
sleep 1

echo "# Let's create a spec with some errors:"
sleep 0.5
echo ""
echo '$ cat broken.tvl.yml'
sleep 0.3

cat << 'EOF'
tvl:
  module: demo.errors
tvl_version: "1.0"

tvars:
  - name: model
    type: enum[str]
    domain: []              # Empty domain!
  - name: temp
    type: float
    domain: { range: [0.0, 1.0] }

constraints:
  structural:
    - expr: 'unknown_var = true'   # Undeclared TVAR!
    - expr: 'temp = 0.5'           # Float equality warning
EOF

echo ""
sleep 2

echo "# Run validation to see diagnostics:"
sleep 0.5
echo ""
echo '$ tvl validate broken.tvl.yml'
sleep 0.3

# This will show errors
tvl validate broken.tvl.yml || true

sleep 2
echo ""
echo "# Each error has a code. Let's look up E1002:"
sleep 0.5
echo ""
echo '$ tvl explain E1002'
sleep 0.3

tvl explain E1002

sleep 2
