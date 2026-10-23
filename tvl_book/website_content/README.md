# TVL Website Content

This directory is intentionally small. The earlier MDX-authored interactive
book skeleton (`chapters/`, `patterns/`, `materials/`, `paths/`, `concepts/`,
`images/`, `site_overrides/`, and the TVL 1.0–1.2 book chapters) was never
routed by the live site (`website/`) and was removed as unused legacy
content, since it still linked to a contributor's personal SDK fork rather
than the canonical repository.

What remains is actively referenced, not legacy:

- `book/chapter-06-requirements-in-production.md`: the TVL 1.3 requirements/
  monitors/responses chapter, linked from the top-level `README.md`,
  `docs/index.md`, and `docs/guides/requirements-monitors-responses.md`, and
  covered by `tests/test_runtime_doc_snippets.py`.
- `microsims/orientation-rag-circuit/`: the interactive MicroSim, used as the
  default output path for `tvl_tools/microsim_bridge`.

This directory remains under the CC-BY-4.0 license declared in `LICENSE`
(and `LICENSE-content` at the repo root).
