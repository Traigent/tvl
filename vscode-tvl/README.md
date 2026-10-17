# TVL - Tuned Variables Language

[![License: Apache--2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)

VS Code extension for [TVL (Tuned Variables Language)](https://tvl-lang.org), a typed, machine-checkable language for specifying what an AI agent must achieve, which parts of its design may vary, and what evidence is required before a candidate may be accepted.

The extension is not published to the VS Code Marketplace or Open VSX. Build it from this repository and install the resulting `.vsix` file (see [Installation](#installation-from-source)).

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

Full syntax highlighting for `.tvl.yml` and `.tvl.yaml` files:

- **Keywords**: `tvl`, `tvars`, `constraints`, `objectives`
- **Types**: `enum[str]`, `float`, `int`, `bool`
- **Constraint operators**: `when`, `then`, `require`
- **Directions**: `maximize`, `minimize`

### Validation

Integrated validation using the TVL CLI tools:

- **On-save validation**: Automatically validate TVL files when saved
- **Manual validation**: Run "TVL: Validate Current File" command
- **Linting**: Run "TVL: Lint Current File" for best practices

### Error Highlighting

Validation and lint issues appear as:
- Errors in the Problems panel
- Inline squiggles in the editor
- Quick navigation to problem locations

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

## Example TVL File

This module passes `tvl-validate`, `tvl-lint`, `tvl-check-structural`, and `tvl-check-operational`:

```yaml
tvl:
  module: corp.support.rag_bot

environment:
  snapshot_id: "2026-01-01T00:00:00Z"
  bindings:
    llm_gateway: us-east-1
  context:
    gateway_baseline_latency_ms: 180

evaluation_set:
  dataset: s3://datasets/support-tickets/dev.jsonl
  seed: 2024

tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4o", "gpt-4o-mini"]

  - name: temperature
    type: float
    domain:
      range: [0.0, 1.0]
      resolution: 0.05

constraints:
  structural:
    - when: model = "gpt-4o"
      then: temperature <= 0.7

objectives:
  - name: quality
    metric_ref: metrics.quality.v1
    direction: maximize
  - name: cost
    metric_ref: metrics.cost.v1
    direction: minimize

promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  min_effect:
    quality: 0.01
    cost: 0.001
```

## Links

- [TVL Specification](https://tvl-lang.org/specification)
- [Examples](https://github.com/Traigent/tvl/tree/main/spec/examples)

## About

TVL is developed by [Traigent](https://traigent.com).

## License

Apache-2.0 - see [LICENSE](LICENSE) for details.
