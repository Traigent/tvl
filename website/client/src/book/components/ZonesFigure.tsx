/**
 * Figure 13.1: what runs where. Zones stacked from top to bottom, each a titled band of
 * boxes; arrows between adjacent zones carry a label. Colour is never the only carrier:
 * every zone is named in its title, and a dashed arrow is also labelled.
 */
interface Zone {
  title: string;
  /** Box labels; "\n" breaks a line. */
  items: string[];
  /** The zone's accent: TVL's own zone uses "evidence", the others "excluded". */
  tone: "evidence" | "excluded";
}

interface Link {
  /** Index of the zone the arrow leaves. */
  from: number;
  /** Index of an adjacent zone. */
  to: number;
  label: string;
  /** Horizontal position of the arrow, as a fraction of the width. */
  at: number;
  dashed?: boolean;
}

const W = 640;
const PAD = 10;
const GAP = 8;
const LINE = 15;
const TITLE = 22;
const BETWEEN = 44;

export default function ZonesFigure({ alt, caption, zones, links }: { alt: string; caption: string; zones: Zone[]; links: Link[] }) {
  const lines = Math.max(...zones.flatMap((z) => z.items.map((i) => i.split("\n").length)));
  const boxH = lines * LINE + 12;
  const zoneH = TITLE + boxH + PAD;
  const top = (i: number) => i * (zoneH + BETWEEN);
  const H = top(zones.length - 1) + zoneH + 2;
  const text = { fontFamily: "var(--book-sans)", fill: "var(--book-fg)" } as const;
  return (
    <figure className="book-figure book-zones">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={alt} style={{ width: "100%", height: "auto", display: "block" }}>
        <defs>
          <marker id="zones-arrow" viewBox="0 0 10 10" refX={9} refY={5} markerWidth={7} markerHeight={7} orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--book-fg)" />
          </marker>
        </defs>
        <rect x={0} y={0} width={W} height={H} fill="var(--book-bg)" />
        {zones.map((z, i) => {
          const y = top(i);
          const colour = `var(--book-${z.tone})`;
          const n = z.items.length;
          const bw = (W - 2 * PAD - (n - 1) * GAP) / n;
          return (
            <g key={z.title}>
              <rect x={1} y={y + 1} width={W - 2} height={zoneH - 2} rx={8} fill="none" stroke={colour} strokeWidth={z.tone === "evidence" ? 2.5 : 1.5} />
              <text x={PAD} y={y + 16} fontSize={13.5} fontWeight={700} {...text} fill={colour}>
                {z.title}
              </text>
              {z.items.map((item, j) => {
                const bx = PAD + j * (bw + GAP);
                const by = y + TITLE;
                const parts = item.split("\n");
                const first = by + boxH / 2 - ((parts.length - 1) * LINE) / 2 + 4.5;
                return (
                  <g key={item}>
                    <rect x={bx} y={by} width={bw} height={boxH} rx={5} fill="var(--book-panel)" stroke="var(--book-line)" />
                    {parts.map((p, k) => (
                      <text key={k} x={bx + bw / 2} y={first + k * LINE} textAnchor="middle" fontSize={12.5} {...text}>
                        {p}
                      </text>
                    ))}
                  </g>
                );
              })}
            </g>
          );
        })}
        {links.map((l) => {
          const down = l.to > l.from;
          const upper = Math.min(l.from, l.to);
          const y1 = top(upper) + zoneH + 2;
          const y2 = top(upper + 1) - 2;
          const x = W * l.at;
          return (
            <g key={l.label}>
              <line
                x1={x}
                x2={x}
                y1={down ? y1 : y2}
                y2={down ? y2 : y1}
                stroke="var(--book-fg)"
                strokeWidth={1.6}
                strokeDasharray={l.dashed ? "5 4" : undefined}
                markerEnd="url(#zones-arrow)"
              />
              <text x={x + 8} y={(y1 + y2) / 2 + 4.5} fontSize={12.5} fontStyle="italic" {...text}>
                {l.label}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption>{caption}</figcaption>
    </figure>
  );
}
