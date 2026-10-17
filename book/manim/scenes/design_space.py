"""Original pilot scene: a rule greys out cells of an agent design space.

A 2-D grid of agent designs (model x max_tool_calls). Two structural rules over
the tuned variables exclude some cells. One idea, fixed colour meaning:
green = allowed, grey with a cross = excluded.

Made with Manim Community Edition (MIT). Original work; nothing here comes from
3Blue1Brown's videos or repositories.
"""

from __future__ import annotations

import sys
from pathlib import Path

from manim import (
    DOWN, LEFT, RIGHT, UP, Create, FadeIn, FadeOut, Line, Rectangle, VGroup, Write,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PAL, BookScene, T  # noqa: E402  (frame crop, theme, book fonts)

MODELS = ["small", "medium", "large"]
CALLS = [0, 1, 2, 4, 8]
# Rule 1: when model = "small" then max_tool_calls <= 2
# Rule 2: when model = "large" then max_tool_calls >= 1
def excluded_by_rule1(m: str, c: int) -> bool:
    return m == "small" and c > 2

def excluded_by_rule2(m: str, c: int) -> bool:
    return m == "large" and c < 1


class DesignSpace(BookScene):
    def construct(self) -> None:
        w, h = 1.3, 0.72
        origin_x = -1.8

        title = T("Every agent design is a cell", 40, PAL["fg"]).to_edge(UP, buff=0.25)
        self.play(Write(title), run_time=1)

        cells: dict[tuple[str, int], Rectangle] = {}
        grid = VGroup()
        for i, m in enumerate(MODELS):
            for j, c in enumerate(CALLS):
                r = Rectangle(width=w, height=h, color=PAL["allowed"], fill_color=PAL["allowed"], fill_opacity=0.35, stroke_width=2)
                r.move_to([origin_x + j * (w + 0.1), 0.9 - i * (h + 0.1), 0])
                cells[(m, c)] = r
                grid.add(r)
        row_labels = VGroup(*[
            T(m, 32, PAL["fg"]).next_to(cells[(m, CALLS[0])], LEFT, buff=0.25)
            for m in MODELS
        ])
        col_labels = VGroup(*[
            T(str(c), 32, PAL["fg"]).next_to(cells[(MODELS[0], c)], UP, buff=0.15)
            for c in CALLS
        ])
        x_title = T("max_tool_calls", 30, PAL["muted"], mono=True).next_to(col_labels, UP, buff=0.12)
        y_title = T("model", 30, PAL["muted"], mono=True).next_to(row_labels, UP, buff=0.3).align_to(row_labels, RIGHT)
        self.play(FadeIn(grid), FadeIn(row_labels), FadeIn(col_labels), FadeIn(x_title), FadeIn(y_title), run_time=1.5)
        legend = T("15 designs, all allowed so far", 32, PAL["allowed"]).to_edge(DOWN, buff=0.4)
        self.play(FadeIn(legend))
        self.wait(1)
        self.snap("1-grid")

        marks: list = []
        def exclude(pred) -> list:
            anims = []
            for (m, c), r in cells.items():
                if pred(m, c) and r.fill_color.to_hex().lower() != PAL["excluded"].lower():
                    cross = VGroup(
                        Line(r.get_corner(UP + LEFT), r.get_corner(DOWN + RIGHT), color=PAL["excluded"], stroke_width=3),
                        Line(r.get_corner(UP + RIGHT), r.get_corner(DOWN + LEFT), color=PAL["excluded"], stroke_width=3),
                    )
                    marks.append(cross)
                    anims.append(r.animate.set_fill(PAL["excluded"], opacity=0.25).set_stroke(PAL["excluded"]))
                    anims.append(Create(cross))
            return anims

        rule1 = T('rule 1:  when model = "small"\nthen  max_tool_calls <= 2', 30, PAL["fg"], mono=True, line_spacing=0.6).move_to([0, -1.8, 0])
        self.play(FadeOut(legend), Write(rule1))
        self.play(*exclude(excluded_by_rule1), run_time=1.5)
        n1 = 15 - sum(excluded_by_rule1(m, c) for m in MODELS for c in CALLS)
        count1 = T(f"{n1} of 15 designs allowed", 32, PAL["allowed"]).move_to([0, -2.78, 0])
        self.play(FadeIn(count1))
        self.wait(1)
        self.snap("2-rule1")

        rule2 = T('rule 2:  when model = "large"\nthen  max_tool_calls >= 1', 30, PAL["fg"], mono=True, line_spacing=0.6).move_to(rule1)
        self.play(FadeOut(rule1), FadeOut(count1), Write(rule2))
        self.play(*exclude(excluded_by_rule2), run_time=1.5)
        n2 = sum(1 for m in MODELS for c in CALLS if not excluded_by_rule1(m, c) and not excluded_by_rule2(m, c))
        count2 = T(f"{n2} of 15 allowed; crossed cells are excluded", 30, PAL["allowed"]).move_to([0, -2.78, 0])
        self.play(FadeIn(count2))
        self.wait(2)
        self.snap("3-final")
