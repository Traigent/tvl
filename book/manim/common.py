"""Shared set-up for the book's Manim scenes: frame crop, theme, fonts, helpers.

Every scene imports this module first. It sets the cropped frame, picks the dark
(screen) or light (print) palette from BOOK_THEME, registers the book's fonts,
and offers text and mark helpers that keep labels readable in print.

Print size. The print route shows a frame about 84 mm wide (two frames per row on
a 174 mm text block, 6 mm gap). The frame is 11.2 Manim units wide, so one unit is
7.5 mm on paper. Manim sets Text at (font_size / 72) units per em, so
pt = font_size * 7.5 / 25.4 = font_size * 0.2953. MIN_FS = 28 gives 8.27 pt.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from manim import (
    DOWN, LEFT, ORIGIN, RIGHT, UP, Line, Scene, Text, VGroup, VMobject, config,
)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fonts  # noqa: E402
from palette import DARK, LIGHT  # noqa: E402

fonts.register()

# Crop the empty margins (the default 14.2 x 8 frame leaves a wide border).
config.frame_width = 11.2
config.frame_height = 11.2 * 9 / 16  # 6.3

THEME = os.environ.get("BOOK_THEME", "dark")
PAL = LIGHT if THEME == "light" else DARK
SNAP_DIR = os.environ.get("BOOK_SNAP_DIR")

SANS = fonts.SANS
MONO = fonts.MONO

PRINT_FRAME_MM = 84.0
UNIT_MM = PRINT_FRAME_MM / 11.2
MIN_FS = 28  # 8.27 pt in print


def pt_of(font_size: float) -> float:
    return font_size / 72 * UNIT_MM / 25.4 * 72


if pt_of(MIN_FS) < 8.0:
    raise ValueError(f"minimum font size renders below 8 pt: {pt_of(MIN_FS)}")

_sizes: list[int] = []


def T(s: str, fs: int = 28, color: str | None = None, mono: bool = False, **kw) -> Text:
    """A Text in the book fonts. Refuses a size that would print below 8 pt."""
    if fs < MIN_FS:
        raise ValueError(f"font_size {fs} prints at {pt_of(fs):.1f} pt (< 8 pt): {s!r}")
    _sizes.append(fs)
    return Text(s, font=MONO if mono else SANS, font_size=fs, color=color or PAL["fg"], **kw)


def check_mark(center, size: float = 0.34, color: str | None = None, width: float = 5) -> VMobject:
    cx, cy = center[0], center[1]
    m = VMobject(stroke_color=color or PAL["allowed"], stroke_width=width)
    m.set_points_as_corners([
        [cx - size * 0.5, cy - size * 0.02, 0],
        [cx - size * 0.15, cy - size * 0.38, 0],
        [cx + size * 0.55, cy + size * 0.42, 0],
    ])
    return m


def cross_mark(center, size: float = 0.34, color: str | None = None, width: float = 5) -> VGroup:
    cx, cy = center[0], center[1]
    h = size * 0.5
    c = color or PAL["excluded"]
    return VGroup(
        Line([cx - h, cy + h, 0], [cx + h, cy - h, 0], color=c, stroke_width=width),
        Line([cx - h, cy - h, 0], [cx + h, cy + h, 0], color=c, stroke_width=width),
    )


class BookScene(Scene):
    """Scene with a themed background and the snapshot helper."""

    def snap(self, name: str) -> None:
        if SNAP_DIR:
            Path(SNAP_DIR).mkdir(parents=True, exist_ok=True)
            self.camera.get_image().save(Path(SNAP_DIR) / f"{THEME}-{name}.png")

    # Pacing: every play() and wait() is scaled by SPEED so a scene fits the 6 to 12 s
    # budget; hold() is a pause on a key frame and is never scaled.
    SPEED = 1.0

    def setup(self) -> None:
        self.camera.background_color = PAL["bg"]

    def play(self, *animations, **kwargs):
        kwargs["run_time"] = kwargs.get("run_time", 1.0) * self.SPEED
        return super().play(*animations, **kwargs)

    def wait(self, duration: float = 1.0, *args, **kwargs):
        return super().wait(duration * self.SPEED, *args, **kwargs)

    def hold(self, duration: float = 1.2) -> None:
        super().wait(duration)

    def tear_down(self) -> None:
        if _sizes:
            print(f"[book] smallest label {min(_sizes)} -> {pt_of(min(_sizes)):.2f} pt in print")
