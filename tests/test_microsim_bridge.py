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
