# Validation Phase 5: Advanced Type System and Promotion Policy

This directory contains conformance test examples for advanced TVL features:

## Type System Tests

| File | Description | Expected Result |
|------|-------------|-----------------|
| `tuple-product-semantics.tvl.yml` | Tuple type with product (Cartesian) semantics | VALID |
| `callable-registry-ref.tvl.yml` | Callable type with registry reference | VALID |
| `empty-domain-error.tvl.yml` | Empty enum domain | ERROR: E1002 |

Tuple implementation note: when tuple component domains use float ranges, include an explicit
`resolution` so the component can be enumerated deterministically.

## Promotion Policy Tests

| File | Description | Expected Result |
|------|-------------|-----------------|
| `banded-objective-tost.tvl.yml` | Banded objective with TOST | VALID |
| `banded-objective-invalid-bounds.tvl.yml` | Band with L >= U | ERROR: E4003 |
| `chance-constraint-valid.tvl.yml` | Valid chance constraint | VALID |
| `chance-constraint-invalid-threshold.tvl.yml` | Threshold > 1 | ERROR: E5005 |
| `bh-adjustment.tvl.yml` | Benjamini-Hochberg adjustment | VALID |
| `multi-objective-epsilon.tvl.yml` | Multi-objective with per-objective epsilon | VALID |

## Coverage

These examples cover sections from the formal specification:

- **Appendix: Type System for TVL** - T-Tuple, T-Callable rules
- **Appendix: Statistical Procedures** - BH, TOST, Clopper-Pearson
- **Appendix: TVL Language Definition** - Policy YAML schema

## Running Tests

```bash
cd tvl/
pytest tests/test_type_system.py tests/test_promotion_policy.py -v
```
