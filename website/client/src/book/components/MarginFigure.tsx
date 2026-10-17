/**
 * Figure 6.3: the three tests read from one interval. A number line of the
 * difference candidate minus incumbent, with the margin as a shaded strip around
 * zero; each row is one run's interval for the difference, with a dot at the
 * observed difference. The numbers come from the gate's --json reports (the chapter
 * passes them in; the book's output check recomputes them from fresh runs).
 * Colour is never the only carrier: each row also names its verdict.
 */
interface Row {
  label: string;
  verdict: string;
  delta: number;
  lo: number;
  hi: number;
  tone: "evidence" | "unknown" | "breach";
}

const W = 640;
const LEFT = 16;
const RIGHT = 16;
const TOP = 40;
const ROW = 46;
const AXIS_GAP = 18;
const BOTTOM = 46;

export default function MarginFigure({
  alt,
  caption,
  margin,
  min,
  max,
  unit,
  rows,
}: {
  alt: string;
  caption: string;
  margin: number;
  min: number;
  max: number;
  /** Multiply values by this for the tick labels (100: points). */
  unit: number;
  rows: Row[];
}) {
  const H = TOP + ROW * rows.length + AXIS_GAP + BOTTOM;
  const plotW = W - LEFT - RIGHT;
  const x = (v: number) => LEFT + (plotW * (v - min)) / (max - min);
  const axisY = TOP + ROW * rows.length + AXIS_GAP / 2;
  const step = 0.1;
  const ticks: number[] = [];
  for (let t = Math.ceil(min / step) * step; t <= max + 1e-9; t += step) ticks.push(Math.round(t * 100) / 100);
  const fmt = (v: number) => {
    const n = Math.round(v * unit);
    return n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "0";
  };
  const text = { fontFamily: "var(--book-sans)", fill: "var(--book-fg)" } as const;

  return (
    <figure className="book-figure book-margin">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={alt} style={{ width: "100%", height: "auto", display: "block" }}>
        <rect x={0} y={0} width={W} height={H} fill="var(--book-bg)" />
        {/* the margin strip and its edges */}
        <rect x={x(-margin)} y={TOP - 8} width={x(margin) - x(-margin)} height={axisY - TOP + 8} fill="var(--book-panel)" />
        {[-margin, margin].map((m) => (
          <line key={m} x1={x(m)} x2={x(m)} y1={TOP - 8} y2={axisY} stroke="var(--book-muted)" strokeWidth={1.2} strokeDasharray="4 3" />
        ))}
        <line x1={x(0)} x2={x(0)} y1={TOP - 8} y2={axisY} stroke="var(--book-line)" strokeWidth={1} />
        {/* zone labels */}
        <text x={x(-margin) - 8} y={TOP - 18} textAnchor="end" fontSize={13} {...text}>
          {`← worse by more than the margin`}
        </text>
        <text x={x(margin) + 8} y={TOP - 18} fontSize={13} {...text}>
          {`better by more than the margin →`}
        </text>
        <text x={x(0)} y={TOP - 18} textAnchor="middle" fontSize={12} fill="var(--book-muted)" fontFamily="var(--book-sans)">
          {`±${fmt(margin).replace("+", "")}`}
        </text>
        {rows.map((r, i) => {
          const cy = TOP + ROW * i + ROW / 2 + 10;
          const colour = `var(--book-${r.tone})`;
          // The label sits above its line and starts at the line's left end, so it reads
          // left to right inside the plot.
          return (
            <g key={r.label}>
              <line x1={x(r.lo)} x2={x(r.hi)} y1={cy} y2={cy} stroke={colour} strokeWidth={3} strokeLinecap="butt" />
              <line x1={x(r.lo)} x2={x(r.lo)} y1={cy - 7} y2={cy + 7} stroke={colour} strokeWidth={2.5} />
              <line x1={x(r.hi)} x2={x(r.hi)} y1={cy - 7} y2={cy + 7} stroke={colour} strokeWidth={2.5} />
              <circle cx={x(r.delta)} cy={cy} r={5} fill={colour} stroke="var(--book-bg)" strokeWidth={1.5} />
              <text
                x={x(r.lo)}
                y={cy - 12}
                fontSize={13}
                stroke="var(--book-bg)"
                strokeWidth={5}
                paintOrder="stroke"
                strokeLinejoin="round"
                {...text}
              >
                {`${r.label}: `}
                <tspan fontWeight={700}>{r.verdict}</tspan>
              </text>
            </g>
          );
        })}
        {/* the axis */}
        <line x1={LEFT} x2={W - RIGHT} y1={axisY} y2={axisY} stroke="var(--book-fg)" strokeWidth={1} />
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={axisY} y2={axisY + 5} stroke="var(--book-fg)" strokeWidth={1} />
            <text x={x(t)} y={axisY + 19} textAnchor="middle" fontSize={12} fill="var(--book-muted)" fontFamily="var(--book-sans)">
              {fmt(t)}
            </text>
          </g>
        ))}
        <text x={LEFT + plotW / 2} y={H - 8} textAnchor="middle" fontSize={13} fill="var(--book-muted)" fontFamily="var(--book-sans)">
          difference in resolution rate, candidate minus incumbent (points); dot: observed, line: 90% interval
        </text>
      </svg>
      <figcaption>{caption}</figcaption>
    </figure>
  );
}
