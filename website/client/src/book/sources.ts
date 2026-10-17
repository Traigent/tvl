/** Normative sources the book links to. Links are pinned to a reviewed commit. */
export const PINNED_COMMIT = "82a0d5651965e724efe2905e83daeb503f623a8e";

export const SOURCES = {
  "rfc-0001": {
    label: "RFC 0001",
    path: "formalization/rfc-0001-knob-bindings-cvars-policies.md",
  },
  "rfc-0002": {
    label: "RFC 0002",
    path: "formalization/rfc-0002-composite-knobs.md",
  },
  "rfc-0003": {
    label: "RFC 0003",
    path: "formalization/rfc-0003-runtime-requirements-monitors-responses.md",
  },
  semantics: { label: "Formal semantics", path: "formalization/tvl-formal-semantics.md" },
  language: { label: "Language reference", path: "docs/reference/language.md" },
  "promotion-evidence": { label: "Promotion evidence contract", path: "spec/promotion-evidence-contract.md" },
  guide: { label: "Requirements, monitors and responses guide", path: "docs/guides/requirements-monitors-responses.md" },
  "getting-started": { label: "Getting started", path: "docs/getting-started.md" },
  "constraint-language": { label: "Constraint language reference", path: "docs/reference/constraint-language.md" },
  "error-codes": { label: "Error code catalog", path: "docs/reference/error-codes.md" },
  schema: { label: "TVL JSON Schema", path: "spec/grammar/tvl.schema.json" },
  conformance: { label: "Conformance suite", path: "conformance/README.md" },
  // The RFC process was added to the contributing guide after PINNED_COMMIT, so this one
  // link is pinned to a later commit of main that has it.
  contributing: { label: "Contributing guide", path: "CONTRIBUTING.md", commit: "acfd1ccfaf44356427cbbcca01a8dbdafaa9fd50" },
  // Discussions are a live forum, not a file: there is no commit to pin.
  discussions: { label: "GitHub Discussions", url: "https://github.com/Traigent/tvl/discussions" },
} as const satisfies Record<string, Source>;

interface Source {
  label: string;
  /** A file in the repository, linked at PINNED_COMMIT or at its own `commit`. */
  path?: string;
  commit?: string;
  /** A page that is not a file, linked as it is. */
  url?: string;
}

export type SourceKey = keyof typeof SOURCES;

export function pinnedUrl(key: SourceKey): string {
  const src: Source = SOURCES[key];
  if (src.url) return src.url;
  return `https://github.com/Traigent/tvl/blob/${src.commit ?? PINNED_COMMIT}/${src.path}`;
}

/** True when a source is linked at the book's PINNED_COMMIT. */
export function atPinnedCommit(key: SourceKey): boolean {
  const src: Source = SOURCES[key];
  return !src.url && !src.commit;
}
