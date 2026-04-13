from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Domain:
    path: str
    kind: str  # enum, int, float, bool
    values: Optional[List[Any]] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    precision: int = 1000  # float scaling (1 precision unit = 1/precision)

    @property
    def resolution(self) -> int:
        if self.kind == "float":
            return max(1, self.precision)
        return 1

    def encode(self, value: Any) -> int:
        if self.kind == "bool":
            if isinstance(value, bool):
                return 1 if value else 0
            if isinstance(value, int) and value in (0, 1):
                return value
            raise ValueError(f"{self.path}: expected bool, got {value!r}")

        if self.kind == "enum":
            assert self.values is not None
            if value not in self.values:
                raise ValueError(f"{self.path}: value {value!r} not in enum {self.values}")
            return self.values.index(value)

        if self.kind == "int":
            if not isinstance(value, int):
                raise ValueError(f"{self.path}: expected int, got {value!r}")
            return value

        if self.kind == "float":
            if not isinstance(value, (int, float)):
                raise ValueError(f"{self.path}: expected float, got {value!r}")
            scaled = float(value) * self.precision
            rounded = round(scaled)
            if abs(scaled - rounded) > 1e-9:
                raise ValueError(
                    f"{self.path}: value {value!r} is not on the precision grid "
                    f"(precision={self.precision}, resolution={1/self.precision})"
                )
            return int(rounded)

        raise ValueError(f"{self.path}: unsupported domain kind {self.kind}")

    def decode(self, raw: int) -> Any:
        if self.kind == "bool":
            return bool(raw)
        if self.kind == "enum":
            assert self.values is not None
            return self.values[raw]
        if self.kind == "int":
            return raw
        if self.kind == "float":
            return raw / self.precision
        return raw

    def contains(self, value: Any) -> bool:
        try:
            encoded = self.encode(value)
        except ValueError:
            return False

        if self.kind == "enum":
            return True

        if self.kind == "bool":
            return encoded in (0, 1)

        lower = self._encode_bound_lower(self.minimum) if self.minimum is not None else None
        upper = self._encode_bound_upper(self.maximum) if self.maximum is not None else None
        if lower is not None and encoded < lower:
            return False
        if upper is not None and encoded > upper:
            return False

        # For floats, non-grid values are already rejected by encode() above.
        # No additional check needed for int.

        return True

    def _encode_bound_lower(self, value: float | int | None) -> Optional[int]:
        if value is None:
            return None
        if self.kind == "float":
            import math
            return int(math.ceil(float(value) * self.precision))
        return int(value)

    def _encode_bound_upper(self, value: float | int | None) -> Optional[int]:
        if value is None:
            return None
        if self.kind == "float":
            import math
            return int(math.floor(float(value) * self.precision))
        return int(value)


def extract_domains(tvars: Dict[str, Any]) -> Dict[str, Domain]:
    domains: Dict[str, Domain] = {}

    if isinstance(tvars, dict):
        for key, value in tvars.items():
            _walk_legacy(domains, key, value)
        return domains

    if isinstance(tvars, list):
        for decl in tvars:
            if not isinstance(decl, dict):
                continue
            name = decl.get("name")
            dtype = (decl.get("type") or "").lower()
            if not isinstance(name, str):
                continue
            domain_spec = decl.get("domain")
            domains[name] = _domain_from_decl(name, dtype, domain_spec)
        return domains

    raise ValueError("tvars must be a mapping or list of declarations")


@dataclass
class ValidationOptions:
    skip_budget_checks: bool = False
    skip_cost_estimation: bool = False


def extract_validation_options(module: Dict[str, Any]) -> ValidationOptions:
    tvl_block = module.get("tvl") or {}
    validation_block = tvl_block.get("validation") or {}
    if not isinstance(validation_block, dict):
        return ValidationOptions()
    return ValidationOptions(
        skip_budget_checks=bool(validation_block.get("skip_budget_checks", False)),
        skip_cost_estimation=bool(validation_block.get("skip_cost_estimation", False)),
    )


def _walk_legacy(domains: Dict[str, Domain], name: str, node: Any, prefix: str = "") -> None:
    path = f"{prefix}.{name}" if prefix else name
    if isinstance(node, dict) and "type" in node:
        kind = node["type"].lower()
        if kind == "enum":
            values = list(node.get("values", []))
            if not values:
                raise ValueError(f"{path}: enum domain requires non-empty values")
            domains[path] = Domain(path=path, kind="enum", values=values)
        elif kind == "bool":
            domains[path] = Domain(path=path, kind="bool")
        elif kind == "int":
            minimum = node.get("min")
            maximum = node.get("max")
            domains[path] = Domain(path=path, kind="int", minimum=minimum, maximum=maximum)
        elif kind == "float":
            minimum = node.get("min")
            maximum = node.get("max")
            precision = int(node.get("precision", 1000))
            domains[path] = Domain(path=path, kind="float", minimum=minimum, maximum=maximum, precision=precision)
        else:
            raise ValueError(f"{path}: unsupported domain type {kind}")
    elif isinstance(node, dict):
        for child, spec in node.items():
            _walk_legacy(domains, child, spec, path)
    else:
        raise ValueError(f"{path}: expected mapping for domain definition")


_MAX_TUPLE_PRODUCT = 10_000  # guard against combinatorial explosion


def _resolve_range_values(name: str, idx: int, comp: dict) -> List[Any]:
    """Resolve a range spec into an explicit list of values."""
    r = comp["range"]
    if not (isinstance(r, list) and len(r) == 2):
        return []
    lo_raw, hi_raw = r[0], r[1]
    resolution = comp.get("resolution")
    if resolution is not None and isinstance(resolution, (int, float)) and float(resolution) > 0:
        lo_f, hi_f = float(lo_raw), float(hi_raw)
        step = float(resolution)
        n_steps = int(round((hi_f - lo_f) / step))
        return [round(lo_f + i * step, 12) for i in range(n_steps + 1)]
    if isinstance(lo_raw, float) or isinstance(hi_raw, float):
        raise ValueError(
            f"{name}: tuple component {idx} has float range "
            f"[{lo_raw}, {hi_raw}] but no 'resolution'; "
            f"add resolution to enumerate grid points"
        )
    lo, hi = int(lo_raw), int(hi_raw)
    return list(range(lo, hi + 1))


def _resolve_component_values(name: str, idx: int, comp: Any) -> List[Any]:
    """Resolve a single tuple component spec into its domain values."""
    if isinstance(comp, dict):
        if "values" in comp:
            return list(comp["values"])
        if "set" in comp:
            return list(comp["set"])
        if "range" in comp:
            vals = _resolve_range_values(name, idx, comp)
            if vals:
                return vals
        if "components" in comp:
            # Nested tuple component: recurse through product enumeration.
            return _enumerate_tuple_product(name, comp["components"])
        if "registry" in comp:
            # Registry-backed component values are resolved externally.
            return ["__registry_unresolved_0__", "__registry_unresolved_1__"]
        raise ValueError(
            f"{name}: tuple component {idx} has no 'values', 'set', valid 'range', "
            f"'components', or 'registry'"
        )
    if isinstance(comp, list):
        return list(comp)
    raise ValueError(
        f"{name}: tuple component {idx} must be a mapping with "
        f"'values'/'set'/'range'/'components'/'registry' or a list"
    )


def _enumerate_tuple_product(name: str, components: Any) -> List[Any]:
    """Enumerate the Cartesian product of tuple component domains.

    Each component is a dict with a ``values`` (or ``set``) key listing its
    domain elements.  Returns a list of tuples suitable for enum encoding.
    """
    if not isinstance(components, list) or not components:
        raise ValueError(f"{name}: tuple domain must define a non-empty 'components' list")

    import itertools

    axis_values: List[List[Any]] = []
    for idx, comp in enumerate(components):
        vals = _resolve_component_values(name, idx, comp)
        if not vals:
            raise ValueError(f"{name}: tuple component {idx} has empty domain")
        axis_values.append(vals)

    product_size = 1
    for av in axis_values:
        product_size *= len(av)
        if product_size > _MAX_TUPLE_PRODUCT:
            raise ValueError(
                f"{name}: tuple product size {product_size} exceeds limit "
                f"{_MAX_TUPLE_PRODUCT}; consider reducing component domains"
            )

    return list(itertools.product(*axis_values))


def _domain_from_decl(name: str, dtype: str, spec: Any) -> Domain:
    kind = _normalize_dtype(dtype)
    if kind == "bool":
        return Domain(path=name, kind="bool")

    if kind == "enum":
        values: List[Any]
        if isinstance(spec, dict):
            if "set" in spec:
                values = list(spec.get("set", []))
            elif "registry" in spec:
                # Registry-backed domains are resolved externally; keep a small placeholder
                # so downstream tooling can operate without crashing.
                values = ["__registry_unresolved_0__", "__registry_unresolved_1__"]
            elif "components" in spec:
                values = _enumerate_tuple_product(name, spec["components"])
            else:
                raise ValueError(f"{name}: unsupported enum domain spec {spec}")
        else:
            values = list(spec or [])
        if all(isinstance(v, (int, float)) for v in values):
            values = sorted(values)
        if not values:
            raise ValueError(f"{name}: enum domain requires values")
        return Domain(path=name, kind="enum", values=values)

    if kind in {"int", "float"}:
        minimum: Optional[float] = None
        maximum: Optional[float] = None
        precision = 1000 if kind == "float" else 1
        if isinstance(spec, dict):
            if "range" in spec:
                range_vals = spec.get("range", [])
                if isinstance(range_vals, list) and len(range_vals) == 2:
                    minimum = float(range_vals[0])
                    maximum = float(range_vals[1])
                if kind == "float":
                    resolution = spec.get("resolution")
                    if isinstance(resolution, (int, float)) and resolution > 0:
                        precision = int(round(1 / float(resolution)))
            elif "set" in spec:
                values = list(spec.get("set", []))
                if not values:
                    raise ValueError(f"{name}: set domain must list values")
                return Domain(path=name, kind="enum", values=values)
            elif "registry" in spec:
                # Registry-backed domains are treated as opaque enums until resolved externally.
                return Domain(path=name, kind="enum", values=[])
        return Domain(path=name, kind=kind, minimum=minimum, maximum=maximum, precision=precision)

    raise ValueError(f"{name}: unsupported TVAR type '{dtype}'")


def _normalize_dtype(dtype: str) -> str:
    if dtype.startswith("enum"):
        return "enum"
    if dtype.startswith("tuple"):
        return "enum"
    if dtype.startswith("callable"):
        return "enum"
    if dtype in {"bool", "int", "float"}:
        return dtype
    return dtype


def flatten_assignments(data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for key, value in (data or {}).items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and not _is_leaf_dict(value):
            flat.update(flatten_assignments(value, path))
        else:
            flat[path] = value
    return flat


def _is_leaf_dict(node: Dict[str, Any]) -> bool:
    return any(k in node for k in {"type", "values", "min", "max", "precision"})
