# TVL

TVL (Tuned Variable Language) is a typed specification language for governed tuning, validation, and promotion of AI agents and other adaptive systems.
It includes the language spec, validators, CLI tools, editor support, examples, educational materials, and website source for `tvl-lang.org`.

## What Is Here

- `spec/` — normative grammar, schemas, examples, and promotion artifacts
- `python/` — lightweight Python SDK and validation logic
- `tvl_tools/` — CLI tools for parse, lint, validate, structural checks, operational checks, compose, config validation, measurement validation, and CI gates
- `tests/` — core public validation and tooling tests
- `conformance/` — small black-box compatibility cases
- `vscode-tvl/` — TVL-only VS Code extension
- `editor_shared/` — shared editor grammar and language configuration assets
- `docs/` — reference docs and getting-started material
- `tvl_book/` — canonical examples, website content, figures, and study materials
- `website/` — React site that powers `tvl-lang.org`
- `formalization/` — formal semantics notes
- `proofs/` — Lean mechanization for selected TVL results
- `demos/` — reproducible terminal demos

## Quick Start

Install the Python package and CLI tools from the repo root:

```bash
python -m pip install -e ".[dev]"
```

Then validate one shipped example:

```bash
tvl-validate spec/examples/rag-support-bot.tvl.yml
tvl-check-structural spec/examples/rag-support-bot.tvl.yml
tvl-check-operational spec/examples/rag-support-bot.tvl.yml
```

## Website

The public site lives under `website/`. Its canonical educational content is synced from:

- `docs/`
- `spec/`
- `tvl_book/website_content/`
- `tvl_book/examples/`

To refresh website-owned generated content:

```bash
cd website
python3 scripts/sync_canonical_resources.py
```

## Using This Repository

Start with:

1. `spec/examples/` for complete TVL modules
2. `docs/` for the language reference and walkthroughs
3. `tvl_tools/` and `python/` for validation and automation
4. `website/` if you are working on the public site

## License

- Code, schemas, validators, CLI tools, editor support, tests, executable examples, and the website application are licensed under Apache-2.0 in [LICENSE](LICENSE), unless a subdirectory provides its own license file.
- Authored documentation, website/book learning content, formalization notes, figures, and the specification PDF are licensed under CC-BY-4.0 as described in [LICENSE-content](LICENSE-content).
- Generated website copies in `website/client/public/docs/` and `website/client/public/book-assets/` follow the same CC-BY-4.0 content license as their canonical sources.

## Links

- Website: <https://tvl-lang.org>
- Repository: <https://github.com/Traigent/tvl>
- Issues: <https://github.com/Traigent/tvl/issues>
