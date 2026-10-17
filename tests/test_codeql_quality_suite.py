"""Keep comprehensive CodeQL coverage active without silent scan guards."""

import copy
import re
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/codeql.yml"
LANGUAGES = ["python", "javascript-typescript", "actions"]
CHECKOUT_RE = re.compile(r"^actions/checkout@[0-9a-f]{40}$")
CODEQL_RE = re.compile(r"^github/codeql-action/(init|analyze)@[0-9a-f]{40}$")
VERSION_COMMENT_RE = re.compile(r"#\s*v\d+(\.\d+){0,2}\b")


def _workflow():
    # BaseLoader preserves GitHub Actions' on key instead of YAML 1.1's bool.
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _assert_version_comment(uses):
    # Comments are lost in the parsed dict, so read the raw workflow text.
    lines = [
        line
        for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if uses in line
    ]
    assert lines, f"{uses} not found in workflow source"
    assert all(
        VERSION_COMMENT_RE.search(line.split(uses, 1)[1]) for line in lines
    ), f"{uses} needs a same-line # v<version> comment"


def _assert_scan_contract(workflow):
    assert set(workflow["on"]) == {"pull_request", "push", "schedule"}
    assert workflow["on"]["pull_request"]["branches"] == ["main"]
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["on"]["schedule"] == [{"cron": "23 3 * * 1"}]
    assert workflow["permissions"] == {
        "actions": "read",
        "contents": "read",
        "security-events": "write",
    }
    assert workflow["concurrency"] == {
        "group": "codeql-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}",
        "cancel-in-progress": "true",
    }
    job = workflow["jobs"]["analyze"]
    assert "if" not in job, "scan job must be unguarded"
    assert job.get("continue-on-error", "false") == "false"
    assert job["strategy"]["fail-fast"] == "false"
    assert job["strategy"]["matrix"] == {
        "include": [
            {"language": language, "build-mode": "none"} for language in LANGUAGES
        ]
    }, "all supported languages must retain build-mode none"
    steps = job["steps"]
    assert len(steps) == 3
    checkout, init, analyze = steps
    assert CHECKOUT_RE.match(
        checkout["uses"]
    ), "checkout must be pinned to a full commit SHA"
    _assert_version_comment(checkout["uses"])
    assert checkout["with"] == {"persist-credentials": "false"}
    assert CODEQL_RE.match(init["uses"]), "init must be pinned to a full commit SHA"
    assert init["with"] == {
        "languages": "${{ matrix.language }}",
        "build-mode": "${{ matrix.build-mode }}",
        "queries": "security-and-quality",
    }, "every event and language must select security-and-quality without filters"
    assert CODEQL_RE.match(
        analyze["uses"]
    ), "analyze must be pinned to a full commit SHA"
    assert (
        init["uses"].split("@")[1] == analyze["uses"].split("@")[1]
    ), "CodeQL init and analyze must share one pin"
    _assert_version_comment(init["uses"])
    _assert_version_comment(analyze["uses"])
    for step in steps:
        assert "if" not in step, "scan steps must be unguarded"
        assert step.get("continue-on-error", "false") == "false"


def test_codeql_comprehensive_scan_contract():
    _assert_scan_contract(_workflow())


def test_uniform_suite_is_a_valid_control():
    workflow = _workflow()
    workflow["jobs"]["analyze"]["steps"][1]["with"]["queries"] = "security-and-quality"
    _assert_scan_contract(workflow)


@pytest.mark.parametrize(
    "mutation,message",
    [
        ("scheduled_only", "every event and language"),
        ("missing_actions", "all supported languages"),
        ("guarded_init", "scan steps must be unguarded"),
    ],
)
def test_scan_contract_rejects_coverage_regressions(mutation, message):
    workflow = copy.deepcopy(_workflow())
    job = workflow["jobs"]["analyze"]
    job["steps"][1]["with"]["queries"] = "security-and-quality"
    if mutation == "scheduled_only":
        job["steps"][1]["with"][
            "queries"
        ] = "${{ github.event_name == 'schedule' && 'security-and-quality' || '' }}"
    elif mutation == "missing_actions":
        job["strategy"]["matrix"]["include"] = [
            row
            for row in job["strategy"]["matrix"]["include"]
            if row["language"] != "actions"
        ]
    else:
        job["steps"][1]["if"] = "${{ false }}"
    with pytest.raises(AssertionError, match=message):
        _assert_scan_contract(workflow)
