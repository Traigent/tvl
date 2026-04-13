# TVL

TVL (Tuned Variable Language) is a typed specification language for governed tuning, validation, and promotion of AI agents and other adaptive systems.

This repository is the day-1 public home for TVL. In the short term, some materials here are copied from existing Traigent repositories while we converge on a single source of truth. That duplication is intentional for now.

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

## Repository Status

This repo is being assembled as a TVL-first open-source home. Current priorities:

1. keep the core spec and validators stable
2. keep the public website and examples aligned with the canonical content
3. gradually remove short-term duplication from legacy internal repos

## License

- Root repository materials are currently under the MIT license in [LICENSE](LICENSE), unless a subdirectory provides its own license file.
- CLI tools in `tvl_tools/` retain their Apache 2.0 license.

## Links

- Website: <https://tvl-lang.org>
- Repository: <https://github.com/Traigent/tvl>
- Issues: <https://github.com/Traigent/tvl/issues>
