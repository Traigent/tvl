// Shared helpers for the book scripts. The chapter list is generated from the
// MDX files' front-matter, the same source the site reads.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";

const here = path.dirname(fileURLToPath(import.meta.url));
export const projectRoot = path.resolve(here, "..");
export const repoRoot = path.resolve(projectRoot, "..");
export const chaptersDir = path.join(projectRoot, "client", "src", "book", "chapters");

export function readChapters() {
  const chapters = [];
  for (const file of fs.readdirSync(chaptersDir).filter((f) => f.endsWith(".mdx"))) {
    const text = fs.readFileSync(path.join(chaptersDir, file), "utf8");
    const m = /^---\n([\s\S]*?)\n---/.exec(text);
    if (!m) throw new Error(`${file}: missing front-matter`);
    const fm = parse(m[1]);
    if (!fm.title || !fm.slug || typeof fm.order !== "number") {
      throw new Error(`${file}: front-matter needs title, slug and order`);
    }
    chapters.push({ file, title: fm.title, slug: fm.slug, order: fm.order, draft: !!fm.draft, pilot: !!fm.pilot, planned: !!fm.planned });
  }
  return chapters.sort((a, b) => a.order - b.order);
}

export function chaptersForBuild(includePilot) {
  return readChapters().filter((c) => (includePilot || !c.pilot) && !c.planned);
}

/** Planned stubs: listed in the contents only, with no chapter body. */
export function plannedForBuild() {
  return readChapters().filter((c) => c.planned);
}

export const pdfPath = path.join(projectRoot, "dist", "public", "book", "tvl-book.pdf");
export const reportPath = path.join(projectRoot, "dist", "book-pdf-report.json");
export const MAX_PAGES = 100;

/**
 * The book's source commit: GITHUB_SHA in CI, else git HEAD. The PDF build stamps it on
 * the print route (?commit=), and vite.config.ts injects it into the site at build time
 * (__BOOK_COMMIT__), so <TestedRef/> names the same commit on the web and in print.
 */
export function sourceCommit() {
  if (process.env.GITHUB_SHA) return process.env.GITHUB_SHA;
  try {
    return execFileSync("git", ["rev-parse", "HEAD"], { cwd: projectRoot, encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
}
