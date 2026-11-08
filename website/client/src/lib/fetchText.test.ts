import { readdirSync, readFileSync, statSync } from "fs";
import { createServer } from "http";
import path from "path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const SRC = path.resolve(import.meta.dirname, "..");

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
    const raw = sourceFiles(SRC)
      .filter(file => file !== helper)
      .flatMap(file =>
        readFileSync(file, "utf8")
          .split("\n")
          .map((line, i) => ({ line, at: `${path.relative(SRC, file)}:${i + 1}` }))
          .filter(({ line }) => /(^|[^\w.])fetch\(/.test(line))
          .map(({ at }) => at)
      );
    expect(raw).toEqual([]);
  });
});
