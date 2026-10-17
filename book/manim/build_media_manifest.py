"""Write book/manim/media-manifest.json: source hashes, versions, provenance per asset.

Run by render.sh after a render. tests/test_book_media.py recomputes the source
hashes and fails when a scene or the palette changed without a re-render.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MEDIA_ROOT = REPO / "website" / "client" / "public" / "book" / "media"
MANIFEST = HERE / "media-manifest.json"
# Shared modules every scene imports: frame crop, theme, fonts.
SUPPORT = ("common.py", "fonts.py")
PROVENANCE = "original, made with Manim Community Edition (MIT)"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True)
    ap.add_argument("--render-command", required=True)
    args = ap.parse_args()

    scene_src = HERE / "scenes" / f"{args.scene}.py"
    palette_src = HERE / "palette.py"
    existing = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"scenes": {}}
    assets = []
    for f in sorted((MEDIA_ROOT / args.scene).iterdir()):
        assets.append(
            {
                "path": f.relative_to(REPO).as_posix(),
                "sha256": sha256(f),
                "bytes": f.stat().st_size,
            }
        )
    existing["scenes"][args.scene] = {
        "scene_source": scene_src.relative_to(REPO).as_posix(),
        "scene_source_sha256": sha256(scene_src),
        "palette_source": palette_src.relative_to(REPO).as_posix(),
        "palette_sha256": sha256(palette_src),
        "support_sha256": {
            f"book/manim/{name}": sha256(HERE / name) for name in SUPPORT
        },
        "manim_version": version("manim"),
        "render_command": args.render_command,
        "provenance": PROVENANCE,
        "assets": assets,
    }
    MANIFEST.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n")
    print(f"wrote {MANIFEST}")


if __name__ == "__main__":
    main()
