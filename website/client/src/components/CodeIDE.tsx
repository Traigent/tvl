import { Fragment, useMemo } from "react";
import type { ReactNode } from "react";
import type Prism from "prismjs";

import { resolvePrismLanguage, tokenizeCode } from "@/lib/prism";

interface CodeIDEProps {
  code: string;
  language: string;
  filename?: string;
}

export default function CodeIDE({ code, language, filename }: CodeIDEProps) {
  const resolvedLanguage = resolvePrismLanguage(language);
  const tokens = useMemo(() => tokenizeCode(code, resolvedLanguage), [code, resolvedLanguage]);

  const renderToken = (token: string | Prism.Token, key: string): ReactNode => {
    if (typeof token === "string") {
      return <Fragment key={key}>{token}</Fragment>;
    }

    const aliases = Array.isArray(token.alias)
      ? token.alias
      : token.alias
        ? [token.alias]
        : [];
    const className = ["token", token.type, ...aliases].join(" ");
    const content = Array.isArray(token.content)
      ? token.content.map((child, index) => renderToken(child, `${key}-${index}`))
      : renderToken(token.content as string | Prism.Token, `${key}-0`);

    return (
      <span key={key} className={className}>
        {content}
      </span>
    );
  };

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
        <code className={`language-${resolvedLanguage}`}>
          {tokens.map((token, index) => renderToken(token, `${resolvedLanguage}-${index}`))}
        </code>
      </pre>
    </div>
  );
}
