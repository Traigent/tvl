"""Figure 4.2: an environment condition filters the whole design space at once.

Production brief (kept here, not on the public page): reuse the final state of the
design_space scene, twelve allowed cells and three crossed excluded cells. In front of
the grid a gate with two gauges, labelled in the mono font. Frame one: the gauges read
180 and 180, each with a check mark; the gate is open. Then the latency needle sweeps
from 180 to 420 while the capacity needle drops from 180 to 120. The capacity gauge
keeps its check, since 120 is still at least 100. On the latency gauge a reading of
exactly 300 still passes; only after the value exceeds 300 does the gauge turn red
(breach) and get a cross. Then the gate shuts and all twelve allowed cells dim to the
excluded grey at the same moment, with no per-cell crossing. A caption line names the
snapshot dates. Green = allowed, grey = excluded, red = the failed condition, each
colour paired with a check or cross. Print frames: (1) the open gate with both checks;
(2) the failed latency gauge, the passing capacity gauge at 120 and the whole grid greyed.

Facts shown (sources):
  grid: models small/medium/large, max_tool_calls 0,1,2,4,8; excluded by the two
    rules: small with 4 and 8, large with 0 -> 12 allowed (04-what-is-allowed.mdx, Fig 4.1;
    ch04/support-bot.tvl.yml constraints.structural)
  conditions, verbatim from constraints.derived (ch04/support-bot-resolved.tvl.yml
    lines 48-49): gateway_baseline_latency_ms <= 300 ; rpm_limit - rpm_current_load >= 100
  snapshot 2026-10-01T00:00:00Z: latency 180, rpm_limit 600, load 420 -> spare 180
    (support-bot-resolved.tvl.yml lines 7-14)
  snapshot 2026-10-14T09:00:00Z: latency 420, rpm_limit 600, load 480 -> spare 120
    (busy-gateway.tvl.yml lines 7-14; chapter text: "600 minus 480, which is 120")

Made with Manim Community Edition (MIT). Original work; nothing here comes from
3Blue1Brown's videos or repositories.
"""

from __future__ import annotations

import sys
from pathlib import Path

from manim import (
    DOWN, LEFT, RIGHT, UP, Create, FadeIn, FadeOut, Line, Rectangle, Polygon, ValueTracker,
    VGroup, always_redraw, linear, smooth,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import PAL, BookScene, T, check_mark, cross_mark  # noqa: E402

MODELS = ["small", "medium", "large"]
CALLS = [0, 1, 2, 4, 8]
EXCLUDED = {("small", 4), ("small", 8), ("large", 0)}  # the two rules of chapter 4

LAT_LIMIT, CAP_MIN = 300, 100
BAR_X0, BAR_W = -5.2, 6.0
LAT_MAX, CAP_MAX = 500, 300


class EnvironmentFilter(BookScene):
    SPEED = 0.9  # keeps the scene inside the 6 to 12 s budget

    def construct(self) -> None:
        # ---- the grid: final state of design_space (12 allowed, 3 crossed) -----------
        w, h, gap = 1.0, 0.5, 0.07
        gx, gy = -1.15, 2.45
        cells = {}
        grid = VGroup()
        for i, m in enumerate(MODELS):
            for j, c in enumerate(CALLS):
                r = Rectangle(width=w, height=h, stroke_width=2)
                r.move_to([gx + (j - 2) * (w + gap), gy - i * (h + gap), 0])
                if (m, c) in EXCLUDED:
                    r.set_fill(PAL["excluded"], opacity=0.25).set_stroke(PAL["excluded"])
                else:
                    r.set_fill(PAL["allowed"], opacity=0.35).set_stroke(PAL["allowed"])
                cells[(m, c)] = r
                grid.add(r)
        crosses = VGroup()
        for key in EXCLUDED:
            r = cells[key]
            crosses.add(
                Line(r.get_corner(UP + LEFT), r.get_corner(DOWN + RIGHT), color=PAL["excluded"], stroke_width=3),
                Line(r.get_corner(UP + RIGHT), r.get_corner(DOWN + LEFT), color=PAL["excluded"], stroke_width=3),
            )
        row_labels = VGroup(*[T(m, 28, PAL["fg"]).next_to(cells[(m, 0)], LEFT, buff=0.2) for m in MODELS])
        col_labels = VGroup(*[T(str(c), 28, PAL["fg"]).next_to(cells[("small", c)], UP, buff=0.08) for c in CALLS])
        status_open = VGroup(T("gate open", 30, PAL["allowed"]), T("12 allowed", 30, PAL["allowed"])).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        status_open.move_to([3.05, gy - 0.57, 0], aligned_edge=LEFT)
        status_open_mark = check_mark([2.7, gy - 0.3, 0], 0.4, PAL["allowed"])
        status_closed = VGroup(T("gate closed", 30, PAL["excluded"]), T("none pass", 30, PAL["excluded"])).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        status_closed.move_to([3.05, gy - 0.57, 0], aligned_edge=LEFT)
        status_closed_mark = cross_mark([2.7, gy - 0.3, 0], 0.4, PAL["excluded"])

        # ---- the gate: a bar that is drawn across the passage when it is closed -------
        gate_y = 0.62
        post_l = Rectangle(width=0.16, height=0.45, color=PAL["fg"], stroke_width=2).set_fill(PAL["fg"], opacity=1).move_to([-5.3, gate_y, 0])
        post_r = Rectangle(width=0.16, height=0.45, color=PAL["fg"], stroke_width=2).set_fill(PAL["fg"], opacity=1).move_to([5.3, gate_y, 0])
        open_t = ValueTracker(0.0)  # 0 = open, 1 = closed
        def gate_bar():
            t = open_t.get_value()
            end = -5.3 + 0.1 + (10.4 - 0.2) * (0.06 + 0.94 * t)
            colour = PAL["excluded"] if t > 0.5 else PAL["allowed"]
            return Line([-5.2, gate_y, 0], [end, gate_y, 0], color=colour, stroke_width=10)
        bar = always_redraw(gate_bar)

        # ---- the gauges ------------------------------------------------------------
        lat = ValueTracker(180)
        cap = ValueTracker(180)
        y_lat, y_cap = -0.4, -1.75  # bar centres

        def bar_x(value: float, vmax: float) -> float:
            return BAR_X0 + BAR_W * value / vmax

        def make_gauge(tracker, vmax, limit, y, ok_fn):
            def build():
                v = tracker.get_value()
                ok = ok_fn(v)
                col = PAL["allowed"] if ok else PAL["breach"]
                track = Rectangle(width=BAR_W, height=0.3, color=PAL["muted"], stroke_width=2).move_to([BAR_X0 + BAR_W / 2, y, 0])
                fill_w = max(BAR_W * v / vmax, 0.01)
                fill = Rectangle(width=fill_w, height=0.3, stroke_width=0).set_fill(col, opacity=0.55).move_to([BAR_X0 + fill_w / 2, y, 0])
                lim_x = bar_x(limit, vmax)
                lim = Line([lim_x, y - 0.3, 0], [lim_x, y + 0.3, 0], color=PAL["fg"], stroke_width=4)
                nx = bar_x(v, vmax)
                needle = Polygon([nx - 0.14, y - 0.42, 0], [nx + 0.14, y - 0.42, 0], [nx, y - 0.16, 0], color=col, stroke_width=2).set_fill(col, opacity=1)
                needle_line = Line([nx, y - 0.16, 0], [nx, y + 0.15, 0], color=col, stroke_width=5)
                mark = check_mark([3.0, y], 0.42, col) if ok else cross_mark([3.0, y], 0.42, col)
                return VGroup(track, fill, lim, needle, needle_line, mark)
            return always_redraw(build)

        gauge_lat = make_gauge(lat, LAT_MAX, LAT_LIMIT, y_lat, lambda v: v <= LAT_LIMIT + 1e-9)
        gauge_cap = make_gauge(cap, CAP_MAX, CAP_MIN, y_cap, lambda v: v >= CAP_MIN - 1e-9)
        cond_lat = T("gateway_baseline_latency_ms <= 300", 28, PAL["fg"], mono=True).move_to([BAR_X0, y_lat + 0.5, 0], aligned_edge=LEFT)
        cond_cap = T("rpm_limit - rpm_current_load >= 100", 28, PAL["fg"], mono=True).move_to([BAR_X0, y_cap + 0.5, 0], aligned_edge=LEFT)
        lim_lat = T("300", 28, PAL["muted"]).move_to([bar_x(LAT_LIMIT, LAT_MAX) + 0.0, y_lat + 0.0, 0]).shift(UP * 0.0)
        lim_lat.next_to([bar_x(LAT_LIMIT, LAT_MAX), y_lat - 0.3, 0], DOWN, buff=0.05).shift(RIGHT * 0.0)
        lim_cap = T("100", 28, PAL["muted"]).next_to([bar_x(CAP_MIN, CAP_MAX), y_cap - 0.3, 0], DOWN, buff=0.05)
        lat_read = always_redraw(lambda: T(f"{int(round(lat.get_value()))} ms", 30, PAL["fg"]).move_to([4.4, y_lat, 0]))
        cap_read = always_redraw(lambda: T(f"spare {int(round(cap.get_value()))}", 30, PAL["fg"]).move_to([4.4, y_cap, 0]))

        cap_line1 = T("snapshot 2026-10-01", 30, PAL["fg"]).move_to([0, -2.8, 0])
        cap_line2 = T("snapshot 2026-10-14", 30, PAL["fg"]).move_to([0, -2.8, 0])
        exact = T("exactly 300 still passes", 30, PAL["fg"]).move_to([0, -2.8, 0])

        # ---- frame 1: the open gate, both gauges passing -----------------------------
        self.play(FadeIn(grid), FadeIn(crosses), FadeIn(row_labels), FadeIn(col_labels), run_time=1.0)
        self.play(FadeIn(post_l), FadeIn(post_r), FadeIn(bar), FadeIn(status_open), FadeIn(status_open_mark), run_time=0.7)
        self.play(
            FadeIn(cond_lat), FadeIn(cond_cap), FadeIn(gauge_lat), FadeIn(gauge_cap),
            FadeIn(lim_lat), FadeIn(lim_cap), FadeIn(lat_read), FadeIn(cap_read), FadeIn(cap_line1),
            run_time=1.0,
        )
        self.hold(1.2)
        self.snap("1-open")

        # ---- the sweep: latency 180 -> 300 (pause, still passes) -> 420; capacity 180 -> 120
        self.play(FadeOut(cap_line1), FadeIn(cap_line2), run_time=0.5)
        self.play(lat.animate.set_value(300), cap.animate.set_value(150), run_time=1.6, rate_func=linear)
        self.play(FadeOut(cap_line2), FadeIn(exact), run_time=0.4)
        self.hold(1.0)
        self.play(FadeOut(exact), FadeIn(cap_line2), run_time=0.4)
        self.play(lat.animate.set_value(420), cap.animate.set_value(120), run_time=1.4, rate_func=linear)
        self.wait(0.5)

        # ---- the gate closes; every allowed cell greys together, no crossing ---------
        dim = [cells[k].animate.set_fill(PAL["excluded"], opacity=0.25).set_stroke(PAL["excluded"]) for k in cells if k not in EXCLUDED]
        self.play(
            open_t.animate.set_value(1.0),
            *dim,
            FadeOut(status_open), FadeOut(status_open_mark),
            FadeIn(status_closed), FadeIn(status_closed_mark),
            run_time=1.1,
        )
        self.hold(1.2)
        self.snap("2-closed")
