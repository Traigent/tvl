import { useEffect, useRef, useState } from "react";
import { useSearch } from "wouter";
import { ChapterReferences, chapterNumber, DesignSpaceMotif, PredictAnswers } from "../components";
import { beginPending, reportBookError } from "../components/pending";
import { editionLine, includePilotFromSearch, lastWrittenChapter, plannedChapters, readableChapters, type Chapter } from "../chapters";
import { BUILD_COMMIT } from "../buildInfo";
import { ChapterProvider, CommitContext, PrintContext } from "../context";
import { mdxComponents } from "../mdxComponents";
import "../book.css";
import bookCssUrl from "../book.css?url";

function ChapterBody({ chapter }: { chapter: Chapter }) {
  const Body = chapter.Component;
  const n = chapterNumber(chapter.order, chapter.pilot);
  return (
    <section className="book-chapter" id={`chap-${chapter.slug}`} data-slug={chapter.slug} data-title={chapter.title}>
      <ChapterProvider slug={chapter.slug}>
        {n !== null && <p className="book-chapter-num">{`Chapter ${n}`}</p>}
        <h1 className={`chapter-title ${chapter.draft ? "is-draft" : ""}`}>
          <span className="run-title">{chapter.title}</span>
          <span className="run-mark">{chapter.draft ? "Draft \u2014 TVL 1.3" : "\u00a0"}</span>
        </h1>
        {chapter.draft && <p className="book-draft-note">Draft chapter: describes TVL 1.3, which is not yet released.</p>}
        <Body components={mdxComponents} />
        <PredictAnswers />
        <ChapterReferences />
      </ChapterProvider>
    </section>
  );
}

/** Wait until nothing async is pending and the DOM has been quiet for a moment. */
async function settle(): Promise<void> {
  const quiet = (ms: number) => new Promise((r) => setTimeout(r, ms));
  for (let i = 0; i < 600; i++) {
    if ((window.__BOOK_PENDING__ ?? 0) === 0) {
      await quiet(250);
      if ((window.__BOOK_PENDING__ ?? 0) === 0) return;
    }
    await quiet(100);
  }
  reportBookError("timed out waiting for async book content");
}

export default function BookPrint() {
  const search = useSearch();
  const params = new URLSearchParams(search);
  const pilot = includePilotFromSearch(search);
  const commit = params.get("commit") ?? "unknown";
  const chapters = readableChapters(pilot);
  const planned = plannedChapters();
  const date = params.get("date") ?? new Date().toISOString().slice(0, 10);
  const rootRef = useRef<HTMLDivElement>(null);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    if (started) return;
    setStarted(true);
    const releaseRoute = beginPending();
    document.title = `TVL, Visually (${commit.slice(0, 12)})`;
    // The install instructions name the commit the book was tested at (<TestedRef/>). The
    // stamp on this route and the commit built into the site must be the same one.
    if (!/^[0-9a-f]{40}$/.test(commit)) reportBookError(`print route has no source commit (got "${commit}")`);
    else if (BUILD_COMMIT !== commit) reportBookError(`site built at ${BUILD_COMMIT.slice(0, 12)}, but printed for ${commit.slice(0, 12)}: rebuild the site`);
    (async () => {
      try {
        releaseRoute();
        // Load every face now, while the site CSS that declares them is still present, so that
        // pagination measures the real fonts.
        await Promise.all(
          ['400 1em "Book Serif"', 'italic 400 1em "Book Serif"', '700 1em "Book Serif"', '400 1em "Book Sans"', '700 1em "Book Sans"', '400 1em "Book Mono"'].map((f) =>
            document.fonts.load(f, "Aa0 \u2192 \u2014"),
          ),
        );
        await document.fonts.ready;
        await settle();
        await document.fonts.ready;
        const root = rootRef.current;
        if (!root) throw new Error("print root missing");
        // Mark the first use of each glossary term in each chapter (a raised "g" via CSS).
        for (const chap of Array.from(root.querySelectorAll(".book-chapter"))) {
          const seen = new Set<string>();
          for (const el of Array.from(chap.querySelectorAll<HTMLElement>("[data-term]"))) {
            const id = el.dataset.term ?? "";
            if (seen.has(id)) continue;
            seen.add(id);
            el.classList.add("book-term-first");
          }
        }
        const { Previewer } = await import("pagedjs");
        const host = document.createElement("div");
        host.id = "paged-host";
        host.className = "book-root book-print"; // Paged.js drops the cloned wrapper, so the scope class goes on the host
        document.body.appendChild(host);
        // Paged.js is given only the book stylesheet. The site's Tailwind CSS is not needed
        // for print and Paged.js's CSS parser does not cope with all of it.
        const css = await (await fetch(bookCssUrl)).text();
        const sheets: Record<string, string>[] = [{ [new URL(bookCssUrl, location.href).href]: css }];
        for (const el of Array.from(document.head.querySelectorAll("style"))) el.remove();
        for (const link of Array.from(document.querySelectorAll('link[rel="stylesheet"]'))) link.remove();
        const previewer = new Previewer();
        await previewer.preview(root.cloneNode(true) as HTMLElement, sheets, host);
        root.setAttribute("hidden", "");
        // The hidden source keeps the same ids as the paginated copy. References by id
        // (SVG arrow markers, in-document links) would resolve to the hidden source
        // first, so rename its ids: every reference then lands on the printed pages.
        for (const el of Array.from(root.querySelectorAll("[id]"))) el.id = `src-${el.id}`;
        await document.fonts.ready;
        window.__BOOK_READY__ = true;
      } catch (e) {
        reportBookError(`paged: ${String(e)}`);
        window.__BOOK_READY__ = true;
      }
    })();
  }, [started, commit]);

  return (
    <PrintContext.Provider value={true}>
      <CommitContext.Provider value={commit}>
        <div className="book-root book-print" ref={rootRef} data-pilot={pilot ? "1" : "0"}>
          <section className="book-titlepage">
            <DesignSpaceMotif className="book-cover-motif" />
            <p className="book-kicker">The TVL Book</p>
            <h1 className="book-title">TVL, Visually</h1>
            <p className="book-subtitle">Specifying what an AI agent must do</p>
            <p className="book-edition">{editionLine()}</p>
            <p className="book-meta">
              {date} &middot; source commit {commit.slice(0, 12)}
              <br />
              Prose and figures: CC-BY-4.0 &middot; tvl-lang.org/book
            </p>
          </section>
          <section className="book-contents">
            <h1 className="book-contents-title">
              <span className="run-title">Contents</span>
              <span className="run-mark">{"\u00a0"}</span>
            </h1>
            <ol>
              {chapters.map((c) => (
                <li key={c.slug}>
                  <a href={`#chap-${c.slug}`} className="book-toc-link">
                    {`${chapterNumber(c.order, c.pilot) !== null ? `${c.order}. ` : ""}${c.title}${c.draft ? " (draft)" : ""}`}
                  </a>
                </li>
              ))}
            </ol>
            {planned.length > 0 && (
              <div className="book-contents-planned">
                <h2 className="book-contents-planned-title">Planned chapters</h2>
                <p>{`This edition covers chapters 1 to ${lastWrittenChapter()}. The chapters below are planned and not yet written.`}</p>
                <ol>
                  {planned.map((c) => (
                    <li key={c.slug}>{`${c.order}. ${c.title}${c.draft ? " (draft)" : ""}`}</li>
                  ))}
                </ol>
              </div>
            )}
          </section>
          {chapters.map((c) => (
            <ChapterBody key={c.slug} chapter={c} />
          ))}
        </div>
      </CommitContext.Provider>
    </PrintContext.Provider>
  );
}

