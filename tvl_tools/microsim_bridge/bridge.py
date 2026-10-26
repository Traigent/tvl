from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import json

from tvl.yaml_safe import safe_load


@dataclass
class SliderConfig:
    minimum: float
    maximum: float
    step: float


def _to_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _infer_slider(definition: dict[str, Any]) -> SliderConfig | None:
    if "values" in definition and isinstance(definition["values"], Iterable):
        values = [
            _to_number(entry) for entry in definition["values"] if _to_number(entry) is not None
        ]
        if not values:
            return None
        values.sort()
        minimum = values[0]
        maximum = values[-1]
        step = values[1] - values[0] if len(values) > 1 else 1.0
        return SliderConfig(minimum=minimum, maximum=maximum, step=step)
    if "range" in definition and isinstance(definition["range"], Iterable):
        bounds = list(definition["range"])
        if len(bounds) != 2:
            return None
        minimum = _to_number(bounds[0])
        maximum = _to_number(bounds[1])
        if minimum is None or maximum is None:
            return None
        span = maximum - minimum
        resolution = _to_number(definition.get("resolution"))
        if resolution is not None and resolution > 0:
            # A declared range resolution is the grid (Definition 3.6): use it as the step.
            return SliderConfig(minimum=minimum, maximum=maximum, step=resolution)
        # Provide a sensible default step: divide into 16 increments (avoid zeros).
        step = round(span / 16, 4) if span > 0 else 0.1
        return SliderConfig(minimum=minimum, maximum=maximum, step=step)
    return None


def _infer_default(definition: dict[str, Any]) -> float | int | None:
    for key in ("value", "default", "initial", "start"):
        if key in definition:
            maybe_number = _to_number(definition[key])
            if maybe_number is not None:
                return maybe_number
    slider = _infer_slider(definition)
    if slider:
        midpoint = (slider.minimum + slider.maximum) / 2
        step = slider.step or 1.0
        return round(midpoint / step) * step
    return None


def _format_defaults(configuration_space: dict[str, Any]) -> dict[str, float | int]:
    defaults: dict[str, float | int] = {}
    for name, definition in configuration_space.items():
        default = _infer_default(definition)
        if default is None:
            continue
        if isinstance(definition.get("type"), str) and definition["type"] in {"integer", "discrete"}:
            default = int(round(default))
        defaults[name] = default
    return defaults


def _clamp(value: float, slider: SliderConfig | None) -> float:
    if slider is None:
        return value
    return max(slider.minimum, min(slider.maximum, value))


def _snap_to_step(value: float, slider: SliderConfig | None) -> float:
    if slider is None or slider.step <= 0:
        return value
    normalized = (value - slider.minimum) / slider.step
    snapped = round(normalized) * slider.step + slider.minimum
    return _clamp(snapped, slider)


def _coerce(name: str, value: float, slider: SliderConfig | None, type_name: str | None) -> float | int:
    value = _snap_to_step(value, slider)
    if type_name in {"integer", "discrete"}:
        return int(round(value))
    if type_name and type_name.startswith("categorical"):
        return value
    # For continuous values, limit to four decimal places to avoid noisy diffs.
    return round(value, 4)


def _adjust_presets(
    defaults: dict[str, float | int],
    sliders: dict[str, SliderConfig],
    types: dict[str, str],
) -> dict[str, dict[str, float | int]]:
    presets: dict[str, dict[str, float | int]] = {}
    baseline = defaults.copy()
    presets["baseline"] = baseline

    def slider_for(name: str) -> SliderConfig | None:
        return sliders.get(name)

    # Latency spike: raise top_k, drop rerank weight, trim tokens.
    latency = baseline.copy()
    if "retriever_top_k" in latency:
        slider = slider_for("retriever_top_k")
        latency["retriever_top_k"] = _coerce(
            "retriever_top_k",
            latency["retriever_top_k"] * 1.3,
            slider,
            types.get("retriever_top_k"),
        )
    if "rerank_weight" in latency:
        slider = slider_for("rerank_weight")
        latency["rerank_weight"] = _coerce(
            "rerank_weight",
            latency["rerank_weight"] - 0.1,
            slider,
            types.get("rerank_weight"),
        )
    if "response_tokens" in latency:
        slider = slider_for("response_tokens")
        latency["response_tokens"] = _coerce(
            "response_tokens",
            latency["response_tokens"] * 0.8,
            slider,
            types.get("response_tokens"),
        )
    presets["latency-spike"] = latency

    # Budget shift: lower top_k, increase rerank weight, extend tokens.
    budget = baseline.copy()
    if "retriever_top_k" in budget:
        slider = slider_for("retriever_top_k")
        budget["retriever_top_k"] = _coerce(
            "retriever_top_k",
            budget["retriever_top_k"] * 0.75,
            slider,
            types.get("retriever_top_k"),
        )
    if "rerank_weight" in budget:
        slider = slider_for("rerank_weight")
        budget["rerank_weight"] = _coerce(
            "rerank_weight",
            budget["rerank_weight"] + 0.12,
            slider,
            types.get("rerank_weight"),
        )
    if "response_tokens" in budget:
        slider = slider_for("response_tokens")
        budget["response_tokens"] = _coerce(
            "response_tokens",
            budget["response_tokens"] * 1.15,
            slider,
            types.get("response_tokens"),
        )
    presets["budget-shift"] = budget

    return presets


def _tvar_definition(decl: dict[str, Any]) -> dict[str, Any] | None:
    """Legacy-shaped slider definition of a numeric ``tvars`` declaration, else None."""
    type_name = str(decl.get("type") or "").lower()
    domain = decl.get("domain")
    if isinstance(domain, list):
        domain = {"set": domain}
    if not isinstance(domain, dict):
        return None
    definition: dict[str, Any] = {}
    if "range" in domain:
        definition["range"] = domain["range"]
        if "resolution" in domain:
            definition["resolution"] = domain["resolution"]
    elif "set" in domain or "values" in domain:
        definition["values"] = domain.get("set", domain.get("values"))
    else:
        return None
    if type_name == "int":
        definition["type"] = "integer"
    elif type_name == "float":
        definition["type"] = "continuous"
    elif type_name.startswith("enum"):
        values = definition.get("values")
        numeric = isinstance(values, list) and values and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in values
        )
        if not numeric:
            return None
        definition["type"] = "discrete" if all(isinstance(v, int) for v in values) else "continuous"
    else:
        return None
    return definition


def _configuration_space(spec: dict[str, Any]) -> dict[str, Any]:
    """Numeric knobs of a TVL module (``tvars``); the legacy ``configuration_space`` block is a fallback."""
    space: dict[str, Any] = {}
    tvars = spec.get("tvars")
    if isinstance(tvars, list):
        for decl in tvars:
            if isinstance(decl, dict) and isinstance(decl.get("name"), str):
                definition = _tvar_definition(decl)
                if definition is not None:
                    space[decl["name"]] = definition
    if space:
        return space
    legacy = spec.get("configuration_space")
    return legacy if isinstance(legacy, dict) else {}


def _load_spec(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return safe_load(handle)


def build_presets(path: Path) -> dict[str, Any]:
    spec = _load_spec(path)
    configuration_space = _configuration_space(spec)
    defaults = _format_defaults(configuration_space)

    types = {
        name: (configuration_space.get(name, {}).get("type") or "").lower()
        for name in configuration_space
    }

    sliders = {
        name: slider
        for name in configuration_space
        if (slider := _infer_slider(configuration_space[name])) is not None
    }

    slider_payload = {
        name: {
            "min": slider.minimum,
            "max": slider.maximum,
            "step": slider.step,
        }
        for name, slider in sliders.items()
    }

    presets = _adjust_presets(defaults, sliders, types)
    legacy_spec = spec.get("spec") if isinstance(spec.get("spec"), dict) else {}
    tvl_block = spec.get("tvl") if isinstance(spec.get("tvl"), dict) else {}
    payload = {
        "version": "1.0.0",
        "source": {
            "spec_id": tvl_block.get("module", legacy_spec.get("id")),
            "spec_version": spec.get("tvl_version", legacy_spec.get("version")),
        },
        "defaults": {
            key: presets["baseline"][key] for key in presets["baseline"]
        },
        "sliders": slider_payload,
        "presets": {
            key: {
                _serialize_key(k): presets[key][k]
                for k in presets[key]
            }
            for key in presets
        },
    }
    return payload


def _serialize_key(name: str) -> str:
    return name if "_" not in name else name


def dump_presets(payload: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
