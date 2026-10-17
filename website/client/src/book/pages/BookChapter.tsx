import { Link, useParams, useSearch } from "wouter";
import Seo from "@/components/Seo";
import NotFound from "@/pages/NotFound";
import BookShell, { DraftBadge } from "../BookShell";
import { allChapters, includePilotFromSearch, readableChapters, visibleChapters } from "../chapters";
import { chapterNumber } from "../components";
import { ChapterProvider } from "../context";
import { mdxComponents } from "../mdxComponents";

export default function BookChapter() {
  const { slug } = useParams<{ slug: string }>();
  const pilot = includePilotFromSearch(useSearch());
  const chapters = readableChapters(pilot);
  const shellChapters = visibleChapters(pilot);
  const index = chapters.findIndex((c) => c.slug === slug);
  const chapter = index >= 0 ? chapters[index] : allChapters.find((c) => c.slug === slug && !c.pilot);
  if (!chapter) return <NotFound />;
  const q = pilot ? "?pilot=1" : "";
  const prev = index > 0 ? chapters[index - 1] : undefined;
  const next = index >= 0 && index < chapters.length - 1 ? chapters[index + 1] : undefined;
  const Body = chapter.Component;
  const chapterRobots = chapter.planned ? "noindex,nofollow" : "index,follow";
  return (
    <BookShell chapters={shellChapters} currentSlug={chapter.slug} pilotQuery={q}>
      <Seo title={`${chapter.title} | TVL, Visually`} description={chapter.summary ?? chapter.title} path={`/book/${chapter.slug}`} robots={chapterRobots} />
      <article className="book-article">
        {chapterNumber(chapter.order, chapter.pilot) !== null && <p className="book-chapter-num">Chapter {chapter.order}{chapter.planned ? " (planned)" : ""}</p>}
        <h1 className="book-h1">
          {chapter.title} {chapter.draft && <DraftBadge />}
        </h1>
        {chapter.planned ? (
          <>
            <p className="book-lede">{chapter.summary}</p>
            <p>
              This chapter is planned and not yet written. See <Link href={`/book/whats-coming${q}`}>what is coming</Link>.
            </p>
          </>
        ) : (
          <ChapterProvider slug={chapter.slug}>
            <Body components={mdxComponents} />
          </ChapterProvider>
        )}
      </article>
      <nav className="book-pager" aria-label="Previous and next chapter">
        {prev ? <Link href={`/book/${prev.slug}${q}`}>&larr; {prev.title}</Link> : <span />}
        {next ? <Link href={`/book/${next.slug}${q}`}>{next.title} &rarr;</Link> : <span />}
      </nav>
    </BookShell>
  );
}
