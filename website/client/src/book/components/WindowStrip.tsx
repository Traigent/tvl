/**
 * Figure 10.1: an illustrative run of 6-hour windows of one runtime monitor. Each cell
 * is a window with its counts and its verdict; a bracket marks the episode, and a
 * second bracket the recovery deadline in window time. The verdicts are those of the
 * exact-rational method for the counts shown, with every unit classified; the book's
 * output check recomputes them. Colour is never the only carrier: every cell names
 * its verdict.
 */
interface Cell {
  label: string;
  n: number;
  k: number;
  verdict: string;
  tone: "evidence" | "unknown" | "breach";
}

const W = 640;
const LEFT = 6;
const TOP = 8;
const CELL_H = 74;

export default function WindowStrip({
  alt,
  caption,
  cells,
  episode,
  deadline,
}: {
  alt: string;
  caption: string;
  cells: Cell[];
  /** First and last cell index of the episode. */
  episode: [number, number];
  /** Cell index whose end is the recovery deadline, and its label. */
  deadline: { at: number; label: string };
}) {
  const cw = (W - 2 * LEFT) / cells.length;
  const H = TOP + CELL_H + 74;
  const text = { fontFamily: "var(--book-sans)", fill: "var(--book-fg)" } as const;
  const x = (i: number) => LEFT + cw * i;
  const by1 = TOP + CELL_H + 16;
  const by2 = by1 + 30;
  return (
    <figure className="book-figure book-windows">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={alt} style={{ width: "100%", height: "auto", display: "block" }}>
        <rect x={0} y={0} width={W} height={H} fill="var(--book-bg)" />
        {cells.map((c, i) => {
          const colour = `var(--book-${c.tone})`;
          return (
            <g key={c.label}>
              <rect x={x(i) + 2} y={TOP} width={cw - 4} height={CELL_H} rx={4} fill="var(--book-panel)" stroke={colour} strokeWidth={2.5} />
              <text x={x(i) + cw / 2} y={TOP + 17} textAnchor="middle" fontSize={12.5} fontWeight={700} {...text}>
                {c.label}
              </text>
              <text x={x(i) + cw / 2} y={TOP + 36} textAnchor="middle" fontSize={12} {...text}>
                {`${c.k} of ${c.n}`}
              </text>
              <text x={x(i) + cw / 2} y={TOP + 58} textAnchor="middle" fontSize={11.5} fontWeight={700} fill={colour} fontFamily="var(--book-sans)">
                {c.verdict}
              </text>
            </g>
          );
        })}
        {/* episode bracket */}
        <line x1={x(episode[0]) + 4} x2={x(episode[1] + 1) - 4} y1={by1} y2={by1} stroke="var(--book-breach)" strokeWidth={2} />
        <line x1={x(episode[0]) + 4} x2={x(episode[0]) + 4} y1={by1 - 6} y2={by1 + 6} stroke="var(--book-breach)" strokeWidth={2} />
        <line x1={x(episode[1] + 1) - 4} x2={x(episode[1] + 1) - 4} y1={by1 - 6} y2={by1 + 6} stroke="var(--book-breach)" strokeWidth={2} />
        <text x={LEFT + 2} y={by1 + 16} fontSize={12} {...text}>
          {`episode (red): opens at ${cells[episode[0]].label}, the first BREACHED window; resolves after 2 MET windows in a row`}
        </text>
        {/* recovery deadline, in window time: from the end of the opening window */}
        <line x1={x(episode[0] + 1)} x2={x(deadline.at + 1)} y1={by2 + 8} y2={by2 + 8} stroke="var(--book-muted)" strokeWidth={1.5} strokeDasharray="5 3" />
        <line x1={x(episode[0] + 1)} x2={x(episode[0] + 1)} y1={by2 + 2} y2={by2 + 14} stroke="var(--book-muted)" strokeWidth={1.5} />
        <line x1={x(deadline.at + 1)} x2={x(deadline.at + 1)} y1={by2 + 2} y2={by2 + 14} stroke="var(--book-muted)" strokeWidth={1.5} />
        <text x={LEFT + 2} y={by2 + 26} fontSize={12} fill="var(--book-muted)" fontFamily="var(--book-sans)">
          {deadline.label}
        </text>
      </svg>
      <figcaption>{caption}</figcaption>
    </figure>
  );
}
