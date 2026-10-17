/**
 * The cover motif: the design space as a grid of cells, drawn from the book's
 * own palette (allowed = green, excluded = grey with a cross). It is the picture
 * of the idea in chapters 3 and 4: every agent design is a cell, and rules cross
 * some of them out. Decorative: the title carries the meaning.
 */
const COLS = 9;
const ROWS = 5;
// Cells crossed out by two imaginary rules: the top-right corner and the bottom-left corner.
const excluded = (r: number, c: number) => (r === 0 && c >= 6) || (r === 1 && c >= 7) || (r === 2 && c === 8) || (r === ROWS - 1 && c <= 1) || (r === ROWS - 2 && c === 0);

export default function DesignSpaceMotif({ className }: { className?: string }) {
  const size = 36;
  const gap = 6;
  const w = COLS * size + (COLS - 1) * gap;
  const h = ROWS * size + (ROWS - 1) * gap;
  const cells = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const x = c * (size + gap);
      const y = r * (size + gap);
      const out = excluded(r, c);
      cells.push(
        <g key={`${r}-${c}`}>
          <rect
            x={x} y={y} width={size} height={size} rx={4}
            fill={out ? "var(--book-excluded)" : "var(--book-allowed)"}
            fillOpacity={out ? 0.18 : 0.38}
            stroke={out ? "var(--book-excluded)" : "var(--book-allowed)"}
            strokeWidth={2}
          />
          {out && (
            <path d={`M${x + 8} ${y + 8}L${x + size - 8} ${y + size - 8}M${x + size - 8} ${y + 8}L${x + 8} ${y + size - 8}`} stroke="var(--book-excluded)" strokeWidth={2.5} strokeLinecap="round" />
          )}
        </g>,
      );
    }
  }
  return (
    <svg className={className} viewBox={`-3 -3 ${w + 6} ${h + 6}`} aria-hidden="true" focusable="false">
      {cells}
    </svg>
  );
}
