import { parse } from "yaml";
import manifestText from "../../../../../spec/examples/book/manifest.yaml?raw";
import CodeBlock, { wholeWords } from "./CodeBlock";
import { usePrint } from "../context";

interface ManifestEntry {
  file: string;
  expect: string;
  checker: string;
  /** For checkers that also take the module (tvl-config-validate, tvl-measure-validate). */
  module?: string;
  /** For checkers that also take a candidate configuration (tvl-measure-validate). */
  config?: string;
  /** tvl-compose / tvl-compile-runtime: an organisation pack to compose with. */
  pack?: string;
  /** tvl-ci-gate: the incumbent's bundle (the file is the candidate's). */
  incumbent?: string;
  /** tvl-compile-runtime: the token map. */
  token_map?: string;
  note?: string;
}

const files = {
  ...import.meta.glob("../../../../../spec/examples/book/**/*.{yml,yaml}", { query: "?raw", import: "default", eager: true }),
  // The runnable project's committed bundles and configurations (chapter 6).
  ...import.meta.glob("../../../../../book/support-bot/{bundles,configs}/**/*.{yml,yaml}", {
    query: "?raw",
    import: "default",
    eager: true,
  }),
} as Record<string, string>;

/**
 * Manifest paths are relative to spec/examples/book/, except those that start
 * with "book/": those are relative to the repository root (the runnable project).
 */
export function repoPath(file: string): string {
  return file.startsWith("book/") ? file : `spec/examples/book/${file}`;
}

const manifest: ManifestEntry[] = (parse(manifestText) as { examples: ManifestEntry[] }).examples;

function sourceFor(file: string): string {
  const key = Object.keys(files).find((k) => k.endsWith(`/${repoPath(file)}`));
  if (!key) throw new Error(`Example file not found: ${repoPath(file)}`);
  return files[key];
}

export function expectLabel(e: string): string {
  if (e === "valid") return "valid";
  if (e === "pass") return "passes";
  if (e === "sat") return "satisfiable (SAT)";
  if (e === "unsat") return "unsatisfiable (UNSAT)";
  if (e.startsWith("warning:")) return `warning (passes): ${e.slice(8)}`;
  if (e.startsWith("lint:")) return `lint finding: ${e.slice(5)}`;
  if (e.startsWith("fail:")) return `fails: ${e.slice(5)}`;
  if (e.startsWith("not_ready:")) return `valid, not promotion-ready: ${e.slice(10)}`;
  if (e === "composed") return "composes";
  if (e.startsWith("reject:")) return `composition refused: ${e.slice(7)}`;
  if (e === "compiled") return "compiles (two files written)";
  if (e === "Promote" || e === "Reject" || e === "NoDecision") return `gate decision: ${e}`;
  return e;
}

const CHECKER_FLAGS: Record<string, string> = {
  "tvl-validate": "",
  "tvl-lint": "",
  "tvl-check-structural": "",
  "tvl-check-operational": "",
  "tvl-config-validate": "",
  "tvl-measure-validate": "",
};

interface ExampleProps {
  file: string;
  /** Pick the manifest entry by checker when a file has several. */
  checker?: string;
  /** Pick the manifest entry by expected result when a checker has several. */
  expect?: string;
  title?: string;
  /** Show only these 1-based lines, e.g. "21-30"; the check still runs on the whole file. */
  lines?: string;
  /**
   * false: leave out the expected result, for a listing that a Predict box asks about.
   * Show it after the box with <ExampleResult file=... />.
   */
  result?: boolean;
}

/**
 * Listings up to this many lines stay whole on one printed page; longer ones may
 * split. A whole module of the running example fits under it.
 */
const LONG_LISTING_LINES = 45;

/**
 * The 1-based lines to show: one range such as "21-30", or several in order such as
 * "1-8,16". A gap between ranges is shown as one line holding "…", indented like the
 * line after it, so a shortened listing never reads as the whole file.
 */
function excerpt(code: string, lines: string, file: string): string {
  const all = code.replace(/\n$/, "").split("\n");
  const out: string[] = [];
  let last = 0;
  for (const part of lines.split(",")) {
    const m = /^(\d+)(?:-(\d+))?$/.exec(part.trim());
    if (!m) throw new Error(`Example ${file}: lines must look like "21-30" or "1-8,16"`);
    const from = Number(m[1]);
    const to = Number(m[2] ?? m[1]);
    if (from <= last || to < from || to > all.length) throw new Error(`Example ${file}: lines ${lines} out of range or order`);
    if (last && from > last + 1) out.push(`${/^\s*/.exec(all[from - 1])?.[0] ?? ""}\u2026`);
    out.push(...all.slice(from - 1, to));
    last = to;
  }
  return out.join("\n") + "\n";
}

function manifestEntry(file: string, checker?: string, expect?: string): ManifestEntry {
  const entries = manifest.filter(
    (m) => m.file === file && (!checker || m.checker === checker) && (!expect || m.expect === expect),
  );
  if (entries.length === 0) throw new Error(`Example ${file} is not in the book manifest`);
  return entries[0];
}

/** The expected result and the command that checks it, from the book manifest. */
function ResultRow({ entry, file }: { entry: ManifestEntry; file: string }) {
  const print = usePrint();
  const target = [entry.module, entry.config, entry.incumbent, file].filter((f): f is string => Boolean(f)).map(repoPath).join(" ");
  const pack = entry.pack ? ` --pack ${repoPath(entry.pack)}` : "";
  const cmd =
    entry.checker === "tvl-compose"
      ? `tvl-compose ${target}${pack} --validate -o composed.tvl.yml`
      : entry.checker === "tvl-compile-runtime"
        ? `tvl-compile-runtime ${target}${pack} --token-map ${repoPath(entry.token_map ?? "")} --out-dir out`
        : `${entry.checker}${CHECKER_FLAGS[entry.checker] ?? ""} ${target}`;
  return (
    <div className="book-example-result">
      <div>
        <span className="book-label">Expected result</span> <b>{expectLabel(entry.expect)}</b>
        {entry.note ? <span> &mdash; {entry.note}</span> : null}
      </div>
      <div>
        <span className="book-label">Check it</span> <code>{print ? wholeWords(cmd) : cmd}</code>
      </div>
    </div>
  );
}

/** The result row of an Example shown with result={false}, placed later in the text. */
export function ExampleResult({ file, checker, expect }: { file: string; checker?: string; expect?: string }) {
  return <ResultRow entry={manifestEntry(file, checker, expect)} file={file} />;
}

export default function Example({ file, checker, expect, title, lines, result = true }: ExampleProps) {
  const print = usePrint();
  const entry = manifestEntry(file, checker, expect);
  const source = sourceFor(file);
  const code = lines ? excerpt(source, lines, file) : source;
  const isLong = code.replace(/\n$/, "").split("\n").length > LONG_LISTING_LINES;
  const path = `${repoPath(file)}${lines ? `, lines\u00a0${lines.replace(/-/g, "\u2060\u2013\u2060").replace(/,/g, ",\u00a0")}` : ""}`;
  return (
    <figure className={`book-example${isLong ? " book-example-long" : ""}`}>
      <figcaption className="book-example-title">
        <strong>{title ?? file.split("/").pop()}</strong>
        <span className="book-path"> {print ? wholeWords(path) : path}</span>
      </figcaption>
      <CodeBlock code={code} path={file} long={isLong} />
      {result ? <ResultRow entry={entry} file={file} /> : null}
    </figure>
  );
}
