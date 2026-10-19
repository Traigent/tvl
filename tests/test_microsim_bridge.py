"""MicroSim export uses TVAR ranges and requires an explicit destination."""

import json

import pytest
import yaml

from tvl_tools.microsim_bridge import cli
from tvl_tools.microsim_bridge.bridge import build_presets


def _spec(tmp_path, tvars):
    path = tmp_path / "module.yml"
    path.write_text(yaml.safe_dump({"tvl": {"module": "test.controls"}, "tvl_version": "1.0", "tvars": tvars}))
    return path


def test_range_tvars_export_snapped_integer_and_float_values(tmp_path):
    path = _spec(tmp_path, [
        {"name": "retriever_top_k", "type": "int", "domain": {"range": [3, 11], "resolution": 2}},
        {"name": "rerank_weight", "type": "float", "domain": {"range": [0, 1]}},
    ])
    payload = build_presets(path)
    assert payload["source"] == {"spec_id": "test.controls", "spec_version": "1.0"}
    assert payload["defaults"] == {"retriever_top_k": 7, "rerank_weight": 0.5}
    assert payload["sliders"]["retriever_top_k"] == {"min": 3, "max": 11, "step": 2}
    assert payload["sliders"]["rerank_weight"]["step"] == 0.0625
    for preset in payload["presets"].values():
        value = preset["retriever_top_k"]
        assert type(value) is int and 3 <= value <= 11 and (value - 3) % 2 == 0


def test_non_range_and_non_integral_resolution_are_named_on_stderr(tmp_path, capsys):
    path = _spec(tmp_path, [
        {"name": "unused", "type": "enum[str]", "domain": ["a"]},
        {"name": "fractional", "type": "int", "domain": {"range": [1, 4], "resolution": 0.5}},
        {"name": "custom_control", "type": "int", "domain": {"range": [1, 4]}},
    ])
    cli.main([str(path), "--dry-run"])
    output = capsys.readouterr()
    assert set(json.loads(output.out)["defaults"]) == {"custom_control"}
    assert "unused" in output.err and "fractional" in output.err
    assert "no exported TVAR matches a MicroSim control" in output.err


def test_empty_export_refuses_without_writing(tmp_path, capsys):
    path = _spec(tmp_path, [{"name": "choice", "type": "enum[str]", "domain": ["a"]}])
    destination = tmp_path / "presets.json"
    with pytest.raises(SystemExit) as exc:
        cli.main([str(path), "-o", str(destination)])
    assert exc.value.code == 2
    assert not destination.exists()
    assert "no exportable" in capsys.readouterr().err


def test_no_destination_leaves_bundled_path_untouched(tmp_path, monkeypatch, capsys):
    path = _spec(tmp_path, [{"name": "retriever_top_k", "type": "int", "domain": {"range": [1, 4]}}])
    bundled = tmp_path / "tvl_book/website_content/microsims/orientation-rag-circuit/microsim_presets.json"
    bundled.parent.mkdir(parents=True)
    bundled.write_text("sentinel\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        cli.main([str(path)])
    assert exc.value.code == 2 and bundled.read_text() == "sentinel\n"
    assert "--output is required" in capsys.readouterr().err


def test_explicit_destination_and_write_failure(tmp_path, capsys):
    path = _spec(tmp_path, [{"name": "response_tokens", "type": "int", "domain": {"range": [50, 100]}}])
    destination = tmp_path / "presets.json"
    cli.main([str(path), "-o", str(destination)])
    assert json.loads(destination.read_text())["defaults"]["response_tokens"] == 75
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        cli.main([str(path), "-o", str(tmp_path)])
    assert exc.value.code == 2 and "cannot write" in capsys.readouterr().err


def test_legacy_configuration_space_still_exports(tmp_path):
    path = tmp_path / "legacy.yml"
    path.write_text(yaml.safe_dump({"spec": {"id": "test.legacy", "version": "1.0"}, "configuration_space": {"retriever_top_k": {"type": "integer", "range": [3, 11]}}}))
    payload = build_presets(path)
    assert payload["defaults"]["retriever_top_k"] == 7
    assert payload["source"]["spec_id"] == "test.legacy"


def test_small_float_resolution_keeps_lower_anchored_grid(tmp_path):
    path = _spec(tmp_path, [{"name": "rerank_weight", "type": "float", "domain": {"range": [0, 0.0001], "resolution": 0.00003}}])
    payload = build_presets(path)
    for preset in payload["presets"].values():
        value = preset["rerank_weight"]
        assert value / 0.00003 == pytest.approx(round(value / 0.00003))


@pytest.mark.parametrize("kind,bounds,resolution", [
    ("int", [0.6, 0.9], 1), ("float", [0, 1], float("inf")),
    ("float", [0, float("inf")], 0.1), ("float", [0, 1], -1),
    ("float", [0, 1], 0), ("float", [0, 1], True),
    ("float", [0, 1], "small"), ("float", [0, 1], float("nan")),
])
@pytest.mark.parametrize("dry_run", [False, True])
def test_invalid_numeric_domain_refuses_before_write(kind, bounds, resolution, dry_run, tmp_path, capsys):
    path = _spec(tmp_path, [{"name": "response_tokens", "type": kind, "domain": {"range": bounds, "resolution": resolution}}])
    output = tmp_path / "presets.json"
    output.write_text("sentinel\n")
    args = [str(path), "--dry-run"] if dry_run else [str(path), "-o", str(output)]
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2 and output.read_text() == "sentinel\n"
    captured = capsys.readouterr()
    assert "response_tokens" in captured.err and "Traceback" not in captured.err
    if dry_run:
        assert json.loads(captured.out)["ok"] is False


def test_nonfinite_payload_cannot_truncate_destination(tmp_path):
    from tvl_tools.microsim_bridge.bridge import dump_presets

    output = tmp_path / "presets.json"
    output.write_text("sentinel\n")
    with pytest.raises(ValueError):
        dump_presets({"value": float("inf")}, output)
    assert output.read_text() == "sentinel\n"


@pytest.mark.parametrize("bounds,resolution", [
    ([9007199254740993, 9007199254740993], 1),
    ([-9007199254740993, -9007199254740993], 1),
    ([0, 9007199254740993], 1),
    ([0, 10], 9007199254740993),
    ([0, 9007199254740992], 1),
    ([0, 10], 9007199254740992.0),
])
def test_unsafe_integer_precision_is_refused_by_builder(bounds, resolution, tmp_path):
    path = _spec(tmp_path, [{"name": "retriever_top_k", "type": "int", "domain": {"range": bounds, "resolution": resolution}}])
    with pytest.raises(ValueError, match="unsupported numeric precision"):
        build_presets(path)


@pytest.mark.parametrize("bounds,resolution", [
    ([9007199254740993, 9007199254740993], 1),
    ([-9007199254740993, -9007199254740993], 1),
    ([0, 9007199254740993], 1),
    ([0, 10], 9007199254740993),
    ([0, 9007199254740992], 1),
    ([0, 10], 9007199254740992.0),
])
@pytest.mark.parametrize("dry_run", [False, True])
def test_unsafe_integer_precision_cli_preserves_destination(bounds, resolution, dry_run, tmp_path):
    import subprocess
    import sys

    path = _spec(tmp_path, [{"name": "retriever_top_k", "type": "int", "domain": {"range": bounds, "resolution": resolution}}])
    output = tmp_path / "presets.json"
    output.write_text("sentinel\n")
    args = ["--dry-run"] if dry_run else ["-o", str(output)]
    result = subprocess.run([sys.executable, "-m", "tvl_tools.microsim_bridge", str(path), *args], capture_output=True, text=True, check=False)
    assert result.returncode == 2, result.stdout + result.stderr
    assert output.read_text() == "sentinel\n"
    assert "unsupported numeric precision" in result.stderr
    assert "retriever_top_k" in result.stderr and "Traceback" not in result.stderr
    if dry_run:
        assert json.loads(result.stdout)["ok"] is False


@pytest.mark.parametrize("value", [-9007199254740991, 9007199254740991])
def test_safe_integer_boundary_singletons_remain_exact(value, tmp_path):
    path = _spec(tmp_path, [{"name": "retriever_top_k", "type": "int", "domain": {"range": [value, value]}}])
    payload = build_presets(path)
    assert payload["sliders"]["retriever_top_k"] == {"min": value, "max": value, "step": 1}
    assert payload["defaults"]["retriever_top_k"] == value
    assert all(preset["retriever_top_k"] == value for preset in payload["presets"].values())


def test_safe_integer_boundary_resolution_remains_exact(tmp_path):
    value = 9007199254740991
    path = _spec(tmp_path, [{"name": "retriever_top_k", "type": "int", "domain": {"range": [0, value], "resolution": value}}])
    payload = build_presets(path)
    assert payload["sliders"]["retriever_top_k"]["step"] == value
    assert all(preset["retriever_top_k"] in {0, value} for preset in payload["presets"].values())


@pytest.mark.parametrize("lower,upper,step", [
    (9007199254740891, 9007199254740991, 3),
    (-9007199254740991, -9007199254740891, 7),
    (-9007199254740991, 9007199254740991, 3),
    (-9007199254740991, 9007199254740990, 7),
])
def test_safe_integer_offset_and_signed_span_presets_keep_original_grid(lower, upper, step, tmp_path):
    path = _spec(tmp_path, [{"name": "retriever_top_k", "type": "int", "domain": {"range": [lower, upper], "resolution": step}}])
    payload = build_presets(path)
    assert payload["sliders"]["retriever_top_k"] == {"min": lower, "max": upper, "step": step}
    values = [payload["defaults"]["retriever_top_k"], *(preset["retriever_top_k"] for preset in payload["presets"].values())]
    assert all(type(value) is int and lower <= value <= upper and (value - lower) % step == 0 for value in values)


@pytest.mark.parametrize("shape", ["range", "values", "default"])
@pytest.mark.parametrize("value", [9007199254740993, -9007199254740993, "9007199254740993"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_legacy_unsafe_original_integer_cli_preserves_destination(shape, value, dry_run, tmp_path):
    import subprocess
    import sys

    definition = {"type": "integer", shape: [value, value] if shape == "range" else [value] if shape == "values" else value}
    path = tmp_path / "legacy.yml"
    path.write_text(yaml.safe_dump({"configuration_space": {"retriever_top_k": definition}}))
    output = tmp_path / "presets.json"
    output.write_text("sentinel\n")
    args = ["--dry-run"] if dry_run else ["-o", str(output)]
    result = subprocess.run([sys.executable, "-m", "tvl_tools.microsim_bridge", str(path), *args], capture_output=True, text=True, check=False)
    assert result.returncode == 2, result.stdout + result.stderr
    assert output.read_text() == "sentinel\n"
    assert "unsupported numeric precision" in result.stderr and "Traceback" not in result.stderr
    if dry_run:
        assert json.loads(result.stdout)["ok"] is False


@pytest.mark.parametrize("type_name", ["int", "integer", "discrete"])
@pytest.mark.parametrize("key", ["value", "default", "initial", "start"])
def test_legacy_integer_context_rejects_nonintegral_large_numeric_string(type_name, key, tmp_path):
    path = tmp_path / "legacy.yml"
    path.write_text(yaml.safe_dump({"configuration_space": {"custom_control": {"type": type_name, key: "9007199254740993.5"}}}))
    with pytest.raises(ValueError, match="unsupported numeric precision"):
        build_presets(path)


@pytest.mark.parametrize("shape", ["range", "values", "default"])
@pytest.mark.parametrize("value", [-9007199254740991, 9007199254740991, "3"])
def test_legacy_safe_integer_and_numeric_string_controls_remain_supported(shape, value, tmp_path):
    definition = {"type": "integer", shape: [value, value] if shape == "range" else [value] if shape == "values" else value}
    path = tmp_path / "legacy.yml"
    path.write_text(yaml.safe_dump({"configuration_space": {"custom_control": definition}}))
    payload = build_presets(path)
    assert payload["defaults"]["custom_control"] == int(value)
    assert all(preset["custom_control"] == int(value) for preset in payload["presets"].values())


@pytest.mark.parametrize("value", [1e20, "9007199254740993.5", "0.25"])
def test_legacy_large_finite_float_and_fractional_string_controls_stay_supported(value, tmp_path):
    path = tmp_path / "legacy.yml"
    path.write_text(yaml.safe_dump({"configuration_space": {"custom_control": {"type": "float", "default": value}}}))
    payload = build_presets(path)
    assert payload["defaults"]["custom_control"] == float(value)



def test_modern_large_finite_float_stays_supported(tmp_path):
    value = 1e20
    path = _spec(tmp_path, [{"name": "custom_control", "type": "float", "domain": {"range": [value, value]}}])
    payload = build_presets(path)
    assert payload["defaults"]["custom_control"] == value


@pytest.mark.parametrize("shape", ["modern-bounds", "modern-resolution", "legacy-range", "legacy-values", "legacy-default"])
@pytest.mark.parametrize("sign", ["", "-"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_raw_yaml_fractional_integer_precision_refuses_before_write(shape, sign, dry_run, tmp_path):
    import subprocess
    import sys

    raw = f"{sign}9007199254740990.5"
    if shape.startswith("modern"):
        domain = f"range: [{raw}, {raw}]" if shape == "modern-bounds" else f"range: [0, 9007199254740991]\n      resolution: {raw}"
        source = f"tvars:\n  - name: retriever_top_k\n    type: int\n    domain:\n      {domain}\n"
    else:
        key = shape.removeprefix("legacy-")
        value = f"[{raw}, {raw}]" if key == "range" else f"[{raw}]" if key == "values" else raw
        source = f"configuration_space:\n  retriever_top_k:\n    type: integer\n    {key}: {value}\n"
    path = tmp_path / "raw.yml"
    path.write_text(source)
    output = tmp_path / "presets.json"
    output.write_text("sentinel\n")
    args = ["--dry-run"] if dry_run else ["-o", str(output)]
    result = subprocess.run([sys.executable, "-m", "tvl_tools.microsim_bridge", str(path), *args], capture_output=True, text=True, check=False)
    assert result.returncode == 2, result.stdout + result.stderr
    assert output.read_text() == "sentinel\n"
    assert "unsupported numeric precision" in result.stderr and raw in result.stderr
    assert "Traceback" not in result.stderr
    if dry_run:
        assert json.loads(result.stdout)["ok"] is False


@pytest.mark.parametrize("lower,upper,step", [
    (0.1, 0.3, 0.1), (0.1, 0.35, 0.1),
    (0.0, 0.0001, 0.00003), (-0.3, -0.1, 0.1),
    (0.05, 0.35, 0.1), (-0.35, 0.25, 0.2),
])
@pytest.mark.parametrize("dry_run", [False, True])
def test_float_grid_serialized_values_keep_original_decimal_bounds(lower, upper, step, dry_run, tmp_path):
    import subprocess
    import sys
    from fractions import Fraction

    path = _spec(tmp_path, [{"name": "rerank_weight", "type": "float", "domain": {"range": [lower, upper], "resolution": step}}])
    output = tmp_path / "presets.json"
    args = ["--dry-run"] if dry_run else ["-o", str(output)]
    result = subprocess.run([sys.executable, "-m", "tvl_tools.microsim_bridge", str(path), *args], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout if dry_run else output.read_text())
    lo, hi, resolution = (Fraction(repr(value)) for value in (lower, upper, step))
    values = [payload["defaults"]["rerank_weight"], *(preset["rerank_weight"] for preset in payload["presets"].values())]
    for value in values:
        exact = Fraction(repr(value))
        assert lo <= exact <= hi
        assert (exact - lo) % resolution == 0


@pytest.mark.parametrize("source,expected", [
    ("tvars:\n  - name: retriever_top_k\n    type: int\n    domain:\n      range: [3.0, 11.0]\n      resolution: 2.0\n", 7),
    ("tvars:\n  - name: custom_control\n    type: float\n    domain:\n      range: [1.0e+20, 1.0e+20]\n", 1e20),
    ('configuration_space:\n  custom_control:\n    type: float\n    default: "9007199254740993.5"\n', float("9007199254740993.5")),
])
@pytest.mark.parametrize("dry_run", [False, True])
def test_raw_yaml_supported_numeric_controls_remain_usable(source, expected, dry_run, tmp_path):
    import subprocess
    import sys

    path = tmp_path / "control.yml"
    path.write_text(source)
    output = tmp_path / "presets.json"
    args = ["--dry-run"] if dry_run else ["-o", str(output)]
    result = subprocess.run([sys.executable, "-m", "tvl_tools.microsim_bridge", str(path), *args], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout if dry_run else output.read_text())
    assert list(payload["defaults"].values()) == [expected]
