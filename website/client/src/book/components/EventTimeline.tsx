/**
 * Figure 9.1: illustrative unit histories for one event pattern. Each row is one unit
 * (a trace): its events in execution order, left to right, and the outcome that the
 * predicate's definition gives that complete history. Colour is never the only
 * carrier: every row names its outcome, and a violating event is also struck through.
 */
interface Mark {
  /** Short event label, e.g. "approve T1". */
  label: string;
  /** The event that makes the history violate. */
  culprit?: boolean;
}

interface Row {
  label: string;
  outcome: string;
  tone: "allowed" | "breach";
  events: Mark[];
}

const W = 640;
const LEFT = 8;
const ROW = 58;
const TOP = 12; // row label above the line, event labels below it
const SLOT = 132;
const FIRST = 150;

export default function EventTimeline({ alt, caption, rows }: { alt: string; caption: string; rows: Row[] }) {
  const H = TOP + ROW * rows.length + 4;
  const text = { fontFamily: "var(--book-sans)", fill: "var(--book-fg)" } as const;
  return (
    <figure className="book-figure book-timeline">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={alt} style={{ width: "100%", height: "auto", display: "block" }}>
        <rect x={0} y={0} width={W} height={H} fill="var(--book-bg)" />
        {rows.map((r, i) => {
          const y = TOP + ROW * i;
          const cy = y + 34;
          const colour = `var(--book-${r.tone})`;
          const end = FIRST + SLOT * (r.events.length - 1);
          return (
            <g key={r.label}>
              <text x={LEFT} y={y + 12} fontSize={13} fontWeight={700} {...text}>
                {r.label}
              </text>
              <text x={LEFT} y={cy + 5} fontSize={13} fill={colour} fontFamily="var(--book-sans)" fontWeight={700}>
                {r.outcome}
              </text>
              <line x1={FIRST - 16} x2={Math.max(end + 16, FIRST + 16)} y1={cy} y2={cy} stroke="var(--book-line)" strokeWidth={2} />
              {r.events.map((e, j) => {
                const cx = FIRST + SLOT * j;
                const c = e.culprit ? "var(--book-breach)" : "var(--book-evidence)";
                return (
                  <g key={j}>
                    <circle cx={cx} cy={cy} r={6} fill={c} stroke="var(--book-bg)" strokeWidth={1.5} />
                    {e.culprit && <line x1={cx - 9} x2={cx + 9} y1={cy - 9} y2={cy + 9} stroke={c} strokeWidth={2.5} />}
                    <text x={cx} y={cy + 20} textAnchor="middle" fontSize={12.5} {...text} fontWeight={e.culprit ? 700 : 400}>
                      {e.label}
                    </text>
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      <figcaption>{caption}</figcaption>
    </figure>
  );
}
