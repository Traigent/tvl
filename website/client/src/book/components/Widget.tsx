import type { ReactNode } from "react";
import { usePrint } from "../context";

interface WidgetProps {
  title: string;
  caption: string;
  /** Interactive body for the web. */
  children: ReactNode;
  /** Static replacement for print: a frame or table plus text. */
  fallback: ReactNode;
}

export default function Widget({ title, caption, children, fallback }: WidgetProps) {
  const print = usePrint();
  return (
    <figure className="book-widget">
      <div className="book-widget-title">{print ? "Explorable (static view)" : "Explore it"}: {title}</div>
      <div className="book-widget-body">{print ? fallback : children}</div>
      <figcaption>{caption}</figcaption>
    </figure>
  );
}
