import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "wouter";
import { allChapters, lastWrittenChapter, plannedChapters } from "../chapters";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { usePrint, useChapter } from "../context";
import { glossary } from "../glossary";
import { PINNED_COMMIT, pinnedUrl, SOURCES, type SourceKey } from "../sources";

export function Callout({ kind = "note", title, children }: { kind?: "note" | "warning" | "tip"; title?: string; children: ReactNode }) {
  const label = title ?? (kind === "warning" ? "Careful" : kind === "tip" ? "Tip" : "Note");
  return (
    <aside className={`book-callout book-callout-${kind}`}>
      <div className="book-box-title">{label}</div>
      <div>{children}</div>
    </aside>
  );
}

export function KeyTakeaways({ children }: { children: ReactNode }) {
  return (
    <aside className="book-callout book-takeaways">
      <div className="book-box-title">Key takeaways</div>
      <div>{children}</div>
    </aside>
  );
}

export function TryIt({ children }: { children: ReactNode }) {
  return (
    <aside className="book-callout book-tryit">
      <div className="book-box-title">Try it</div>
      <div>{children}</div>
    </aside>
  );
}

export function Misconception({ wrong, children }: { wrong: string; children: ReactNode }) {
  return (
    <aside className="book-callout book-misconception">
      <div className="book-box-title">You might think&hellip;</div>
      <p className="book-wrong">&ldquo;{wrong}&rdquo;</p>
      <div>
        <b>Why not:</b> {children}
      </div>
    </aside>
  );
}

export function Predict({ question, children }: { question: ReactNode; children: ReactNode }) {
  const print = usePrint();
  const chapter = useChapter();
  const id = useId();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (print && chapter) chapter.register({ id, question, answer: children });
    // registration happens once per mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [print]);

  const index = print && chapter ? chapter.answers.findIndex((a) => a.id === id) + 1 : 0;
  const label = chapter && index ? answerLabel(chapter.slug, index) : "";

  return (
    <aside className="book-callout book-predict">
      <div className="book-box-title">Predict first</div>
      <div>{question}</div>
      {print ? (
        <p className="book-answer-ref">
          Write your guess here: ______________. The answer is at the end of this chapter{label ? ` (answer ${label})` : ""}.
        </p>
      ) : (
        <>
          <button type="button" className="book-reveal" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            {open ? "Hide the answer" : "Show the answer"}
          </button>
          {open && <div className="book-answer">{children}</div>}
        </>
      )}
    </aside>
  );
}

/**
 * An answer's label, unique in the book: the chapter number and the answer's place in
 * the chapter, such as "6.2". Chapters without a number fall back to the place alone.
 */
export function answerLabel(slug: string, index: number): string {
  const c = allChapters.find((ch) => ch.slug === slug);
  const n = c ? chapterNumber(c.order, c.pilot) : null;
  return n ? `${n}.${index}` : String(index);
}

export function PredictAnswers() {
  const chapter = useChapter();
  if (!chapter || chapter.answers.length === 0) return null;
  return (
    <section className="book-answers">
      <h2 className="book-answers-title">Answers to the predictions</h2>
      <ol className="book-answers-list">
        {chapter.answers.map((a, i) => (
          <li key={a.id}>
            <b className="book-answer-label">{`Answer ${answerLabel(chapter.slug, i + 1)}. `}</b>
            <div className="book-answer-q">{a.question}</div>
            <div>{a.answer}</div>
          </li>
        ))}
      </ol>
    </section>
  );
}

const TERM_LABELS: Record<string, string> = {
  tvar: "Tuned variable (tvar)",
  sat: "SAT",
  unsat: "UNSAT",
  "unsat-core": "UNSAT core",
  tost: "TOST",
  pareto: "Pareto dominance",
  "epsilon-pareto": "Epsilon-Pareto",
  "non-inferior": "Non-inferior",
  derived: "constraints.derived",
  "p-value": "p-value",
  "one-sided": "One-sided test",
  "multiple-testing": "Multiple-testing adjustment",
  placement: "Placement (pre and post cascades)",
  "state-keys": "state_keys",
  theta: "Theta (θ)",
  epsilon: "Epsilon (ε)",
  ceiling: "Ceiling, ⌈x⌉",
  rfc: "RFC",
  "abstaining-sample": "Abstaining sample",
};

/** The heading a glossary entry carries. */
export function termLabel(id: string): string {
  if (TERM_LABELS[id]) return TERM_LABELS[id];
  const words = id.replace(/-/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * A glossary term. Print: plain text; the first use in each chapter gets a raised "g"
 * (added by the print route), and the definition is in the Glossary at the back.
 * Web: a button that opens an accessible popover on hover, keyboard focus and tap or
 * click; Esc closes it. The same popover component serves all four.
 */
export function Term({ id, children }: { id: string; children: ReactNode }) {
  const print = usePrint();
  const def = glossary[id];
  const [open, setOpen] = useState(false);
  const closeTimer = useRef<number | null>(null);
  const cancelClose = () => {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
    closeTimer.current = null;
  };
  const closeSoon = () => {
    cancelClose();
    closeTimer.current = window.setTimeout(() => setOpen(false), 120);
  };
  useEffect(() => cancelClose, []);
  // Esc closes the popover even when it was opened by hover alone (no focus inside it).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        cancelClose();
        setOpen(false);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  if (!def) throw new Error(`Unknown glossary term: ${id}`);
  if (print) {
    return (
      <span className="book-term" data-term={id}>
        {children}
      </span>
    );
  }
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="book-term"
          onPointerEnter={(e) => {
            if (e.pointerType === "mouse") {
              cancelClose();
              setOpen(true);
            }
          }}
          onPointerLeave={(e) => {
            if (e.pointerType === "mouse") closeSoon();
          }}
          onFocus={(e) => {
            // Open on keyboard focus only: a pointer press focuses the button too, and the
            // click that follows would then close what the focus just opened.
            if (e.currentTarget.matches(":focus-visible")) setOpen(true);
          }}
          onBlur={() => setOpen(false)}
        >
          {children}
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="book-term-pop w-80 max-w-[90vw] text-sm leading-relaxed"
        onOpenAutoFocus={(e) => e.preventDefault()}
        onCloseAutoFocus={(e) => e.preventDefault()}
        onPointerEnter={cancelClose}
        onPointerLeave={closeSoon}
      >
        <p className="mb-1 font-semibold">{termLabel(id)}</p>
        <p>{def}</p>
        <Link className="mt-2 inline-block underline" href={`/book/glossary#glossary-${id}`}>
          See the glossary
        </Link>
      </PopoverContent>
    </Popover>
  );
}

/** The glossary, sorted A to Z by heading. Used on the Glossary page, web and print. */
export function GlossaryList() {
  const entries = Object.entries(glossary)
    .map(([id, def]) => ({ id, def, label: termLabel(id) }))
    .sort((x, y) => x.label.localeCompare(y.label, "en", { sensitivity: "base" }));
  const groups: { letter: string; items: typeof entries }[] = [];
  for (const e of entries) {
    const letter = e.label.charAt(0).toUpperCase();
    const last = groups[groups.length - 1];
    if (last && last.letter === letter) last.items.push(e);
    else groups.push({ letter, items: [e] });
  }
  return (
    <div className="book-glossary">
      {groups.map((g) => (
        <section key={g.letter} className="book-glossary-group">
          <h2 className="book-glossary-letter" aria-label={`Terms starting with ${g.letter}`}>{g.letter}</h2>
          <dl>
            {g.items.map((e) => (
              <div className="book-glossary-entry" key={e.id} id={`glossary-${e.id}`}>
                <dt>{e.label}</dt>
                <dd>{e.def}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}

/** The planned chapters with their one-line summaries ("What's coming"). */
export function PlannedList() {
  const planned = plannedChapters();
  return (
    <ol className="book-planned-list" start={planned[0]?.order}>
      {planned.map((c) => (
        <li key={c.slug}>
          <b>{`${c.order}. ${c.title}`}</b>
          <div>{c.summary}</div>
        </li>
      ))}
    </ol>
  );
}

/**
 * A link to a pinned normative source. `children` is the name the prose uses;
 * `section` is the part of the source cited.
 *
 * Web: an ordinary link, reading "children, section".
 * Print: the name and a numbered marker such as [3]. The chapter's reference
 * list (ChapterReferences) holds the full pinned URL, so no raw URL interrupts
 * the sentence. One number per source per chapter; its sections are listed.
 */
export function Ref({ to, section, children }: { to: SourceKey; section?: string; children?: ReactNode }) {
  const print = usePrint();
  const chapter = useChapter();
  const src = SOURCES[to];
  if (!src) throw new Error(`Unknown source: ${to}`);

  useEffect(() => {
    if (print && chapter) chapter.registerRef(to, section);
    // registration happens once per mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [print]);

  const name = children ?? src.label;
  if (print) {
    const n = chapter ? chapter.refs.findIndex((r) => r.to === to) + 1 : 0;
    return (
      <span className="book-refname">
        {name}
        {n > 0 && chapter && (
          <a className="book-refmark" href={`#ref-${chapter.slug}-${n}`}>{`\u00a0[${n}]`}</a>
        )}
      </span>
    );
  }
  return (
    <a className="book-ref" href={pinnedUrl(to)} target="_blank" rel="noreferrer">
      {name}
      {section ? `, ${section}` : null}
    </a>
  );
}

/**
 * "section 6.1" and "sections 9.5 and 9.6" merge into "sections 6.1, 9.5, 9.6";
 * other parts (quoted headings) follow, separated by semicolons.
 */
function describeSections(sections: string[]): string {
  const nums: string[] = [];
  const other: string[] = [];
  for (const s of sections) {
    const m = /^sections? (.+)$/.exec(s);
    if (!m) {
      if (!other.includes(s)) other.push(s);
      continue;
    }
    for (const n of m[1].split(/,\s*|\s+and\s+/)) if (!nums.includes(n)) nums.push(n);
  }
  nums.sort((x, y) => x.localeCompare(y, "en", { numeric: true }));
  const parts = nums.length ? [`${nums.length > 1 ? "sections" : "section"} ${nums.join(", ")}`, ...other] : other;
  return parts.join("; ");
}

/** Print only: the numbered sources a chapter cites, with their full pinned URLs. */
export function ChapterReferences() {
  const chapter = useChapter();
  if (!chapter || chapter.refs.length === 0) return null;
  return (
    <section className="book-references">
      <h2 className="book-references-title">References</h2>
      <p className="book-references-note">
        {`Optional reading: the sources this chapter cites, pinned to commit ${PINNED_COMMIT.slice(0, 12)}.`}
      </p>
      <ol>
        {chapter.refs.map((r, i) => {
          const key = r.to as SourceKey;
          const url = pinnedUrl(key);
          return (
            <li key={r.to} id={`ref-${chapter.slug}-${i + 1}`}>
              <span className="book-ref-n">{`[${i + 1}]`}</span>
              <span>
                {`${SOURCES[key].label}${r.sections.length ? `: ${describeSections(r.sections)}` : ""}. `}
                <a className="book-ref-url" href={url}>
                  {url}
                </a>
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** Link to another section of the book; print adds the page number via target-counter. */
export function XRef({ to, children }: { to: string; children: ReactNode }) {
  return (
    <a className="book-xref" href={`#${to}`}>
      {children}
    </a>
  );
}

/**
 * Link to another chapter by its number (front-matter `order`). Until that
 * chapter exists the text is plain, so a forward link never dangles. On the
 * web it opens the chapter page; in print it adds the page number.
 */
export function ChapterLink({ n, children }: { n: number; children?: ReactNode }) {
  const print = usePrint();
  const target = allChapters.find((c) => c.order === n && !c.pilot);
  const label = children ?? `chapter ${n}`;
  if (!target) return <span className="book-chapref">{label}</span>;
  if (target.planned) {
    // Not written yet: never a dead link. The web names the chapter and says it is planned;
    // print keeps the prose plain (the contents page lists what is planned).
    if (print) return <span className="book-chapref">{label}</span>;
    return (
      <span className="book-chapref book-chapref-planned" title={`${target.title}: planned, not yet written (this edition covers chapters 1 to ${lastWrittenChapter()})`}>
        {label}
        {` (${target.title}, planned)`}
      </span>
    );
  }
  if (print) {
    return (
      <a className="book-xref" href={`#chap-${target.slug}`}>
        {label}
      </a>
    );
  }
  return <Link href={`/book/${target.slug}`}>{label}</Link>;
}

/** Chapters numbered 1 to 89 carry a number; front and back matter do not. */
export function chapterNumber(order: number, pilot?: boolean): number | null {
  return !pilot && order >= 1 && order < 90 ? order : null;
}
