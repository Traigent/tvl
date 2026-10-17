// Checks on the built book PDF. Run after build_book_pdf.mjs. Exits non-zero on any failure.
//   - page count <= 100            (pdfinfo)
//   - every chapter title present, in order, in the contents and in the body (pdftotext)
//   - the install pins the tested commit ("git checkout <commit>", pdftotext)
//   - every font embedded          (pdffonts)
//   - no code-block overflow, no broken images or anchors, no page errors (report from the build)
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import { chaptersForBuild, MAX_PAGES, pdfPath, reportPath } from "./book_lib.mjs";

const failures = [];
const fail = (m) => failures.push(m);
const run = (cmd, args) => execFileSync(cmd, args, { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });

if (!fs.existsSync(pdfPath)) throw new Error(`missing ${pdfPath}: run pnpm book:pdf`);
if (!fs.existsSync(reportPath)) throw new Error(`missing ${reportPath}: run pnpm book:pdf`);
const report = JSON.parse(fs.readFileSync(reportPath, "utf8"));

// 1. page count
const info = run("pdfinfo", [pdfPath]);
const pages = Number(/^Pages:\s+(\d+)/m.exec(info)?.[1]);
if (!pages) fail("could not read the page count");
if (pages > MAX_PAGES) fail(`page count ${pages} exceeds ${MAX_PAGES}`);
if (report.pageCount && Math.abs(report.pageCount - pages) > 1) {
  fail(`paginated page count ${report.pageCount} differs from the PDF's ${pages}`);
}

// 2. chapter titles, in order, twice (contents page, then chapter heads)
const squash = (s) => s.replace(/\s+/g, " ");
const text = squash(run("pdftotext", ["-layout", pdfPath, "-"]));
const titles = chaptersForBuild(report.pilot).map((c) => squash(c.title));
let pos = 0;
for (const pass of ["contents", "chapter heading"]) {
  for (const t of titles) {
    const at = text.indexOf(t, pos);
    if (at < 0) {
      fail(`chapter title missing or out of order (${pass}): "${t}"`);
      break;
    }
    pos = at + t.length;
  }
}

// 2b. planned chapters are listed in the contents, with the edition notice
for (const t of report.plannedChapters ?? []) {
  if (!text.includes(squash(t))) fail(`planned chapter missing from the contents: "${t}"`);
}
if ((report.plannedChapters ?? []).length && !/Planned chapters/.test(text)) fail('contents has no "Planned chapters" heading');
// The edition line names the last written chapter, from the same chapter list the build used.
const lastWritten = Math.max(0, ...chaptersForBuild(report.pilot).filter((c) => c.order >= 1 && c.order < 90).map((c) => c.order));
if (!new RegExp(`Work in progress\\s+\\S\\s+chapters 1\\S${lastWritten} of \\d+`).test(text)) fail(`cover has no edition line (Work in progress, chapters 1-${lastWritten} of M)`);

// 2c. the install instructions pin the commit the book was tested at (<TestedRef/>)
if (!/^[0-9a-f]{40}$/.test(String(report.commit))) fail(`the build has no source commit (got "${report.commit}")`);
else if (!text.includes(`git checkout ${report.commit}`)) fail(`install instructions do not pin the tested commit: no "git checkout ${report.commit}"`);

// 2d. tagged PDF with an outline (reading order and alt text for assistive technology)
if (!/^Tagged:\s+yes/m.test(info)) fail(`PDF is not tagged (pdfinfo: ${/^Tagged:.*$/m.exec(info)?.[0] ?? "no Tagged line"})`);

// 3. fonts embedded
const fonts = run("pdffonts", [pdfPath]).split("\n").slice(2).filter(Boolean);
if (fonts.length === 0) fail("pdffonts lists no fonts");
for (const line of fonts) {
  const cols = line.trim().split(/\s+/);
  const emb = cols[cols.length - 5];
  if (emb !== "yes") fail(`font not embedded: ${line.trim()}`);
}

// 4. DOM measurements from the build
for (const k of ["overflowingPre", "overflowingTables", "brokenImages", "brokenAnchors", "splitBoxes", "missingAlt", "errors", "problems"]) {
  if (report[k]?.length) fail(`${k}: ${JSON.stringify(report[k])}`);
}
if (report.pilot && report.mermaidSvgs < 1) fail("pilot build has no rendered Mermaid diagram");

console.log(`pages: ${pages} (limit ${MAX_PAGES}); chapters checked: ${titles.length}; fonts: ${fonts.length}; commit ${String(report.commit).slice(0, 12)}; pilot=${report.pilot}`);
if (failures.length) {
  console.error("PDF checks FAILED:\n  - " + failures.join("\n  - "));
  process.exit(1);
}
console.log("PDF checks passed");
