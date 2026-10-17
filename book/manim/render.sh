#!/usr/bin/env bash
# Render the book's Manim scenes into website/client/public/book/media/<scene>/.
# Rendering stays local (Manim, LaTeX and cairo are heavy for CI); CI only checks
# the hashes in media-manifest.json (tests/test_book_media.py).
#
# Needs: book/manim/.venv with `pip install -r requirements.txt`. Manim's text
# engine (ManimPango) needs the pango and cairo development libraries to be
# installed once; set MANIM_LIB_PREFIX to a prefix that holds them (e.g. a
# conda-forge env) if they are not system-wide.
#
# Usage: render.sh [scene ...]   (default: all scenes in the table below)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
MEDIA="$REPO/website/client/public/book/media"

if [[ -n "${MANIM_LIB_PREFIX:-}" ]]; then
  export LD_LIBRARY_PATH="$MANIM_LIB_PREFIX/lib:${LD_LIBRARY_PATH:-}"
  export FONTCONFIG_FILE="${FONTCONFIG_FILE:-/etc/fonts/fonts.conf}"
fi
MANIM="$HERE/.venv/bin/manim"
PY="$HERE/.venv/bin/python"
COMMON=(-r 1280,720 --fps 30 --disable_caching)

# scene file | Scene class | print snapshot names, in order (light theme) | poster snapshot (dark)
declare -A CLASS=(
  [design_space]=DesignSpace
  [scattered_to_gathered]=ScatteredToGathered
  [design_space_grows]=DesignSpaceGrows
  [environment_filter]=EnvironmentFilter
  [better_with_margins]=BetterWithMargins
)
declare -A FRAMES=(
  [design_space]="1-grid 2-rule1 3-final"
  [scattered_to_gathered]="1-scattered 2-gathered"
  [design_space_grows]="1-grid 2-block 3-blocks"
  [environment_filter]="1-open 2-closed"
  [better_with_margins]="1-front 2-margins 3-verdicts"
)
declare -A POSTER=(
  [design_space]=3-final
  [scattered_to_gathered]=2-gathered
  [design_space_grows]=3-blocks
  [environment_filter]=2-closed
  [better_with_margins]=3-verdicts
)
ORDER=(design_space scattered_to_gathered design_space_grows environment_filter better_with_margins)
SCENES=("$@")
[[ ${#SCENES[@]} -eq 0 ]] && SCENES=("${ORDER[@]}")

cd "$HERE"
for scene in "${SCENES[@]}"; do
  cls="${CLASS[$scene]:?unknown scene $scene}"
  src="$HERE/scenes/$scene.py"
  out="$MEDIA/$scene"
  work="$(mktemp -d "${TMPDIR:-/tmp}/book-manim.XXXXXX")"
  mkdir -p "$out"
  rm -f "$out"/*
  # 1. Screen version (dark palette): WebM and MP4, plus the dark frames.
  export BOOK_THEME=dark BOOK_SNAP_DIR="$work/snaps"
  timeout 900 "$MANIM" render "${COMMON[@]}" --media_dir "$work/media" --format webm -o "$scene" "$src" "$cls"
  timeout 900 "$MANIM" render "${COMMON[@]}" --media_dir "$work/media" --format mp4 -o "$scene" "$src" "$cls"
  # 2. Print version (light palette): the frame sequence used on paper.
  export BOOK_THEME=light
  timeout 900 "$MANIM" render "${COMMON[@]}" --media_dir "$work/media" --format mp4 -o "${scene}_light" "$src" "$cls"

  cp "$(find "$work/media" -name "$scene.webm" | head -1)" "$out/$scene.webm"
  cp "$(find "$work/media" -name "$scene.mp4" | head -1)" "$out/$scene.mp4"
  cp "$work/snaps/dark-${POSTER[$scene]}.png" "$out/$scene-poster.png"
  n=1
  for f in ${FRAMES[$scene]}; do
    cp "$work/snaps/light-$f.png" "$out/frame-$n.png"
    n=$((n + 1))
  done
  CMD="manim render -r 1280,720 --fps 30 --format {webm,mp4} -o $scene book/manim/scenes/$scene.py $cls (BOOK_THEME=dark screen, BOOK_THEME=light frames)"
  "$PY" "$HERE/build_media_manifest.py" --scene "$scene" --render-command "$CMD"
  rm -rf "$work"
  ls -l "$out"
done
