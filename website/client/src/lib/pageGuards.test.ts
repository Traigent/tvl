import { readFileSync } from "fs";
import path from "path";
import { describe, expect, it } from "vitest";

const PAGES = path.resolve(import.meta.dirname, "..", "pages");

describe("SpecViewer Copy and Download wait for loaded content (#236)", () => {
  const spec = readFileSync(path.join(PAGES, "SpecViewer.tsx"), "utf8");

  it("the Copy button is disabled while loading or when there is no content", () => {
    expect(spec).toMatch(/<Button\s+onClick=\{handleCopy\}[^>]*disabled=\{loading \|\| !content\}/);
  });

  it("the Download button is disabled while loading or when there is no content", () => {
    expect(spec).toMatch(/<Button\s+onClick=\{handleDownload\}[^>]*disabled=\{loading \|\| !content\}/);
  });
});

describe("Examples preview ignores superseded requests (#236)", () => {
  const examples = readFileSync(path.join(PAGES, "Examples.tsx"), "utf8");

  it("togglePreview returns early when its request is no longer current, after the load", () => {
    const toggle = examples.slice(examples.indexOf("const togglePreview"), examples.indexOf("const renderExampleCard"));
    const load = toggle.indexOf("await loadFileContent(path);");
    const guard = toggle.indexOf("if (!isCurrent()) return;");
    expect(load).toBeGreaterThan(-1);
    expect(guard).toBeGreaterThan(load);
  });
});
