"""Schema and lint agree on the numeric validation boundaries."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from tvl.lints import lint_module
from tvl.schema import validator

ROOT = Path(__file__).resolve().parents[1]
BASE = yaml.safe_load((ROOT / "spec/examples/rag-support-bot.tvl.yml").read_text())


@pytest.mark.parametrize("field,value", [
    ("threshold", -0.1), ("threshold", 5),
    ("confidence", 0), ("confidence", 1),
])
def test_chance_bounds_reject_in_schema_and_lint(field, value):
    doc = copy.deepcopy(BASE)
    doc["promotion_policy"]["chance_constraints"][0][field] = value
    assert list(validator().iter_errors(doc))
    assert f"invalid_chance_{field}" in {i["code"] for i in lint_module(doc)}


@pytest.mark.parametrize("field,value", [("threshold", 0), ("threshold", 1), ("confidence", 0.5)])
def test_chance_bound_controls(field, value):
    doc = copy.deepcopy(BASE)
    doc["promotion_policy"]["chance_constraints"][0][field] = value
    assert not list(validator().iter_errors(doc))
    assert not [i for i in lint_module(doc) if i.get("severity") == "error"]


@pytest.mark.parametrize("field", ["tol", "alpha"])
def test_banded_objective_zero_rejected(field):
    doc = copy.deepcopy(BASE)
    band = {"target": {"center": 1, "tol": 0.1}, "test": "TOST", "alpha": 0.05}
    if field == "tol":
        band["target"]["tol"] = 0
    else:
        band["alpha"] = 0
    doc["objectives"] = [{"name": "quality", "band": band}]
    assert list(validator().iter_errors(doc))
    assert [i for i in lint_module(doc) if i.get("severity") == "error"]


@pytest.mark.parametrize("missing", ["strategy", "window", "threshold"])
def test_exploration_required_fields(missing):
    doc = copy.deepcopy(BASE)
    if missing == "strategy":
        doc["exploration"].pop(missing)
    else:
        doc["exploration"]["convergence"].pop(missing)
    assert list(validator().iter_errors(doc))
    assert [i for i in lint_module(doc) if i.get("severity") == "error"]


def test_hypervolume_zero_threshold_rejected():
    doc = copy.deepcopy(BASE)
    doc["exploration"]["convergence"]["threshold"] = 0
    assert list(validator().iter_errors(doc))
    assert "invalid_convergence_threshold" in {i["code"] for i in lint_module(doc)}


def test_absent_and_null_exploration_stay_valid():
    for value in (None, "absent"):
        doc = copy.deepcopy(BASE)
        if value == "absent":
            doc.pop("exploration")
        else:
            doc["exploration"] = value
        assert not list(validator().iter_errors(doc))


def test_missing_min_effect_remains_a_documented_lint_boundary():
    doc = copy.deepcopy(BASE)
    doc["promotion_policy"]["min_effect"].pop("quality")
    assert not list(validator().iter_errors(doc))
    assert "missing_min_effect" in {i["code"] for i in lint_module(doc)}


def test_role_diagnostics_keep_each_monitor_index():
    path = next((ROOT / "spec/examples/runtime-1.3").glob("02-*.yml"))
    doc = yaml.safe_load(path.read_text())
    assert not [i for i in lint_module(doc) if i.get("severity") == "error"]
    del doc["monitors"][0]["window"]
    del doc["monitors"][0]["decision"]["confidence"]
    doc["monitors"][1]["evidence"]["resolution"] = "terminal_status_v1"

    paths = {
        tuple(i["path"]) for i in lint_module(doc)
        if i["code"] == "runtime_invalid_profile"
    }
    assert paths == {
        ("monitors", 0, "window"),
        ("monitors", 0, "decision", "confidence"),
        ("monitors", 1, "evidence", "resolution"),
    }


def test_action_parameter_diagnostics_keep_response_and_rule_indices():
    path = next((ROOT / "spec/examples/runtime-1.3").glob("02-*.yml"))
    doc = yaml.safe_load(path.read_text())
    monitor = doc["monitors"][0]["name"]
    doc["responses"] = [
        {
            "name": f"controls_{index}",
            "rules": [
                {
                    "id": "restore", "do": "rollback", "approval": "human",
                    "trigger": {"monitor": monitor, "event": "episode_continued"},
                },
                {
                    "id": "stop", "do": "suspend", "approval": "human",
                    "fallback": "invalid_fallback",
                    "trigger": {"monitor": monitor, "event": "episode_continued"},
                },
            ],
        }
        for index in range(2)
    ]
    paths = {
        tuple(i["path"]) for i in lint_module(doc)
        if i["code"] == "runtime_invalid_ladder"
    }
    assert paths == {
        ("responses", index, "rules", rule, field)
        for index in range(2)
        for rule, field in ((0, "target"), (1, "fallback"))
    }


# The boundaries above prove the schema and the lint both REJECT. The schema
# runs first in tvl-validate, so a shared bound could still be reported under
# the generic `schema_error` code while tvl-lint and tvl-ci-gate report the
# documented one -- a new tool-to-tool divergence created by closing the old
# one. docs/reference/error-codes.md lists tvl-validate as a reporter of every
# code below, so these assert WHICH code tvl-validate surfaces, not only that
# it fails.

_SHARED_BOUND_CASES = {
    "invalid_chance_threshold": lambda d: d["promotion_policy"]["chance_constraints"][0]
    .__setitem__("threshold", 5),
    "invalid_chance_confidence": lambda d: d["promotion_policy"]["chance_constraints"][0]
    .__setitem__("confidence", 0),
    "invalid_band_tolerance": lambda d: d.__setitem__(
        "objectives",
        [{"name": "quality", "band": {"target": {"center": 1, "tol": 0}, "test": "TOST", "alpha": 0.05}}],
    ),
    "invalid_band_alpha": lambda d: d.__setitem__(
        "objectives",
        [{"name": "quality", "band": {"target": {"center": 1, "tol": 0.1}, "test": "TOST", "alpha": 0}}],
    ),
    "invalid_convergence_threshold": lambda d: d["exploration"]["convergence"]
    .__setitem__("threshold", 0),
    "invalid_convergence_window": lambda d: d["exploration"]["convergence"].pop("window"),
    "missing_strategy": lambda d: d["exploration"].pop("strategy"),
    "invalid_enum_domain": lambda d: d["tvars"].append(
        {"name": "probe_enum", "type": "enum[int]", "domain": ["three", 4]}
    ),
}


def _cli_codes(tool: str, path: Path) -> tuple[int, set[str]]:
    """Run a CLI the way a user does and return its exit status and codes."""
    proc = subprocess.run(
        [sys.executable, "-m", f"tvl_tools.{tool}.cli", str(path), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.stdout, f"{tool} printed nothing; stderr={proc.stderr[:400]}"
    payload = json.loads(proc.stdout)
    return proc.returncode, {issue["code"] for issue in payload["issues"]}


@pytest.mark.parametrize("code", sorted(_SHARED_BOUND_CASES))
def test_tvl_validate_reports_the_documented_code_not_schema_error(code, tmp_path):
    """tvl-validate, tvl-lint and the error-code catalogue name the same code."""
    doc = copy.deepcopy(BASE)
    _SHARED_BOUND_CASES[code](doc)
    path = tmp_path / "module.tvl.yml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    validate_status, validate_codes = _cli_codes("tvl_validate", path)
    lint_status, lint_codes = _cli_codes("tvl_lint", path)

    assert validate_status == 2 and lint_status == 2
    assert code in lint_codes, f"tvl-lint reported {sorted(lint_codes)} instead of {code}"
    assert code in validate_codes, (
        f"tvl-validate reported {sorted(validate_codes)} instead of {code}; "
        "a shared bound must not be downgraded to the generic schema_error"
    )


# Substituting a lint diagnostic for a schema error must be lossless. Each case
# below carries TWO defects, which is where a one-for-one swap goes wrong: a
# dropped diagnostic, or a code attached to an error it does not describe.

def test_two_missing_required_keys_are_both_reported(tmp_path):
    """One lint replacement must not swallow its neighbour's schema error."""
    doc = copy.deepcopy(BASE)
    doc["tvars"][0].pop("type")
    doc["tvars"][0].pop("domain")
    path = tmp_path / "module.tvl.yml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    status, codes = _cli_codes("tvl_validate", path)
    assert status == 2
    # the lint names the missing type; the missing domain has no lint and keeps
    # the generic code -- but it is still reported.
    assert "missing_tvar_type" in codes
    assert "schema_error" in codes


def test_an_unrelated_schema_error_keeps_its_own_diagnosis(tmp_path):
    """A keyword that diagnoses something specific is never given a child's code."""
    doc = copy.deepcopy(BASE)
    doc["exploration"]["bogus_key"] = 1
    doc["exploration"]["convergence"]["threshold"] = 0
    path = tmp_path / "module.tvl.yml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "tvl_tools.tvl_validate.cli", str(path), "--json"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 2
    issues = json.loads(proc.stdout)["issues"]
    assert "invalid_convergence_threshold" in {i["code"] for i in issues}
    assert any(
        i["code"] == "schema_error" and "bogus_key" in i["message"] for i in issues
    ), f"the unknown-key error was lost: {issues}"


def test_every_lint_in_a_branch_subtree_is_reported(tmp_path):
    """`oneOf` names only the branch point; all the reasons inside it must show."""
    doc = copy.deepcopy(BASE)
    doc["objectives"] = [
        {
            "name": "quality",
            "band": {"target": {"center": 0.5, "tol": 0}, "alpha": 0, "test": "TOST"},
        }
    ]
    path = tmp_path / "module.tvl.yml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    validate_status, validate_codes = _cli_codes("tvl_validate", path)
    lint_status, lint_codes = _cli_codes("tvl_lint", path)

    assert validate_status == 2 and lint_status == 2
    assert {"invalid_band_tolerance", "invalid_band_alpha"} <= lint_codes
    assert {"invalid_band_tolerance", "invalid_band_alpha"} <= validate_codes, (
        f"tvl-validate reported {sorted(validate_codes)}; both bounds must keep "
        "their documented code, not collapse into one schema_error"
    )


def test_a_plain_schema_error_is_untouched(tmp_path):
    """A document whose only defect has no lint counterpart is unchanged."""
    doc = copy.deepcopy(BASE)
    doc["tvl"] = 12345
    path = tmp_path / "module.tvl.yml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    status, codes = _cli_codes("tvl_validate", path)
    assert status == 2
    assert codes == {"schema_error"}


def test_a_branch_failure_keeps_a_reason_no_lint_names(tmp_path):
    """Substituting a branch's lints must not discard the branch error itself.

    A `oneOf` failure is reported only at the branch point, so it is the sole
    report of anything inside the branch that no lint covers -- an unknown key,
    say. Replacing it with the lints found inside would lose that.
    """
    doc = copy.deepcopy(BASE)
    doc["objectives"] = [
        {
            "name": "quality",
            "zz_unknown_field": 1,
            "band": {"target": {"center": 0.5, "tol": 0}, "alpha": 0.05, "test": "TOST"},
        }
    ]
    path = tmp_path / "module.tvl.yml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "tvl_tools.tvl_validate.cli", str(path), "--json"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 2
    issues = json.loads(proc.stdout)["issues"]
    codes = {issue["code"] for issue in issues}
    assert "invalid_band_tolerance" in codes, f"the lint inside the branch is missing: {issues}"
    assert "zz_unknown_field" in proc.stdout, (
        "the unknown key is reported nowhere; the branch error was dropped "
        f"in favour of its subtree lints: {issues}"
    )


def test_the_required_key_pattern_matches_this_jsonschema(tmp_path):
    """Pin the message format the `required` path extension parses.

    `_REQUIRED_KEY_RE` reads the missing key out of jsonschema's message because
    `validator_value` is the whole required list. If upstream rewords that
    message the extension stops firing silently, so assert it against a live
    error rather than a remembered string.
    """
    from jsonschema import Draft202012Validator

    from tvl_tools.tvl_validate import cli as validate_cli

    schema = {"type": "object", "properties": {"a": {}}, "required": ["a"]}
    errors = list(Draft202012Validator(schema).iter_errors({}))
    assert len(errors) == 1
    match = validate_cli._REQUIRED_KEY_RE.match(errors[0].message)
    assert match is not None, f"jsonschema now words this as {errors[0].message!r}"
    assert match.group("key") == "a"


def test_an_unknown_key_at_a_lint_path_keeps_its_own_diagnosis(tmp_path):
    """The same-path twin of test_an_unrelated_schema_error_keeps_its_own_diagnosis.

    There the specific keyword and the lint were parent and child. Here they sit
    at the SAME path, which the prefix rule matches -- and no lint can ever name
    an unknown key, so swallowing the schema error loses its only report.
    """
    doc = copy.deepcopy(BASE)
    doc["promotion_policy"]["require_calibration"] = {"enabled": "yes", "bogus": 1}
    path = tmp_path / "module.tvl.yml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "tvl_tools.tvl_validate.cli", str(path), "--json"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 2
    issues = json.loads(proc.stdout)["issues"]
    assert any(i["code"] == "schema_error" and "bogus" in i["message"] for i in issues), (
        f"the unknown-key error was lost to a lint at its own path: {issues}"
    )


def test_the_redacted_channel_is_not_substituted(tmp_path):
    """TVL 1.3 and packs go through `closed_schema_issues`, which redacts paths.

    Matching a redacted path (`<entry>`) against an unredacted lint path finds
    the wrong key, so that channel opts out of substitution entirely and keeps
    the generic, redacted diagnostics it was designed to emit.

    HONEST LABEL: this is a GUARD, not evidence. It is green on the code before
    the opt-out as well -- this fixture does not reach the substitution on that
    channel. It pins the property for the future; the defect it was written for
    was found by review on a different fixture, not by this test.
    """
    doc = copy.deepcopy(BASE)
    doc["tvl"] = "1.3"
    doc["requirements"] = [{"name": "r", "kind": "zero_tolerance", "unit": "trace"}]
    doc["promotion_policy"]["min_effect"]["ghost_customer_key"] = -1
    path = tmp_path / "module.tvl.yml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "tvl_tools.tvl_validate.cli", str(path), "--json"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    payload = json.loads(proc.stdout)
    for issue in payload["issues"]:
        assert not any(k.startswith("_") for k in issue), f"private key leaked: {issue}"
    # The redacted channel never carries a lint's unredacted message.
    assert "ghost_customer_key" not in proc.stdout, (
        "a redacted diagnostic was replaced by an unredacted lint: " + proc.stdout
    )
