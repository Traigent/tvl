"""Extract every guide/book YAML example and check its documented context."""

import io
import json
import re
import sys
import textwrap
from contextlib import redirect_stderr, redirect_stdout
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

from tvl.schema import measurement_validator
from tvl.yaml_safe import safe_load
from tvl_tools.tvl_lint.cli import main as lint_main
from tvl_tools.tvl_validate.cli import main as validate_main


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs/guides/requirements-monitors-responses.md"
BOOK = ROOT / "tvl_book/website_content/book/chapter-06-requirements-in-production.md"
YAML_FENCE = re.compile(r"^[ \t]*```(?:yaml|yml)[^\n]*\n(.*?)^[ \t]*```[ \t]*$", re.M | re.S)
MARKER = re.compile(r"<!-- snippet: (\S+) kind=(\S+) -->\s*$")


def _snippets(path):
    source = path.read_text(encoding="utf-8")
    snippets = []
    for fence in YAML_FENCE.finditer(source):
        marker = MARKER.search(source[:fence.start()])
        assert marker, f"Unmarked YAML snippet in {path}:{source[:fence.start()].count(chr(10)) + 1}"
        snippets.append((*marker.groups(), textwrap.dedent(fence[1])))
    assert snippets, f"No YAML snippets extracted from {path}"
    return snippets


def _header(snippets):
    doc = safe_load(next(body for _, kind, body in snippets if kind == "module"))
    return {key: value for key, value in doc.items() if key not in {"requirements", "monitors", "responses"}}


def _liveness(monitor):
    name = monitor + "_evidence"
    return (
        {"name": name, "kind": "evidence_liveness", "unit": "window", "of": monitor, "max_stale_windows": 2},
        {"name": name + "_check", "requirement": name, "phase": "runtime",
         "evidence": {"source": "windows"}, "decision": {"method": "exact_count_v1"}},
    )


def _primary_monitor(requirement):
    monitor = {
        "name": requirement["name"] + "_prod", "requirement": requirement["name"], "phase": "runtime",
        "evidence": {"source": "customer_side", "deployment_environment": "production"},
        "window": {"tumbling_hours": 24, "grace_minutes": 60},
        "decision": {"method": "exact_count_v1"},
        "episode": {"closure_windows": 1, "closure_max_age_hours": 48},
    }
    if requirement["kind"] == "rate_bound":
        # The wrapper must permit MET at min_samples, including the 1% examples.
        n, theta = 200, Fraction(str(requirement["max_rate"]))
        while (1 - theta) ** n > Fraction(1, 20):
            n += 1
        monitor["decision"] = {
            "method": "clopper_pearson_rational_v2", "confidence": 0.95, "false_alarm_budget": 0.05,
            "horizon_days": 30, "min_samples": n, "max_unresolved_fraction": 0.05,
        }
    if requirement["violation"].get("pattern") in {"precedence", "bounded_response", "protocol"}:
        monitor["limits"] = {"max_active_obligations": 64, "max_tracked_correlations": 1024}
    return monitor


def _wrap(kind, body, snippets, tmp_path):
    if kind in {"module", "pack", "yaml-plain"}:
        return body
    header = _header(snippets)
    if kind == "body":
        # Concatenation preserves YAML anchors within the fragment.
        return yaml.safe_dump(header, sort_keys=False) + body
    fragment = safe_load(body)
    if kind == "overlay":
        from tvl_tools.tvl_compose.cli import compose

        assert fragment["_tvl_overlay"]["extends"] == "support-bot.tvl.yml"
        base = next(text for name, _, text in _snippets(GUIDE) if name == "support-bot")
        (tmp_path / "support-bot.tvl.yml").write_text(base, encoding="utf-8")
        overlay_path = tmp_path / "example.overlay.yml"
        overlay_path.write_text(body, encoding="utf-8")
        doc = compose(overlay_path)
    elif kind in {"req", "monitorfrag"}:
        if kind == "req":
            assert len(fragment) == 1
            requirement = fragment[0]
            monitors = [_primary_monitor(requirement)]
        else:
            monitors = fragment
            # The monitor fragment explicitly refers to this requirement.
            requirement = {
                "name": "charge_needs_authorization", "kind": "zero_tolerance", "unit": "invocation",
                "violation": {"pattern": "precedence", "a": {"event": "authorization_granted", "ref": "payment_auth"},
                              "b": {"event": "tool_call", "tool": "payments.charge"},
                              "mode": "single_use", "correlate_by": "correlation_id"},
            }
        live_requirement, live_monitor = _liveness(monitors[0]["name"])
        doc = dict(header, requirements=[requirement, live_requirement], monitors=[*monitors, live_monitor])
    elif kind == "ladder":
        doc = safe_load(next(text for name, _, text in snippets if name == "campus-latency"))
        doc["responses"] = fragment["responses"]
    elif kind in {"rules", "evidence", "addmon", "addreq"}:
        doc = safe_load(next(text for name, _, text in _snippets(GUIDE) if name == "support-bot"))
        if kind == "rules":
            doc["responses"] = [{"name": "ladder", "rules": fragment}]
        elif kind == "evidence":
            monitor = next(m for m in doc["monitors"] if m["name"] == "fast_enough_prod")
            monitor["evidence"] = fragment["evidence"]
        elif kind == "addmon":
            doc["monitors"].extend(fragment)
        else:
            names = {r["name"] for r in fragment}
            doc["requirements"] = [r for r in doc["requirements"] if r["name"] not in names] + fragment
    else:
        raise AssertionError(f"Unknown snippet context: {kind}")
    return yaml.safe_dump(doc, sort_keys=False)


def _run_cli(main, path, monkeypatch):
    output, errors = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "argv", ["tvl-doc-check", str(path), "--format", "json"])
    code = 0
    with redirect_stdout(output), redirect_stderr(errors):
        try:
            main()
        except SystemExit as exc:
            code = exc.code
    assert not errors.getvalue(), errors.getvalue()
    return code, json.loads(output.getvalue())


CASES = [(path, name, kind, body) for path in (GUIDE, BOOK) for name, kind, body in _snippets(path)]


@pytest.mark.parametrize("path,name,kind,body", CASES, ids=[f"{path.stem}:{name}" for path, name, _, _ in CASES])
def test_documented_yaml_snippet(path, name, kind, body, tmp_path, monkeypatch):
    wrapped = _wrap(kind, body, _snippets(path), tmp_path)
    snippet_path = tmp_path / (name + ".yml")
    snippet_path.write_text(wrapped, encoding="utf-8")
    validate_code, validated = _run_cli(validate_main, snippet_path, monkeypatch)
    lint_code, linted = _run_cli(lint_main, snippet_path, monkeypatch)
    if kind == "yaml-plain":
        # These fences are measurement bundles, intentionally not TVL modules.
        measurement_validator().validate(safe_load(body))
        assert validate_code == 2 and not validated["ok"]
        assert {issue["code"] for issue in validated["issues"]} == {"schema_error"}
        assert lint_code == 2 and not linted["ok"]
        assert {issue["code"] for issue in linted["issues"]} == {"empty_objectives", "invalid_alpha"}
    else:
        assert validate_code == 0 and validated["ok"], validated
        assert lint_code == 0 and linted["ok"], linted
