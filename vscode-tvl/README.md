# TVL - Tuned Variables Language

[![License: Apache--2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)

VS Code extension for [TVL (Tuned Variables Language)](https://tvl-lang.org), a typed, machine-checkable language for specifying what an AI agent must achieve, which parts of its design may vary, and what evidence is required before a candidate may be accepted.

The extension is not published to the VS Code Marketplace or Open VSX. Build it from this repository and install the resulting `.vsix` file (see [Installation](#installation-from-source)).

> **TVL 1.3 (draft) support:** Includes syntax highlighting, snippets, bundled JSON Schemas, and field-addressed diagnostics for TVL 1.3 draft runtime blocks (`requirements`, `monitors`, `responses`) and organisation floor packs (`tvl_pack`, RFC 0003 draft).

## Scope note

Shared TVL grammar and language-configuration assets live in `editor_shared/vscode/` at the repository root. This package carries byte-identical copies in `syntaxes/tvl.tmLanguage.json` and `language-configuration.json`. After changing a shared asset, copy it into this package by hand:

```bash
cp ../editor_shared/vscode/tvl.tmLanguage.json syntaxes/tvl.tmLanguage.json
cp ../editor_shared/vscode/language-configuration.json language-configuration.json
```

## Installation (from source)

1. Install the TVL command-line tools from the repository root (see [Requirements](#requirements)).
2. Build and package the extension:

   ```bash
   cd vscode-tvl
   npm ci
   npm run compile
   npx vsce package
   ```

   This writes `tvl-<version>.vsix` into `vscode-tvl/`.
3. Install the package into VS Code:

   ```bash
   code --install-extension tvl-0.1.0.vsix
   ```

   Replace `0.1.0` with the version in `package.json` if it differs. You can also use the Extensions view, "Install from VSIX...".

To run the extension's own tests: `npm test`.

## Features

### Syntax Highlighting

Full syntax highlighting for `.tvl.yml`, `.tvl.yaml`, `.pack.tvl.yml`, and `.pack.tvl.yaml` files:

- **Top-level blocks**: `tvl`, `tvl_version`, `pack`, `tvars`, `cvars`, `policies`, `composites`, `constraints`, `objectives`, `promotion_policy`, `requirements`, `monitors`, `responses`
- **TVL 1.3 requirement kinds & units**: `rate_bound`, `zero_tolerance`, `recovery_time`, `evidence_liveness`, `trace`, `invocation`, `episode`, `window`
- **TVL 1.3 patterns & metrics**: `absence`, `bounded_existence`, `precedence`, `bounded_response`, `protocol`, `wall_clock_latency_ms`, `cost_usd`, `total_tokens`, `tool_calls`, `traigent.refusal.v1`
- **TVL 1.3 trace & monitor events**: `unit_start`, `unit_end`, `tool_call`, `tool_result`, `model_call`, `handoff`, `error`, `authorization_granted`, `authorization_revoked`, `episode_opened`, `episode_continued`, `episode_open_for`, `episode_resolved`, `episode_withdrawn`, `recovery_overdue`, `recovery_cancelled`, `recovery_recovered`, `burn_breached`, `stale`, `live_again`, `unit_violation`
- **TVL 1.3 response actions & approvals**: `notify`, `open_next_step`, `optimize`, `rollback`, `throttle`, `degrade`, `suspend`, `block_action`, `halt_unit`, `none`, `standing`, `human`
- **Types & operators**: `enum[str]`, `float`, `int`, `bool`, `when`, `then`, `require`, `maximize`, `minimize`

### Snippets (TVL 1.3 Draft)

Built-in snippets for authoring TVL 1.3 runtime blocks and packs:

| Prefix | Description |
|--------|-------------|
| `tvl-rate-bound` | `rate_bound` requirement + runtime monitor + `evidence_liveness` pair |
| `tvl-zero-tolerance-guard` | `zero_tolerance` requirement + `customer_side` monitor + `evidence_liveness` pair + local guard (`block_action`) |
| `tvl-recovery` | `recovery_time` requirement and `episodes` obligation monitor |
| `tvl-promotion-monitor` | `promotion`-phase monitor on `evaluation_set` for release gating |
| `tvl-responses-ladder` | `responses` escalation ladder (`notify`, `open_next_step`, `rollback`, human-approved `suspend`) |
| `tvl-pack-floor` | `tvl_pack` organisation floor document with `tenant_floor` monitors and responses |

### Bundled Schema Validation

Bundled schemas in `schemas/` integrate with the YAML Language Server (`redhat.vscode-yaml`):

- `*.tvl.yml` / `*.tvl.yaml` module files validate against `schemas/tvl.schema.json` (including `examples` and `x-enum` completion hints for closed TVL 1.3 enums)
- `*.pack.tvl.yml` / `*.pack.tvl.yaml` (and `tvl_pack` documents with a root `pack` key) validate against `schemas/tvl-pack.schema.json`

### CLI Validation and Linting

Integrated validation using the TVL CLI tools (`tvl-validate` and `tvl-lint`):

- **On-save validation**: Automatically validate TVL files when saved
- **Manual validation**: Run "TVL: Validate Current File" command
- **Linting**: Run "TVL: Lint Current File" for normative lint checks
- **Field-addressed diagnostics**: Every schema and lint issue returned on exit code 2 is surfaced in the Problems panel with its diagnostic code and dotted field path (e.g., `requirements.0.max_rate: ...`)

## Requirements

The extension shells out to the TVL CLI tools, so they must be on your `PATH` (or configured through `tvl.cli.path`). Install them from the repository root:

```bash
git clone https://github.com/Traigent/tvl.git
cd tvl
python -m pip install -e .
```

Verify installation:

```bash
tvl-validate --help
```

## Extension Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `tvl.validation.enable` | `true` | Enable/disable TVL validation |
| `tvl.validation.onSave` | `true` | Validate TVL files on save |
| `tvl.cli.path` | `tvl-validate` | Path to tvl-validate CLI tool |

## Commands

| Command | Description |
|---------|-------------|
| `TVL: Validate Current File` | Validate the current TVL file |
| `TVL: Lint Current File` | Lint the current TVL file |

## Example TVL 1.3 File (Draft)

This module passes `tvl-validate`, `tvl-lint`, `tvl-check-structural`, and `tvl-check-operational`:

```yaml
tvl:
  module: corp.support.rag_bot
tvl_version: "1.3"

environment:
  snapshot_id: "2026-10-16T00:00:00Z"

evaluation_set:
  dataset: support_eval_v1

tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4o", "gpt-4o-mini"]

objectives:
  - name: quality
    direction: maximize

promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  min_effect:
    quality: 0.02

requirements:
  - name: latency_2s
    kind: rate_bound
    unit: trace
    violation: { metric: wall_clock_latency_ms, exceeds: 2000 }
    max_rate: 0.05
  - name: latency_2s_live
    kind: evidence_liveness
    unit: window
    of: latency_2s_prod
    max_stale_windows: 4

monitors:
  - name: latency_2s_prod
    requirement: latency_2s
    phase: runtime
    profile: backend_v1
    evidence: { source: backend_trace_metadata }
    decision: { method: clopper_pearson_exact_v1 }
  - name: latency_2s_live_check
    requirement: latency_2s_live
    phase: runtime
    evidence: { source: windows }
    decision: { method: exact_count_v1 }

responses:
  - name: latency_alerts
    rules:
      - { id: warn_open, trigger: { monitor: latency_2s_prod, event: episode_opened }, do: notify, severity: warning }
```

## Links

- [TVL Specification](https://tvl-lang.org/specification)
- [Examples](https://github.com/Traigent/tvl/tree/main/spec/examples)

## About

TVL is developed by [Traigent](https://traigent.com).

## License

Apache-2.0 - see [LICENSE](LICENSE) for details.
