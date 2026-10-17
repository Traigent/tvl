# Change Log

All notable changes to the TVL extension will be documented in this file.

## Unreleased — TVL 1.3 (draft)

### Added

- Syntax highlighting for TVL 1.3 (RFC 0003 draft) blocks (`requirements`, `monitors`, `responses`, `pack` / `tvl_pack`) and keys in `vscode-tvl/syntaxes/tvl.tmLanguage.json` and `editor_shared/vscode/tvl.tmLanguage.json`.
- Syntax highlighting for TVL 1.3 closed enums: requirement kinds (`rate_bound`, `zero_tolerance`, `recovery_time`, `evidence_liveness`), predicate patterns (`absence`, `bounded_existence`, `precedence`, `bounded_response`, `protocol`), trace and monitor events, response actions (`notify`, `open_next_step`, `optimize`, `rollback`, `throttle`, `degrade`, `suspend`, `block_action`, `halt_unit`), approvals (`none`, `standing`, `human`), and monitor decision methods/sources/profiles.
- Snippets (`snippets/tvl.code-snippets` and `editor_shared/vscode/tvl.code-snippets`):
  - `tvl-rate-bound`: `rate_bound` requirement + runtime monitor + `evidence_liveness` pair
  - `tvl-zero-tolerance-guard`: `zero_tolerance` requirement + monitor + liveness pair + local guard
  - `tvl-recovery`: `recovery_time` requirement + `episodes` obligation monitor
  - `tvl-promotion-monitor`: promotion monitor on `evaluation_set`
  - `tvl-responses-ladder`: `responses` escalation ladder
  - `tvl-pack-floor`: `tvl_pack` organisation floor document
- Bundled JSON Schemas (`schemas/tvl.schema.json` and `schemas/tvl-pack.schema.json`) and YAML/JSON schema associations so `*.tvl.yml` / `*.tvl.yaml` validate against the module schema and `*.pack.tvl.yml` / `*.pack.tvl.yaml` (and `tvl_pack` documents) validate against the pack schema.

### Fixed

- Fixed validation and lint handling when `tvl-validate` or `tvl-lint` exits with code 2 so `result.issues` is never dropped and every issue is reported with its diagnostic code, line location, and dotted field path.

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
