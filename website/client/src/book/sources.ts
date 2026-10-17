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
} as const;

export type SourceKey = keyof typeof SOURCES;

export function pinnedUrl(key: SourceKey): string {
  return `https://github.com/Traigent/tvl/blob/${PINNED_COMMIT}/${SOURCES[key].path}`;
}
