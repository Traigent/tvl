import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
// @ts-expect-error plain ESM module without types
import { resolveStaticPath } from "./static_path.mjs";

let tmp: string;
let root: string;

beforeAll(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), "static-path-"));
  root = path.join(tmp, "public");
  fs.mkdirSync(path.join(root, "book"), { recursive: true });
  fs.mkdirSync(path.join(tmp, "public-evil"));
  fs.writeFileSync(path.join(root, "index.html"), "root");
  fs.writeFileSync(path.join(root, "book", "x"), "x");
  fs.writeFileSync(path.join(tmp, "x"), "outside");
  fs.writeFileSync(path.join(tmp, "public-evil", "secret"), "evil");
});
afterAll(() => fs.rmSync(tmp, { recursive: true, force: true }));

describe("resolveStaticPath", () => {
  it("serves a valid file", () => {
    expect(resolveStaticPath(root, "/book/x")).toEqual({ status: 200, file: path.join(root, "book", "x") });
  });
  it("serves a directory index and the SPA fallback", () => {
    expect(resolveStaticPath(root, "/").file).toBe(path.join(root, "index.html"));
    expect(resolveStaticPath(root, "/missing").file).toBe(path.join(root, "index.html"));
  });
  it("never leaves the root for ../x", () => {
    const r = resolveStaticPath(root, "/../x");
    expect(r.file).not.toBe(path.join(tmp, "x"));
    expect(r.file).toBe(path.join(root, "index.html"));
  });
  it("never leaves the root for %2e%2e/x", () => {
    const r = resolveStaticPath(root, "/%2e%2e/x");
    expect(r.file).toBe(path.join(root, "index.html"));
  });
  it("does not reach a sibling directory sharing the prefix", () => {
    const r = resolveStaticPath(root, "/../public-evil/secret");
    expect(r.file).toBe(path.join(root, "index.html"));
  });
  it("rejects malformed encoding with 400", () => {
    expect(resolveStaticPath(root, "/%E0%A4%A")).toEqual({ status: 400 });
  });
});
