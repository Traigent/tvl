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

  it("only a successful load is written into fileContents, never a failed one", () => {
    const load = examples.slice(examples.indexOf("const loadFileContent"), examples.indexOf("const copyToClipboard"));
    const ok = load.indexOf("if (result.ok) {");
    const elseAt = load.indexOf("} else {");
    expect(ok).toBeGreaterThan(-1);
    expect(elseAt).toBeGreaterThan(ok);
    expect(load.match(/setFileContents\(/g)?.length ?? 0).toBe(1);
    expect(load.slice(ok, elseAt)).toContain("setFileContents(");
  });
});

describe("SpecViewer ignores superseded loads and keeps loading state honest (#236)", () => {
  const spec = readFileSync(path.join(PAGES, "SpecViewer.tsx"), "utf8");

  it("a response is written to content only while its request is still current", () => {
    expect(spec).toMatch(/if \(isCurrent\(\)\) setContent\(text\);/);
  });

  it("the finally block clears loading only while its request is still current", () => {
    expect(spec).toMatch(/\.finally\(\(\) => \{\s*if \(isCurrent\(\)\) setLoading\(false\);\s*\}\)/);
  });

  it("a failed load is ignored once superseded and otherwise shows a toast", () => {
    expect(spec).toMatch(/\.catch\(\(err\) => \{\s*if \(!isCurrent\(\)\) return;[\s\S]*?toast\.error\("Failed to load file"\);\s*\}\)/);
  });
});

describe("Specification shows an error state when its documentation fails to load (#272)", () => {
  const spec = readFileSync(path.join(PAGES, "Specification.tsx"), "utf8");

  it("the rejection handler records a visible error message, not only a console entry", () => {
    expect(spec).toMatch(/\.catch\(\(err\) => \{\s*console\.error\("[^"]*", err\);\s*setLoadError\(/);
  });

  it("both documentation tabs render the error message in place of their content", () => {
    expect(spec.match(/\) : loadError \? \(/g)?.length ?? 0).toBe(2);
    expect(spec).toMatch(/role="alert"/);
  });
});
