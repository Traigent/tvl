"""Every workflow action is pinned to a full commit SHA with a version comment.

Mirrors the OpenSSF Scorecard Pinned-Dependencies check, so Dependabot action
bumps keep passing while an unpinned action fails.
"""

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted(
    (Path(__file__).resolve().parents[1] / ".github/workflows").glob("*.yml")
)
USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)(.*)$")
PIN_RE = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
VERSION_COMMENT_RE = re.compile(r"#\s*v\d+(\.\d+){0,2}\b")


def _uses_lines():
    for path in WORKFLOWS:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = USES_RE.match(line)
            if match:
                yield pytest.param(
                    path.name, number, match.group(1).strip("'\""), match.group(2),
                    id=f"{path.name}:{number}",
                )


def test_workflows_exist():
    assert WORKFLOWS, "no workflows found"


@pytest.mark.parametrize("name,number,action,rest", list(_uses_lines()))
def test_action_is_pinned_with_version_comment(name, number, action, rest):
    if action.startswith("./"):
        return
    assert PIN_RE.match(action), f"{name}:{number} {action} is not pinned to a full SHA"
    assert VERSION_COMMENT_RE.search(rest), f"{name}:{number} {action} lacks a # v<version> comment"
