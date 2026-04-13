# TVL Terminal Demos

This directory contains scripts for generating terminal demo videos/GIFs for documentation and GitHub READMEs.

## Tool Options

| Tool | Scripted | Output Formats | Best For |
|------|----------|----------------|----------|
| **[VHS](https://github.com/charmbracelet/vhs)** (recommended) | ✅ Yes | GIF, MP4, WebM | Reproducible, version-controlled demos |
| **[asciinema](https://asciinema.org/)** | ❌ Live | asciicast, SVG, GIF | Quick recordings, embeddable player |
| **[terminalizer](https://github.com/faressoft/terminalizer)** | Partial | GIF, WebM | Simple recordings |
| **[svg-term-cli](https://github.com/marionebl/svg-term-cli)** | Converts | SVG | Lightweight, scalable |

## Quick Start with VHS

### 1. Install VHS

```bash
# macOS
brew install vhs

# Linux (via Go)
go install github.com/charmbracelet/vhs@latest

# Arch Linux
yay -S vhs

# Or download binary from GitHub releases
# https://github.com/charmbracelet/vhs/releases
```

### 2. Generate All Demos

```bash
cd tvl/demos
./generate-all.sh
```

### 3. Generate Single Demo

```bash
cd tvl/demos/tapes
vhs validate-spec.tape
```

## Directory Structure

```text
demos/
├── README.md
├── generate-all.sh        # Generate all demos
├── tapes/                  # VHS tape files (scripts)
│   ├── _theme.tape         # Shared theme settings
│   ├── validate-spec.tape
│   ├── constraint-check.tape
│   ├── error-diagnostics.tape
│   └── quick-start.tape
├── mock-cli/               # Mock CLI for demos
│   ├── tvl                 # Simulated tvl command
│   └── tvo                 # Simulated tvo command
└── output/                 # Generated GIFs/videos
    ├── validate-spec.gif
    └── ...
```

## Demo Catalog

| Demo | Description | Duration |
|------|-------------|----------|
| `validate-spec` | Validate a TVL spec file | ~15s |
| `constraint-check` | Check structural constraints with SAT | ~20s |
| `error-diagnostics` | Show helpful error messages | ~20s |
| `quick-start` | End-to-end workflow | ~30s |

## VHS Tape File Syntax

VHS uses `.tape` files with a simple DSL:

```tape
# Include shared theme
Source tapes/_theme.tape

# Set output
Output output/my-demo.gif

# Commands
Type "tvl validate spec.yml"
Enter
Sleep 2s

# Hide commands you don't want shown
Hide
Type "clear"
Enter
Show
```

### Key Commands

| Command | Description | Example |
|---------|-------------|---------|
| `Type` | Type text | `Type "hello"` |
| `Enter` | Press Enter | `Enter` |
| `Sleep` | Pause | `Sleep 2s` |
| `Hide`/`Show` | Hide/show typing | `Hide` |
| `Set` | Configure setting | `Set FontSize 16` |
| `Env` | Set environment var | `Env PATH "..."` |
| `Source` | Include another tape | `Source _theme.tape` |

## Mock CLI

The `mock-cli/` directory contains simulated `tvl` and `tvo` commands that produce realistic output for demos without requiring the actual CLI.

```bash
# Test the mock CLI
./mock-cli/tvl --help
./mock-cli/tvl validate examples/spec.tvl.yml
./mock-cli/tvl check-sat examples/spec.tvl.yml
./mock-cli/tvl explain E1002
```

## Alternative: asciinema

For quick one-off recordings:

```bash
# Install
pip install asciinema

# Record
asciinema rec demo.cast

# Play back
asciinema play demo.cast

# Convert to GIF (requires agg)
cargo install agg
agg demo.cast demo.gif

# Or convert to SVG
npm install -g svg-term-cli
svg-term --in demo.cast --out demo.svg
```

## Embedding in GitHub

### GIF (most compatible)

```markdown
![TVL Demo](demos/output/validate-spec.gif)
```

### With size control

```html
<p align="center">
  <img src="demos/output/validate-spec.gif" alt="TVL Demo" width="800">
</p>
```

### asciinema embed (interactive)

```html
<a href="https://asciinema.org/a/YOUR_ID">
  <img src="https://asciinema.org/a/YOUR_ID.svg" />
</a>
```

### SVG (lightweight, scalable)

```markdown
![TVL Demo](demos/output/demo.svg)
```

## Customization

### Theme Settings

Edit `tapes/_theme.tape`:

```tape
Set Width 1200
Set Height 600
Set FontSize 16
Set FontFamily "JetBrains Mono"
Set Theme "Dracula"
Set TypingSpeed 50ms
```

Available themes: `Dracula`, `GitHub Dark`, `Monokai`, `Nord`, `One Dark`, etc.

### Adding New Demos

1. Create `tapes/your-demo.tape`
2. Start with `Source tapes/_theme.tape`
3. Set output: `Output output/your-demo.gif`
4. Add to `generate-all.sh`
5. Run: `vhs tapes/your-demo.tape`

## Output Formats

```tape
Output demo.gif          # Animated GIF (default, most compatible)
Output demo.mp4          # Video (smaller file size)
Output demo.webm         # WebM video (web-optimized)
Output demo.png          # Final frame screenshot
```

## Tips

1. **Keep demos short** (15-30 seconds max)
2. **Use comments** to explain what's happening
3. **Add pauses** after important output (`Sleep 2s`)
4. **Use Hide/Show** for setup commands
5. **Test with `vhs record`** to iterate quickly
6. **Use mock CLI** for consistent, error-free demos

## Troubleshooting

### VHS not found

```bash
# Add Go bin to PATH
export PATH="$PATH:$(go env GOPATH)/bin"
```

### Font not found

VHS uses fonts from your system. Install JetBrains Mono:

```bash
# macOS
brew tap homebrew/cask-fonts
brew install font-jetbrains-mono

# Linux
sudo apt install fonts-jetbrains-mono
```

### GIF too large

```tape
Set Framerate 15       # Lower framerate (default: 50)
Set Quality 80         # Lower quality
```

Or use MP4/WebM format for smaller files.
