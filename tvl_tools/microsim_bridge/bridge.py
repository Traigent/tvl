from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

import json
import math

from tvl.yaml_safe import safe_load


@dataclass
class SliderConfig:
    minimum: float
    maximum: float
    step: float


def _check_numeric_precision(
    value: Any, *, integer_context: bool = False, context: str = "numeric value"
) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, str):
        try:
            exact = Decimal(value)
        except InvalidOperation:
            return
        unsafe = (
            exact.is_finite()
            and exact == exact.to_integral_value()
            and (exact > _JS_MAX_SAFE_INTEGER or exact < -_JS_MAX_SAFE_INTEGER)
        )
    elif isinstance(value, int):
        unsafe = abs(value) > _JS_MAX_SAFE_INTEGER
    elif isinstance(value, float):
        unsafe = integer_context and math.isfinite(value) and abs(value) > _JS_MAX_SAFE_INTEGER
    else:
        return
    if unsafe:
        raise ValueError(
            f"{context}: unsupported numeric precision; integer values must be within "
            f"JavaScript's safe integer range [-{_JS_MAX_SAFE_INTEGER}, {_JS_MAX_SAFE_INTEGER}]"
        )


def _to_number(value: Any, *, integer_context: bool = False) -> float | None:
    _check_numeric_precision(value, integer_context=integer_context)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return None
        _check_numeric_precision(parsed, integer_context=integer_context)
        return parsed
    return None


def _infer_slider(definition: dict[str, Any]) -> SliderConfig | None:
    integer_context = definition.get("type") in ("int", "integer", "discrete")
    if "values" in definition and isinstance(definition["values"], Iterable):
        values = [
            number for entry in definition["values"]
            if (number := _to_number(entry, integer_context=integer_context)) is not None
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
        minimum = _to_number(bounds[0], integer_context=integer_context)
        maximum = _to_number(bounds[1], integer_context=integer_context)
        if minimum is None or maximum is None:
            return None
        span = maximum - minimum
        # Provide a sensible default step: divide into 16 increments (avoid zeros).
        step = (round(span / 16, 4) or span / 16) if span > 0 else 0.1
        return SliderConfig(minimum=minimum, maximum=maximum, step=step)
    return None


def _infer_default(definition: dict[str, Any]) -> float | int | None:
    integer_context = definition.get("type") in ("int", "integer", "discrete")
    for key in ("value", "default", "initial", "start"):
        if key in definition:
            maybe_number = _to_number(definition[key], integer_context=integer_context)
            if maybe_number is not None:
                return maybe_number
    slider = _infer_slider(definition)
    if slider:
        return _snap_to_step((slider.minimum + slider.maximum) / 2, slider)
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
    if all(type(part) is int for part in (slider.minimum, slider.maximum, slider.step)):
        last_step = (slider.maximum - slider.minimum) // slider.step
        step_index = max(0, min(round((Fraction(value) - slider.minimum) / slider.step), last_step))
        return step_index * slider.step + slider.minimum
    normalized = (value - slider.minimum) / slider.step
    last_step = math.floor((slider.maximum - slider.minimum) / slider.step + 1e-12)
    step_index = max(0, min(round(normalized), last_step))
    return step_index * slider.step + slider.minimum


def _coerce(name: str, value: float, slider: SliderConfig | None, type_name: str | None) -> float | int:
    value = _snap_to_step(value, slider)
    if type_name in {"integer", "discrete"}:
        return int(round(value))
    if type_name and type_name.startswith("categorical"):
        return value
    return value


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


def _load_spec(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return safe_load(handle)


# The only keys the Orientation RAG MicroSim reads (app.js FIELD_MAP).
MICROSIM_CONTROLS = ("retriever_top_k", "rerank_weight", "response_tokens")
_JS_MAX_SAFE_INTEGER = 2**53 - 1


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _tvar_slider(tvar: dict[str, Any], warnings: list[str]) -> SliderConfig | None:
    """Slider for an ``int``/``float`` TVAR with a ``domain.range``; ``None`` (with a warning) otherwise."""
    name = tvar.get("name")
    kind = tvar.get("type")
    domain = tvar.get("domain")
    bounds = domain.get("range") if isinstance(domain, dict) else None
    if kind not in {"int", "float"} or not isinstance(bounds, list):
        warnings.append(f"skipped TVAR '{name}' (type {kind}): only int/float range domains are exported")
        return None
    # Inspect original values before float conversion can round a large integer.
    numeric_values = [*bounds, domain.get("resolution")]
    for value in numeric_values:
        _check_numeric_precision(value, integer_context=kind == "int", context=f"TVAR '{name}'")
    if len(bounds) != 2 or not all(_is_number(b) for b in bounds) or bounds[0] > bounds[1]:
        raise ValueError(f"TVAR '{name}': domain.range must be a finite numeric [low, high] pair")
    minimum, maximum = float(bounds[0]), float(bounds[1])
    if kind == "int" and not all(bound.is_integer() for bound in (minimum, maximum)):
        raise ValueError(f"TVAR '{name}': int domain.range bounds must be integers")
    resolution = domain.get("resolution")
    if "resolution" in domain and (not _is_number(resolution) or resolution <= 0):
        raise ValueError(f"TVAR '{name}': resolution must be finite and positive")
    if _is_number(resolution) and resolution > 0:
        if kind == "int" and not float(resolution).is_integer():
            warnings.append(f"skipped TVAR '{name}': int TVAR has non-integral resolution {resolution}")
            return None
        step = float(resolution)
    elif kind == "int":
        step = 1.0
    else:
        span = maximum - minimum
        step = (round(span / 16, 4) or span / 16) if span > 0 else 0.1
    if kind == "int":
        return SliderConfig(minimum=int(bounds[0]), maximum=int(bounds[1]), step=int(step))
    return SliderConfig(minimum=minimum, maximum=maximum, step=step)


def _tvar_space(
    tvars: list[Any], warnings: list[str]
) -> tuple[dict[str, float | int], dict[str, SliderConfig], dict[str, str]]:
    defaults: dict[str, float | int] = {}
    sliders: dict[str, SliderConfig] = {}
    types: dict[str, str] = {}
    for tvar in tvars:
        if not isinstance(tvar, dict) or not isinstance(tvar.get("name"), str):
            continue
        slider = _tvar_slider(tvar, warnings)
        if slider is None:
            continue
        name = tvar["name"]
        midpoint = (
            Fraction(slider.minimum + slider.maximum, 2)
            if tvar["type"] == "int"
            else (slider.minimum + slider.maximum) / 2
        )
        default = _snap_to_step(midpoint, slider)
        if tvar["type"] == "int":
            types[name] = "integer"
            slider = SliderConfig(
                minimum=int(slider.minimum), maximum=int(slider.maximum), step=int(slider.step)
            )
            defaults[name] = round(default)
        else:
            types[name] = "float"
            defaults[name] = default
        sliders[name] = slider
    return defaults, sliders, types


def build_presets(path: Path, warnings: list[str] | None = None) -> dict[str, Any]:
    return presets_from_spec(_load_spec(path), warnings)


def presets_from_spec(spec: dict[str, Any], warnings: list[str] | None = None) -> dict[str, Any]:
    """Build the MicroSim preset payload from a parsed TVL module.

    Sliders come from ``int``/``float`` TVARs with a ``domain.range``; every other
    TVAR is skipped and named in ``warnings``. A document without ``tvars`` is
    read through the legacy ``configuration_space`` mapping.
    """
    if warnings is None:
        warnings = []
    if "tvars" in spec:
        tvars = spec.get("tvars") if isinstance(spec.get("tvars"), list) else []
        defaults, sliders, types = _tvar_space(tvars, warnings)
        header = spec.get("tvl") if isinstance(spec.get("tvl"), dict) else {}
        source = {"spec_id": header.get("module"), "spec_version": spec.get("tvl_version")}
    else:
        configuration_space = spec.get("configuration_space") or {}
        if not isinstance(configuration_space, dict) or not all(
            isinstance(definition, dict) for definition in configuration_space.values()
        ):
            raise ValueError("configuration_space must map names to variable definitions")
        legacy_header = spec.get("spec") or {}
        if not isinstance(legacy_header, dict):
            raise ValueError("spec must be a mapping")
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
        source = {
            "spec_id": legacy_header.get("id"),
            "spec_version": legacy_header.get("version"),
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
    payload = {
        "version": "1.0.0",
        "source": source,
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
    serialized = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(serialized, encoding="utf-8")
