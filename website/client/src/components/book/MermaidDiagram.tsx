import { useEffect, useId, useState } from "react";
import mermaid from "mermaid";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

let mermaidInitialized = false;

function ensureMermaid() {
  if (mermaidInitialized) {
    return;
  }
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    theme: "base",
    flowchart: {
      useMaxWidth: false,
      htmlLabels: true,
    },
    themeVariables: {
      darkMode: false,
      background: "#f8fafc",
      primaryColor: "#e0f2fe",
      primaryTextColor: "#0f172a",
      primaryBorderColor: "#0284c7",
      lineColor: "#0369a1",
      secondaryColor: "#eff6ff",
      tertiaryColor: "#f8fafc",
      textColor: "#0f172a",
      fontFamily: "Inter, sans-serif",
      fontSize: "18px",
    },
  });
  mermaidInitialized = true;
}

interface MermaidDiagramProps {
  chart: string;
}

export default function MermaidDiagram({ chart }: MermaidDiagramProps) {
  const [svg, setSvg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const id = useId().replace(/:/g, "-");

  useEffect(() => {
    let active = true;
    ensureMermaid();

    mermaid
      .render(`tvl-book-mermaid-${id}`, chart)
      .then(({ svg: rendered }) => {
        if (active) {
          setSvg(rendered);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to render mermaid diagram.");
        }
      });

    return () => {
      active = false;
    };
  }, [chart, id]);

  return (
    <Card className="my-6 overflow-hidden border-sky-300/30 bg-[linear-gradient(180deg,_#f8fbff,_#eef6ff)] shadow-xl shadow-sky-500/5 ring-1 ring-sky-200/40">
      <CardHeader className="border-b border-sky-300/20 bg-gradient-to-r from-sky-100 via-slate-50 to-white">
        <CardTitle className="text-base text-slate-900">System Diagram</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto p-4">
        {error ? (
          <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        ) : (
          <div
            className="mermaid-shell min-w-max text-slate-900"
            // Mermaid returns an SVG string. We only inject renderer output after
            // initializing Mermaid with `securityLevel: "strict"` above.
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        )}
      </CardContent>
    </Card>
  );
}
