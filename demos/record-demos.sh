#!/bin/bash
# Generate all TVL demo recordings
# Usage: ./record-demos.sh [--svg-only]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set TERM if not set
export TERM="${TERM:-xterm-256color}"

# Create output directory
mkdir -p output

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     TVL Demo Generator                 ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Make scripts executable
chmod +x scripts/*.sh mock-cli/* 2>/dev/null || true

# Step 1: Generate cast files using Python
echo -e "${GREEN}Step 1:${NC} Generating asciinema cast files..."
python3 scripts/generate-cast.py

# Step 2: Convert to SVG if svg-term is available
if command -v svg-term &> /dev/null; then
    echo ""
    echo -e "${GREEN}Step 2:${NC} Converting to animated SVG..."
    for f in output/*.cast; do
        name=$(basename "$f" .cast)
        echo "  → Converting $name..."
        svg-term --in "$f" --out "output/${name}.svg" --window --width 120 --height 35 2>/dev/null
        echo "    ✓ output/${name}.svg"
    done
else
    echo ""
    echo -e "${YELLOW}Note:${NC} svg-term not found. Install with:"
    echo "  npm install -g svg-term-cli"
fi

# Summary
echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}Done!${NC} Generated files:"
echo ""
ls -lh output/*.cast output/*.svg 2>/dev/null || ls -lh output/*.cast
echo ""
echo -e "${BLUE}Usage:${NC}"
echo "  • SVG: Embed directly in GitHub README"
echo "  • Cast: Play with 'asciinema play output/validate.cast'"
echo ""
echo -e "${BLUE}Embed in README.md:${NC}"
echo '  ![TVL Demo](tvl/demos/output/validate.svg)'
