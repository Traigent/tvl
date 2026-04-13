# TVL - Tuned Variables Language

[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/traigent.tvl?style=flat-square)](https://marketplace.visualstudio.com/items?itemName=traigent.tvl)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](https://opensource.org/licenses/MIT)

VS Code extension for [TVL (Tuned Variables Language)](https://tvl-lang.org) - the declarative language for defining how your AI systems should be tuned.

## Scope note

Shared TVL grammar/config assets are maintained in `editor_shared/vscode/` and synced into this package via:

```bash
npm run sync:shared
```

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

Install the TVL CLI tools:

```bash
pip install tvl-spec
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

```yaml
tvl:
  module: corp.support.rag_bot
tvl_version: "1.0"

tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4o", "claude-3-sonnet"]

  - name: temperature
    type: float
    domain: { range: [0.0, 1.0] }

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
```

## Links

- [TVL Documentation](https://tvl-lang.org)
- [TVL CLI Reference](https://tvl-lang.org/tools/cli-reference)
- [Examples](https://github.com/Traigent/tvl/tree/main/spec/examples)

## About

TVL is developed by [Traigent](https://traigent.com), the LLM optimization platform.

## License

MIT License - see [LICENSE](LICENSE) for details.
