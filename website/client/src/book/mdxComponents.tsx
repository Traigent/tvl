import type { ReactNode } from "react";
import {
  Callout, ChapterLink, CodeBlock, CoverageFigure, EventTimeline, Example, ExampleResult, Figure, GlossaryList, KeyTakeaways, MarginFigure, Mermaid, Misconception, PlannedList,
  Predict, Ref, SampleSizeSlider, Term, TestedRef, TryIt, Widget, WindowStrip, XRef,
} from "./components";
import { wholeWords } from "./components/CodeBlock";
import { usePrint } from "./context";

function textOf(node: ReactNode): string {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (node && typeof node === "object" && "props" in node) {
    return textOf((node as { props: { children?: ReactNode } }).props.children);
  }
  return "";
}

function Pre({ children }: { children?: ReactNode }) {
  const child = children as { props?: { className?: string; children?: ReactNode } } | undefined;
  const cls = child?.props?.className ?? "";
  const lang = /language-(\w[\w-]*)/.exec(cls)?.[1];
  return <CodeBlock code={textOf(child?.props?.children)} language={lang} />;
}

/**
 * Inline code. Print keeps each space-separated word whole, so an inline command or path
 * such as `python book/support-bot/robustness.py --seeds 400` breaks only at a space.
 */
function InlineCode({ children, className }: { children?: ReactNode; className?: string }) {
  const print = usePrint();
  const text = textOf(children);
  if (!print || typeof children !== "string") return <code className={className}>{children}</code>;
  return <code className={className}>{wholeWords(text)}</code>;
}

function Table({ children }: { children?: ReactNode }) {
  return (
    <div className="book-table">
      <table>{children}</table>
    </div>
  );
}

export const mdxComponents = {
  pre: Pre,
  code: InlineCode,
  table: Table,
  Callout, ChapterLink, CoverageFigure, EventTimeline, Example, ExampleResult, Figure, GlossaryList, KeyTakeaways, MarginFigure, Mermaid, Misconception, PlannedList, Predict,
  Ref, SampleSizeSlider, Term, TestedRef, TryIt, Widget, WindowStrip, XRef,
};
