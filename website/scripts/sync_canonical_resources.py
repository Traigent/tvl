from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WEBSITE_ROOT = REPO_ROOT / "website"
PUBLIC_ROOT = WEBSITE_ROOT / "client" / "public"
GENERATED_BOOK_ROOT = WEBSITE_ROOT / "client" / "src" / "generated" / "book"
GENERATED_BOOK_CONTENT_ROOT = GENERATED_BOOK_ROOT / "content"
BOOK_CONTENT_ROOT = REPO_ROOT / "tvl_book" / "website_content"
BOOK_CHAPTERS_ROOT = BOOK_CONTENT_ROOT / "chapters"
BOOK_MATERIALS_ROOT = BOOK_CONTENT_ROOT / "materials"
BOOK_PATTERNS_ROOT = BOOK_CONTENT_ROOT / "patterns"
BOOK_PATHS_ROOT = BOOK_CONTENT_ROOT / "paths"
BOOK_CONCEPTS_PATH = BOOK_CONTENT_ROOT / "concepts" / "graph.yml"
PUBLIC_BOOK_ASSETS_ROOT = PUBLIC_ROOT / "book-assets"

# These stay website-owned on purpose. They can still be referenced by the
# generated compatibility manifests, so sync depends on them remaining present,
# but they are not copied from canonical TVL sources.
SITE_LOCAL_PUBLIC_FILES = (
    PUBLIC_ROOT / "examples" / "artifact_manifest.json",
    PUBLIC_ROOT / "examples" / "validate_helper.py",
)


class SyncError(RuntimeError):
    """Raised when canonical resource sync cannot complete safely."""


def display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def infer_language(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".tvl.yml"):
        return "tvl"
    if lower.endswith(".py"):
        return "python"
    if lower.endswith(".sh"):
        return "bash"
    if lower.endswith(".json"):
        return "json"
    if lower.endswith(".md") or lower.endswith(".mdx"):
        return "markdown"
    if lower.endswith(".yml") or lower.endswith(".yaml"):
        return "yaml"
    if lower.endswith(".html"):
        return "html"
    return "text"


def json_bytes(data: Any) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SyncError(f"Missing required JSON file: {path.relative_to(REPO_ROOT)}") from exc


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SyncError(f"Missing required YAML file: {path.relative_to(REPO_ROOT)}") from exc


def slugify_section_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def parse_frontmatter_document(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"(?s)^---\n(.*?)\n---\n?(.*)$", text)
    if not match:
        raise SyncError(f"MDX content is missing YAML frontmatter: {display_path(path)}")
    frontmatter = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).lstrip()
    if not isinstance(frontmatter, dict):
        raise SyncError(f"Frontmatter must be a mapping: {display_path(path)}")
    return frontmatter, body


def expect_text(value: Any, *, field: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SyncError(f"{context} must provide non-empty '{field}'")
    return value.strip()


def expect_bool(value: Any, *, field: str, context: str) -> bool:
    if not isinstance(value, bool):
        raise SyncError(f"{context} must provide boolean '{field}'")
    return value


def expect_int(value: Any, *, field: str, context: str) -> int:
    if not isinstance(value, int):
        raise SyncError(f"{context} must provide integer '{field}'")
    return value


def expect_string_list(value: Any, *, field: str, context: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SyncError(f"{context} must provide string-list '{field}'")
    return [item.strip() for item in value]


def strip_mdx(text: str) -> str:
    stripped = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    stripped = re.sub(r"!\[.*?\]\(.*?\)", " ", stripped)
    stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
    stripped = re.sub(r"`([^`]+)`", r"\1", stripped)
    stripped = re.sub(r"[#>*_]", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped.strip()


def extract_plain_paragraphs(body: str, *, limit: int | None = 3) -> list[str]:
    paragraphs: list[str] = []
    for block in body.split("\n\n"):
        candidate = strip_mdx(block)
        if not candidate:
            continue
        paragraphs.append(candidate)
        if limit is not None and len(paragraphs) >= limit:
            break
    return paragraphs


def iter_copy_pairs() -> list[tuple[Path, Path]]:
    docs = [
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
        (REPO_ROOT / "tvl_book" / "tvl_specification.pdf", PUBLIC_ROOT / "docs" / "specification.pdf"),
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
        (REPO_ROOT / "tvl_book" / "examples" / "ch5_integration_pipeline.sh", PUBLIC_ROOT / "examples" / "book" / "ch5_integration_pipeline.sh"),
        (REPO_ROOT / "tvl_book" / "examples" / "ch5_integration_pipeline.sh", PUBLIC_ROOT / "examples" / "ci_pipeline.sh"),
        (REPO_ROOT / "tvl_book" / "examples" / "ch5_integration_manifest.yaml", PUBLIC_ROOT / "examples" / "book" / "ch5_integration_manifest.yaml"),
    ]

    return docs + examples


def iter_book_asset_pairs() -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for source in sorted((BOOK_CONTENT_ROOT / "images").rglob("*")):
        if source.is_file():
            destination = PUBLIC_BOOK_ASSETS_ROOT / "images" / source.relative_to(BOOK_CONTENT_ROOT / "images")
            pairs.append((source, destination))
    for source in sorted((BOOK_CONTENT_ROOT / "microsims").rglob("*")):
        if source.is_file():
            destination = PUBLIC_BOOK_ASSETS_ROOT / "microsims" / source.relative_to(BOOK_CONTENT_ROOT / "microsims")
            pairs.append((source, destination))
    return pairs


def strip_frontmatter(path: Path) -> str:
    _, body = parse_frontmatter_document(path)
    return body


def collect_example_source_map(copy_pairs: Iterable[tuple[Path, Path]]) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for source, destination in copy_pairs:
        if destination.is_relative_to(PUBLIC_ROOT):
            mapping["/" + destination.relative_to(PUBLIC_ROOT).as_posix()] = source
    for site_local in SITE_LOCAL_PUBLIC_FILES:
        if site_local.is_file():
            mapping["/" + site_local.relative_to(PUBLIC_ROOT).as_posix()] = site_local
    return mapping


def build_code_example(public_path: str, *, source_map: dict[str, Path]) -> dict[str, Any]:
    if public_path not in source_map:
        raise SyncError(f"Unknown example reference in canonical book content: {public_path}")
    source = source_map[public_path]
    if not source.is_file():
        raise SyncError(f"Example reference does not exist: {source.relative_to(REPO_ROOT)}")
    filename = Path(public_path).name
    return {
        "language": infer_language(filename),
        "filename": filename,
        "code": source.read_text(encoding="utf-8"),
        "downloadPath": public_path,
    }


def validate_example_reference(public_path: str, *, source_map: dict[str, Path], context: str) -> str:
    if public_path not in source_map:
        raise SyncError(f"{context} references unknown example asset '{public_path}'")
    source = source_map[public_path]
    if not source.is_file():
        raise SyncError(f"{context} references missing example asset '{display_path(source)}'")
    return public_path


def validate_section_reference(ref: str, *, known_sections: set[str], context: str) -> str:
    if ref not in known_sections:
        raise SyncError(f"{context} references unknown section '{ref}'")
    return ref


def build_book_outputs(*, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    copy_pairs = iter_copy_pairs()
    example_source_map = collect_example_source_map(copy_pairs)
    chapters: list[dict[str, Any]] = []
    section_lookup: dict[str, dict[str, Any]] = {}
    section_search_text: dict[str, str] = {}
    patterns: list[dict[str, Any]] = []
    pattern_search_text: dict[str, str] = {}
    compatibility_sections: dict[str, Any] = {}
    generated_content: dict[str, bytes] = {}
    generated_public_assets: dict[str, bytes] = {}
    known_sections: set[str] = set()

    if not BOOK_CHAPTERS_ROOT.is_dir():
        raise SyncError(f"Canonical book chapters directory is missing: {BOOK_CHAPTERS_ROOT.relative_to(repo_root)}")

    chapter_dirs = sorted(
        [path for path in BOOK_CHAPTERS_ROOT.iterdir() if path.is_dir()],
        key=lambda path: parse_frontmatter_document(path / "chapter.mdx")[0].get("id", 0),
    )

    for chapter_dir in chapter_dirs:
        chapter_frontmatter, chapter_body = parse_frontmatter_document(chapter_dir / "chapter.mdx")
        chapter_context = f"chapter '{chapter_dir.name}'"
        chapter = {
            "id": expect_int(chapter_frontmatter.get("id"), field="id", context=chapter_context),
            "slug": expect_text(chapter_frontmatter.get("slug"), field="slug", context=chapter_context),
            "title": expect_text(chapter_frontmatter.get("title"), field="title", context=chapter_context),
            "summary": expect_text(chapter_frontmatter.get("summary"), field="summary", context=chapter_context),
            "estimatedMinutes": expect_int(
                chapter_frontmatter.get("estimated_minutes"),
                field="estimated_minutes",
                context=chapter_context,
            ),
            "learningObjectives": expect_string_list(
                chapter_frontmatter.get("learning_objectives"),
                field="learning_objectives",
                context=chapter_context,
            ),
            "prerequisites": expect_string_list(
                chapter_frontmatter.get("prerequisites"),
                field="prerequisites",
                context=chapter_context,
            ),
            "pathTags": expect_string_list(
                chapter_frontmatter.get("path_tags"),
                field="path_tags",
                context=chapter_context,
            ),
            "primaryExample": expect_text(
                chapter_frontmatter.get("primary_example"),
                field="primary_example",
                context=chapter_context,
            ),
            "introModulePath": f"/src/generated/book/content/chapters/{chapter_dir.name}/chapter.mdx",
            "introExcerpt": extract_plain_paragraphs(chapter_body, limit=2),
            "sections": [],
        }
        generated_content[f"chapters/{chapter_dir.name}/chapter.mdx"] = chapter_body.encode("utf-8")

        for section_path in sorted(chapter_dir.glob("[0-9][0-9]-*.mdx")):
            section_frontmatter, section_body = parse_frontmatter_document(section_path)
            section_context = f"section '{section_path.relative_to(repo_root)}'"
            chapter_slug = expect_text(section_frontmatter.get("chapter"), field="chapter", context=section_context)
            if chapter_slug != chapter["slug"]:
                raise SyncError(
                    f"{section_context} declares chapter '{chapter_slug}' but is nested under '{chapter['slug']}'"
                )
            example_refs = [
                validate_example_reference(ref, source_map=example_source_map, context=section_context)
                for ref in expect_string_list(
                    section_frontmatter.get("example_refs"),
                    field="example_refs",
                    context=section_context,
                )
            ]
            excerpt = extract_plain_paragraphs(section_body, limit=3)
            content = extract_plain_paragraphs(section_body, limit=None)
            section = {
                "id": expect_text(section_frontmatter.get("id"), field="id", context=section_context),
                "slug": expect_text(section_frontmatter.get("slug"), field="slug", context=section_context),
                "title": expect_text(section_frontmatter.get("title"), field="title", context=section_context),
                "summary": expect_text(section_frontmatter.get("summary"), field="summary", context=section_context),
                "chapter": chapter_slug,
                "estimatedMinutes": expect_int(
                    section_frontmatter.get("estimated_minutes"),
                    field="estimated_minutes",
                    context=section_context,
                ),
                "interactive": expect_bool(
                    section_frontmatter.get("interactive"),
                    field="interactive",
                    context=section_context,
                ),
                "conceptRefs": expect_string_list(
                    section_frontmatter.get("concept_refs"),
                    field="concept_refs",
                    context=section_context,
                ),
                "exampleRefs": example_refs,
                "opalBridge": expect_bool(
                    section_frontmatter.get("opal_bridge"),
                    field="opal_bridge",
                    context=section_context,
                ),
                "route": f"/book/chapter/{chapter['slug']}/section/{expect_text(section_frontmatter.get('slug'), field='slug', context=section_context)}",
                "modulePath": f"/src/generated/book/content/chapters/{chapter_dir.name}/{section_path.name}",
                "excerpt": excerpt,
            }
            generated_content[f"chapters/{chapter_dir.name}/{section_path.name}"] = section_body.encode("utf-8")
            chapter["sections"].append(section)

            route_key = f"{chapter['slug']}/{section['slug']}"
            known_sections.add(route_key)
            section_lookup[route_key] = section
            section_search_text[route_key] = strip_mdx(section_body)

            compatibility_sections[f"{chapter['slug']}-{section['slug']}"] = {
                "title": section["title"],
                "description": section["summary"],
                "content": content,
                "examples": [build_code_example(path, source_map=example_source_map) for path in section["exampleRefs"]],
            }

        chapters.append(chapter)

    materials = []
    if BOOK_MATERIALS_ROOT.is_dir():
        material_paths = sorted(
            BOOK_MATERIALS_ROOT.glob("*.mdx"),
            key=lambda path: parse_frontmatter_document(path)[0].get("sort_order", 999),
        )
        for material_path in material_paths:
            material_frontmatter, material_body = parse_frontmatter_document(material_path)
            material_context = f"material '{material_path.relative_to(repo_root)}'"
            slug = expect_text(material_frontmatter.get("slug"), field="slug", context=material_context)
            related_sections = [
                validate_section_reference(ref, known_sections=known_sections, context=material_context)
                for ref in expect_string_list(
                    material_frontmatter.get("related_sections"),
                    field="related_sections",
                    context=material_context,
                )
            ]
            download_name = f"{slug}.md"
            materials.append(
                {
                    "id": expect_text(material_frontmatter.get("id"), field="id", context=material_context),
                    "slug": slug,
                    "title": expect_text(material_frontmatter.get("title"), field="title", context=material_context),
                    "summary": expect_text(
                        material_frontmatter.get("summary"),
                        field="summary",
                        context=material_context,
                    ),
                    "audience": expect_text(
                        material_frontmatter.get("audience"),
                        field="audience",
                        context=material_context,
                    ),
                    "materialType": expect_text(
                        material_frontmatter.get("material_type"),
                        field="material_type",
                        context=material_context,
                    ),
                    "estimatedMinutes": expect_int(
                        material_frontmatter.get("estimated_minutes"),
                        field="estimated_minutes",
                        context=material_context,
                    ),
                    "objectives": expect_string_list(
                        material_frontmatter.get("objectives"),
                        field="objectives",
                        context=material_context,
                    ),
                    "relatedSections": related_sections,
                    "route": f"/book/materials/{slug}",
                    "modulePath": f"/src/generated/book/content/materials/{material_path.name}",
                    "downloadPath": f"/book-assets/materials/{download_name}",
                }
            )
            generated_content[f"materials/{material_path.name}"] = material_body.encode("utf-8")
            generated_public_assets[f"materials/{download_name}"] = material_body.encode("utf-8")

    if BOOK_PATTERNS_ROOT.is_dir():
        pattern_paths = sorted(
            BOOK_PATTERNS_ROOT.glob("*.mdx"),
            key=lambda path: parse_frontmatter_document(path)[0].get("sort_order", 999),
        )
        for pattern_path in pattern_paths:
            pattern_frontmatter, pattern_body = parse_frontmatter_document(pattern_path)
            pattern_context = f"pattern '{pattern_path.relative_to(repo_root)}'"
            slug = expect_text(pattern_frontmatter.get("slug"), field="slug", context=pattern_context)
            related_sections = [
                validate_section_reference(ref, known_sections=known_sections, context=pattern_context)
                for ref in expect_string_list(
                    pattern_frontmatter.get("related_sections"),
                    field="related_sections",
                    context=pattern_context,
                )
            ]
            pattern = {
                "id": expect_text(pattern_frontmatter.get("id"), field="id", context=pattern_context),
                "slug": slug,
                "title": expect_text(pattern_frontmatter.get("title"), field="title", context=pattern_context),
                "summary": expect_text(pattern_frontmatter.get("summary"), field="summary", context=pattern_context),
                "family": expect_text(pattern_frontmatter.get("family"), field="family", context=pattern_context),
                "sortOrder": expect_int(
                    pattern_frontmatter.get("sort_order"),
                    field="sort_order",
                    context=pattern_context,
                ),
                "estimatedMinutes": expect_int(
                    pattern_frontmatter.get("estimated_minutes"),
                    field="estimated_minutes",
                    context=pattern_context,
                ),
                "tunedVariables": expect_string_list(
                    pattern_frontmatter.get("tuned_variables"),
                    field="tuned_variables",
                    context=pattern_context,
                ),
                "decisionAxes": expect_string_list(
                    pattern_frontmatter.get("decision_axes"),
                    field="decision_axes",
                    context=pattern_context,
                ),
                "failureModes": expect_string_list(
                    pattern_frontmatter.get("failure_modes"),
                    field="failure_modes",
                    context=pattern_context,
                ),
                "relatedSections": related_sections,
                "conceptRefs": expect_string_list(
                    pattern_frontmatter.get("concept_refs"),
                    field="concept_refs",
                    context=pattern_context,
                ),
                "primaryExample": validate_example_reference(
                    expect_text(
                        pattern_frontmatter.get("primary_example"),
                        field="primary_example",
                        context=pattern_context,
                    ),
                    source_map=example_source_map,
                    context=pattern_context,
                ),
                "route": f"/book/patterns/{slug}",
                "modulePath": f"/src/generated/book/content/patterns/{pattern_path.name}",
            }
            patterns.append(pattern)
            pattern_search_text[slug] = strip_mdx(pattern_body)
            generated_content[f"patterns/{pattern_path.name}"] = pattern_body.encode("utf-8")

    compatibility_chapters = {
        "chapters": [
            {
                "id": chapter["id"],
                "title": chapter["title"],
                "slug": chapter["slug"],
                "description": chapter["summary"],
                "sections": [
                    {"title": section["title"], "content": section["summary"], "slug": section["slug"]}
                    for section in chapter["sections"]
                ],
            }
            for chapter in chapters
        ]
    }

    paths = []
    for path_file in sorted(BOOK_PATHS_ROOT.glob("*.yml")):
        context = f"path '{path_file.relative_to(repo_root)}'"
        payload = load_yaml(path_file)
        if not isinstance(payload, dict):
            raise SyncError(f"{context} must be a mapping")
        entry_sections = [
            validate_section_reference(ref, known_sections=known_sections, context=context)
            for ref in expect_string_list(payload.get("entry_sections"), field="entry_sections", context=context)
        ]
        completion_sections = [
            validate_section_reference(ref, known_sections=known_sections, context=context)
            for ref in expect_string_list(payload.get("completion_sections"), field="completion_sections", context=context)
        ]
        sections = [
            validate_section_reference(ref, known_sections=known_sections, context=context)
            for ref in expect_string_list(payload.get("sections"), field="sections", context=context)
        ]
        missing_members = sorted({*entry_sections, *completion_sections} - set(sections))
        if missing_members:
            raise SyncError(
                f"{context} must include entry/completion refs in 'sections': {', '.join(missing_members)}"
            )
        paths.append(
            {
                "id": expect_text(payload.get("id"), field="id", context=context),
                "title": expect_text(payload.get("title"), field="title", context=context),
                "audience": expect_text(payload.get("audience"), field="audience", context=context),
                "goal": expect_text(payload.get("goal"), field="goal", context=context),
                "sections": sections,
                "entrySections": entry_sections,
                "completionSections": completion_sections,
                "estimatedMinutes": expect_int(payload.get("estimated_minutes"), field="estimated_minutes", context=context),
            }
        )

    concepts_payload = load_yaml(BOOK_CONCEPTS_PATH)
    if not isinstance(concepts_payload, dict):
        raise SyncError("Concept graph must be a mapping")
    raw_concepts = concepts_payload.get("concepts")
    if not isinstance(raw_concepts, list):
        raise SyncError("Concept graph must provide 'concepts' list")

    concepts = []
    concept_ids: set[str] = set()
    for idx, item in enumerate(raw_concepts):
        context = f"concept[{idx}]"
        if not isinstance(item, dict):
            raise SyncError(f"{context} must be a mapping")
        concept_id = expect_text(item.get("id"), field="id", context=context)
        concept_ids.add(concept_id)
        sections = [
            validate_section_reference(ref, known_sections=known_sections, context=context)
            for ref in expect_string_list(item.get("sections"), field="sections", context=context)
        ]
        concepts.append(
            {
                "id": concept_id,
                "term": expect_text(item.get("term"), field="term", context=context),
                "definition": expect_text(item.get("definition"), field="definition", context=context),
                "prerequisites": expect_string_list(item.get("prerequisites"), field="prerequisites", context=context),
                "sections": sections,
            }
        )

    for concept in concepts:
        unknown_prereqs = sorted(set(concept["prerequisites"]) - concept_ids)
        if unknown_prereqs:
            raise SyncError(
                f"Concept '{concept['id']}' references unknown prerequisite concepts: {', '.join(unknown_prereqs)}"
            )

    for section in section_lookup.values():
        unknown_refs = sorted(set(section["conceptRefs"]) - concept_ids)
        if unknown_refs:
            raise SyncError(
                f"Section '{section['chapter']}/{section['slug']}' references unknown concepts: {', '.join(unknown_refs)}"
            )

    for pattern in patterns:
        unknown_refs = sorted(set(pattern["conceptRefs"]) - concept_ids)
        if unknown_refs:
            raise SyncError(
                f"Pattern '{pattern['slug']}' references unknown concepts: {', '.join(unknown_refs)}"
            )

    search = []
    for chapter in chapters:
        for section in chapter["sections"]:
            section_key = f"{chapter['slug']}/{section['slug']}"
            search.append(
                {
                    "id": section["id"],
                    "kind": "section",
                    "title": section["title"],
                    "chapterSlug": chapter["slug"],
                    "chapterTitle": chapter["title"],
                    "sectionSlug": section["slug"],
                    "summary": section["summary"],
                    "route": section["route"],
                    "conceptRefs": section["conceptRefs"],
                    "pathTags": chapter["pathTags"],
                    "text": section_search_text[section_key],
                    "sectionKey": section_key,
                }
            )

    for pattern in patterns:
        search.append(
            {
                "id": pattern["id"],
                "kind": "pattern",
                "title": pattern["title"],
                "summary": pattern["summary"],
                "route": pattern["route"],
                "conceptRefs": pattern["conceptRefs"],
                "pathTags": [],
                "text": pattern_search_text[pattern["slug"]],
                "patternSlug": pattern["slug"],
                "family": pattern["family"],
            }
        )

    manifest = {
        "chapters": chapters,
        "materials": materials,
        "patterns": patterns,
        "paths": paths,
        "concepts": concepts,
        "search": search,
    }

    return {
        "copyPairs": copy_pairs,
        "assetPairs": iter_book_asset_pairs(),
        "generatedContent": generated_content,
        "generatedPublicAssets": generated_public_assets,
        "compatibilityChapters": compatibility_chapters,
        "compatibilitySections": compatibility_sections,
        "manifest": manifest,
    }


def build_expected_outputs(*, repo_root: Path = REPO_ROOT) -> dict[Path, bytes]:
    outputs: dict[Path, bytes] = {}
    book = build_book_outputs(repo_root=repo_root)

    for source, destination in book["copyPairs"]:
        if not source.is_file():
            raise SyncError(f"Missing canonical source file: {source.relative_to(repo_root)}")
        outputs[destination] = source.read_bytes()

    for source, destination in book["assetPairs"]:
        if not source.is_file():
            raise SyncError(f"Missing canonical asset file: {source.relative_to(repo_root)}")
        outputs[destination] = source.read_bytes()

    outputs[PUBLIC_ROOT / "docs" / "chapters.json"] = json_bytes(book["compatibilityChapters"])
    outputs[PUBLIC_ROOT / "docs" / "sections.json"] = json_bytes(book["compatibilitySections"])
    outputs[GENERATED_BOOK_ROOT / "manifest.json"] = json_bytes(book["manifest"])

    for relative_path, content in book["generatedContent"].items():
        outputs[GENERATED_BOOK_CONTENT_ROOT / relative_path] = content

    for relative_path, content in book["generatedPublicAssets"].items():
        outputs[PUBLIC_BOOK_ASSETS_ROOT / relative_path] = content

    return outputs


def clear_generated_targets() -> None:
    for path in (GENERATED_BOOK_ROOT, PUBLIC_BOOK_ASSETS_ROOT):
        if path.exists():
            shutil.rmtree(path)


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

    if not check:
        clear_generated_targets()

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
