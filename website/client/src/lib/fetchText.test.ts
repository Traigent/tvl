import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "fs";
import { createServer } from "http";
import { tmpdir } from "os";
import path from "path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const SRC = path.resolve(import.meta.dirname, "..");

// A direct fetch call: bare, through window/globalThis/self, with or without a space before "(".
const RAW_FETCH = /(^|[^\w.]|(?:^|[^\w.])(?:window|globalThis|self)\s*\.\s*)fetch\s*\(/;

function rawFetchSites(dir: string, skip: string[] = []): string[] {
  return sourceFiles(dir)
    .filter(file => !skip.includes(file))
    .flatMap(file =>
      readFileSync(file, "utf8")
        .split("\n")
        .map((line, i) => ({ line, at: `${path.relative(dir, file)}:${i + 1}` }))
        .filter(({ line }) => RAW_FETCH.test(line))
        .map(({ at }) => at)
    );
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap(name => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return name === "ui" ? [] : sourceFiles(full);
    return /\.(ts|tsx)$/.test(name) && !name.endsWith(".test.ts") ? [full] : [];
  });
}

describe("fetchText (#240)", () => {
  const server = createServer((req, res) => {
    if (req.url === "/docs/language.md") {
      res.writeHead(200, { "Content-Type": "text/markdown" });
      res.end("# TVL language");
      return;
    }
    res.writeHead(404, { "Content-Type": "text/html" });
    res.end("<!doctype html><title>Not found</title>");
  });
  let base = "";

  beforeAll(async () => {
    await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    if (!address || typeof address === "string") throw new Error("failed to bind test server");
    base = `http://127.0.0.1:${address.port}`;
  });
  afterAll(async () => {
    await new Promise<void>(resolve => server.close(() => resolve()));
  });

  it("returns the body of a successful response", async () => {
    const { fetchText } = await import("./fetchText");
    await expect(fetchText(`${base}/docs/language.md`)).resolves.toBe("# TVL language");
  });

  it("rejects on an HTTP error instead of returning the error page as text", async () => {
    const { fetchText } = await import("./fetchText");
    await expect(fetchText(`${base}/docs/missing.md`)).rejects.toThrow(/404/);
  });
});

describe("no client fetch site skips the status check (#240)", () => {
  it("every fetch( in client/src goes through fetchText", () => {
    const helper = path.join(SRC, "lib", "fetchText.ts");
    expect(rawFetchSites(SRC, [helper])).toEqual([]);
  });

  it.each([
    "const r = await fetch(url);",
    "const r = await window.fetch(url);",
    "const r = await globalThis.fetch(url);",
    "const r = await self.fetch(url);",
    "const r = await fetch (url);",
    "fetch(url).then(r => r.text());",
  ])("catches the direct call %s", line => {
    expect(RAW_FETCH.test(line)).toBe(true);
  });

  it.each([
    "const text = await fetchText(url);",
    "const r = await client.fetch(url);",
    "// prefetch(url) is not a fetch call",
  ])("ignores %s", line => {
    expect(RAW_FETCH.test(line)).toBe(false);
  });

  it("goes red on a planted call in a source file", () => {
    const dir = mkdtempSync(path.join(tmpdir(), "fetch-scan-"));
    try {
      writeFileSync(path.join(dir, "Planted.tsx"), "export const load = () => window.fetch('/x');\n");
      expect(rawFetchSites(dir)).toEqual(["Planted.tsx:1"]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
