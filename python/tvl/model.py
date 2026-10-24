from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Dict, List, Optional

# Exact-arithmetic bounds for numeric LITERALS read from source text. Every binary64 value
# (normal or subnormal) is written with at most 17 significant digits and a decimal exponent
# in [-324, 308], so these bounds reject nothing a float can mean, and keep every exact
# rational the checker builds from literals small. Without them ``Fraction("1e-99999999")``
# alone computes 10**99999999 (a hang), and a ~5000-digit witness overflows Python's
# int->str conversion limit.
MAX_LITERAL_DIGITS = 400
MAX_LITERAL_EXPONENT = 400
# Largest numerator/denominator (in decimal digits) ``exact_to_str`` will print.
MAX_EXACT_STR_DIGITS = 2000

_DECIMAL_LITERAL_RE = re.compile(r"\s*[+-]?([0-9_]*)(?:\.([0-9_]*))?(?:[eE]([+-]?[0-9_]+))?\s*")


class ExactLiteralLimitError(ValueError):
    """A numeric literal's mantissa or exponent exceeds the exact-arithmetic bounds."""


class ExactFormatLimitError(ValueError):
    """An exact rational is too large to print within ``MAX_EXACT_STR_DIGITS`` digits."""


def literal_limit_violation(text: str) -> Optional[str]:
    """Why the decimal literal ``text`` exceeds the exact bounds, or None when it is within them.

    Pure text inspection: never builds the rational, so it is O(len(text)).
    """
    match = _DECIMAL_LITERAL_RE.fullmatch(text)
    if match is None:
        return None
    whole, frac, exp = match.group(1) or "", match.group(2) or "", match.group(3)
    digits = len(whole.replace("_", "")) + len(frac.replace("_", ""))
    if digits > MAX_LITERAL_DIGITS:
        return f"numeric literal has {digits} digits (limit {MAX_LITERAL_DIGITS})"
    if exp is not None:
        exp_digits = exp.replace("_", "").lstrip("+-").lstrip("0")
        if len(exp_digits) > 6 or (exp_digits and int(exp_digits) > MAX_LITERAL_EXPONENT):
            return f"numeric literal exponent exceeds +-{MAX_LITERAL_EXPONENT}"
    return None


def bounded_fraction(text: str) -> Fraction:
    """``Fraction(text)`` for a decimal or ratio literal, refusing literals beyond the bounds.

    Raises :class:`ExactLiteralLimitError` (a ``ValueError``) instead of materialising a huge
    power of ten; other malformed text raises ``ValueError`` as ``Fraction`` does.
    """
    reason = literal_limit_violation(text)
    if reason is not None:
        raise ExactLiteralLimitError(f"{reason}: {text[:40]!r}")
    return Fraction(text)


def _decimal_digits_upper(n: int) -> int:
    """Upper bound on the decimal digits of ``|n|`` (no int->str conversion)."""
    return int(abs(n).bit_length() * 0.30103) + 1


def exact_to_str(value: Fraction) -> str:
    """Exact text of a rational: a terminating decimal when one exists, else ``"p/q"``.

    Used for the public exact witness (``StructuralResult.exact_assignment``) so that
    grid points binary64 cannot tell apart stay distinguishable. Raises
    :class:`ExactFormatLimitError` (never a bare int->str ``ValueError``) when the text
    would need more than ``MAX_EXACT_STR_DIGITS`` digits for a numerator or denominator.
    """
    if (
        _decimal_digits_upper(value.numerator) > MAX_EXACT_STR_DIGITS
        or _decimal_digits_upper(value.denominator) > MAX_EXACT_STR_DIGITS
    ):
        raise ExactFormatLimitError(
            f"exact value needs more than {MAX_EXACT_STR_DIGITS} digits to print"
        )
    if value.denominator == 1:
        return str(value.numerator)
    den = value.denominator
    twos = fives = 0
    while den % 2 == 0:
        den //= 2
        twos += 1
    while den % 5 == 0:
        den //= 5
        fives += 1
    if den != 1:
        return f"{value.numerator}/{value.denominator}"
    digits = max(twos, fives)
    if digits > MAX_EXACT_STR_DIGITS:
        raise ExactFormatLimitError(
            f"exact value needs more than {MAX_EXACT_STR_DIGITS} digits to print"
        )
    scaled = value * 10**digits  # an integer by construction
    sign = "-" if scaled < 0 else ""
    text = str(abs(scaled.numerator)).rjust(digits + 1, "0")
    whole, frac = text[:-digits], text[-digits:].rstrip("0")
    return f"{sign}{whole}.{frac}" if frac else f"{sign}{whole}"


class ExactNumber(Fraction):
    """An exact rational that binary64 cannot hold, printed as its exact decimal.

    Used for numeric values the checker builds or parses itself (tuple-range grid points,
    tuple literal components) where a ``float`` would round. It is a ``Fraction``, never a
    ``float``: equality, hashing and arithmetic are exact, so it cannot collapse onto a
    binary64 neighbour in a set or dict, and ``json`` refuses it rather than silently
    emitting a rounded number. ``repr``/``str`` give the exact decimal (or ``p/q``).
    """

    __slots__ = ()

    def __repr__(self) -> str:
        try:
            return exact_to_str(self)
        except ExactFormatLimitError:
            return f"{self.numerator}/{self.denominator}"

    __str__ = __repr__


def exact_or_float(value: Fraction) -> Any:
    """``float(value)`` when that float denotes ``value`` exactly (via :func:`_exact`), else
    an :class:`ExactNumber`.

    Keeps ordinary grid points (``0.1``, ``0.3``) plain floats, as before, so they still match
    user-supplied binary64 values, while a point binary64 cannot hold stays exact.
    """
    try:
        as_float = float(value)
    except OverflowError:
        return ExactNumber(value)
    if math.isfinite(as_float) and Fraction(repr(as_float)) == value:
        return as_float
    return ExactNumber(value)


def exact_number_or_none(value: Any) -> Optional[Fraction]:
    """Exact rational of a declaration number (int, float, Fraction or numeric text), else None.

    Floats with a retained YAML lexeme use that lexeme (bounded); text goes through
    :func:`bounded_fraction`. Raises :class:`ExactLiteralLimitError` for out-of-bounds literals.
    Bools, non-finite floats and non-numeric values give None.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (int, float, Fraction)):
        return _exact(value)
    if isinstance(value, str):
        try:
            return bounded_fraction(value.strip())
        except ExactLiteralLimitError:
            raise
        except (ValueError, ZeroDivisionError):
            return None
    return None


def _positive_step(resolution: Any) -> Optional[Fraction]:
    """Exact value of a numeric ``resolution`` when it is strictly positive, else None.

    Positivity is decided on the exact rational, never on binary64: ``1e-400`` underflows to
    ``0.0`` as a float but its retained lexeme is positive.
    """
    if isinstance(resolution, str):
        return None
    exact = exact_number_or_none(resolution)
    return exact if exact is not None and exact > 0 else None


@dataclass
class Domain:
    path: str
    kind: str  # enum, int, float, bool
    values: Optional[List[Any]] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    precision: int = 1000  # float scaling (1 precision unit = 1/precision)
    # Definition 3.6 grid for floats: value = origin + i * step, 0 <= i <= floor((max - origin) / step).
    # When unset (None) the legacy grid is used: origin 0, step 1/precision.
    origin: Optional[Fraction] = None
    step: Optional[Fraction] = None
    # Declaration provenance: True iff the domain (or a tuple component of it) is
    # registry-backed and so has no resolved values here (formal semantics Definition 3.6:
    # registry interpretation is undefined). Its ``values`` are placeholders; this flag,
    # never a string prefix, is what marks them.
    unresolved: bool = False
    # Exact range endpoints (from the source lexeme, see :func:`exact_number_or_none`). When
    # set they, not the binary64 ``minimum``/``maximum``, bound the grid: a declared
    # ``[0.100000000000000001, 0.100000000000000001]`` is the singleton of that exact value.
    exact_minimum: Optional[Fraction] = None
    exact_maximum: Optional[Fraction] = None

    @property
    def grid_origin(self) -> Fraction:
        return self.origin if self.origin is not None else Fraction(0)

    @property
    def grid_step(self) -> Fraction:
        return self.step if self.step is not None else Fraction(1, max(1, self.precision))

    def grid_index(self, value: Any) -> Fraction:
        """Exact (rational) grid index of ``value``; an integer iff the value is on the grid."""
        return (_exact(value) - self.grid_origin) / self.grid_step

    def grid_count(self) -> Optional[int]:
        """Number of grid points for a bounded float domain, else None."""
        if self.kind != "float" or self.minimum is None or self.maximum is None:
            return None
        hi = self.index_upper()
        lo = self.index_lower()
        return max(0, int(hi) - int(lo) + 1)

    def index_lower(self) -> Optional[int]:
        """Smallest encoded value (grid index for floats, the integer for ints), exactly."""
        if self.minimum is None and self.exact_minimum is None:
            return None
        if self.exact_minimum is not None and self.kind in {"int", "float"}:
            if self.kind == "float":
                return int(math.ceil(self.grid_index(self.exact_minimum)))
            return int(math.ceil(self.exact_minimum))
        return self._encode_bound_lower(self.minimum)

    def index_upper(self) -> Optional[int]:
        """Largest encoded value (grid index for floats, the integer for ints), exactly."""
        if self.maximum is None and self.exact_maximum is None:
            return None
        if self.exact_maximum is not None and self.kind in {"int", "float"}:
            if self.kind == "float":
                return int(math.floor(self.grid_index(self.exact_maximum)))
            return int(math.floor(self.exact_maximum))
        return self._encode_bound_upper(self.maximum)

    @property
    def resolution(self) -> int:
        if self.kind == "float":
            return max(1, self.precision)
        return 1

    def encode(self, value: Any) -> int:
        if self.kind == "bool":
            return _encode_bool(self, value)

        if self.kind == "enum":
            if self.values is None:
                raise ValueError(f"{self.path}: enum domain is missing values")
            if value not in self.values:
                raise ValueError(
                    f"{self.path}: value {value!r} not in enum {self.values}"
                )
            return self.values.index(value)

        if self.kind == "int":
            if not isinstance(value, int):
                raise ValueError(f"{self.path}: expected int, got {value!r}")
            return value

        if self.kind == "float":
            if not isinstance(value, (int, float, Fraction)):
                raise ValueError(f"{self.path}: expected float, got {value!r}")
            if self.step is None and self.origin is None and not isinstance(value, Fraction):
                # Legacy configuration-membership check (origin 0, step 1/precision), kept
                # bit-for-bit (see tests/test_domain_encode_characterization.py). The structural
                # solver never uses it for floats: literal thresholds and candidates go through
                # the exact rational grid index (structural_sat._encode_float_literal).
                scaled = float(value) * self.precision
                rounded = round(scaled)
                if abs(scaled - rounded) > 1e-9:
                    raise ValueError(
                        f"{self.path}: value {value!r} is not on the precision grid "
                        f"(precision={self.precision}, resolution={1/self.precision})"
                    )
                return int(rounded)
            # Exact grid (Definition 3.6): membership is exact, with no tolerance.
            idx = self.grid_index(value)
            if idx.denominator != 1:
                raise ValueError(
                    f"{self.path}: value {value!r} is not on the precision grid "
                    f"(precision={self.precision}, resolution={float(self.grid_step)})"
                )
            return int(idx)

        raise ValueError(f"{self.path}: unsupported domain kind {self.kind}")

    def decode(self, raw: int) -> Any:
        """Public (JSON-compatible) value of an encoded index; floats are plain binary64.

        Use :meth:`decode_exact` wherever the value is compared or evaluated.
        """
        if self.kind == "float":
            if self.origin is None and self.step is None:
                return raw / self.precision
            return float(self.decode_exact(raw))
        return self.decode_exact(raw)

    def decode_exact(self, raw: int) -> Any:
        """Exact value of an encoded index: a ``Fraction`` for floats (origin + raw * step)."""
        if self.kind == "bool":
            return bool(raw)
        if self.kind == "enum":
            if self.values is None:
                raise ValueError(f"{self.path}: enum domain is missing values")
            return self.values[raw]
        if self.kind == "int":
            return raw
        if self.kind == "float":
            return self.grid_origin + raw * self.grid_step
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

        lower = self.index_lower()
        upper = self.index_upper()
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
            # Exact ceil of the rational grid index (legacy grid included).
            return int(math.ceil(self.grid_index(value)))
        return int(value)

    def _encode_bound_upper(self, value: float | int | None) -> Optional[int]:
        if value is None:
            return None
        if self.kind == "float":
            return int(math.floor(self.grid_index(value)))
        return int(value)


def _exact(value: Any) -> Fraction:
    """Exact rational a number denotes.

    A ``Fraction`` is already exact; an ``int`` is itself; a float denotes the decimal of
    its YAML source lexeme when the loader retained one (binary64 could not hold it),
    otherwise the decimal of its shortest repr.
    """
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    raw = getattr(value, "_raw_lexeme", None)
    if isinstance(raw, str):
        try:
            return bounded_fraction(raw)
        except ExactLiteralLimitError:
            raise
        except (ValueError, ZeroDivisionError):
            pass
    return Fraction(repr(float(value)))


def _encode_bool(domain: Domain, value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int) and value in (0, 1):
        return value
    raise ValueError(f"{domain.path}: expected bool, got {value!r}")


def extract_domains(tvars: Dict[str, Any]) -> Dict[str, Domain]:
    domains: Dict[str, Domain] = {}

    if isinstance(tvars, dict):
        for key, value in tvars.items():
            _walk_legacy(domains, key, value)
        return domains

    if isinstance(tvars, list):
        for idx, decl in enumerate(tvars):
            if not isinstance(decl, dict):
                raise ValueError(
                    f"tvars[{idx}]: expected dict, got {type(decl).__name__}"
                )
            name = decl.get("name")
            dtype = (decl.get("type") or "").lower()
            if not isinstance(name, str):
                raise ValueError(
                    f"tvars[{idx}]: missing or non-string 'name' field (got {type(name).__name__ if name is not None else 'None'})"
                )
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


def _walk_legacy(
    domains: Dict[str, Domain], name: str, node: Any, prefix: str = ""
) -> None:
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
            domains[path] = Domain(
                path=path, kind="int", minimum=minimum, maximum=maximum
            )
        elif kind == "float":
            minimum = node.get("min")
            maximum = node.get("max")
            precision = int(node.get("precision", 1000))
            domains[path] = Domain(
                path=path,
                kind="float",
                minimum=minimum,
                maximum=maximum,
                precision=precision,
            )
        else:
            raise ValueError(f"{path}: unsupported domain type {kind}")
    elif isinstance(node, dict):
        for child, spec in node.items():
            _walk_legacy(domains, child, spec, path)
    else:
        raise ValueError(f"{path}: expected mapping for domain definition")


_MAX_TUPLE_PRODUCT = 10_000  # guard against combinatorial explosion


def _product_limit_error(name: str, size: int) -> ValueError:
    return ValueError(
        f"{name}: tuple product size {size} exceeds limit "
        f"{_MAX_TUPLE_PRODUCT}; consider reducing component domains"
    )


def _range_grid(comp: dict) -> Optional[tuple]:
    """``(kind, lo, step, count)`` of a tuple-component range, computed exactly; None if malformed.

    ``kind`` is ``"float"`` (Definition 3.6 grid ``lo + i * step``, ``0 <= i <= floor((hi - lo)
    / step)``, all exact rationals) or ``"int"`` (``lo..hi``). Pure arithmetic: never allocates
    the values, so the cardinality can be checked before anything is built.
    """
    r = comp.get("range")
    if not (isinstance(r, list) and len(r) == 2):
        return None
    lo_raw, hi_raw = r[0], r[1]
    resolution = comp.get("resolution")
    is_float_range = isinstance(lo_raw, float) or isinstance(hi_raw, float)
    step = _positive_step(resolution)
    if step is not None or is_float_range:
        lo, hi = exact_number_or_none(lo_raw), exact_number_or_none(hi_raw)
        if lo is None or hi is None:
            # Non-numeric / non-finite endpoints: keep the legacy float() conversion error.
            lo, hi = _exact(float(lo_raw)), _exact(float(hi_raw))
        # Semantics §2.4: float-range resolution is optional, default 0.001.
        step = step if step is not None else Fraction(1, 1000)
        n_steps = math.floor((hi - lo) / step)
        return ("float", lo, step, max(n_steps, 0) + 1)
    lo_i, hi_i = int(lo_raw), int(hi_raw)
    return ("int", lo_i, 1, max(hi_i - lo_i + 1, 0))


def _resolve_range_values(name: str, idx: int, comp: dict) -> List[Any]:
    """Resolve a range spec into an explicit list of values.

    Grid points are exact (no binary64 rounding): a point is a plain ``float`` when that float
    denotes it exactly, else an :class:`ExactNumber`. The cardinality is checked against the
    tuple product limit BEFORE any value is allocated.
    """
    grid = _range_grid(comp)
    if grid is None:
        return []
    kind, lo, step, count = grid
    if count > _MAX_TUPLE_PRODUCT:
        raise _product_limit_error(name, count)
    if kind == "float":
        return [exact_or_float(lo + i * step) for i in range(count)]
    return list(range(lo, lo + count))


def _range_component_count(comp: Any) -> Optional[int]:
    """Number of values a range component resolves to (without building them), else None.

    None when ``comp`` is not resolved through its ``range`` key (mirrors the precedence of
    :func:`_resolve_component_values`).
    """
    if not isinstance(comp, dict) or "values" in comp or "set" in comp or "range" not in comp:
        return None
    grid = _range_grid(comp)
    return None if grid is None else grid[3]


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


def _has_registry_component(components: Any) -> bool:
    """True iff a (possibly nested) tuple component resolves through its ``registry`` key.

    Mirrors the precedence of :func:`_resolve_component_values`: ``values``/``set``, then a
    non-empty ``range``, then nested ``components``, then ``registry``.
    """
    stack = [components]
    seen: set = set()
    while stack:
        specs = stack.pop()
        if not isinstance(specs, list) or id(specs) in seen:
            continue
        seen.add(id(specs))
        for idx, comp in enumerate(specs):
            if not isinstance(comp, dict) or "values" in comp or "set" in comp:
                continue
            if "range" in comp and _range_component_count(comp):
                continue
            if "components" in comp:
                stack.append(comp["components"])
            elif "registry" in comp:
                return True
    return False


def _enumerate_tuple_product(name: str, components: Any) -> List[Any]:
    """Enumerate the Cartesian product of tuple component domains.

    Each component is a dict with a ``values`` (or ``set``) key listing its
    domain elements.  Returns a list of tuples suitable for enum encoding.
    """
    if not isinstance(components, list) or not components:
        raise ValueError(
            f"{name}: tuple domain must define a non-empty 'components' list"
        )

    import itertools

    axis_values: List[List[Any]] = []
    product_size = 1
    for idx, comp in enumerate(components):
        # A range axis is counted arithmetically and refused BEFORE its values are built.
        count = _range_component_count(comp)
        if count and product_size * count > _MAX_TUPLE_PRODUCT:
            raise _product_limit_error(name, product_size * count)
        vals = _resolve_component_values(name, idx, comp)
        if not vals:
            raise ValueError(f"{name}: tuple component {idx} has empty domain")
        axis_values.append(vals)
        product_size *= len(vals)
        if product_size > _MAX_TUPLE_PRODUCT:
            raise _product_limit_error(name, product_size)

    return list(itertools.product(*axis_values))


def _domain_from_decl(name: str, dtype: str, spec: Any) -> Domain:
    kind = _normalize_dtype(dtype)
    if kind == "bool":
        return Domain(path=name, kind="bool")

    if kind == "enum":
        values: List[Any]
        unresolved = False
        if isinstance(spec, dict):
            if "set" in spec:
                values = list(spec.get("set", []))
            elif "registry" in spec:
                # Registry-backed domains are resolved externally; keep a small placeholder
                # so downstream tooling can operate without crashing.
                values = ["__registry_unresolved_0__", "__registry_unresolved_1__"]
                unresolved = True
            elif "components" in spec:
                values = _enumerate_tuple_product(name, spec["components"])
                unresolved = _has_registry_component(spec["components"])
            else:
                raise ValueError(f"{name}: unsupported enum domain spec {spec}")
        else:
            values = list(spec or [])
        if all(isinstance(v, (int, float)) for v in values):
            values = sorted(values)
        if not values:
            raise ValueError(f"{name}: enum domain requires values")
        return Domain(path=name, kind="enum", values=values, unresolved=unresolved)

    if kind in {"int", "float"}:
        minimum: Optional[float] = None
        maximum: Optional[float] = None
        exact_minimum: Optional[Fraction] = None
        exact_maximum: Optional[Fraction] = None
        precision: int = 1000 if kind == "float" else 1
        origin: Optional[Fraction] = None
        step: Optional[Fraction] = None
        if isinstance(spec, dict):
            if "range" in spec:
                range_vals = spec.get("range", [])
                if isinstance(range_vals, list) and len(range_vals) == 2:
                    minimum = float(range_vals[0])
                    maximum = float(range_vals[1])
                    # The grid is bounded by the EXACT endpoints (source lexeme), never by
                    # their binary64 roundings above.
                    exact_minimum = exact_number_or_none(range_vals[0])
                    exact_maximum = exact_number_or_none(range_vals[1])
                if kind == "float":
                    # Positivity is decided exactly (an underflowed 1e-400 is positive).
                    step = _positive_step(spec.get("resolution"))
                    if step is None:
                        step = Fraction(1, 1000)  # semantics §2.4 default resolution
                    # Exact reciprocal: never a binary64 1/step (which overflows to inf).
                    precision = max(1, round(1 / step))
                    if minimum is not None:
                        origin = exact_minimum if exact_minimum is not None else _exact(minimum)
                    else:
                        origin = Fraction(0)
            elif "set" in spec:
                values = list(spec.get("set", []))
                if not values:
                    raise ValueError(f"{name}: set domain must list values")
                return Domain(path=name, kind="enum", values=values)
            elif "registry" in spec:
                # Registry-backed domains are treated as opaque enums until resolved externally.
                return Domain(path=name, kind="enum", values=[], unresolved=True)
        return Domain(
            path=name, kind=kind, minimum=minimum, maximum=maximum, precision=precision,
            origin=origin, step=step, exact_minimum=exact_minimum, exact_maximum=exact_maximum,
        )

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
