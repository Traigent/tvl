import type { ComponentType } from "react";

export interface ChapterMeta {
  title: string;
  slug: string;
  order: number;
  /** Draft chapters carry a badge on the web and a running-header marker in print. */
  draft?: boolean;
  /** Pilot chapters are rendering tests: hidden from the contents, shown only with ?pilot=1. */
  pilot?: boolean;
  /** Planned chapters have a title and a one-line summary but no body yet. */
  planned?: boolean;
  summary?: string;
}

export interface Chapter extends ChapterMeta {
  Component: ComponentType<Record<string, unknown>>;
}

interface MdxModule {
  default: ComponentType<Record<string, unknown>>;
  frontmatter?: Partial<ChapterMeta>;
}

// The chapter list is generated from the files: nothing else lists chapters.
const modules = import.meta.glob<MdxModule>("./chapters/*.mdx", { eager: true });

function build(): Chapter[] {
  const out: Chapter[] = [];
  for (const [file, mod] of Object.entries(modules)) {
    const fm = mod.frontmatter ?? {};
    if (!fm.title || !fm.slug || typeof fm.order !== "number") {
      throw new Error(`Chapter ${file} needs front-matter title, slug and order`);
    }
    out.push({
      title: fm.title,
      slug: fm.slug,
      order: fm.order,
      draft: Boolean(fm.draft),
      pilot: Boolean(fm.pilot),
      planned: Boolean(fm.planned),
      summary: fm.summary,
      Component: mod.default,
    });
  }
  const slugs = new Set<string>();
  for (const c of out) {
    if (slugs.has(c.slug)) throw new Error(`Duplicate chapter slug ${c.slug}`);
    slugs.add(c.slug);
  }
  return out.sort((a, b) => a.order - b.order);
}

export const allChapters: Chapter[] = build();

export function visibleChapters(includePilot: boolean): Chapter[] {
  return allChapters.filter((c) => includePilot || !c.pilot);
}

export function includePilotFromSearch(search: string): boolean {
  return new URLSearchParams(search).get("pilot") === "1";
}

/** Chapters a reader can open: everything except planned stubs. */
export function readableChapters(includePilot: boolean): Chapter[] {
  return visibleChapters(includePilot).filter((c) => !c.planned);
}

export function plannedChapters(): Chapter[] {
  return allChapters.filter((c) => c.planned);
}

/** The highest-numbered chapter that exists in this edition. */
export function lastWrittenChapter(): number {
  return Math.max(0, ...allChapters.filter((c) => !c.planned && !c.pilot && c.order < 90).map((c) => c.order));
}

/** The number of numbered chapters the book will have, written or planned. */
export function totalChapters(): number {
  return Math.max(0, ...allChapters.filter((c) => !c.pilot && c.order < 90).map((c) => c.order));
}

/**
 * Shows progress while chapters are planned, then the complete edition's chapter count.
 * Appends a draft note only when numbered chapters are marked as draft.
 */
export function editionLine(): string {
  const last = lastWrittenChapter();
  const total = totalChapters();
  if (plannedChapters().length > 0 || last < total) return `Work in progress — chapters 1–${last} of ${total}`;
  const drafts = allChapters.filter((c) => c.draft && !c.pilot && c.order >= 1 && c.order < 90).map((c) => c.order);
  const draftNote = drafts.length ? ` · TVL 1.3 chapters are draft (${Math.min(...drafts)}–${Math.max(...drafts)})` : "";
  return `Complete edition — chapters 1–${total}${draftNote}`;
}
