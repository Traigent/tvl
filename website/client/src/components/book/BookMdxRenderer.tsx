import type { ComponentType, HTMLAttributes, ReactElement, ReactNode } from "react";
import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";

import ConceptCallout from "@/components/book/ConceptCallout";
import CommandSequence from "@/components/book/CommandSequence";
import GlossaryTerm from "@/components/book/GlossaryTerm";
import KnowledgeCheck from "@/components/book/KnowledgeCheck";
import MermaidDiagram from "@/components/book/MermaidDiagram";
import MicrosimEmbed from "@/components/book/MicrosimEmbed";
import PitfallCard from "@/components/book/PitfallCard";
import PredictionPrompt from "@/components/book/PredictionPrompt";
import WorkedExample from "@/components/book/WorkedExample";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type MdxModule = {
  default: ComponentType<Record<string, unknown>>;
};

const mdxModules = import.meta.glob<MdxModule>("/src/generated/book/content/**/*.mdx");

function extractCode(node: ReactNode): { code: string; language: string } | null {
  if (!node || typeof node !== "object") {
    return null;
  }
  const element = node as ReactElement<{ className?: string; children?: ReactNode }>;
  const raw = element.props?.children;
  if (typeof raw !== "string") {
    return null;
  }
  const className = element.props?.className ?? "";
  const match = className.match(/language-([\w-]+)/);
  return {
    code: raw.replace(/\n$/, ""),
    language: match?.[1] ?? "text",
  };
}

function BookPre({ children, ...props }: HTMLAttributes<HTMLPreElement>) {
  const code = extractCode(children);
  if (!code) {
    return <pre {...props}>{children}</pre>;
  }
  if (["bash", "shell", "sh"].includes(code.language)) {
    return <CommandSequence code={code.code} language={code.language} />;
  }
  return <WorkedExample code={code.code} language={code.language} />;
}

const mdxComponents = {
  pre: BookPre,
  code: ({
    className,
    children,
    ...props
  }: HTMLAttributes<HTMLElement> & { children?: ReactNode }) => {
    if (className?.startsWith("language-")) {
      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code
        className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[0.9em] text-primary"
        {...props}
      >
        {children}
      </code>
    );
  },
  a: ({
    href,
    children,
    ...props
  }: HTMLAttributes<HTMLAnchorElement> & { href?: string; children?: ReactNode }) => (
    <a
      href={href}
      className="font-medium text-sky-300 underline decoration-sky-400/40 underline-offset-4 hover:text-sky-200"
      {...props}
    >
      {children}
    </a>
  ),
  table: ({ className, ...props }: HTMLAttributes<HTMLTableElement>) => (
    <div className="my-6 overflow-x-auto">
      <table className={cn("min-w-full border-collapse text-sm", className)} {...props} />
    </div>
  ),
  th: ({ className, ...props }: HTMLAttributes<HTMLTableCellElement>) => (
    <th
      className={cn(
        "border-b border-border/60 bg-muted/40 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground",
        className,
      )}
      {...props}
    />
  ),
  td: ({ className, ...props }: HTMLAttributes<HTMLTableCellElement>) => (
    <td className={cn("border-b border-border/40 px-3 py-2 align-top", className)} {...props} />
  ),
  ConceptCallout,
  Term: GlossaryTerm,
  KnowledgeCheck,
  PitfallCard,
  MermaidDiagram,
  MicrosimEmbed,
  PredictionPrompt,
};

interface BookMdxRendererProps {
  modulePath: string;
  className?: string;
}

export default function BookMdxRenderer({
  modulePath,
  className,
}: BookMdxRendererProps) {
  const [Component, setComponent] = useState<ComponentType<Record<string, unknown>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const loader = mdxModules[modulePath];
    if (!loader) {
      setError(`Missing compiled book module: ${modulePath}`);
      setComponent(null);
      return () => {
        active = false;
      };
    }

    loader()
      .then((mod) => {
        if (!active) {
          return;
        }
        setComponent(() => mod.default);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!active) {
          return;
        }
        setError(err instanceof Error ? err.message : "Unable to load book content.");
        setComponent(null);
      });

    return () => {
      active = false;
    };
  }, [modulePath]);

  if (error) {
    return (
      <Card className="border-destructive/40 bg-destructive/10">
        <CardContent className="flex flex-col gap-3 p-6 text-destructive">
          <div className="text-sm font-semibold uppercase tracking-[0.2em]">Book Module Error</div>
          <p className="text-sm">{error}</p>
          <a href={modulePath} target="_blank" rel="noreferrer">
            <Button variant="outline" size="sm">
              <ExternalLink className="mr-2 h-4 w-4" />
              Inspect Module Path
            </Button>
          </a>
        </CardContent>
      </Card>
    );
  }

  if (!Component) {
    return (
      <div className="space-y-3">
        <div className="h-4 w-32 animate-pulse rounded bg-muted" />
        <div className="h-4 w-full animate-pulse rounded bg-muted/70" />
        <div className="h-4 w-4/5 animate-pulse rounded bg-muted/60" />
      </div>
    );
  }

  return (
    <div className={cn("book-prose", className)}>
      <Component components={mdxComponents} />
    </div>
  );
}
