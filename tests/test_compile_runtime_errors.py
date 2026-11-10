"""Issue #226: tvl-compile-runtime reports malformed input with a code and lets genuine bugs propagate.

The CLI used to map every exception outside its coded paths to ``schema_error``, which hid
programming errors behind a document diagnosis. Only malformed-input conditions may be coded now.
``ValueError``, ``OSError`` and ``OverflowError`` (an integer beyond the float range) reach the
catch-all as ``schema_error``; anything else propagates.
"""

from __future__ import annotations

import copy
import json
import random
import sys
from pathlib import Path

import pytest
from tvl.lints import lint_module
from tvl.runtime import RuntimeClosedError
from tvl.runtime_projection import token_map_template
from tvl.yaml_safe import safe_load

from tvl_tools.tvl_compile_runtime import cli

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "conformance" / "cases" / "runtime" / "projection" / "numbers-enums-and-methods.yml"
FUZZ_CASES = 400
FUZZ_SEED = 0
BIG = 10**400  # an integer no binary64 value can hold
# The catch-all maps these to schema_error (exit 2); any other exception is a bug and must propagate.
CODED_MALFORMED = (ValueError, OSError, OverflowError)


def _numbers_base() -> dict:
    case = safe_load(FIXTURE.read_text(encoding="utf-8"))
    return {
        "module": case["module"],
        "tokens": {"format": "tvl-token-map/1", "tokens": case["input"]["token_map"]},
        "pack": None,
    }


def _unmonitored_base() -> dict:
    module = {
        "tvl": {"module": "example.audit"},
        "environment": {"snapshot_id": "2026-10-01T00:00:00Z"},
        "evaluation_set": {"dataset": "example.eval"},
        "tvars": [{"name": "x", "type": "int", "domain": {"range": [1, 3]}}],
        "objectives": [{"name": "quality", "direction": "maximize"}],
        "promotion_policy": {"dominance": "epsilon_pareto", "alpha": 0.05, "min_effect": {"quality": 0.01}},
        "tvl_version": "1.3",
        "requirements": [{"name": "unused", "kind": "rate_bound", "unit": "trace",
                          "violation": {"metric": "wall_clock_latency_ms", "exceeds": 2000}, "max_rate": 0.05}],
    }
    pack = {"tvl_version": "1.3", "pack": {"module": "example.floor"}, "requirements": [], "monitors": []}
    return _with_tokens(module, pack)


def _with_tokens(module: dict, pack: dict) -> dict:
    tokens = token_map_template([module, pack])
    for index, entry in enumerate(tokens["tokens"]):
        entry["hosted"] = f"tok_{index:04d}"
    return {"module": module, "tokens": tokens, "pack": pack}


def _constructs_base(band_form: str) -> dict:
    """The unmonitored base plus a banded objective, a convergence block and chance constraints.

    ``band_form`` picks the banded target: ``list`` is ``[low, high]``, ``dict`` is ``{center, tol}``.
    Structural constraints are strings, so their numeric literals are covered by a separate test.
    """
    base = _unmonitored_base()
    module = copy.deepcopy(base["module"])
    target = [0.5, 0.9] if band_form == "list" else {"center": 0.7, "tol": 0.1}
    module["objectives"] = [{"name": "quality", "band": {"target": target, "test": "TOST", "alpha": 0.05}}]
    module["promotion_policy"] = {
        "dominance": "epsilon_pareto",
        "alpha": 0.05,
        "min_effect": {},
        "chance_constraints": [{"name": "latency_slo", "threshold": 0.05, "confidence": 0.95}],
    }
    module["exploration"] = {
        "strategy": {"type": "nsga2"},
        "convergence": {"metric": "hypervolume_improvement", "window": 5, "threshold": 0.01},
    }
    module["constraints"] = {"structural": [{"expr": "x >= 1"}], "derived": []}
    return _with_tokens(module, base["pack"])


BASES = [_numbers_base(), _unmonitored_base(), _constructs_base("list"), _constructs_base("dict")]


def _write_tokens(tmp: Path, base: dict) -> list:
    """Write the valid token map and return the remaining CLI arguments (the caller writes the module)."""
    (tmp / "tokens.json").write_text(json.dumps(base["tokens"]), encoding="utf-8")
    return ["--token-map", str(tmp / "tokens.json"), "--out-dir", str(tmp / "out"), "--format", "json"]


def _observe(monkeypatch: pytest.MonkeyPatch) -> list:
    """Record exceptions that reach run_cli's catch-all.

    The RuntimeClosedError branch and the catch-all both call print_output from inside their
    handler, so sys.exc_info() there names the handled exception. Source is not changed.
    """
    seen: list = []
    original = cli.print_output

    def spy(data, format_type, text_renderer=None):
        exc = sys.exc_info()[1]
        if exc is not None and not isinstance(exc, RuntimeClosedError):
            seen.append(exc)
        return original(data, format_type, text_renderer)

    monkeypatch.setattr(cli, "print_output", spy)
    return seen


def _outcome(seen: list, argv: list) -> tuple:
    """Return ('exit', code), ('catchall', exception type) or ('escaped', exception type) for one run."""
    seen.clear()
    try:
        code, _ = cli.run_cli(argv)
    except Exception as exc:  # noqa: BLE001 - the property under test: nothing may escape
        return ("escaped", type(exc))
    if seen:
        return ("catchall", type(seen[0]))
    return ("exit", code)


def _is_allowed(outcome: tuple) -> bool:
    kind, value = outcome
    if kind == "exit":
        return value in (0, 2)
    if kind == "catchall":
        return issubclass(value, CODED_MALFORMED)
    return False


def _paths(obj, path=(), depth=0, out=None):
    if out is None:
        out = []
    out.append(path)
    if depth < 12:
        if isinstance(obj, dict):
            for key, value in obj.items():
                _paths(value, path + (key,), depth + 1, out)
        elif isinstance(obj, list):
            for index, value in enumerate(obj):
                _paths(value, path + (index,), depth + 1, out)
    return out


def _numeric_leaves(obj, path=()):
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [path]
    out = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            out += _numeric_leaves(value, path + (key,))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            out += _numeric_leaves(value, path + (index,))
    return out


def _set(obj, path, value):
    for part in path[:-1]:
        obj = obj[part]
    obj[path[-1]] = value


def _nested(rng: random.Random):
    value = None
    for _ in range(rng.choice([50, 500])):
        value = [value] if rng.random() < 0.5 else {"a": value}
    return value


def _scalar(rng: random.Random):
    if rng.random() < 0.02:
        return "a" * 200_000
    return copy.deepcopy(rng.choice([
        None, True, False, 0, -1, 2**63, 10**400, 1.5, float("nan"), float("inf"),
        "", "x", "\x00", "‮\x00\x1b[0m", "a" * 4000, [], {}, [None], {"k": None},  # noqa: PLE2502 - deliberate control characters as test input
    ]))


def _mutate_obj(rng: random.Random, obj):
    paths = [p for p in _paths(obj) if p]
    if not paths:
        return _scalar(rng)
    path = rng.choice(paths)
    parent = obj
    for part in path[:-1]:
        parent = parent[part]
    key = path[-1]
    op = rng.choice(["delete", "replace", "rename", "nest"])
    if op == "delete":
        if isinstance(parent, dict):
            del parent[key]
        else:
            parent.pop(key)
    elif op == "replace":
        parent[key] = _scalar(rng)
    elif op == "rename" and isinstance(parent, dict):
        parent[rng.choice(["tvl", "pack", "requirements", "tokens", "format", "x"])] = parent.pop(key)
    else:
        parent[key] = _nested(rng)
    return obj


def _mutate_text(rng: random.Random, text: str) -> bytes:
    op = rng.choice(["truncate", "ctrl", "tabs", "empty", "binary", "alias", "nondict", "indent"])
    if op == "truncate":
        return text[: rng.randrange(len(text) + 1)].encode("utf-8")
    if op == "ctrl":
        char = rng.choice(["\x00", "\x1b", "\t", "\r\n", " ", "﻿", "‮", "\x7f", "\U0001F600"])  # noqa: PLE2502 - deliberate control characters as test input
        index = rng.randrange(len(text) + 1)
        return (text[:index] + char + text[index:]).encode("utf-8")
    if op == "tabs":
        return text.replace("  ", "\t").encode("utf-8")
    if op == "empty":
        return b""
    if op == "binary":
        return bytes(rng.randrange(256) for _ in range(64))
    if op == "alias":
        return b"a: &a [1,1,1,1,1,1,1,1,1]\nb: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a]\nc: &c [*b,*b,*b,*b,*b,*b,*b,*b,*b]\n"
    if op == "nondict":
        return rng.choice(["[1, 2]", '"text"', "null", "42"]).encode("utf-8")
    lines = text.splitlines(True) or [""]
    index = rng.randrange(len(lines))
    lines[index] = "\t" + lines[index]
    return "".join(lines).encode("utf-8")


def _fuzz_argv(rng: random.Random, base: dict, tmp: Path) -> list:
    docs = {"module": copy.deepcopy(base["module"]), "tokens": copy.deepcopy(base["tokens"])}
    if base["pack"] is not None:
        docs["pack"] = copy.deepcopy(base["pack"])
    names = {"module": "module.yml", "tokens": "tokens.json", "pack": "pack0.yml"}
    mutated = set(rng.sample(sorted(docs), k=rng.randint(1, len(docs))))
    for name, obj in docs.items():
        if name not in mutated:
            (tmp / names[name]).write_text(json.dumps(obj), encoding="utf-8")
        elif rng.random() < 0.6:
            for _ in range(rng.randint(1, 3)):
                obj = _mutate_obj(rng, obj)
            (tmp / names[name]).write_text(json.dumps(obj, allow_nan=True), encoding="utf-8")
        else:
            (tmp / names[name]).write_bytes(_mutate_text(rng, json.dumps(obj, allow_nan=True)))
    file_arg = str(tmp / "module.yml")
    out_arg = str(tmp / "out")
    if rng.random() < 0.1:
        file_arg = rng.choice([str(tmp), str(tmp / "nope.yml"), ""])
    if rng.random() < 0.1:
        blocker = tmp / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        out_arg = str(blocker)
    argv = [file_arg, "--token-map", str(tmp / "tokens.json"), "--out-dir", out_arg, "--format", "json"]
    if "pack" in docs:
        argv += ["--pack", str(tmp / "pack0.yml")]
    return argv


def test_fuzz_malformed_input_never_escapes_or_hits_unexpected_catch_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Deterministic malformed-input fuzz: every case exits 0 or 2, or hits only the coded mapping."""
    seen = _observe(monkeypatch)
    rng = random.Random(FUZZ_SEED)
    bad = []
    for index in range(FUZZ_CASES):
        base = BASES[rng.randrange(len(BASES))]
        tmp = tmp_path / f"case_{index:04d}"
        tmp.mkdir()
        argv = _fuzz_argv(rng, base, tmp)
        outcome = _outcome(seen, argv)
        if not _is_allowed(outcome):
            bad.append((index, outcome))
    assert not bad, f"{len(bad)} of {FUZZ_CASES} malformed cases escaped or hit an unexpected exception: {bad[:5]}"


@pytest.mark.parametrize("base_index", range(len(BASES)))
def test_numeric_extremes_never_escape_or_hit_unexpected_catch_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, base_index: int,
) -> None:
    """Every numeric leaf of a valid document set to 10**400, -10**400, inf or nan."""
    seen = _observe(monkeypatch)
    base = BASES[base_index]
    bad = []
    count = 0
    for leaf in _numeric_leaves(base["module"]):
        for value in (10**400, -(10**400), float("inf"), float("nan")):
            module = copy.deepcopy(base["module"])
            _set(module, leaf, value)
            tmp = tmp_path / f"leaf_{count:04d}"
            tmp.mkdir()
            (tmp / "module.yml").write_text(json.dumps(module, allow_nan=True), encoding="utf-8")
            argv = [str(tmp / "module.yml")] + _write_tokens(tmp, base)
            if base["pack"] is not None:
                (tmp / "pack0.yml").write_text(json.dumps(base["pack"]), encoding="utf-8")
                argv += ["--pack", str(tmp / "pack0.yml")]
            outcome = _outcome(seen, argv)
            count += 1
            if not _is_allowed(outcome):
                bad.append((leaf, repr(value)[:20], outcome))
    assert count > 0
    assert not bad, f"{len(bad)} numeric-extreme cases escaped or hit an unexpected exception: {bad[:5]}"


@pytest.mark.parametrize(
    "value,cli_code,cli_path",
    [
        # Positive: the schema accepts it; the lint must report it, not overflow in float().
        # The CLI closes the lint path: the customer key 'quality' is reported as <entry>.
        (10**400, "invalid_min_effect", ["promotion_policy", "min_effect", "<entry>"]),
        # Negative: the schema rejects every negative min_effect (-0.01 gives the same) before the lint runs.
        (-(10**400), "schema_error", ["promotion_policy", "min_effect", "<entry>"]),
    ],
    ids=["huge_positive", "huge_negative"],
)
def test_min_effect_too_large_for_a_float_is_a_coded_document_error(
    tmp_path: Path, value: int, cli_code: str, cli_path: list,
) -> None:
    """A malformed min_effect (an integer float() cannot represent) is a coded document error, exit 2."""
    base = _unmonitored_base()
    base["module"]["promotion_policy"]["min_effect"]["quality"] = value
    codes = [issue["code"] for issue in lint_module(base["module"]) if issue["severity"] == "error"]
    assert codes == ["invalid_min_effect"]

    (tmp_path / "module.yml").write_text(json.dumps(base["module"]), encoding="utf-8")
    argv = [str(tmp_path / "module.yml")] + _write_tokens(tmp_path, base)
    code, result = cli.run_cli(argv)
    assert code == 2 and not result["ok"]
    assert result["issues"][0]["code"] == cli_code
    assert result["issues"][0]["path"] == cli_path


@pytest.mark.parametrize("target", ["compile_runtime_document", "lint_module"])
def test_injected_genuine_bug_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, target: str,
) -> None:
    """A RuntimeError from inside the pipeline is a bug in the tool, not a document defect: it propagates."""
    base = BASES[0]
    (tmp_path / "module.yml").write_text(json.dumps(base["module"]), encoding="utf-8")
    argv = [str(tmp_path / "module.yml")] + _write_tokens(tmp_path, base)

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, target, boom)
    with pytest.raises(RuntimeError, match="boom"):
        cli.run_cli(argv)


def _write_case(tmp: Path, base: dict) -> list:
    (tmp / "module.yml").write_text(json.dumps(base["module"]), encoding="utf-8")
    argv = [str(tmp / "module.yml")] + _write_tokens(tmp, base)
    if base["pack"] is not None:
        (tmp / "pack0.yml").write_text(json.dumps(base["pack"]), encoding="utf-8")
        argv += ["--pack", str(tmp / "pack0.yml")]
    return argv


@pytest.mark.parametrize("base_index", range(len(BASES)))
def test_bases_are_valid_documents(tmp_path: Path, base_index: int) -> None:
    """The unmodified bases exit 0, so a failure in the sweeps comes from the injected value alone."""
    code, result = cli.run_cli(_write_case(tmp_path, BASES[base_index]))
    assert code == 0 and result["ok"], result["issues"]


# Structural constraints hold their literals inside a string, so the numeric-leaf sweep cannot reach them.
STRUCTURAL_EXPRS = [
    (f"x <= {BIG}", "constraint_value_out_of_domain", "le"),
    (f"x >= -{BIG}", "constraint_value_out_of_domain", "ge_negative"),
    (f"x in {{{BIG}}}", "constraint_value_out_of_domain", "in_set"),
    (f"-{BIG} <= x <= 2", "constraint_value_out_of_domain", "interval"),
]


@pytest.mark.parametrize("expr,code,_name", STRUCTURAL_EXPRS, ids=[item[2] for item in STRUCTURAL_EXPRS])
def test_structural_literal_beyond_float_range_is_a_coded_issue(
    tmp_path: Path, expr: str, code: str, _name: str,
) -> None:
    base = _constructs_base("list")
    base["module"]["constraints"] = {"structural": [{"expr": expr}], "derived": []}
    errors = [issue for issue in lint_module(base["module"]) if issue["severity"] == "error"]
    assert [issue["code"] for issue in errors] == [code]
    assert errors[0]["path"][:2] == ["constraints", "structural"]

    cli_code, result = cli.run_cli(_write_case(tmp_path, base))
    assert cli_code == 2 and result["issues"][0]["code"] == code


def _set_band_target_list(module: dict, value: int) -> None:
    module["objectives"][0]["band"]["target"] = [value, BIG]


def _set_band_alpha(module: dict, value: int) -> None:
    module["objectives"][0]["band"]["alpha"] = value


def _set_promotion_alpha(module: dict, value: int) -> None:
    module["promotion_policy"]["alpha"] = value


def _set_chance_threshold(module: dict, value: int) -> None:
    module["promotion_policy"]["chance_constraints"][0]["threshold"] = value


def _set_chance_confidence(module: dict, value: int) -> None:
    module["promotion_policy"]["chance_constraints"][0]["confidence"] = value


def _set_convergence_threshold(module: dict, value: int) -> None:
    module["exploration"]["convergence"]["threshold"] = value


def _set_band_tol(module: dict, value: int) -> None:
    module["objectives"][0]["band"]["target"]["tol"] = value


# One row per lint site that calls float() on a document value: (base form, setter, code, path).
LINT_SITES = [
    ("list", _set_band_target_list, "invalid_band_target", ["objectives", 0, "band", "target"]),
    ("dict", _set_band_tol, "invalid_band_center_tol", ["objectives", 0, "band", "target", "tol"]),
    ("list", _set_band_alpha, "invalid_band_alpha", ["objectives", 0, "band", "alpha"]),
    ("list", _set_promotion_alpha, "invalid_alpha", ["promotion_policy", "alpha"]),
    ("list", _set_chance_threshold, "invalid_chance_threshold",
     ["promotion_policy", "chance_constraints", 0, "threshold"]),
    ("list", _set_chance_confidence, "invalid_chance_confidence",
     ["promotion_policy", "chance_constraints", 0, "confidence"]),
    ("list", _set_convergence_threshold, "invalid_convergence_threshold",
     ["exploration", "convergence", "threshold"]),
]


@pytest.mark.parametrize("sign", [1, -1], ids=["huge_positive", "huge_negative"])
@pytest.mark.parametrize(
    "form,setter,code,path",
    LINT_SITES,
    ids=["band_target", "band_tol", "band_alpha", "promotion_alpha", "chance_threshold",
         "chance_confidence", "convergence_threshold"],
)
def test_lint_site_with_integer_beyond_float_range_is_a_coded_issue(
    form: str, setter, code: str, path: list, sign: int,
) -> None:
    """Each float() site reports the out-of-range integer as a coded error at its path, not an exception."""
    base = _constructs_base(form)
    setter(base["module"], sign * BIG)
    errors = [issue for issue in lint_module(base["module"]) if issue["severity"] == "error"]
    assert [(issue["code"], issue["path"]) for issue in errors] == [(code, path)]


def test_overflow_error_from_the_pipeline_is_a_coded_malformed_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Defence in depth: an OverflowError reaching the catch-all is malformed-input range, exit 2 schema_error."""
    argv = _write_case(tmp_path, BASES[0])

    def overflow(*_args, **_kwargs):
        raise OverflowError("int too large to convert to float")

    monkeypatch.setattr(cli, "compile_runtime_document", overflow)
    code, result = cli.run_cli(argv)
    assert code == 2 and result["ok"] is False
    assert result["issues"][0]["code"] == "schema_error"
