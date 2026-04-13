# Change Log

All notable changes to the TVL extension will be documented in this file.

## [0.1.0] - 2024-12-04

### Added

- Initial release
- Syntax highlighting for `.tvl.yml` and `.tvl.yaml` files
- Language configuration (comments, brackets, indentation)
- Integration with tvl-validate CLI
- Integration with tvl-lint CLI
- On-save validation (configurable)
- Commands: "TVL: Validate Current File", "TVL: Lint Current File"
- Configuration options for CLI path and validation behavior

### TVL Keywords Highlighted

- Top-level: `tvl`, `tvl_version`, `tvars`, `constraints`, `objectives`, `defaults`, `meta`
- Properties: `name`, `type`, `domain`, `default`, `description`
- Constraint types: `structural`, `derived`, `operational`
- Constraint operators: `when`, `then`, `require`, `implies`, `forbid`
- Objective directions: `maximize`, `minimize`
- Types: `enum[str]`, `enum[int]`, `float`, `int`, `str`, `bool`
