"""Figure 5.1: better means not worse beyond the margin on any objective, and better
beyond the margin on at least one. Exact values; the band strip shows a banded objective.

Production brief (kept here, not on the public page): axes are resolution rate (up)
and cost per ticket, with the cheaper side to the left, so up-left is good on both.
Frame one: about twenty muted dots; the undominated ones turn to the foreground colour
and are joined by a line labelled 'front'. The camera then moves to one dot, the
incumbent, and a dashed rectangle grows around it (margins). Last, three candidates
drop in: A gets a check and 'better'; C lands inside the box with a neutral outline and
'tie'; B lands above the box but outside its cost edge and gets a cross with 'not
better: worse than the margin on cost'. The label 'Exact-value illustration; not
promotion verdicts' stays visible during the candidate comparison. Green, grey and
neutral each come with a check, a cross or a text label. A 1-D band strip sits beneath
the plot: the target range in the allowed colour, the candidate's mean as a dot with a
short confidence bar; a bar wholly inside the range gets a check and 'inside the band',
a bar that crosses an edge gets 'inconclusive: NoDecision'. Inside a band there is no
better or worse, so the strip has no arrow.
Print frames: (1) the front; (2) the incumbent with its margin box; (3) the three
candidates with verdicts, with the band strip beneath.

Facts shown (sources):
  incumbent 0.80 solved, $0.0120 per ticket (05-what-better-means.mdx, "The incumbent
    solves 80% of tickets at $0.0120 per ticket")
  margins 0.02 (solved) and $0.001 (cost): promotion_policy.min_effect in
    spec/examples/book/ch05/support-bot.tvl.yml lines 66-69
  candidates, from the chapter's table: A 0.83 / $0.0125 better; B 0.86 / $0.0135 not
    better (cost, beyond the margin); C 0.81 / $0.0118 tie
  band: reply_tokens, target [80, 250], test TOST (support-bot.tvl.yml lines 59-63);
    outcomes: inside with TOST evidence passes, outside rejects, otherwise NoDecision
    (chapter, "Bands"). The two band dots are unlabelled illustrations of those outcomes.
  axis ticks in the zoomed view are plain scale marks ($0.0110 ... $0.0140; 0.80, 0.85).

Made with Manim Community Edition (MIT). Original work; nothing here comes from
3Blue1Brown's videos or repositories.
"""

from __future__ import annotations

import sys
from pathlib import Path

from manim import (
    DOWN, LEFT, RIGHT, UP, Arrow, Circle, Create, DashedVMobject, FadeIn, FadeOut, GrowFromCenter,
    Line, Rectangle, ValueTracker, VGroup, VMobject, always_redraw, interpolate_color, ManimColor,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PAL, BookScene, T, check_mark, cross_mark  # noqa: E402

MARGIN_COST, MARGIN_SOLVED = 0.001, 0.02
INC = (0.0120, 0.80)  # (cost per ticket in dollars, share solved)
A, B, C = (0.0125, 0.83), (0.0135, 0.86), (0.0118, 0.81)

# Twenty designs: (cost, solved). Six are undominated (the front); INC is one of them.
FRONT_PTS = [(0.0068, 0.58), (0.0082, 0.68), (0.0098, 0.75), INC, (0.0145, 0.87), (0.0170, 0.92)]
OTHER_PTS = [
    (0.0078, 0.56), (0.0090, 0.63), (0.0095, 0.68), (0.0102, 0.70), (0.0108, 0.73), (0.0112, 0.71),
    (0.0125, 0.74), (0.0130, 0.77), (0.0135, 0.79), (0.0148, 0.80), (0.0150, 0.83), (0.0158, 0.86),
    (0.0165, 0.84), (0.0172, 0.88),
]
ALL_PTS = FRONT_PTS + OTHER_PTS


def undominated(pts):
    out = []
    for p in pts:
        dominated = any(q != p and q[0] <= p[0] and q[1] >= p[1] for q in pts)
        if not dominated:
            out.append(p)
    return sorted(out)


assert len(ALL_PTS) == 20
assert undominated(ALL_PTS) == sorted(FRONT_PTS), undominated(ALL_PTS)

# View windows (cost range, solved range): overview, then zoomed on the incumbent.
WIN0 = ((0.0060, 0.0180), (0.55, 0.95))
WIN1 = ((0.0102, 0.0141), (0.765, 0.885))
XL, XR = -3.9, 5.3  # plot box, left and right
YT = 2.7  # plot box top
YB0, YB1 = -1.9, 0.1  # plot box bottom, overview and final


def lerp(a, b, t):
    return a + (b - a) * t


class BetterWithMargins(BookScene):
    SPEED = 0.5  # keeps the scene inside the 6 to 12 s budget

    def construct(self) -> None:
        zt = ValueTracker(0.0)  # 0 overview, 1 zoomed
        bt = ValueTracker(0.0)  # plot bottom edge: 0 low (tall plot), 1 raised (room for the strip)
        ft = ValueTracker(0.0)  # front highlighted
        ot = ValueTracker(1.0)  # visibility of the dots other than the incumbent
        tk = ValueTracker(0.0)  # tick labels

        def yb():
            return lerp(YB0, YB1, bt.get_value())

        def window():
            z = zt.get_value()
            return (
                (lerp(WIN0[0][0], WIN1[0][0], z), lerp(WIN0[0][1], WIN1[0][1], z)),
                (lerp(WIN0[1][0], WIN1[1][0], z), lerp(WIN0[1][1], WIN1[1][1], z)),
            )

        def to_screen(cost, solved):
            (c0, c1), (s0, s1) = window()
            x = XL + (cost - c0) / (c1 - c0) * (XR - XL)
            y = yb() + (solved - s0) / (s1 - s0) * (YT - yb())
            return x, y

        def inside(x, y):
            return XL - 1e-6 <= x <= XR + 1e-6 and yb() - 1e-6 <= y <= YT + 1e-6

        # ---- axes, drawn from the trackers -------------------------------------
        def axes():
            return VGroup(
                Line([XL, yb(), 0], [XL, YT, 0], color=PAL["fg"], stroke_width=3),
                Line([XL, yb(), 0], [XR, yb(), 0], color=PAL["fg"], stroke_width=3),
            )

        def axis_titles():
            y = yb() - 0.42 - 0.45 * tk.get_value()
            g = VGroup()
            g.add(Arrow([-2.7, y, 0], [XL + 0.05, y, 0], buff=0, color=PAL["fg"], stroke_width=4, max_tip_length_to_length_ratio=0.35, tip_length=0.2))
            g.add(T("cheaper", 28, PAL["fg"]).move_to([-2.6, y, 0], aligned_edge=LEFT))
            g.add(T("cost per ticket", 28, PAL["fg"]).move_to([0.6, y, 0]))
            ymid = (yb() + YT) / 2
            g.add(T("solved", 28, PAL["fg"]).rotate(1.5708).move_to([-5.3, ymid - 0.1, 0]))
            g.add(Arrow([-5.3, ymid + 0.75, 0], [-5.3, min(ymid + 1.5, YT), 0], buff=0, color=PAL["fg"], stroke_width=4, max_tip_length_to_length_ratio=0.35, tip_length=0.2))
            return g

        def ticks():
            a = tk.get_value()
            g = VGroup()
            if a < 0.02:
                return g
            for cost in (0.0110, 0.0120, 0.0130):
                x, _ = to_screen(cost, 0.8)
                g.add(Line([x, yb(), 0], [x, yb() - 0.1, 0], color=PAL["fg"], stroke_width=3))
                g.add(T(f"${cost:.4f}", 28, PAL["muted"]).move_to([x, yb() - 0.32, 0]).set_opacity(a))
            for solved in (0.80, 0.85):
                _, y = to_screen(0.012, solved)
                g.add(Line([XL, y, 0], [XL - 0.1, y, 0], color=PAL["fg"], stroke_width=3))
                g.add(T(f"{solved:.2f}", 28, PAL["muted"]).move_to([XL - 0.62, y, 0]).set_opacity(a))
            return g

        # ---- the dots ----------------------------------------------------------
        mut = ManimColor(PAL["muted"])
        fg = ManimColor(PAL["fg"])

        def dots():
            f = ft.get_value()
            o = ot.get_value()
            g = VGroup()
            for p in ALL_PTS:
                x, y = to_screen(*p)
                if not inside(x, y):
                    continue
                is_front = p in FRONT_PTS
                if p == INC:
                    continue
                col = interpolate_color(mut, fg, f) if is_front else mut
                d = Circle(radius=0.11 if is_front and f > 0.5 else 0.09, color=col, stroke_width=0).set_fill(col, opacity=(0.9 if is_front else 0.7) * o).move_to([x, y, 0])
                g.add(d)
            # the front line, through the undominated dots in cost order
            if f > 0.02 and o > 0.02:
                fp = [to_screen(*p) for p in sorted(FRONT_PTS)]
                if all(inside(x, y) for x, y in fp):
                    line = VMobject(stroke_color=PAL["fg"], stroke_width=3, stroke_opacity=min(f, o))
                    line.set_points_as_corners([[x, y, 0] for x, y in fp])
                    g.add(line)
            x, y = to_screen(*INC)
            if inside(x, y):
                col = interpolate_color(mut, fg, max(f, zt.get_value()))
                g.add(Circle(radius=0.12, color=col, stroke_width=0).set_fill(col, opacity=1).move_to([x, y, 0]))
            return g

        ax = always_redraw(axes)
        titles = always_redraw(axis_titles)
        tick_g = always_redraw(ticks)
        dot_g = always_redraw(dots)

        # ---- phase 1: the cloud and the front ---------------------------------
        self.play(FadeIn(ax), FadeIn(titles), FadeIn(dot_g), run_time=1.0)
        self.wait(0.5)
        fx, fy = to_screen(0.0133, 0.835)
        front_label = T("front", 32, PAL["fg"]).move_to([fx - 0.3, fy + 0.55, 0])
        self.play(ft.animate.set_value(1.0), FadeIn(front_label), run_time=1.3)
        self.hold(1.0)
        self.snap("1-front")

        # ---- phase 2: the camera moves to the incumbent; the margin box grows ------
        self.play(
            FadeOut(front_label),
            zt.animate.set_value(1.0),
            run_time=2.6,
        )
        self.play(ot.animate.set_value(0.0), tk.animate.set_value(1.0), run_time=0.8)
        self.add(tick_g)
        ix, iy = to_screen(*INC)
        inc_lab = T("incumbent: 0.80 solved,\n$0.0120 per ticket", 28, PAL["fg"], line_spacing=0.8).move_to([-1.55, iy + 1.75, 0])
        leader = Line([ix - 1.0, inc_lab.get_bottom()[1] - 0.08, 0], [ix - 0.05, iy + 0.15, 0], color=PAL["muted"], stroke_width=2)
        self.play(FadeIn(inc_lab), Create(leader), run_time=0.8)

        bx = ValueTracker(0.0)  # margin box growth: 0 = a point, 1 = full size
        def box_fn():
            s_ = bx.get_value()
            lx, ly = to_screen(INC[0] - MARGIN_COST, INC[1] - MARGIN_SOLVED)
            rx, ry = to_screen(INC[0] + MARGIN_COST, INC[1] + MARGIN_SOLVED)
            if s_ < 0.02:
                return VGroup()
            r = Rectangle(width=(rx - lx) * s_, height=(ry - ly) * s_, color=PAL["fg"], stroke_width=3)
            r.move_to([(lx + rx) / 2, (ly + ry) / 2, 0])
            return DashedVMobject(r, num_dashes=44)
        box = always_redraw(box_fn)
        self.add(box)
        rx, ry = to_screen(INC[0] + MARGIN_COST, INC[1] + MARGIN_SOLVED)
        marg_lab = T("margins: 0.02 solved,\n$0.001 cost", 28, PAL["fg"], line_spacing=0.8).move_to([3.0, ry + 1.25, 0])
        marg_lead = Line([rx - 0.2, marg_lab.get_bottom()[1] - 0.08, 0], [rx - 0.2, ry + 0.03, 0], color=PAL["muted"], stroke_width=2)
        self.play(bx.animate.set_value(1.0), run_time=1.0)
        self.play(FadeIn(marg_lab), Create(marg_lead), run_time=0.8)
        self.hold(1.0)
        self.snap("2-margins")

        # ---- phase 3: three candidates, verdicts, the band strip ---------------------
        sl = ValueTracker(0.0)
        short_inc = always_redraw(lambda: T("incumbent", 28, PAL["fg"]).next_to([*to_screen(*INC), 0], RIGHT, buff=0.22).set_opacity(sl.get_value()))
        short_marg = always_redraw(lambda: T("margins", 28, PAL["fg"]).next_to([to_screen(INC[0] - MARGIN_COST, 0.8)[0], to_screen(0.012, 0.8)[1], 0], LEFT, buff=0.15).set_opacity(sl.get_value()))
        self.add(short_inc, short_marg)
        self.play(FadeOut(inc_lab), FadeOut(leader), FadeOut(marg_lab), FadeOut(marg_lead), run_time=0.6)
        self.play(bt.animate.set_value(1.0), sl.animate.set_value(1.0), run_time=1.6)
        banner = T("Exact-value illustration; not promotion verdicts", 28, PAL["muted"]).move_to([0, 2.93, 0])

        ax_, ay_ = to_screen(*A)
        bx_, by_ = to_screen(*B)
        cx_, cy_ = to_screen(*C)
        dot_a = Circle(radius=0.13, color=PAL["allowed"], stroke_width=0).set_fill(PAL["allowed"], opacity=1).move_to([ax_, ay_, 0])
        dot_b = Circle(radius=0.13, color=PAL["excluded"], stroke_width=0).set_fill(PAL["excluded"], opacity=1).move_to([bx_, by_, 0])
        dot_c = Circle(radius=0.13, color=PAL["fg"], stroke_width=3).set_fill(PAL["bg"], opacity=1).move_to([cx_, cy_, 0])
        mark_a = check_mark([ax_ + 0.45, ay_], 0.34, PAL["allowed"])
        lab_a = T("A: better", 28, PAL["fg"]).next_to([ax_ + 0.65, ay_, 0], RIGHT, buff=0.0)
        lab_c = T("C: tie", 28, PAL["fg"]).next_to([cx_ - 0.25, cy_, 0], LEFT, buff=0.0)
        lab_b = T("B: not better:\nworse than the margin on cost", 28, PAL["fg"], line_spacing=0.8)
        lab_b.move_to([bx_ - 0.45 - lab_b.width / 2, by_ + 0.0, 0])
        mark_b = cross_mark([bx_ + 0.42, by_], 0.34, PAL["excluded"])
        self.play(FadeIn(banner), run_time=0.5)
        self.play(FadeIn(dot_a, shift=DOWN * 0.5), run_time=0.6)
        self.play(FadeIn(mark_a), FadeIn(lab_a), run_time=0.5)
        self.play(FadeIn(dot_c, shift=DOWN * 0.5), run_time=0.6)
        self.play(FadeIn(lab_c), run_time=0.4)
        self.play(FadeIn(dot_b, shift=DOWN * 0.5), run_time=0.6)
        self.play(FadeIn(mark_b), FadeIn(lab_b), run_time=0.6)
        self.wait(0.6)

        # the band strip: target [80, 250] in the allowed colour, no arrow
        SX0, SXV = -2.6, 7.8 / 330.0  # screen x of 0 tokens, units per token
        def sx(v):
            return SX0 + v * SXV
        strip_axis_y, band_h = -2.45, 0.6
        axis_line = Line([sx(0), strip_axis_y, 0], [sx(330), strip_axis_y, 0], color=PAL["fg"], stroke_width=3)
        band = Rectangle(width=sx(250) - sx(80), height=band_h, color=PAL["allowed"], stroke_width=3).set_fill(PAL["allowed"], opacity=0.3)
        band.move_to([(sx(80) + sx(250)) / 2, strip_axis_y + band_h / 2, 0])
        tick80 = VGroup(Line([sx(80), strip_axis_y, 0], [sx(80), strip_axis_y - 0.1, 0], color=PAL["fg"], stroke_width=3),
                        T("80", 28, PAL["fg"]).move_to([sx(80), strip_axis_y - 0.32, 0]))
        tick250 = VGroup(Line([sx(250), strip_axis_y, 0], [sx(250), strip_axis_y - 0.1, 0], color=PAL["fg"], stroke_width=3),
                         T("250", 28, PAL["fg"]).move_to([sx(250), strip_axis_y - 0.32, 0]))
        strip_name = VGroup(T("reply_tokens", 28, PAL["fg"], mono=True), T("band [80, 250]", 28, PAL["fg"])).arrange(DOWN, aligned_edge=LEFT, buff=0.1)
        strip_name.move_to([-5.45, strip_axis_y + band_h / 2 - 0.05, 0], aligned_edge=LEFT)
        mid_y = strip_axis_y + band_h / 2

        def ci(mean, lo, hi, colour):
            bar = Line([sx(lo), mid_y, 0], [sx(hi), mid_y, 0], color=colour, stroke_width=4)
            caps = VGroup(*[Line([sx(v), mid_y - 0.13, 0], [sx(v), mid_y + 0.13, 0], color=colour, stroke_width=4) for v in (lo, hi)])
            dot = Circle(radius=0.11, color=colour, stroke_width=0).set_fill(colour, opacity=1).move_to([sx(mean), mid_y, 0])
            return VGroup(bar, caps, dot)
        ok_ci = ci(130, 105, 155, PAL["fg"])
        nd_ci = ci(245, 225, 275, PAL["fg"])
        ok_lab = VGroup(check_mark([0, 0], 0.34, PAL["allowed"]), T("inside the band", 28, PAL["fg"])).arrange(RIGHT, buff=0.15)
        ok_lab.move_to([sx(130), strip_axis_y + band_h + 0.45, 0])
        nd_mark = T("?", 32, PAL["unknown"])
        nd_text = T("inconclusive:\nNoDecision", 28, PAL["fg"], line_spacing=0.8)
        nd_lab = VGroup(nd_mark, nd_text).arrange(RIGHT, buff=0.15)
        nd_lab.move_to([sx(250) + 0.45, strip_axis_y + band_h + 0.55, 0])
        self.play(FadeIn(axis_line), FadeIn(band), FadeIn(tick80), FadeIn(tick250), FadeIn(strip_name), run_time=0.9)
        self.play(FadeIn(ok_ci), FadeIn(ok_lab), run_time=0.7)
        self.play(FadeIn(nd_ci), FadeIn(nd_lab), run_time=0.7)
        self.hold(1.0)
        self.snap("3-verdicts")
