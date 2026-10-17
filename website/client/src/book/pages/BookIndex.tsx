import { Link, useSearch } from "wouter";
import Seo from "@/components/Seo";
import BookShell, { DraftBadge } from "../BookShell";
import { editionLine, includePilotFromSearch, lastWrittenChapter, plannedChapters, readableChapters } from "../chapters";
import { chapterNumber, DesignSpaceMotif } from "../components";

export default function BookIndex() {
  const search = useSearch();
  const pilot = includePilotFromSearch(search);
  const chapters = readableChapters(pilot);
  const planned = plannedChapters();
  const q = pilot ? "?pilot=1" : "";
  return (
    <BookShell chapters={[...chapters, ...planned]} pilotQuery={q}>
      <Seo
        title="TVL, Visually | The TVL Book"
        description="A short, visual book that teaches TVL to engineers who build AI agents."
        path="/book"
        robots="index,follow"
      />
      <header className="book-cover">
        <DesignSpaceMotif className="book-cover-motif" />
        <p className="book-kicker">The TVL Book</p>
        <h1 className="book-h1">TVL, Visually</h1>
        <p className="book-lede">
          Specifying what an AI agent must do. A short, visual book for engineers who build agents and have never read a
          specification language.
        </p>
        <p className="book-edition">{editionLine()}</p>
      </header>
      <ol className="book-toc">
        {chapters.map((c) => (
          <li key={c.slug}>
            <Link href={`/book/${c.slug}${q}`}>
              <span className="book-toc-title">
                {chapterNumber(c.order, c.pilot) !== null ? `${c.order}. ` : ""}
                {c.title}
              </span>
            </Link>
            {c.draft && <DraftBadge />}
            {c.summary && <div className="book-toc-sum">{c.summary}</div>}
          </li>
        ))}
      </ol>
      {planned.length > 0 && (
        <section className="book-planned-contents">
          <h2>Planned chapters</h2>
          <p className="book-toc-sum">This edition covers chapters 1 to {lastWrittenChapter()}. The chapters below are planned and not yet written.</p>
          <ol className="book-toc book-toc-planned">
            {planned.map((c) => (
              <li key={c.slug}>
                <span className="book-toc-title">{`${c.order}. ${c.title}`}</span>
                {c.summary && <div className="book-toc-sum">{c.summary}</div>}
              </li>
            ))}
          </ol>
        </section>
      )}
    </BookShell>
  );
}
