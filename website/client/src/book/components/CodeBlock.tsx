import { Fragment, useState } from "react";
import type { ReactNode } from "react";
import { highlightCode, languageFromPath } from "@/lib/prism";
import { usePrint } from "../context";

/**
 * Wrap each highlighted line in its own block span. Paged.js loses newline
 * characters when it splits a <pre> across pages, so lines must not rely on them.
 * Token spans that cross a newline are closed and reopened per line.
 */
export function splitHighlightedLines(html: string): string[] {
  const lines: string[] = [];
  let open: string[] = [];
  let current = "";
  const re = /(<span[^>]*>)|(<\/span>)|\n|[^<\n]+|</g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html))) {
    const t = m[0];
    if (t === "\n") {
      lines.push(current + "</span>".repeat(open.length));
      current = open.join("");
    } else {
      if (m[1]) open.push(t);
      else if (m[2]) open.pop();
      current += t;
    }
  }
  lines.push(current + "</span>".repeat(open.length));
  return lines;
}

/** Words up to this many characters never split in print; longer ones may, so nothing overflows. */
const MAX_WHOLE_WORD = 96;

/**
 * Print: wrap each space-free word of one highlighted line in a nowrap span, so the
 * line breaks only at spaces (Chromium otherwise breaks after a hyphen, splitting
 * "--json"). Token spans open around a word are closed before it and reopened inside
 * it, so the markup stays balanced.
 */
export function keepWordsTogether(line: string, maxWord = MAX_WHOLE_WORD): string {
  const items = line.match(/<span[^>]*>|<\/span>|&[#a-zA-Z0-9]+;| |[^<& ]+|[<&]/g) ?? [];
  const stack: string[] = [];
  let out = "";
  let i = 0;
  while (i < items.length) {
    const t = items[i];
    if (t === " " || t.startsWith("<span") || t === "</span>") {
      if (t.startsWith("<span")) stack.push(t);
      else if (t === "</span>") stack.pop();
      out += t;
      i++;
      continue;
    }
    let j = i;
    let len = 0;
    while (j < items.length && items[j] !== " ") {
      const u = items[j];
      if (!u.startsWith("<") || u.length === 1) len += u.startsWith("&") && u.length > 1 ? 1 : u.length;
      j++;
    }
    const whole = len <= maxWord;
    if (whole) out += "</span>".repeat(stack.length) + '<span class="nw">' + stack.join("");
    for (let k = i; k < j; k++) {
      const u = items[k];
      if (u.startsWith("<span")) stack.push(u);
      else if (u === "</span>") stack.pop();
      out += u;
    }
    if (whole) out += "</span>".repeat(stack.length) + "</span>" + stack.join("");
    i = j;
  }
  return out;
}

/**
 * Print: plain text (an inline command, a path) as space-separated words that each stay
 * whole, so a printed line breaks only at a space. Words over MAX_WHOLE_WORD may still split.
 */
export function wholeWords(text: string): ReactNode {
  return text.split(" ").map((w, i) => (
    <Fragment key={i}>
      {i ? " " : ""}
      {w.length <= MAX_WHOLE_WORD ? <span className="nw">{w}</span> : w}
    </Fragment>
  ));
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

interface CodeBlockProps {
  code: string;
  language?: string;
  path?: string;
  /** Marks the block as a long listing that may split across pages in print. */
  long?: boolean;
}

export default function CodeBlock({ code, language, path, long }: CodeBlockProps) {
  const print = usePrint();
  const [copied, setCopied] = useState(false);
  const lang = language ?? (path ? languageFromPath(path) : "markdown");
  const body = code.replace(/\n$/, "");
  // "text" is tool output: shown verbatim, with no highlighting.
  const highlighted = lang === "text" ? escapeHtml(body) : highlightCode(body, lang);
  const html = splitHighlightedLines(highlighted)
    .map((l) => `<span class="cl">${l === "" ? "&#8203;" : print ? keepWordsTogether(l) : l}</span>`)
    .join("");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable: leave the button inert */
    }
  };

  return (
    <div className={`book-code ${long ? "book-code-long" : ""}`}>
      {!print && (
        <button type="button" className="book-copy" onClick={copy} aria-label="Copy code">
          {copied ? "Copied" : "Copy"}
        </button>
      )}
      <pre tabIndex={0} data-language={lang}>
        <code className={`language-${lang}`} dangerouslySetInnerHTML={{ __html: html }} />
      </pre>
    </div>
  );
}
