import data from "../data/coverage-studies.json";

/**
 * Figure 6.1: what "95% confidence" promises. Each column is one SIMULATED study
 * of a process whose true violation rate is known. The data is computed by
 * book/support-bot/confidence.py with the gate's own upper-bound function, and a
 * test checks the JSON against a fresh run. Colour is never the only carrier:
 * a study whose bound misses the true rate also gets a cross and a label.
 */
interface Study {
  study: number;
  violations: number;
  trials: number;
  upper_bound: number;
  covers: boolean;
}

const W = 640;
const H = 310;
const LEFT = 52;
const RIGHT = 74;
const TOP = 34;
const BOTTOM = 62;
const Y_MAX = 0.14;
const TICKS = [0, 0.02, 0.04, 0.06, 0.08, 0.1, 0.12, 0.14];

export default function CoverageFigure({ alt, caption }: { alt: string; caption: string }) {
  const studies = data.studies as Study[];
  const plotW = W - LEFT - RIGHT;
  const plotH = H - TOP - BOTTOM;
  const step = plotW / studies.length;
  const x = (i: number) => LEFT + step * (i + 0.5);
  const y = (v: number) => TOP + plotH * (1 - v / Y_MAX);
  const pct = (v: number) => `${Math.round(v * 1000) / 10}%`;
  const misses = studies.filter((s) => !s.covers);

  return (
    <figure className="book-figure book-coverage">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={alt} style={{ width: "100%", height: "auto", display: "block" }}>
        <rect x={0} y={0} width={W} height={H} fill="var(--book-bg)" />
        {TICKS.map((t) => (
          <g key={t}>
            <line x1={LEFT} x2={W - RIGHT} y1={y(t)} y2={y(t)} stroke="var(--book-line)" strokeWidth={1} />
            <text x={LEFT - 8} y={y(t) + 4} textAnchor="end" fontSize={12} fill="var(--book-muted)" fontFamily="var(--book-sans)">
              {pct(t)}
            </text>
          </g>
        ))}
        <text x={LEFT} y={TOP - 14} fontSize={12} fill="var(--book-muted)" fontFamily="var(--book-sans)">
          violation rate
        </text>
        <g aria-hidden="true">
          <line x1={W - RIGHT - 4} x2={W - RIGHT - 4} y1={TOP - 6} y2={TOP - 22} stroke="var(--book-evidence)" strokeWidth={1} strokeOpacity={0.5} />
          <line x1={W - RIGHT - 8} x2={W - RIGHT} y1={TOP - 22} y2={TOP - 22} stroke="var(--book-evidence)" strokeWidth={2.5} strokeLinecap="round" />
          <text x={W - RIGHT - 14} y={TOP - 14} textAnchor="end" fontSize={13} fill="var(--book-fg)" fontFamily="var(--book-sans)">
            {`each line is one study's ${Math.round(data.confidence * 100)}% upper bound (the tick)`}
          </text>
        </g>
        {studies.map((s, i) => {
          const colour = s.covers ? "var(--book-evidence)" : "var(--book-breach)";
          const top = y(s.upper_bound);
          return (
            <g key={s.study}>
              <line x1={x(i)} x2={x(i)} y1={y(0)} y2={top} stroke={colour} strokeWidth={1} strokeOpacity={s.covers ? 0.4 : 0.8} />
              <line x1={x(i) - 3.5} x2={x(i) + 3.5} y1={top} y2={top} stroke={colour} strokeWidth={2.5} strokeLinecap="round" />
            </g>
          );
        })}
        <line x1={LEFT} x2={W - RIGHT} y1={y(data.true_rate)} y2={y(data.true_rate)} stroke="var(--book-fg)" strokeWidth={2} strokeDasharray="6 4" />
        <text x={W - RIGHT + 8} y={y(data.true_rate) - 3} fontSize={13} fill="var(--book-fg)" fontFamily="var(--book-sans)">
          true rate
        </text>
        <text x={W - RIGHT + 8} y={y(data.true_rate) + 13} fontSize={13} fill="var(--book-fg)" fontFamily="var(--book-sans)">
          {pct(data.true_rate)}
        </text>
        {misses.map((s) => {
          const i = studies.indexOf(s);
          const cy = y(0) + 14;
          return (
            <path
              key={`miss-${s.study}`}
              d={`M${x(i) - 5} ${cy - 5}L${x(i) + 5} ${cy + 5}M${x(i) + 5} ${cy - 5}L${x(i) - 5} ${cy + 5}`}
              stroke="var(--book-breach)"
              strokeWidth={2.5}
              strokeLinecap="round"
            />
          );
        })}
        {misses.length > 0 && (
          <text
            x={x(studies.indexOf(misses[0])) - 10}
            y={y(0) + 19}
            textAnchor="end"
            fontSize={13}
            fill="var(--book-fg)"
            fontFamily="var(--book-sans)"
          >
            {`bound below the true rate: ${misses.length} studies`}
          </text>
        )}
        <text x={LEFT + plotW / 2} y={H - 10} textAnchor="middle" fontSize={13} fill="var(--book-muted)" fontFamily="var(--book-sans)">
          {`${studies.length} simulated studies, ${data.trials} trials each`}
        </text>
      </svg>
      <figcaption>{caption}</figcaption>
    </figure>
  );
}
