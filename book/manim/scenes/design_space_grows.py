"""Figure 3.1: every knob multiplies the design space (raw combinations, before constraints).

Production brief (kept here, not on the public page): one idea, the design space is the
product of the domains. The scene counts raw combinations and says so on screen all the
way through: the module keeps its small-model rule, but this scene does not apply it.
It starts from the flat grid of design_space (rows small, medium, large; columns 0, 1, 2,
4, 8 tool calls) in neutral outlines, not the allowed green, because no rule has been
applied. A temperature axis grows out of the grid in depth, with 11 tick marks labelled
0.0, 0.5 and 1.0; the grid copies itself along the axis into a block of thin layers and
the counter rolls to 165. The block then duplicates sideways, labelled 'retrieval off'
and 'retrieval on', and the counter rolls to 330. Neither the allowed nor the excluded
colour appears. Print frames: (1) the flat grid at 15; (2) the block at 165; (3) the two
blocks at 330.

Facts shown (source: 03-design-spaces.mdx, paragraph before Figure 3.1; tvars of
spec/examples/book/ch03/support-bot.tvl.yml):
  models small, medium, large (3); max_tool_calls 0, 1, 2, 4, 8 (5) -> 15
  temperature range [0.0, 1.0], resolution 0.1 -> 11 values -> 15 x 11 = 165
  use_retrieval true/false (2) -> 330

Made with Manim Community Edition (MIT). Original work; nothing here comes from
3Blue1Brown's videos or repositories.
"""

from __future__ import annotations

import sys
from pathlib import Path

from manim import (
    DOWN, LEFT, ORIGIN, RIGHT, UP, Create, FadeIn, FadeOut, Line, Rectangle, UpdateFromAlphaFunc,
    ValueTracker, VGroup, always_redraw, LaggedStart, interpolate_color, linear, smooth,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PAL, BookScene, T  # noqa: E402

MODELS = ["small", "medium", "large"]
CALLS = [0, 1, 2, 4, 8]
PHASE1 = 1.45  # the flat grid is drawn larger before it becomes a block
LAYERS = 11  # temperature 0.0, 0.1, ... 1.0
CW, CH, GAP = 0.84, 0.54, 0.08  # cell size in the block view
DX, DY = 0.17, 0.13  # offset of each layer in depth


def make_grid() -> tuple[VGroup, dict]:
    """The 3 x 5 grid at block scale, centred on the origin; neutral outline, no allowed colour."""
    cells = {}
    g = VGroup()
    for i, m in enumerate(MODELS):
        for j, c in enumerate(CALLS):
            r = Rectangle(width=CW, height=CH, color=PAL["muted"], stroke_width=2)
            r.set_fill(PAL["fg"], opacity=0.10)
            r.move_to([(j - 2) * (CW + GAP), (1 - i) * (CH + GAP), 0])
            cells[(m, c)] = r
            g.add(r)
    return g, cells


class DesignSpaceGrows(BookScene):
    SPEED = 0.85  # keeps the scene inside the 6 to 12 s budget

    def construct(self) -> None:
        # ---- counter, fixed label -------------------------------------------------
        n = ValueTracker(15)
        num_right = [-1.45, -2.25, 0]
        number = always_redraw(lambda: T(str(int(round(n.get_value()))), 64, PAL["fg"]).next_to(num_right, LEFT, buff=0).set_y(-2.35))
        fixed = T("raw combinations,\nbefore applying constraints", 28, PAL["muted"], line_spacing=0.8)
        fixed.next_to([-1.2, -2.35, 0], RIGHT, buff=0).set_y(-2.35)

        # ---- phase 1: the flat grid, large, with its labels -----------------------
        grid, cells = make_grid()
        grid.scale(PHASE1).move_to([1.0, 0.35, 0])
        row_labels = VGroup(*[T(m, 30, PAL["fg"]).next_to(cells[(m, CALLS[0])], LEFT, buff=0.25) for m in MODELS])
        col_labels = VGroup(*[T(str(c), 30, PAL["fg"]).next_to(cells[(MODELS[0], c)], UP, buff=0.12) for c in CALLS])
        x_title = T("max_tool_calls", 28, PAL["muted"], mono=True).next_to(col_labels, UP, buff=0.1)
        y_title = T("model", 28, PAL["muted"], mono=True).next_to(row_labels, UP, buff=0.45).align_to(row_labels, RIGHT)
        grid.set_z_index(50)
        self.play(FadeIn(grid), FadeIn(row_labels), FadeIn(col_labels), FadeIn(x_title), FadeIn(y_title), run_time=1.2)
        self.play(FadeIn(number), FadeIn(fixed), run_time=0.8)
        self.hold(1.2)
        self.snap("1-grid")

        # ---- phase 2: depth axis, layers, counter rolls to 165 --------------------
        target = [-1.3, -0.1, 0]  # centre of the front grid in the block view
        self.play(
            grid.animate.scale(1 / PHASE1).move_to(target),
            FadeOut(row_labels), FadeOut(col_labels), FadeOut(x_title), FadeOut(y_title),
            run_time=1.0,
        )
        front_w = 5 * CW + 4 * GAP
        front_h = 3 * CH + 2 * GAP
        fx0 = target[0] - front_w / 2  # front grid left
        fy0 = target[1] - front_h / 2  # front grid bottom
        fill = interpolate_color(__import__("manim").ManimColor(PAL["bg"]), __import__("manim").ManimColor(PAL["fg"]), 0.06)

        # depth axis along the right edge, from the front bottom-right corner
        ax0 = [fx0 + front_w, fy0, 0]
        ax1 = [ax0[0] + (LAYERS - 1) * DX, ax0[1] + (LAYERS - 1) * DY, 0]
        axis_line = Line(ax0, ax1, color=PAL["fg"], stroke_width=3).set_z_index(100)
        ticks = VGroup(*[
            Line([ax0[0] + k * DX, ax0[1] + k * DY, 0], [ax0[0] + k * DX + 0.14, ax0[1] + k * DY - 0.05, 0], color=PAL["fg"], stroke_width=3)
            for k in range(LAYERS)
        ]).set_z_index(100)
        tick_labels = VGroup(*[
            T(txt, 28, PAL["fg"]).next_to([ax0[0] + k * DX + 0.14, ax0[1] + k * DY, 0], RIGHT, buff=0.08)
            for k, txt in ((0, "0.0"), (5, "0.5"), (10, "1.0"))
        ]).set_z_index(100)
        axis_title = T("temperature", 28, PAL["muted"], mono=True).move_to([ax1[0] + 0.35, target[1] + front_h / 2 + (LAYERS - 1) * DY + 0.45, 0]).set_z_index(100)
        self.play(Create(axis_line), Create(ticks), FadeIn(tick_labels), FadeIn(axis_title), run_time=1.3)

        layers = VGroup()
        for k in range(LAYERS - 1, 0, -1):  # back to front
            lay = Rectangle(width=front_w, height=front_h, color=PAL["muted"], stroke_width=2)
            lay.set_fill(fill, opacity=1)
            lay.move_to([target[0] + k * DX, target[1] + k * DY, 0])
            lay.set_z_index(10 + (LAYERS - k))
            layers.add(lay)
        self.play(
            LaggedStart(*[FadeIn(l) for l in layers], lag_ratio=0.12),
            UpdateFromAlphaFunc(n, lambda m, a: m.set_value(15 + (165 - 15) * smooth(a))),
            run_time=2.6,
        )
        self.hold(1.2)
        self.snap("2-block")

        # ---- phase 3: duplicate sideways, retrieval off / on, counter to 330 -------
        block = VGroup(grid, layers)
        block_copy = block.copy()
        self.play(FadeOut(axis_line), FadeOut(ticks), FadeOut(tick_labels), FadeOut(axis_title), run_time=0.6)
        self.add(block_copy)
        cy = 0.45
        self.play(
            block.animate.scale(0.8).move_to([-2.75, cy, 0]),
            block_copy.animate.scale(0.8).move_to([2.75, cy, 0]),
            UpdateFromAlphaFunc(n, lambda m, a: m.set_value(165 + (330 - 165) * smooth(a))),
            run_time=2.0,
        )
        off = T("retrieval off", 30, PAL["fg"]).next_to(block, UP, buff=0.2)
        on = T("retrieval on", 30, PAL["fg"]).next_to(block_copy, UP, buff=0.2)
        self.play(FadeIn(off), FadeIn(on), run_time=0.8)
        self.hold(1.2)
        self.snap("3-blocks")
