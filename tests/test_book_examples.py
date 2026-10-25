"""Run every entry of spec/examples/book/manifest.yaml with the public tools.

The book only shows results that a public checker reproduces. Also proves that
the legacy corpus walkers skip spec/examples/book/ (those files are
deliberately invalid in places and are not part of the legacy 1.0 baseline).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BOOK_EXAMPLES = ROOT / "spec" / "examples" / "book"
MANIFEST = BOOK_EXAMPLES / "manifest.yaml"

CHECKERS = {
    "tvl-validate": ("tvl_tools.tvl_validate.cli", ["--format", "json"]),
    "tvl-lint": ("tvl_tools.tvl_lint.cli", ["--format", "json"]),
    "tvl-check-structural": ("tvl_tools.tvl_check_structural.cli", ["--json"]),
    "tvl-check-operational": ("tvl_tools.tvl_check_operational.cli", ["--json"]),
    "tvl-config-validate": ("tvl_tools.tvl_config_validate.cli", ["--json"]),
    "tvl-measure-validate": ("tvl_tools.tvl_measure_validate.cli", ["--json"]),
    "tvl-compose": ("tvl_tools.tvl_compose.cli", ["--validate", "--format", "json"]),
    "tvl-compile-runtime": ("tvl_tools.tvl_compile_runtime.cli", ["--format", "json"]),
    "tvl-ci-gate": ("tvl_tools.tvl_ci_gate.cli", []),
}
# Which expected results each checker can prove ("lint" and "fail" take a :CODE suffix).
EXPECT_BY_CHECKER = {
    "tvl-validate": {"valid", "lint"},
    "tvl-lint": {"valid", "lint"},
    "tvl-check-structural": {"sat", "unsat"},
    "tvl-check-operational": {"pass", "fail"},
    "tvl-config-validate": {"pass", "fail"},
    "tvl-measure-validate": {"valid", "fail", "not_ready"},
    "tvl-compose": {"composed", "reject"},
    "tvl-compile-runtime": {"compiled", "fail"},
    "tvl-ci-gate": {"Promote", "Reject", "NoDecision"},
}
# Checkers that take the module as an extra first argument (entry key "module").
NEEDS_MODULE = {"tvl-config-validate", "tvl-measure-validate", "tvl-ci-gate"}
# Checkers that also take a configuration before the file (entry key "config").
NEEDS_CONFIG = {"tvl-measure-validate"}
# The gate takes the module, then the incumbent's bundle (entry key "incumbent"), then the candidate's.
NEEDS_INCUMBENT = {"tvl-ci-gate"}


def _resolve(path: str) -> Path:
    """Manifest paths are relative to spec/examples/book/, except those that start
    with "book/": those are relative to the repository root (the runnable project)."""
    return ROOT / path if path.startswith("book/") else BOOK_EXAMPLES / path


def _entries() -> list[dict]:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["examples"]


def _json_objects(text: str) -> list[dict]:
    decoder = json.JSONDecoder()
    out, i = [], 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        obj, end = decoder.raw_decode(text, i)
        out.append(obj)
        i = end
    return out


def _run(
    checker: str, path: Path, module_file: Path | None = None, config_file: Path | None = None,
    extra: list[str] | None = None,
) -> tuple[int, list[dict]]:
    module, flags = CHECKERS[checker]
    flags = [*flags, *(extra or [])]
    code = f"from {module} import main; import sys; sys.exit(main())"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "python"), str(ROOT)])
    targets = [str(f) for f in (module_file, config_file) if f] + [str(path)]
    if checker == "tvl-ci-gate":  # positional arguments first, then --json
        targets, flags = targets + flags, []
    proc = subprocess.run(
        [sys.executable, "-c", code, *flags, *targets],
        capture_output=True, text=True, env=env, cwd=ROOT, timeout=120,
    )
    return proc.returncode, _json_objects(proc.stdout)


def _codes(report: dict) -> set[str]:
    """Diagnostic codes from a checker report.

    Lint issues, config-validate failures, and the measure-validate lists
    (warnings, promotion-readiness issues, objective and chance issues).
    """
    keys = ("issues", "failures", "warnings", "promotion_readiness", "operational", "chance")
    lists = [report[k] for k in keys if isinstance(report.get(k), list)]
    items = [i for lst in lists for i in lst if isinstance(i, dict)]
    return {i["code"] for i in items if i.get("code") and i.get("severity") != "info"}


@pytest.mark.parametrize(
    "entry", _entries(), ids=lambda e: f"{e['file']}::{e['checker']}::{e['expect']}"
)
def test_manifest_entry(entry: dict) -> None:
    path = _resolve(entry["file"])
    assert path.is_file(), f"manifest names a missing file: {entry['file']}"
    checker = entry["checker"]
    assert checker in CHECKERS, f"unknown checker {checker}"
    expect = entry["expect"]
    kind = expect.split(":", 1)[0]
    assert kind in EXPECT_BY_CHECKER[checker], f"{checker} cannot prove {expect}"
    assert (":" in expect) == (kind in {"lint", "fail", "not_ready", "reject"}), f"bad expect {expect}"

    module_file = None
    if checker in NEEDS_MODULE:
        assert entry.get("module"), f"{checker} needs a 'module' entry"
        module_file = _resolve(entry["module"])
        assert module_file.is_file(), f"manifest names a missing module: {entry['module']}"
    config_file = None
    if checker in NEEDS_CONFIG:
        assert entry.get("config"), f"{checker} needs a 'config' entry"
        config_file = _resolve(entry["config"])
        assert config_file.is_file(), f"manifest names a missing config: {entry['config']}"

    extra: list[str] = []
    if entry.get("pack"):
        assert checker in {"tvl-compose", "tvl-compile-runtime"}, f"{checker} takes no pack"
        assert _resolve(entry["pack"]).is_file(), entry["pack"]
        extra += ["--pack", str(_resolve(entry["pack"]))]
    if checker in NEEDS_INCUMBENT:
        assert entry.get("incumbent"), f"{checker} needs an 'incumbent' entry"
        config_file = _resolve(entry["incumbent"])
        assert config_file.is_file(), entry["incumbent"]
        extra += ["--json"]
    if checker in {"tvl-compose", "tvl-compile-runtime"}:
        import tempfile

        out = Path(tempfile.mkdtemp(prefix="book-example-"))
        if checker == "tvl-compose":
            extra += ["-o", str(out / "composed.tvl.yml")]
        else:
            assert entry.get("token_map"), "tvl-compile-runtime needs a 'token_map' entry"
            extra += ["--token-map", str(_resolve(entry["token_map"])), "--out-dir", str(out / "compiled")]

    code, objs = _run(checker, path, module_file, config_file, extra)
    assert objs, "checker produced no JSON"

    if checker == "tvl-compose":
        report = objs[-1]
        if expect == "composed":
            assert code == 0 and report.get("ok") is True and (out / "composed.tvl.yml").is_file(), report
        else:
            wanted = expect.split(":", 1)[1]
            assert code != 0 and report.get("ok") is False and wanted in json.dumps(report), report
        return
    if checker == "tvl-compile-runtime":
        report = objs[-1]
        if expect == "compiled":
            assert code == 0 and report["ok"] is True and report["contract_digest"], report
            assert {p.name for p in (out / "compiled").iterdir()} == {"runtime-contract.json", "runtime-local.json"}
        else:
            assert code != 0 and expect.split(":", 1)[1] in _codes(report), report
        return
    if checker == "tvl-ci-gate":
        report = objs[-1]
        assert report.get("decision") == expect, report
        assert (code == 0) == (expect == "Promote"), code
        return

    if expect in {"valid", "pass"}:
        report = objs[-1]
        assert code == 0 and report["ok"] is True and not _codes(report), report
        if checker == "tvl-measure-validate":
            # A bundle the book shows as valid must also be one the promotion gate accepts.
            assert report["promotion_ready"] is True, report
            assert report["structural"]["ok"] is True, report
    elif kind == "not_ready":
        # A well-formed bundle the promotion gate may not use: exit 0, ok, not promotion-ready.
        report = objs[-1]
        wanted = expect.split(":", 1)[1]
        assert code == 0 and report["ok"] is True and report["promotion_ready"] is False, report
        assert wanted in _codes(report), f"expected {wanted}, got {sorted(_codes(report))}"
    elif kind in {"lint", "fail"}:
        wanted = expect.split(":", 1)[1]
        codes = set().union(*(_codes(o) for o in objs))
        assert wanted in codes, f"expected {wanted}, got {sorted(codes)}"
        assert code != 0
    else:
        phase = [o for o in objs if o.get("kind") == "PhaseResult"]
        assert phase, "no PhaseResult from the structural checker"
        assert phase[-1]["status"] == {"sat": "passed", "unsat": "unsat"}[expect], phase[-1]
        assert (code == 0) == (expect == "sat")


def test_every_book_example_is_listed() -> None:
    listed = {e["file"] for e in _entries() if not e["file"].startswith("book/")}
    on_disk = {
        p.relative_to(BOOK_EXAMPLES).as_posix()
        for p in BOOK_EXAMPLES.rglob("*")
        if p.is_file() and p.suffix in {".yml", ".yaml"} and p.name != "manifest.yaml"
    }
    assert on_disk == listed, (on_disk ^ listed)


def test_project_files_shown_in_the_book_are_committed_project_files() -> None:
    """Entries outside spec/examples/book/ may only name the runnable project's bundles or configs."""
    outside = [e["file"] for e in _entries() if e["file"].startswith("book/")]
    for f in outside:
        assert f.startswith(("book/support-bot/bundles/", "book/support-bot/configs/")), f
        assert (ROOT / f).is_file(), f


def test_legacy_walkers_skip_book_examples() -> None:
    """The recursive legacy corpus must not contain spec/examples/book/."""
    from tests.model_checking import test_legacy_corpus
    from tests import test_cvars_policies

    assert any(BOOK_EXAMPLES.rglob("*.yml")), "book fixtures should exist"
    assert not [p for p in test_legacy_corpus.CORPUS if BOOK_EXAMPLES in p.parents]
    assert BOOK_EXAMPLES in test_cvars_policies.SKIPPED_EXAMPLE_DIRS
    walked = [p for p in test_cvars_policies.iter_example_files()]
    assert walked and not [p for p in walked if BOOK_EXAMPLES in p.parents]
