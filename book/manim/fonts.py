"""Register the book's fonts (Inter, JetBrains Mono) with ManimPango.

The book ships variable woff2 files. Pango cannot read woff2, so this module
converts each one to a static TTF in a cache directory (fontTools + brotli) and
registers it. Family names are "Inter" and "JetBrains Mono"; call register()
before building any Text.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import manimpango
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FONT_DIR = Path(__file__).resolve().parents[2] / "website" / "client" / "public" / "fonts"
SOURCES = {
    # (woff2 file, family name set on the static instance, weight)
    "Inter": ("inter/Inter-Variable.woff2", 400),
    "JetBrains Mono": ("jetbrains-mono/JetBrainsMono-Variable.woff2", 400),
}
SANS = "Inter"
MONO = "JetBrains Mono"


def register() -> None:
    cache = Path(tempfile.gettempdir()) / "book-manim-fonts-v2"
    cache.mkdir(exist_ok=True)
    for family, (rel, weight) in SOURCES.items():
        out = cache / f"{family.replace(' ', '')}-static.ttf"
        if not out.exists():
            font = TTFont(str(FONT_DIR / rel))
            static = instancer.instantiateVariableFont(font, {"wght": weight}, inplace=False)
            for rec in static["name"].names:
                if rec.nameID in (1, 16):
                    rec.string = family
                elif rec.nameID in (2, 17):
                    rec.string = "Regular"
            if family == MONO and "GSUB" in static:
                # JetBrains Mono's contextual alternates draw ">=" and "<=" as one symbol.
                # The book quotes TVL as typed, so drop the substitution table.
                del static["GSUB"]
            static.flavor = None
            static.save(str(out))
        if not manimpango.register_font(str(out)):
            raise RuntimeError(f"cannot register font {out}")
