import { readFileSync } from "fs";
import path from "path";
import { describe, expect, it } from "vitest";

const PAGES = path.resolve(import.meta.dirname, "..", "pages");
const ALLOWED = new Set(["/examples/a.yml"]);

describe("loadExample (#240)", () => {
  it("returns the content of a successful load", async () => {
    const { loadExample } = await import("./exampleLoad");
    await expect(loadExample("/examples/a.yml", ALLOWED, undefined, async () => "a: 1")).resolves.toEqual({
      ok: true,
      content: "a: 1",
    });
  });

  it("reports a failed load as an error, never as file content", async () => {
    const { loadExample } = await import("./exampleLoad");
    const result = await loadExample("/examples/a.yml", ALLOWED, undefined, async () => {
      throw new Error("GET /examples/a.yml failed: HTTP 404");
    });
    expect(result.ok).toBe(false);
    expect(result).not.toHaveProperty("content");
    if (!result.ok) expect(result.error).toMatch(/404/);
  });

  it("rejects a path outside the example list without fetching", async () => {
    const { loadExample } = await import("./exampleLoad");
    let fetched = false;
    const result = await loadExample("/etc/passwd", ALLOWED, undefined, async () => {
      fetched = true;
      return "";
    });
    expect(result.ok).toBe(false);
    expect(fetched).toBe(false);
  });

  it("uses the cached content without fetching", async () => {
    const { loadExample } = await import("./exampleLoad");
    const result = await loadExample("/examples/a.yml", ALLOWED, "cached", async () => {
      throw new Error("must not fetch");
    });
    expect(result).toEqual({ ok: true, content: "cached" });
  });
});

describe("Examples page uses the load result (#240)", () => {
  const examples = readFileSync(path.join(PAGES, "Examples.tsx"), "utf8");

  it("Copy writes to the clipboard only after a successful load", () => {
    const copy = examples.slice(examples.indexOf("const copyToClipboard"), examples.indexOf("const togglePreview"));
    expect(copy).toContain("loadFileContent(");
    expect(copy.indexOf("if (!result.ok)")).toBeGreaterThan(-1);
    expect(copy.indexOf("if (!result.ok)")).toBeLessThan(copy.indexOf("writeText("));
  });

  it("the preview panel renders a stored load error only when one is set", () => {
    // The error block must sit behind a truthy previewErrors[example.path] check, not just contain the message.
    expect(examples).toMatch(
      /\)\s*:\s*previewErrors\[example\.path\]\s*\?\s*\(\s*<div role="alert"[^>]*>\s*\{previewErrors\[example\.path\]\}\s*<\/div>\s*\)\s*:/,
    );
  });
});
