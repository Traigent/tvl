import { useEffect, useId, useRef, useState } from "react";
import { usePrint } from "../context";
import { beginPending, reportBookError } from "./pending";

interface MermaidProps {
  chart: string;
  alt: string;
  caption?: string;
}

export default function Mermaid({ chart, alt, caption }: MermaidProps) {
  const print = usePrint();
  const rawId = useId().replace(/[^a-zA-Z0-9]/g, "");
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");

  useEffect(() => {
    const done = beginPending();
    let cancelled = false;
    (async () => {
      try {
        const { default: mermaid } = await import("mermaid");
        const dark = !print && document.documentElement.classList.contains("dark");
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: dark ? "dark" : "neutral",
          fontFamily: "'Book Sans', sans-serif",
        });
        const { svg } = await mermaid.render(`mmd-${rawId}`, chart);
        if (!cancelled) setSvg(svg);
      } catch (e) {
        reportBookError(`mermaid: ${String(e)}`);
      } finally {
        done();
      }
    })();
    return () => {
      cancelled = true;
      done();
    };
  }, [chart, print, rawId]);

  return (
    <figure className="book-figure book-mermaid">
      <div ref={ref} role="img" aria-label={alt} dangerouslySetInnerHTML={{ __html: svg }} />
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  );
}
