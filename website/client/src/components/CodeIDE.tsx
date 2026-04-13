import { useMemo } from "react";

import { highlightCode, resolvePrismLanguage } from "@/lib/prism";

interface CodeIDEProps {
  code: string;
  language: string;
  filename?: string;
}

export default function CodeIDE({ code, language, filename }: CodeIDEProps) {
  const resolvedLanguage = resolvePrismLanguage(language);
  const highlighted = useMemo(() => highlightCode(code, resolvedLanguage), [code, resolvedLanguage]);

  return (
    <div className="code-ide overflow-hidden rounded-lg border border-border/70 bg-card/40">
      <div className="flex items-center justify-between border-b border-border/60 bg-muted/35 px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-red-400/80" />
          <span className="h-2.5 w-2.5 rounded-full bg-yellow-400/80" />
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" />
          {filename ? <span className="ml-2 text-xs text-muted-foreground">{filename}</span> : null}
        </div>
        <span className="rounded border border-border/70 bg-background/60 px-2 py-0.5 text-[11px] uppercase tracking-wide text-muted-foreground">
          {resolvedLanguage}
        </span>
      </div>
      <pre className="m-0 overflow-x-auto px-4 py-4 text-sm">
        <code
          className={`language-${resolvedLanguage}`}
          dangerouslySetInnerHTML={{ __html: highlighted }}
        />
      </pre>
    </div>
  );
}

