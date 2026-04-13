#!/bin/bash
# Generate all TVL demo GIFs using VHS
# Usage: ./generate-all.sh [--mp4] [--webm]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAPES_DIR="$SCRIPT_DIR/tapes"
OUTPUT_DIR="$SCRIPT_DIR/output"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if VHS is installed
if ! command -v vhs &> /dev/null; then
    echo "VHS is not installed. Install with:"
    echo "  brew install vhs       # macOS"
    echo "  go install github.com/charmbracelet/vhs@latest  # Linux"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# List of demos to generate
DEMOS=(
    "validate-spec"
    "constraint-check"
    "error-diagnostics"
    "quick-start"
)

echo -e "${BLUE}Generating TVL demo videos...${NC}"
echo ""

for demo in "${DEMOS[@]}"; do
    tape_file="$TAPES_DIR/$demo.tape"

    if [[ -f "$tape_file" ]]; then
        echo -e "${GREEN}→${NC} Generating $demo..."

        # Change to tapes directory for relative paths
        cd "$TAPES_DIR"
        vhs "$demo.tape"
        cd "$SCRIPT_DIR"

        echo "  ✓ Created output/$demo.gif"
    else
        echo "  ⚠ Skipping $demo (tape file not found)"
    fi
done

echo ""
echo -e "${GREEN}Done!${NC} Generated files:"
ls -lh "$OUTPUT_DIR"/*.gif 2>/dev/null || echo "  (no GIF files found)"

# Optional: Generate additional formats
if [[ "$1" == "--mp4" ]] || [[ "$2" == "--mp4" ]]; then
    echo ""
    echo "Converting to MP4..."
    for gif in "$OUTPUT_DIR"/*.gif; do
        mp4="${gif%.gif}.mp4"
        ffmpeg -i "$gif" -movflags faststart -pix_fmt yuv420p -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" "$mp4" -y 2>/dev/null
        echo "  ✓ Created $(basename "$mp4")"
    done
fi

if [[ "$1" == "--webm" ]] || [[ "$2" == "--webm" ]]; then
    echo ""
    echo "Converting to WebM..."
    for gif in "$OUTPUT_DIR"/*.gif; do
        webm="${gif%.gif}.webm"
        ffmpeg -i "$gif" -c:v libvpx-vp9 -b:v 0 -crf 30 "$webm" -y 2>/dev/null
        echo "  ✓ Created $(basename "$webm")"
    done
fi
