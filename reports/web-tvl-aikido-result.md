# tvl Aikido security slice

## Scope checked

- Worktree: `/home/nimrodbu/Traigent_enterprise/worktrees/aikido-20260619/tvl-main`
- Branch/base: `codex/aikido-tvl-main` on `origin/main`
- CSV rows covered:
  - `18504054` / `315917055` - Express not emitting security headers
- `18795990` / `317886600`, `317886598` - `sendFile()` / file inclusion path traversal findings
  - `29752503` / `315917037` - `dangerouslySetInnerHTML` in `website/client/src/components/CodeIDE.tsx`
  - `18504058` / `315916984`, `315916992` - workflow action pinning
  - `32511197` / `328573321` - `cairosvg`
  - `32511202` / `328573519`, `328573444`, `328573478`, `328573563`, `328573606`, `328573644` - `pillow`
  - `32511213` / `328573815`, `328573773` - `urllib3`
  - `32511208` / `328573679` - `pyarrow`
  - `32511211` / `328573713` - `pytest`
  - `32172473` / `328573020`, `328573073`, `328572974` - `aiohttp`
  - `32172475` / `328573374`, `328573417` - `filelock`
  - `32511212` / `328573745` - `requests`
  - `30484441` / `315915187`, `315915255`, `315915162`, `315915214`, `315915258`, `315915297`, `315915304`, `323038632`, `323038647`, `323038668`, `323038662`, `329845509` - `dompurify`
  - `31809735` / `315916134`, `315916194` - `zod`
  - `31144885` / `315914752` - `@ungap/structured-clone`
  - `31809751` / `315915406`, `315915475`, `315915529` - `mermaid`
  - `31809773` / `315915586` - `qs`
  - `31809779` / `315915641` - `uuid`
  - low hardening touched:
    - `21787912` / `315917046` - examples fetch allowlist
    - `18504060` / `315917005` - replaced enum `assert` guards

## Files intentionally changed

- `.github/workflows/ci.yml`
- `.github/workflows/tvl-website-deploy.yml`
- `pyproject.toml`
- `python/tvl/model.py`
- `uv.lock`
- `website/client/src/components/CodeIDE.tsx`
- `website/client/src/lib/prism.ts`
- `website/client/src/pages/Examples.tsx`
- `website/package.json`
- `website/pnpm-lock.yaml`
- `website/server/index.ts`
- `website/server/index.test.ts`

## What changed

- Hardened the website server:
  - disabled `x-powered-by`
  - added CSP and standard security headers
  - resolved the SPA fallback path once and served the resolved `index.html` path
- Replaced `CodeIDE` HTML string injection with Prism token rendering, removing the `dangerouslySetInnerHTML` sink entirely.
- Added an allowlist guard before examples-page fetches.
- Replaced enum `assert` checks with explicit `ValueError` branches in `python/tvl/model.py`.
- Pinned workflow actions in CI and website deploy to exact SHAs.
- Refreshed `website/pnpm-lock.yaml` with direct version bumps and scoped `pnpm.overrides`:
  - `mermaid 11.15.0`
  - `zod 4.4.3`
  - `dompurify 3.4.11`
  - `qs 6.15.2`
  - `uuid 11.1.1`
  - `@ungap/structured-clone 1.3.1`
- Narrowed Python support metadata to `>=3.10` and regenerated `uv.lock`, which removed the stale vulnerable `<3.10` branch and resolved the scoped packages onto patched versions (`aiohttp 3.14.1`, `cairosvg 2.9.0`, `filelock 3.29.4`, `pillow 12.2.0`, `pyarrow 24.0.0`, `pytest 9.1.1`, `requests 2.34.2`, `urllib3 2.7.0`).

## Validation commands

- `pnpm install --lockfile-only`
  - success
- `pnpm install --lockfile-only` after package/override bumps
  - success
- `uv lock --upgrade-package cairosvg --upgrade-package pillow --upgrade-package urllib3 --upgrade-package pyarrow --upgrade-package aiohttp --upgrade-package filelock --upgrade-package requests --upgrade-package pytest`
  - initial run only advanced `pytest`
  - after `requires-python >=3.10`, rerun succeeded and removed the vulnerable `<3.10` branch
- `pnpm install --frozen-lockfile`
  - success
- `pnpm run check`
  - success
- `pnpm run build`
  - success
  - warnings only: large chunk-size warnings
- `pnpm exec vitest --root . run server/index.test.ts`
  - blocked by sandbox: local socket bind returns `EPERM` even on `127.0.0.1`
- `uv run pytest -q tests`
  - partial signal only: 358 passed, 2 failed, 2 import/setup errors from the existing test harness environment
- `uv run --extra dev python -c "...model enum guard ok"`
  - success

## Remaining / deferred

- No external-only surface-monitoring rows were identified in this TVL slice.
- One low row remains deferred as a likely false positive:
  - `315917031` (`tvl_book/scripts/bootstrap_mdx_book.py`) reads from the static chapter configuration, not arbitrary user-controlled paths.
- `pnpm run build` refreshed generated files under `website/client/public/docs/` and `website/client/public/schemas/`; those are validation collateral, not part of the intended security patch.

## PR-ready

- `yes` for the scoped repo-owned fixes.
- Caveat: the server Vitest file is sandbox-blocked on socket bind, so the build/typecheck and focused Python checks are the reliable local validation signals from this environment.
