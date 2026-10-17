from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WEBSITE_ROOT = REPO_ROOT / "website"
PUBLIC_ROOT = WEBSITE_ROOT / "client" / "public"

# These stay website-owned on purpose. The Examples page links to them, so sync
# depends on them remaining present, but they are not copied from canonical TVL
# sources.
SITE_LOCAL_PUBLIC_FILES = (
    PUBLIC_ROOT / "examples" / "artifact_manifest.json",
    PUBLIC_ROOT / "examples" / "validate_helper.py",
)


class SyncError(RuntimeError):
    """Raised when canonical resource sync cannot complete safely."""


def iter_copy_pairs() -> list[tuple[Path, Path]]:
    docs = [
        (REPO_ROOT / "docs" / "agent-requirements.md", PUBLIC_ROOT / "docs" / "agent-requirements.md"),
        (REPO_ROOT / "docs" / "reference" / "language.md", PUBLIC_ROOT / "docs" / "language.md"),
        (REPO_ROOT / "docs" / "reference" / "schema.md", PUBLIC_ROOT / "docs" / "schema.md"),
        (REPO_ROOT / "docs" / "reference" / "verification.md", PUBLIC_ROOT / "docs" / "verification.md"),
        (REPO_ROOT / "docs" / "reference" / "constraint-language.md", PUBLIC_ROOT / "docs" / "constraint-language.md"),
        (REPO_ROOT / "docs" / "examples" / "walkthroughs.md", PUBLIC_ROOT / "docs" / "walkthroughs.md"),
        (REPO_ROOT / "spec" / "grammar" / "tvl.schema.json", PUBLIC_ROOT / "docs" / "tvl.schema.json"),
        (REPO_ROOT / "spec" / "grammar" / "tvl-configuration.schema.json", PUBLIC_ROOT / "docs" / "tvl-configuration.schema.json"),
        (REPO_ROOT / "spec" / "grammar" / "tvl-measurement.schema.json", PUBLIC_ROOT / "docs" / "tvl-measurement.schema.json"),
        (REPO_ROOT / "spec" / "grammar" / "tvl.ebnf", PUBLIC_ROOT / "docs" / "tvl.ebnf"),
        (REPO_ROOT / "spec" / "grammar" / "tvl.schema.json", PUBLIC_ROOT / "schemas" / "tvl.schema.json"),
        (REPO_ROOT / "spec" / "grammar" / "tvl-configuration.schema.json", PUBLIC_ROOT / "schemas" / "tvl-configuration.schema.json"),
        (REPO_ROOT / "spec" / "grammar" / "tvl-measurement.schema.json", PUBLIC_ROOT / "schemas" / "tvl-measurement.schema.json"),
        (REPO_ROOT / "spec" / "grammar" / "tvl.ebnf", PUBLIC_ROOT / "schemas" / "tvl.ebnf"),
    ]

    examples = [
        (REPO_ROOT / "spec" / "examples" / "rag-support-bot.tvl.yml", PUBLIC_ROOT / "examples" / "rag-support-bot.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "agent-router.tvl.yml", PUBLIC_ROOT / "examples" / "agent-router.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "cost-optimization.tvl.yml", PUBLIC_ROOT / "examples" / "cost-optimization.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "multi-tenant-router.tvl.yml", PUBLIC_ROOT / "examples" / "multi-tenant-router.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "tool-use.yml", PUBLIC_ROOT / "examples" / "tool-use.yml"),
        (REPO_ROOT / "spec" / "examples" / "tool-use.yml", PUBLIC_ROOT / "examples" / "tool-use.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "text-to-sql.yml", PUBLIC_ROOT / "examples" / "text-to-sql.yml"),
        (REPO_ROOT / "spec" / "examples" / "text-to-sql.yml", PUBLIC_ROOT / "examples" / "text-to-sql.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "validation-phase2" / "structural-sat.tvl.yml", PUBLIC_ROOT / "examples" / "validation-phase2" / "structural-sat.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "validation-phase2" / "structural-sat.tvl.yml", PUBLIC_ROOT / "examples" / "structural-sat.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "validation-phase2" / "structural-unsat.tvl.yml", PUBLIC_ROOT / "examples" / "validation-phase2" / "structural-unsat.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "validation-phase2" / "structural-unsat.tvl.yml", PUBLIC_ROOT / "examples" / "structural-unsat.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "validation-phase3" / "budget-invalid.tvl.yml", PUBLIC_ROOT / "examples" / "validation-phase3" / "budget-invalid.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "validation-phase3" / "budget-invalid.tvl.yml", PUBLIC_ROOT / "examples" / "budget-invalid.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "validation-phase5" / "banded-objective-tost.tvl.yml", PUBLIC_ROOT / "examples" / "validation-phase5" / "banded-objective-tost.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "validation-phase5" / "chance-constraint-valid.tvl.yml", PUBLIC_ROOT / "examples" / "validation-phase5" / "chance-constraint-valid.tvl.yml"),
        (REPO_ROOT / "spec" / "examples" / "validation-phase5" / "callable-registry-ref.tvl.yml", PUBLIC_ROOT / "examples" / "validation-phase5" / "callable-registry-ref.tvl.yml"),
        (REPO_ROOT / "tvl_book" / "examples" / "ch2_hello_tvl.tvl.yml", PUBLIC_ROOT / "examples" / "book" / "ch2_hello_tvl.tvl.yml"),
        (REPO_ROOT / "tvl_book" / "examples" / "ch2_hello_tvl.tvl.yml", PUBLIC_ROOT / "examples" / "hello_tvl.yml"),
        (REPO_ROOT / "tvl_book" / "examples" / "ch2_hello_tvl.tvl.yml", PUBLIC_ROOT / "examples" / "hello_tvl_v1.tvl.yml"),
        (REPO_ROOT / "tvl_book" / "examples" / "ch2_validate_spec.py", PUBLIC_ROOT / "examples" / "book" / "ch2_validate_spec.py"),
        (REPO_ROOT / "tvl_book" / "examples" / "ch4_base_module.tvl.yml", PUBLIC_ROOT / "examples" / "book" / "ch4_base_module.tvl.yml"),
        (REPO_ROOT / "tvl_book" / "examples" / "ch4_base_module.tvl.yml", PUBLIC_ROOT / "examples" / "compose_base.tvl.yml"),
        (REPO_ROOT / "tvl_book" / "examples" / "ch4_staging.overlay.yml", PUBLIC_ROOT / "examples" / "book" / "ch4_staging.overlay.yml"),
        (REPO_ROOT / "tvl_book" / "examples" / "ch4_staging.overlay.yml", PUBLIC_ROOT / "examples" / "compose_staging.overlay.yml"),
        (REPO_ROOT / "tvl_book" / "examples" / "ch4_production.overlay.yml", PUBLIC_ROOT / "examples" / "book" / "ch4_production.overlay.yml"),
        (REPO_ROOT / "tvl_book" / "examples" / "ch4_hotfix.overlay.yml", PUBLIC_ROOT / "examples" / "book" / "ch4_hotfix.overlay.yml"),
        (REPO_ROOT / "tvl_book" / "examples" / "ch4_hotfix.overlay.yml", PUBLIC_ROOT / "examples" / "hotfix.overlay.yml"),
    ]

    return docs + examples


def build_expected_outputs() -> dict[Path, bytes]:
    outputs: dict[Path, bytes] = {}

    for source, destination in iter_copy_pairs():
        if not source.is_file():
            raise SyncError(f"Missing canonical source file: {source.relative_to(REPO_ROOT)}")
        outputs[destination] = source.read_bytes()

    for site_local in SITE_LOCAL_PUBLIC_FILES:
        if not site_local.is_file():
            raise SyncError(f"Missing site-local file: {site_local.relative_to(REPO_ROOT)}")

    return outputs


def compare_or_write(destination: Path, expected: bytes, *, check: bool, mismatches: list[str]) -> None:
    if check:
        if not destination.is_file():
            mismatches.append(f"Missing generated file: {destination.relative_to(REPO_ROOT)}")
            return
        if destination.read_bytes() != expected:
            mismatches.append(f"Stale generated file: {destination.relative_to(REPO_ROOT)}")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(expected)


def run_sync(*, check: bool) -> list[str]:
    mismatches: list[str] = []
    expected_outputs = build_expected_outputs()

    for destination in sorted(expected_outputs):
        compare_or_write(destination, expected_outputs[destination], check=check, mismatches=mismatches)

    return mismatches


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync canonical TVL website resources into the React app.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify mirrored/generated outputs are up to date without writing files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        mismatches = run_sync(check=args.check)
    except SyncError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if mismatches:
            for mismatch in mismatches:
                print(mismatch, file=sys.stderr)
            return 1
        print("Canonical TVL website resources are up to date.")
        return 0

    print(
        "site-local public files remain unchanged:",
        ", ".join(path.relative_to(REPO_ROOT).as_posix() for path in SITE_LOCAL_PUBLIC_FILES),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
