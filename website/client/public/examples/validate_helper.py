#!/usr/bin/env python3
"""Deprecated compatibility helper for the TVL website.

Prefer `book/ch2_validate_spec.py` for the canonical Chapter 2 helper example.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> int:
    print("$", " ".join(cmd))
    proc = subprocess.run(cmd, check=False)
    return proc.returncode


def main() -> int:
    module = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("hello_tvl.yml")

    checks = [
        ["tvl-parse", str(module)],
        ["tvl-lint", str(module)],
        ["tvl-validate", str(module)],
        ["tvl-check-structural", str(module)],
    ]

    for cmd in checks:
        rc = run(cmd)
        if rc != 0:
            return rc

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
