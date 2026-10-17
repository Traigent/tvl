// Build the downloadable book PDF from the built site.
//
//   1. serve dist/public locally;
//   2. open /book/print and wait for fonts, images, Mermaid and Paged.js;
//   3. measure code-block overflow in the paginated DOM;
//   4. print to A4 PDF with Chromium and write dist/public/book/tvl-book.pdf.
//
// BOOK_PILOT=1 includes the pilot chapter; BOOK_PILOT=0 (CI, deploy) leaves it out.
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { chromium } from "playwright";
import { chaptersForBuild, plannedForBuild, projectRoot, pdfPath, reportPath, sourceCommit } from "./book_lib.mjs";

const distPublic = path.join(projectRoot, "dist", "public");
const includePilot = process.env.BOOK_PILOT === "1";
const READY_TIMEOUT_MS = 240_000;

const MIME = {
  ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".woff2": "font/woff2",
  ".webm": "video/webm", ".mp4": "video/mp4", ".yml": "text/plain", ".txt": "text/plain",
};

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    let file = path.join(distPublic, decodeURIComponent(url.pathname));
    if (!file.startsWith(distPublic)) {
      res.writeHead(403).end();
      return;
    }
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
    if (!fs.existsSync(file)) file = path.join(distPublic, "index.html"); // SPA fallback
    res.writeHead(200, { "content-type": MIME[path.extname(file)] ?? "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

async function main() {
  if (!fs.existsSync(path.join(distPublic, "index.html"))) {
    throw new Error("dist/public is missing: run `pnpm run build` first");
  }
  const sha = sourceCommit();
  const expected = chaptersForBuild(includePilot);
  const server = await serve();
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch();
  const problems = [];
  try {
    const page = await browser.newPage({ viewport: { width: 794, height: 1123 } });
    // The book is self-hosted; do not depend on the site's Google Fonts import.
    await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, (route) => route.abort());
    page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
      if (m.type() === "error" && !/fonts\.(googleapis|gstatic)|net::ERR_FAILED/.test(m.text())) {
        problems.push(`console: ${m.text()}`);
      }
    });
    page.on("requestfailed", (r) => {
      if (!/fonts\.(googleapis|gstatic)/.test(r.url())) problems.push(`request failed: ${r.url()}`);
    });
    await page.goto(`${origin}/book/print?commit=${sha}${includePilot ? "&pilot=1" : ""}`, { waitUntil: "load" });
    await page.waitForFunction(() => window.__BOOK_READY__ === true, null, { timeout: READY_TIMEOUT_MS });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForFunction(() => [...document.images].every((i) => i.complete));

    const dom = await page.evaluate(() => {
      const bad = (el) => el.scrollWidth > el.clientWidth + 1;
      const label = (el) => (el.textContent ?? "").trim().slice(0, 60);
      const pages = document.querySelectorAll(".pagedjs_page");
      return {
        pageCount: pages.length,
        errors: window.__BOOK_ERRORS__ ?? [],
        overflowingPre: [...document.querySelectorAll(".pagedjs_page pre")].filter(bad).map(label),
        overflowingTables: [...document.querySelectorAll(".pagedjs_page table")].filter(bad).map(label),
        brokenImages: [...document.images].filter((i) => !i.naturalWidth).map((i) => i.src),
        brokenAnchors: [...document.querySelectorAll(".pagedjs_page a[href^='#']")]
          .map((a) => a.getAttribute("href"))
          .filter((h) => h && !document.querySelector(`[id="${h.slice(1)}"]`)),
        splitBoxes: (() => {
          // Boxes that Paged.js cut across pages. A fragment is bad when it is empty (a border and a
          // title with nothing under it) or when its body is under two lines high.
          const BOX = ".book-callout, .book-example, .book-takeaways, .book-tryit, .book-predict, .book-misconception";
          const TITLE = ".book-box-title, .book-example-title";
          const out = [];
          for (const page of document.querySelectorAll(".pagedjs_page")) {
            const pageNo = Number(page.getAttribute("data-page-number")) || 0;
            for (const el of page.querySelectorAll(BOX)) {
              const split = el.hasAttribute("data-split-from") || el.hasAttribute("data-split-to");
              if (!split) continue;
              const kids = [...el.children].filter((c) => !c.matches(TITLE));
              const hasText = kids.some((c) => (c.textContent ?? "").replace(/[\s\u200b]/g, "").length > 0);
              const style = getComputedStyle(el);
              const line = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.5;
              let bodyH = 0;
              if (kids.length) {
                const top = Math.min(...kids.map((c) => c.getBoundingClientRect().top));
                const bottom = Math.max(...kids.map((c) => c.getBoundingClientRect().bottom));
                bodyH = bottom - top;
              }
              if (!hasText || bodyH < 2 * line) {
                out.push({ page: pageNo, kind: el.className.split(" ").slice(0, 2).join(" "), bodyPx: Math.round(bodyH), twoLinesPx: Math.round(2 * line), empty: !hasText, text: label(el) });
              }
            }
          }
          // Short boxes must not split at all: a split is allowed only when the whole box is taller
          // than 60% of the page's text area.
          const groups = new Map();
          for (const page of document.querySelectorAll(".pagedjs_page")) {
            const pageNo = Number(page.getAttribute("data-page-number")) || 0;
            const area = page.querySelector(".pagedjs_page_content");
            const areaH = area ? area.getBoundingClientRect().height : 950;
            for (const el of page.querySelectorAll(BOX)) {
              const ref = el.getAttribute("data-ref");
              if (!ref || !(el.hasAttribute("data-split-from") || el.hasAttribute("data-split-to"))) continue;
              const g = groups.get(ref) ?? { pages: [], height: 0, areaH, el };
              g.pages.push(pageNo);
              g.height += el.getBoundingClientRect().height;
              groups.set(ref, g);
            }
          }
          for (const g of groups.values()) {
            if (g.pages.length > 1 && g.height < 0.6 * g.areaH) {
              out.push({ page: g.pages[0], pages: g.pages, kind: g.el.className.split(" ").slice(0, 2).join(" "), shortBoxSplit: true, totalPx: Math.round(g.height), limitPx: Math.round(0.6 * g.areaH), text: label(g.el) });
            }
          }
          return out;
        })(),
        missingAlt: [
          ...[...document.querySelectorAll(".pagedjs_page img")].filter((i) => !(i.getAttribute("alt") ?? "").trim()).map((i) => `img ${i.getAttribute("src")}`),
          ...[...document.querySelectorAll(".pagedjs_page figure [role='img'], .pagedjs_page figure[role='group']")].filter((e) => !(e.getAttribute("aria-label") ?? "").trim()).map((e) => `${e.tagName.toLowerCase()} without aria-label`),
        ],
        mermaidSvgs: document.querySelectorAll(".pagedjs_page .book-mermaid svg").length,
        chapters: [...document.querySelectorAll(".pagedjs_page .chapter-title")].map((h) => h.textContent?.trim()),
      };
    });

    fs.mkdirSync(path.dirname(pdfPath), { recursive: true });
    await page.pdf({ path: pdfPath, format: "A4", printBackground: true, preferCSSPageSize: true, tagged: true, outline: true });

    const report = { commit: sha, pilot: includePilot, pdf: path.relative(projectRoot, pdfPath), expectedChapters: expected.map((c) => c.title), plannedChapters: plannedForBuild().map((c) => c.title), problems, ...dom };
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + "\n");
    console.log(`wrote ${pdfPath} (${dom.pageCount} paginated pages, commit ${sha.slice(0, 12)}, pilot=${includePilot})`);
    if (problems.length) console.log(`page problems:\n  ${problems.join("\n  ")}`);
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
