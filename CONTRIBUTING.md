# Contributing to TVL

Thank you for your interest in improving TVL. This repository contains the normative specification, the reference tools and Python SDK, examples, the formal semantics and proofs, the VS Code extension, and the website. By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- Questions and bug reports: see [SUPPORT.md](SUPPORT.md). Security issues go through [SECURITY.md](SECURITY.md), never a public issue.
- For anything larger than a fix, open an issue first so a maintainer can say whether it fits.
- A change to the language itself follows the [RFC process](#proposing-a-spec-change).
- How decisions are made: [GOVERNANCE.md](GOVERNANCE.md).

## Contributor agreement

External pull requests need a signed contributor license agreement before they can be merged. The agreement for this repository is being prepared; until it is published here, external pull requests cannot be merged. Issues, RFC drafts and comments are welcome now. Contributions from Traigent employees are covered by their employment agreements.

## Development setup

You need Python 3.10 or newer. CI uses Python 3.11 and installs the package in editable mode with the `dev` extra. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

The repository also contains a `uv.lock` file. If you use [uv](https://docs.astral.sh/uv/), run `uv sync --extra dev` to install the package and the development dependencies from it; CI does not use uv, so the `pip` command above is the reference.

For website changes, also install [Node.js](https://nodejs.org/en/download) 22 and [pnpm](https://pnpm.io/installation) 10, matching CI. For VS Code extension changes, install Node.js 22, which includes npm.

The command-line tools are installed with the package: `tvl-parse`, `tvl-lint`, `tvl-validate`, `tvl-config-validate`, `tvl-measure-validate`, `tvl-ci-gate`, `tvl-check-structural`, `tvl-check-operational`, `tvl-compose`, `tvl-compile-runtime` and `tvl-microsim-bridge`. Return codes: `0` on success (for `tvl-ci-gate`, a `Promote` decision); `5` when `tvl-config-validate` fails; `2` for every other validation, lint, structural UNSAT, operational, composition, compilation or gate failure.

## Running the checks

Run what is relevant to your change before opening a pull request. CI runs the Python tests, the website build and tests, CodeQL, and (for changes under `proofs/`, `spec/grammar/`, `formalization/`) the Lean build.

| Area | Command |
|------|---------|
| Python tests (CI) | `pytest -q tests` |
| Conformance suite | `pytest -q tests/test_conformance_suite.py` |
| Conformance fixture integrity (TVL 1.3 draft) | `python conformance/tools/check_runtime_cases.py` |
| Lean proofs (CI) | `cd proofs && lake build` (needs the Lean toolchain from [elan](https://github.com/leanprover/elan); CI also rejects `sorry`, `admit` and `axiom` in `proofs/`) |
| Website (CI) | `cd website && pnpm install --frozen-lockfile && pnpm run test && pnpm run build` |
| VS Code extension | `cd vscode-tvl && npm ci && npm test` |

The conformance suite is also part of `pytest -q tests`; the second row runs it alone.

When you add or change an example, run the tools on it:

```bash
tvl-validate spec/examples/<file>.yml
tvl-lint spec/examples/<file>.yml
```

Examples live in `spec/examples/`. Keep them focused (15 to 40 lines).

Some files are copies. If you change `spec/grammar/*.json`, copy the files into `vscode-tvl/schemas/` and `editor_shared/vscode/schemas/` so they stay byte-identical (`tests/test_editor_schema_sync.py` fails otherwise). When files under `docs/` or `spec/` that the website mirrors change, run `pnpm --dir website run sync:canonical`.

### Lint

The project sets a `ruff` target version in `pyproject.toml`. `ruff` is not part of the `dev` extra and CI does not run it, and the existing code has findings, so a whole-tree `ruff check .` is not a clean baseline. Run it on the files you touch and do not add new findings:

```bash
python -m pip install ruff
ruff check path/to/changed_file.py
```

## Pull requests

- **One topic per pull request.** Keep the diff reviewable.
- **Tests for behaviour changes.** A bug fix includes a test that fails without the fix.
- **Changelog.** Add an entry under `[Unreleased]` in [CHANGELOG.md](CHANGELOG.md).
- **Diagnostics.** Every new lint code or diagnostic is documented in [docs/reference/error-codes.md](docs/reference/error-codes.md).
- **Documentation.** Update the docs under `docs/` when behaviour or syntax changes.
- **Do not include secrets, credentials or customer data** in examples, tests or fixtures.
- Fill in the [pull request template](.github/PULL_REQUEST_TEMPLATE.md). A maintainer is requested for review automatically ([CODEOWNERS](.github/CODEOWNERS)).
- Open the pull request when the change is complete and the checks above pass locally.

### Commit messages

Follow the repository history: [Conventional Commits](https://www.conventionalcommits.org/), for example `feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`, `ci: ...`, with an optional scope such as `fix(validation): ...`. Write the subject in the imperative and say why in the body when it is not obvious.

## Proposing a spec change

For a clarification or a small gap, open a **Spec change** issue. A change that alters the language (new syntax or blocks, a different meaning for a construct, new or changed diagnostic codes, schema or promotion-contract changes) needs an RFC.

1. Copy [formalization/rfc-template.md](formalization/rfc-template.md) to `formalization/rfc-NNNN-short-title.md` and open a pull request.
2. Discuss it in the open on that pull request.
3. The maintainers accept or reject it, as described in [GOVERNANCE.md](GOVERNANCE.md).
4. An accepted spec change includes conformance cases and, where it touches constructs covered by the formal semantics or the Lean proofs, the matching updates.

The full lifecycle, numbering and review rules are in [formalization/README.md](formalization/README.md). Keep normative statements precise.
