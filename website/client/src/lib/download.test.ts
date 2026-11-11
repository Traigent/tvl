import { readdirSync, readFileSync, statSync } from "fs";
import path from "path";
import { afterEach, describe, expect, it, vi } from "vitest";

const SRC = path.resolve(import.meta.dirname, "..");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap(name => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.(ts|tsx)$/.test(name) && !name.endsWith(".test.ts") ? [full] : [];
  });
}

function count(text: string, needle: string): number {
  return text.split(needle).length - 1;
}

describe("object URL lifecycle (#235)", () => {
  it("every file that creates an object URL also revokes it", () => {
    const unbalanced = sourceFiles(SRC)
      .map(file => {
        const text = readFileSync(file, "utf8");
        return {
          file: path.relative(SRC, file),
          created: count(text, "URL.createObjectURL("),
          revoked: count(text, "URL.revokeObjectURL("),
        };
      })
      .filter(f => f.created !== f.revoked);
    expect(unbalanced).toEqual([]);
  });
});

describe("downloadText (#235)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("clicks an anchor for the blob URL, then revokes that URL", async () => {
    const { downloadText } = await import("./download");
    const events: string[] = [];
    const anchor = {
      href: "",
      download: "",
      click: () => events.push(`click ${anchor.href}`),
    };
    vi.stubGlobal("document", {
      createElement: (tag: string) => {
        expect(tag).toBe("a");
        return anchor;
      },
      body: {
        appendChild: () => events.push("append"),
        removeChild: () => events.push("remove"),
      },
    });
    vi.spyOn(URL, "createObjectURL").mockImplementation(() => "blob:test-1");
    const revoke = vi
      .spyOn(URL, "revokeObjectURL")
      .mockImplementation(url => {
        events.push(`revoke ${url}`);
      });

    vi.useFakeTimers();
    try {
      downloadText("spec text", "tvl.ebnf");
      expect(revoke).not.toHaveBeenCalled();
      vi.runAllTimers();
    } finally {
      vi.useRealTimers();
    }

    expect(anchor.download).toBe("tvl.ebnf");
    expect(revoke).toHaveBeenCalledTimes(1);
    expect(revoke).toHaveBeenCalledWith("blob:test-1");
    expect(events).toEqual(["append", "click blob:test-1", "remove", "revoke blob:test-1"]);
  });

  it("revokes the URL even when the click throws", async () => {
    const { downloadText } = await import("./download");
    vi.stubGlobal("document", {
      createElement: () => ({
        click: () => {
          throw new Error("blocked");
        },
      }),
      body: { appendChild: () => undefined, removeChild: () => undefined },
    });
    vi.spyOn(URL, "createObjectURL").mockImplementation(() => "blob:test-2");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);

    vi.useFakeTimers();
    try {
      expect(() => downloadText("x", "x.md")).toThrow("blocked");
      vi.runAllTimers();
    } finally {
      vi.useRealTimers();
    }
    expect(revoke).toHaveBeenCalledWith("blob:test-2");
  });
});
