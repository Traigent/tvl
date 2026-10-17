"""Figure 1.1: scattered rules only clash once they are gathered.

Production brief (kept here, not on the public page): four rounded boxes, one rule
each, glide into one file; the three rules about the model and the tool-call limit
get a red outline and a clash mark that links them, with the label 'no design obeys
all three'. The evaluation script's rule stays grey ('measured result: not part of
this clash'). Red always comes with the clash mark, never colour alone.
Print frames: (1) the four scattered boxes; (2) the four rules in one file, three marked.

Facts shown (source: 01-the-problem.mdx, table "One bot, four places", and the three
numbered rules; example spec/examples/book/ch01/scattered-rules.tvl.yml):
  boxes: prompt, config file, evaluation script, launch checklist
  rules: "at least 4 tool calls" (prompt), "small model: at most 2 tool calls" (config),
         "solved share must not drop" (evaluation script), "use the small model" (checklist)

Made with Manim Community Edition (MIT). Original work; nothing here comes from
3Blue1Brown's videos or repositories.
"""

from __future__ import annotations

import sys
from pathlib import Path

from manim import (
    DOWN, LEFT, RIGHT, UP, Create, FadeIn, FadeOut, Line, RoundedRectangle, VGroup, Write,
    Circle,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PAL, BookScene, T, cross_mark  # noqa: E402

# (box title, rule text in the mono font, grid position)
BOXES = [
    ("prompt", "at least 4\ntool calls", (-2.75, 1.35)),
    ("config file", "small model:\nat most 2 tool calls", (2.75, 1.35)),
    ("evaluation script", "solved share\nmust not drop", (-2.75, -1.35)),
    ("launch checklist", "use the\nsmall model", (2.75, -1.35)),
]
# Row order inside the gathered file: the three clashing rules together, then the grey one.
ORDER = ["launch checklist", "config file", "prompt", "evaluation script"]
CLASH = {"launch checklist", "config file", "prompt"}


class ScatteredToGathered(BookScene):
    def construct(self) -> None:
        boxes, rules, titles = {}, {}, {}
        for name, rule, (x, y) in BOXES:
            box = RoundedRectangle(corner_radius=0.18, width=5.2, height=2.3, color=PAL["muted"], stroke_width=3).move_to([x, y, 0])
            t = T(name, 30, PAL["muted"]).move_to([x, y + 0.82, 0])
            r = T(rule, 28, PAL["fg"], mono=True, line_spacing=0.7).move_to([x, y - 0.2, 0])
            boxes[name], rules[name], titles[name] = box, r, t
        self.play(*[Create(b) for b in boxes.values()], *[FadeIn(t) for t in titles.values()], run_time=1.0)
        self.play(*[FadeIn(r) for r in rules.values()], run_time=0.8)
        self.hold(1.2)
        self.snap("1-scattered")

        # The single file outline, with the rules gliding in one at a time.
        file_w, file_h = 5.8, 5.0
        file_box = RoundedRectangle(corner_radius=0.12, width=file_w, height=file_h, color=PAL["fg"], stroke_width=3).move_to([-2.3, -0.0, 0])
        file_title = T("one file", 30, PAL["fg"]).move_to([-2.3, file_h / 2 - 0.3, 0])
        row_y = {name: file_h / 2 - 1.05 - i * 1.12 for i, name in enumerate(ORDER)}
        self.play(
            *[FadeOut(t) for t in titles.values()],
            *[FadeOut(b) for b in boxes.values()],
            Create(file_box), FadeIn(file_title),
            run_time=0.9,
        )
        # The boxes are gone; the rules stay put until they glide, so the move reads as gathering.
        for name in ORDER:
            self.play(rules[name].animate.move_to([-2.3, row_y[name], 0]), run_time=0.6)

        # Clash: red outlines + a bracket with a clash mark that links the three rules.
        rects = {}
        for name in ORDER:
            colour = PAL["breach"] if name in CLASH else PAL["excluded"]
            rects[name] = RoundedRectangle(corner_radius=0.1, width=5.2, height=0.98, color=colour, stroke_width=3).move_to([-2.3, row_y[name], 0])
        self.play(*[Create(r) for r in rects.values()], run_time=0.8)

        top = rects["launch checklist"].get_right()
        bot = rects["prompt"].get_right()
        mid_x = top[0] + 0.55
        bracket = VGroup(
            Line(top, [mid_x, top[1], 0], color=PAL["breach"], stroke_width=4),
            Line([mid_x, top[1], 0], [mid_x, bot[1], 0], color=PAL["breach"], stroke_width=4),
            Line([mid_x, bot[1], 0], bot, color=PAL["breach"], stroke_width=4),
        )
        mid_y = (top[1] + bot[1]) / 2
        clash = VGroup(
            Circle(radius=0.3, color=PAL["breach"], stroke_width=4).set_fill(PAL["bg"], opacity=1).move_to([mid_x, mid_y, 0]),
            cross_mark([mid_x, mid_y, 0], size=0.34, color=PAL["breach"], width=5),
        )
        verdict = T("no design obeys\nall three", 36, PAL["breach"], line_spacing=0.8).move_to([3.5, mid_y, 0])
        grey_note = T("measured result:\nnot part of\nthis clash", 30, PAL["excluded"], line_spacing=0.8).move_to([3.4, row_y["evaluation script"], 0])
        self.play(Create(bracket), run_time=0.7)
        self.play(FadeIn(clash), Write(verdict), run_time=1.0)
        self.play(FadeIn(grey_note), run_time=0.6)
        self.hold(1.2)
        self.snap("2-gathered")
