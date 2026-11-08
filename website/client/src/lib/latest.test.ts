import { readFileSync } from "fs";
import path from "path";
import { describe, expect, it } from "vitest";

const PAGES = path.resolve(import.meta.dirname, "..", "pages");

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(r => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("latestOnly (#236)", () => {
  it("lets only the latest request apply when an earlier one resolves last", async () => {
    const { latestOnly } = await import("./latest");
    const requests = latestOnly();
    const applied: string[] = [];
    let loading: string | null = null;

    // The Examples sequence from the issue: Preview A (slow), then Preview B (fast).
    const run = async (name: string, load: Promise<void>) => {
      const isCurrent = requests.begin();
      loading = name;
      await load;
      if (!isCurrent()) return;
      applied.push(name);
      loading = null;
    };
    const slowA = deferred<void>();
    const fastB = deferred<void>();
    const a = run("A", slowA.promise);
    const b = run("B", fastB.promise);
    fastB.resolve();
    await b;
    slowA.resolve();
    await a;

    expect(applied).toEqual(["B"]);
    expect(loading).toBeNull();
  });

  it("cancel() invalidates every outstanding request", async () => {
    const { latestOnly } = await import("./latest");
    const requests = latestOnly();
    const first = requests.begin();
    requests.cancel();
    expect(first()).toBe(false);
    const second = requests.begin();
    expect(second()).toBe(true);
  });
});

describe("pages guard their fetches (#236)", () => {
  const specViewer = readFileSync(path.join(PAGES, "SpecViewer.tsx"), "utf8");
  const examples = readFileSync(path.join(PAGES, "Examples.tsx"), "utf8");

  it("SpecViewer re-enters the loading state and ignores superseded responses", () => {
    const effect = specViewer.slice(specViewer.indexOf("useEffect(() => {"));
    const body = effect.slice(0, effect.indexOf("}, [config]);"));
    expect(body).toContain("setLoading(true)");
    expect(body).toMatch(/\.begin\(\)/);
    expect(body).toMatch(/return \(\) => .*\.cancel\(\)/);
  });

  it("Examples.togglePreview applies only the latest preview request", () => {
    const start = examples.indexOf("const togglePreview");
    const body = examples.slice(start, examples.indexOf("const renderExampleCard", start));
    expect(body).toMatch(/\.begin\(\)/);
    expect(body).toMatch(/if \(!isCurrent\(\)\) return;/);
  });
});
