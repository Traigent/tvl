import { useState } from "react";

/** Pilot widget: slide the sample size and read a plain-language label. */
export function labelFor(n: number): string {
  if (n < 20) return "far too few samples to say anything";
  if (n < 100) return "enough for a rough impression only";
  if (n < 400) return "enough for a cautious decision";
  return "enough for a confident decision";
}

export const SAMPLE_POINTS = [10, 50, 200, 800];

export default function SampleSizeSlider() {
  const [n, setN] = useState(100);
  return (
    <div>
      <label htmlFor="n-slider">
        Sample size <b>n = {n}</b>
      </label>
      <input
        id="n-slider"
        type="range"
        min={0}
        max={1000}
        step={10}
        value={n}
        onChange={(e) => setN(Number(e.target.value))}
        style={{ width: "100%" }}
      />
      <p aria-live="polite">With {n} examples you have {labelFor(n)}.</p>
    </div>
  );
}
