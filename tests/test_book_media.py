"""Book media integrity: scene sources, palette, rendered assets and references.

Rendering stays local (book/manim/render.sh). CI only recomputes hashes, so a
scene or palette change without a re-render fails here.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIM = ROOT / "book" / "manim"
MANIFEST = MANIM / "media-manifest.json"
MEDIA = ROOT / "website" / "client" / "public" / "book" / "media"
CHAPTERS = ROOT / "website" / "client" / "src" / "book" / "chapters"
BOOK_CSS = ROOT / "website" / "client" / "src" / "book" / "book.css"
MAX_VIDEO_BYTES = 1_500_000


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def test_manifest_exists_and_names_provenance() -> None:
    scenes = _manifest()["scenes"]
    assert scenes, "media manifest lists no scenes"
    for name, rec in scenes.items():
        assert rec["provenance"] == "original, made with Manim Community Edition (MIT)", name
        assert rec["manim_version"] and rec["render_command"], name


@pytest.mark.parametrize("scene", sorted(_manifest()["scenes"]))
def test_scene_changed_without_rerender_fails(scene: str) -> None:
    rec = _manifest()["scenes"][scene]
    assert _sha(ROOT / rec["scene_source"]) == rec["scene_source_sha256"], (
        f"{rec['scene_source']} changed since the last render: run book/manim/render.sh"
    )
    assert _sha(ROOT / rec["palette_source"]) == rec["palette_sha256"], (
        "book/manim/palette.py changed since the last render: run book/manim/render.sh"
    )


@pytest.mark.parametrize("scene", sorted(_manifest()["scenes"]))
def test_shared_scene_modules_unchanged_since_render(scene: str) -> None:
    support = _manifest()["scenes"][scene].get("support_sha256", {})
    assert support, f"{scene}: manifest records no support modules (common.py, fonts.py)"
    for path, digest in support.items():
        assert _sha(ROOT / path) == digest, f"{path} changed since the last render: run book/manim/render.sh"


@pytest.mark.parametrize("scene", sorted(_manifest()["scenes"]))
def test_rendered_assets_exist_and_match(scene: str) -> None:
    for asset in _manifest()["scenes"][scene]["assets"]:
        path = ROOT / asset["path"]
        assert path.is_file(), f"missing media file {asset['path']}"
        assert _sha(path) == asset["sha256"], f"{asset['path']} differs from the manifest"
        if path.suffix in {".webm", ".mp4"}:
            assert path.stat().st_size <= MAX_VIDEO_BYTES, f"{asset['path']} exceeds 1.5 MB"


def test_scene_sources_are_all_in_the_manifest() -> None:
    listed = set(_manifest()["scenes"])
    on_disk = {p.stem for p in (MANIM / "scenes").glob("*.py")}
    assert on_disk == listed, on_disk ^ listed


def test_palette_matches_css_variables() -> None:
    ns: dict = {}
    exec((MANIM / "palette.py").read_text(), ns)  # pure constants
    css = BOOK_CSS.read_text()
    light_block = css.split(".book-root {", 1)[1].split("}", 1)[0]
    dark_block = css.split(".dark .book-root:not(.book-print) {", 1)[1].split("}", 1)[0]
    for meaning in ns["MEANINGS"]:
        assert f"--book-{meaning}: {ns['LIGHT'][meaning]};" in light_block, meaning
        assert f"--book-{meaning}: {ns['DARK'][meaning]};" in dark_block, meaning


def test_chapters_reference_only_existing_media() -> None:
    checked = 0
    for mdx in sorted(CHAPTERS.glob("*.mdx")):
        text = mdx.read_text()
        # One <Figure ... /> block at a time: a chapter may hold several figures.
        for block in re.findall(r"<Figure\b.*?\n/>", text, flags=re.S):
            base = re.search(r'base="(/book/media/[^"]+)"', block)
            stem = re.search(r'stem="([^"]+)"', block)
            assert base and stem, f"{mdx.name}: Figure without base and stem"
            folder = ROOT / "website" / "client" / "public" / base.group(1).lstrip("/")
            for name in (f"{stem.group(1)}.webm", f"{stem.group(1)}.mp4", f"{stem.group(1)}-poster.png"):
                assert (folder / name).is_file(), f"{mdx.name}: missing {folder / name}"
                checked += 1
            for src in re.findall(r'src:\s*"([^"]+)"', block):
                assert (folder / src).is_file(), f"{mdx.name}: missing frame {folder / src}"
                checked += 1
    assert checked, "no media references were checked"
