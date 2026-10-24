# Security Policy

## Scope

This policy covers everything in this repository:

- the TVL specification, JSON Schemas and grammar;
- the Python tools and SDK (`tvl_tools/`, `python/`);
- the VS Code extension (`vscode-tvl/`) and shared editor code;
- the website source (`website/`), published at <https://tvl-lang.org>.

Examples of issues in scope: a validator that crashes or hangs on crafted input, unsafe parsing or file access in a tool, a vulnerability in the extension or website, or a flaw in the specification that lets an unsafe module pass a check the specification says it must fail.

## Reporting a vulnerability

**Do not report security vulnerabilities through public GitHub issues.**

1. **Preferred:** use GitHub private vulnerability reporting: <https://github.com/Traigent/tvl/security/advisories/new>.
2. **Alternatively:** email [security@traigent.ai](mailto:security@traigent.ai).

Please include:

- a description of the vulnerability and where it is (file, tool, or page);
- steps to reproduce, ideally a minimal TVL module or command;
- the potential impact;
- the version or commit you tested;
- a suggested fix, if you have one.

Do not include real secrets or customer data in a report or in example files.

We will acknowledge receipt within 48 hours and provide a detailed response within 7 days.

## Supported versions

| Version | Status |
|---------|--------|
| 1.5.x | Supported |
| 1.3.x–1.4.x | Best effort |
| Below 1.3 | Not supported |

## Disclosure

We follow coordinated disclosure. We will work with you on a fix and a timeline, publish an advisory when a fix is available, and credit you in the advisory if you want to be credited. Please give us a reasonable chance to fix the issue before you disclose it publicly.
