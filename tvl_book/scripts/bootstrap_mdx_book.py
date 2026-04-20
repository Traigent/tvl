from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
WEBSITE_CONTENT_ROOT = REPO_ROOT / "tvl" / "tvl_book" / "website_content"
BOOK_SOURCE_ROOT = WEBSITE_CONTENT_ROOT / "book"
CHAPTERS_ROOT = WEBSITE_CONTENT_ROOT / "chapters"


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def strip_markdown(text: str) -> str:
    cleaned = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"[#>*_]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def extract_summary(text: str) -> str:
    blocks = [block.strip() for block in text.strip().split("\n\n") if block.strip()]
    for block in blocks:
        if block.startswith(("```", "<", "!!!", "|", "-", "*", "1.", "**")):
            continue
        if "```" in block:
            continue
        summary = strip_markdown(block)
        if summary:
            return summary.rstrip(".") + "."
    if blocks:
        return strip_markdown(blocks[0]).rstrip(".") + "."
    return "Section summary pending."


def to_frontmatter(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()


def wrap_component(name: str, attrs: dict[str, Any], content: str) -> str:
    attr_parts: list[str] = []
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, bool):
            attr_parts.append(f'{key}={{{str(value).lower()}}}')
            continue
        escaped = str(value).replace('"', "&quot;")
        attr_parts.append(f'{key}="{escaped}"')
    rendered_attrs = (" " + " ".join(attr_parts)) if attr_parts else ""
    body = content.strip()
    return f"<{name}{rendered_attrs}>\n\n{body}\n\n</{name}>"


ADMONITION_RE = re.compile(
    r'(?ms)^!!!\s+([a-zA-Z_-]+)(?:\s+"([^"]+)")?\n((?:^(?: {4}|\t).*(?:\n|$))+)',
    re.MULTILINE,
)

MERMAID_RE = re.compile(r"(?ms)^```mermaid\n(.*?)\n```[ \t]*\n?", re.MULTILINE)
IFRAME_RE = re.compile(r'<iframe\s+([^>]*?)src="([^"]+)"([^>]*)></iframe>', re.DOTALL)
ATTR_LIST_LINK_RE = re.compile(r"(\[[^\]]+\]\([^)]+\))\{[^}]+\}")


def convert_relative_asset_path(path: str) -> str:
    updated = path
    updated = updated.replace("../../sims/", "/book-assets/microsims/")
    updated = updated.replace("../sims/", "/book-assets/microsims/")
    updated = updated.replace("../../img/", "/book-assets/images/")
    updated = updated.replace("../img/", "/book-assets/images/")
    updated = updated.replace("/index.md", "/main.html")
    return updated


def transform_iframe(match: re.Match[str]) -> str:
    before, src, after = match.groups()
    full = f"{before} {after}"
    height_match = re.search(r'height="(\d+)px"', full)
    title = "Interactive Lab"
    lowered_src = src.lower()
    if "orientation-rag-circuit" in lowered_src:
        title = "Orientation RAG Circuit"
    safe_src = convert_relative_asset_path(src)
    height = int(height_match.group(1)) if height_match else 640
    return f'<MicrosimEmbed title="{title}" src="{safe_src}" height={{{height}}} />\n'


def transform_admonitions(text: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        tone = match.group(1).strip().lower()
        title = (match.group(2) or tone.replace("-", " ").title()).strip()
        content = textwrap.dedent(match.group(3)).strip()
        if tone in {"pitfall", "reliability"}:
            return wrap_component("PitfallCard", {"title": title, "tone": tone}, content)
        return wrap_component("ConceptCallout", {"title": title, "tone": tone}, content)

    return ADMONITION_RE.sub(replacer, text)


def transform_mermaid(text: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        chart = match.group(1).strip()
        return f"<MermaidDiagram chart={{{json.dumps(chart, ensure_ascii=False)}}} />\n\n"

    return MERMAID_RE.sub(replacer, text)


def transform_markdown_to_mdx(text: str) -> str:
    output = text.replace("\r\n", "\n")
    output = ATTR_LIST_LINK_RE.sub(r"\1", output)
    output = transform_admonitions(output)
    output = transform_mermaid(output)
    output = IFRAME_RE.sub(transform_iframe, output)
    output = convert_relative_asset_path(output)
    output = re.sub(r"\n{3,}", "\n\n", output).strip() + "\n"
    return output


def split_chapter_markdown(text: str) -> tuple[str, list[tuple[str, str]]]:
    normalized = text.replace("\r\n", "\n").strip()
    lines = normalized.splitlines()
    if lines and lines[0].startswith("# "):
        normalized = "\n".join(lines[1:]).lstrip()

    pieces = re.split(r"(?m)^## ", normalized)
    intro = pieces[0].strip()
    sections: list[tuple[str, str]] = []
    for piece in pieces[1:]:
        title, _, body = piece.partition("\n")
        sections.append((title.strip(), body.lstrip()))
    return intro, sections


@dataclass(frozen=True)
class ChapterConfig:
    source: str
    id: int
    slug: str
    title: str
    summary: str
    estimated_minutes: int
    learning_objectives: list[str]
    prerequisites: list[str]
    path_tags: list[str]
    primary_example: str


CHAPTERS = [
    ChapterConfig(
        source="chapter-01-motivation.md",
        id=1,
        slug="why-tvl-exists",
        title="Why TVL Exists",
        summary="Why tuned variables and governed optimization are required for modern AI systems under drift.",
        estimated_minutes=18,
        learning_objectives=[
            "Recognize why static configuration breaks under model, latency, and budget drift.",
            "Understand the core TVL loop: declare, validate, explore, and promote with evidence.",
            "Anchor the rest of the book on the Campus Orientation RAG running example.",
        ],
        prerequisites=[],
        path_tags=["quickstart", "architect", "operator"],
        primary_example="/examples/rag-support-bot.tvl.yml",
    ),
    ChapterConfig(
        source="chapter-02-basics.md",
        id=2,
        slug="getting-fluent-in-tvl",
        title="Getting Fluent in TVL",
        summary="A practical TVL walkthrough from first module to repeatable validation and hands-on intuition.",
        estimated_minutes=26,
        learning_objectives=[
            "Author a valid TVL module with typed TVARs, objectives, and promotion policy.",
            "Run the core validation commands and understand what they catch.",
            "Build intuition for tuning variables through a live microsim.",
        ],
        prerequisites=["why-tvl-exists"],
        path_tags=["quickstart", "architect"],
        primary_example="/examples/book/ch2_hello_tvl.tvl.yml",
    ),
    ChapterConfig(
        source="chapter-03-constraints.md",
        id=3,
        slug="constraints-units-safety-nets",
        title="Constraints, Units, and Safety Nets",
        summary="Typed structural constraints, derived checks, and satisfiability preflights for safe exploration.",
        estimated_minutes=28,
        learning_objectives=[
            "Differentiate structural constraints from derived operational checks.",
            "Write TVL-native formulas that compile into deterministic feasibility checks.",
            "Use SAT tooling and tests to catch invalid search spaces early.",
        ],
        prerequisites=["why-tvl-exists", "getting-fluent-in-tvl"],
        path_tags=["quickstart", "architect", "operator"],
        primary_example="/examples/validation-phase2/structural-sat.tvl.yml",
    ),
    ChapterConfig(
        source="chapter-04-patterns.md",
        id=4,
        slug="patterns-for-real-deployments",
        title="Patterns for Real Deployments",
        summary="Composition, overlays, safe narrowing, and provenance patterns for production operations.",
        estimated_minutes=24,
        learning_objectives=[
            "Apply environment-aware overlays without polluting the core TVL schema.",
            "Use safe narrowing patterns to move from base modules to staging, production, and hotfixes.",
            "Capture provenance so promotions remain replayable and reviewable.",
        ],
        prerequisites=["getting-fluent-in-tvl", "constraints-units-safety-nets"],
        path_tags=["architect", "operator"],
        primary_example="/examples/book/ch4_base_module.tvl.yml",
    ),
    ChapterConfig(
        source="chapter-05-integration.md",
        id=5,
        slug="integration-patterns",
        title="Integration Patterns",
        summary="How TVL plugs into CI, optimizer runtime, data validation, and auditable promotion flows.",
        estimated_minutes=22,
        learning_objectives=[
            "Wire the TVL CLI into a deterministic CI pipeline.",
            "Understand how Triagent/TVO and DVL consume TVL outputs.",
            "Treat manifests as the operational record for promotion decisions.",
        ],
        prerequisites=["getting-fluent-in-tvl", "constraints-units-safety-nets", "patterns-for-real-deployments"],
        path_tags=["quickstart", "architect", "operator"],
        primary_example="/examples/ci_pipeline.sh",
    ),
]


SECTION_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {
    ("why-tvl-exists", "Design Goals at a Glance"): {
        "estimated_minutes": 6,
        "concept_refs": ["drift-governance", "tvars", "promotion-policy"],
        "example_refs": ["/examples/rag-support-bot.tvl.yml"],
    },
    ("why-tvl-exists", "Running Example · Campus Orientation RAG"): {
        "interactive": False,
        "estimated_minutes": 8,
        "concept_refs": ["running-example", "environment-snapshot", "evaluation-set"],
        "example_refs": ["/examples/rag-support-bot.tvl.yml"],
    },
    ("getting-fluent-in-tvl", "Minimal Working Spec"): {
        "estimated_minutes": 7,
        "concept_refs": ["tvars", "evaluation-set", "promotion-policy"],
        "example_refs": ["/examples/book/ch2_hello_tvl.tvl.yml"],
    },
    ("getting-fluent-in-tvl", "Validation Warm-Up"): {
        "estimated_minutes": 6,
        "concept_refs": ["validation-workflow", "cli-toolchain"],
        "example_refs": ["/examples/book/ch2_validate_spec.py"],
    },
    ("getting-fluent-in-tvl", "TVL 0.9 Type System"): {
        "title": "TVL Type System",
        "estimated_minutes": 5,
        "concept_refs": ["tvars", "type-system"],
        "example_refs": ["/examples/tool-use.tvl.yml"],
    },
    ("getting-fluent-in-tvl", "Analog Circuit Lab · Explore the Knobs"): {
        "interactive": True,
        "estimated_minutes": 8,
        "concept_refs": ["running-example", "microsim-lab", "structural-constraints"],
        "example_refs": ["/examples/book/ch2_hello_tvl.tvl.yml"],
    },
    ("constraints-units-safety-nets", "Two Kinds of Constraints"): {
        "estimated_minutes": 6,
        "concept_refs": ["structural-constraints", "derived-constraints", "operational-checks"],
        "example_refs": ["/examples/text-to-sql.tvl.yml"],
    },
    ("constraints-units-safety-nets", "Structural Constraint Syntax"): {
        "estimated_minutes": 7,
        "concept_refs": ["structural-constraints", "satisfiability"],
        "example_refs": ["/examples/validation-phase2/structural-sat.tvl.yml"],
    },
    ("constraints-units-safety-nets", "Derived Constraints"): {
        "estimated_minutes": 5,
        "concept_refs": ["derived-constraints", "operational-checks", "environment-snapshot"],
        "example_refs": ["/examples/validation-phase3/budget-invalid.tvl.yml"],
    },
    ("constraints-units-safety-nets", "Analog Circuit Drill · Watch Constraints React"): {
        "interactive": True,
        "estimated_minutes": 7,
        "concept_refs": ["microsim-lab", "structural-constraints", "derived-constraints"],
        "example_refs": ["/examples/validation-phase2/structural-sat.tvl.yml"],
    },
    ("constraints-units-safety-nets", "Testing Constraints"): {
        "estimated_minutes": 6,
        "concept_refs": ["satisfiability", "validation-workflow", "structural-constraints"],
        "example_refs": ["/examples/ci_pipeline.sh"],
    },
    ("patterns-for-real-deployments", "Layered Specifications"): {
        "estimated_minutes": 7,
        "concept_refs": ["overlays", "safe-narrowing", "environment-snapshot"],
        "example_refs": ["/examples/book/ch4_base_module.tvl.yml", "/examples/book/ch4_staging.overlay.yml"],
    },
    ("patterns-for-real-deployments", "Visualizing Overlays"): {
        "estimated_minutes": 5,
        "concept_refs": ["overlays", "safe-narrowing"],
        "example_refs": ["/examples/book/ch4_base_module.tvl.yml"],
    },
    ("patterns-for-real-deployments", "Hotfix Playbook"): {
        "estimated_minutes": 6,
        "concept_refs": ["overlays", "safe-narrowing", "provenance"],
        "example_refs": ["/examples/book/ch4_hotfix.overlay.yml"],
    },
    ("patterns-for-real-deployments", "Provenance Matters"): {
        "estimated_minutes": 5,
        "concept_refs": ["provenance", "promotion-manifest"],
        "example_refs": ["/examples/book/ch5_integration_manifest.yaml"],
    },
    ("integration-patterns", "TVL CLI Tools"): {
        "estimated_minutes": 7,
        "concept_refs": ["cli-toolchain", "validation-workflow"],
        "example_refs": ["/examples/ci_pipeline.sh"],
    },
    ("integration-patterns", "Field Notes · Replay the Optimization Story"): {
        "interactive": True,
        "estimated_minutes": 6,
        "concept_refs": ["microsim-lab", "triagent-integration", "promotion-manifest"],
        "example_refs": ["/examples/ci_pipeline.sh"],
    },
    ("integration-patterns", "Manifests and Promotion"): {
        "estimated_minutes": 5,
        "concept_refs": ["promotion-manifest", "triagent-integration", "dvl-integration"],
        "example_refs": ["/examples/book/ch5_integration_manifest.yaml"],
        "opal_bridge": True,
    },
}


def default_section_metadata(chapter: ChapterConfig, title: str, body: str) -> dict[str, Any]:
    return {
        "id": f"chapter-{chapter.id:02d}-{slugify(title)}",
        "slug": slugify(title),
        "title": title,
        "summary": extract_summary(body),
        "chapter": chapter.slug,
        "estimated_minutes": 5,
        "interactive": False,
        "concept_refs": [],
        "example_refs": [],
        "opal_bridge": False,
    }


def ensure_dirs() -> None:
    (WEBSITE_CONTENT_ROOT / "paths").mkdir(parents=True, exist_ok=True)
    (WEBSITE_CONTENT_ROOT / "concepts").mkdir(parents=True, exist_ok=True)
    CHAPTERS_ROOT.mkdir(parents=True, exist_ok=True)


def write_if_changed(path: Path, content: str) -> None:
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_chapters() -> None:
    for chapter in CHAPTERS:
        source_path = BOOK_SOURCE_ROOT / chapter.source
        intro, sections = split_chapter_markdown(source_path.read_text(encoding="utf-8"))
        chapter_dir = CHAPTERS_ROOT / chapter.slug
        chapter_dir.mkdir(parents=True, exist_ok=True)

        chapter_frontmatter = {
            "id": chapter.id,
            "slug": chapter.slug,
            "title": chapter.title,
            "summary": chapter.summary,
            "estimated_minutes": chapter.estimated_minutes,
            "learning_objectives": chapter.learning_objectives,
            "prerequisites": chapter.prerequisites,
            "path_tags": chapter.path_tags,
            "primary_example": chapter.primary_example,
        }
        chapter_body = transform_markdown_to_mdx(intro)
        chapter_content = f"---\n{to_frontmatter(chapter_frontmatter)}\n---\n\n{chapter_body}"
        write_if_changed(chapter_dir / "chapter.mdx", chapter_content)

        for idx, (title, body) in enumerate(sections, start=1):
            section_frontmatter = default_section_metadata(chapter, title, body)
            section_frontmatter.update(SECTION_OVERRIDES.get((chapter.slug, title), {}))
            section_body = transform_markdown_to_mdx(body)
            section_content = f"---\n{to_frontmatter(section_frontmatter)}\n---\n\n{section_body}"
            filename = f"{idx:02d}-{section_frontmatter['slug']}.mdx"
            write_if_changed(chapter_dir / filename, section_content)


def build_paths() -> None:
    paths = {
        "quickstart": {
            "id": "quickstart",
            "title": "Quickstart",
            "audience": "Engineers who need a valid TVL module fast.",
            "goal": "Author, validate, and reason about one real TVL module with at least one interactive checkpoint.",
            "sections": [
                "getting-fluent-in-tvl/minimal-working-spec",
                "getting-fluent-in-tvl/validation-warm-up",
                "getting-fluent-in-tvl/analog-circuit-lab-explore-the-knobs",
                "constraints-units-safety-nets/two-kinds-of-constraints",
                "constraints-units-safety-nets/testing-constraints",
                "integration-patterns/tvl-cli-tools",
            ],
            "entry_sections": [
                "getting-fluent-in-tvl/minimal-working-spec",
            ],
            "completion_sections": [
                "constraints-units-safety-nets/testing-constraints",
                "integration-patterns/tvl-cli-tools",
            ],
            "estimated_minutes": 42,
        },
        "architect": {
            "id": "architect",
            "title": "Architect",
            "audience": "Technical leads designing governed optimization systems.",
            "goal": "Understand the language model, constraints, overlays, and integration contracts end to end.",
            "sections": [
                "why-tvl-exists/running-example-campus-orientation-rag",
                "getting-fluent-in-tvl/tvl-types-and-domains",
                "constraints-units-safety-nets/structural-constraint-syntax",
                "patterns-for-real-deployments/layered-specifications",
                "patterns-for-real-deployments/visualizing-overlays",
                "patterns-for-real-deployments/provenance-matters",
                "integration-patterns/manifests-and-promotion",
            ],
            "entry_sections": [
                "why-tvl-exists/running-example-campus-orientation-rag",
                "getting-fluent-in-tvl/tvl-types-and-domains",
            ],
            "completion_sections": [
                "patterns-for-real-deployments/provenance-matters",
                "integration-patterns/manifests-and-promotion",
            ],
            "estimated_minutes": 90,
        },
        "operator": {
            "id": "operator",
            "title": "Operator",
            "audience": "Platform and reliability engineers owning rollout safety.",
            "goal": "Operate constraints, overlays, provenance, and promotion evidence confidently during change and incident response.",
            "sections": [
                "constraints-units-safety-nets/two-kinds-of-constraints",
                "constraints-units-safety-nets/operational-preconditions",
                "constraints-units-safety-nets/testing-constraints",
                "patterns-for-real-deployments/layered-specifications",
                "patterns-for-real-deployments/hotfix-playbook",
                "patterns-for-real-deployments/provenance-matters",
                "integration-patterns/tvl-cli-tools",
                "integration-patterns/manifests-and-promotion",
            ],
            "entry_sections": [
                "constraints-units-safety-nets/two-kinds-of-constraints",
                "patterns-for-real-deployments/hotfix-playbook",
            ],
            "completion_sections": [
                "integration-patterns/tvl-cli-tools",
                "integration-patterns/manifests-and-promotion",
            ],
            "estimated_minutes": 72,
        },
    }
    for path_id, payload in paths.items():
        write_if_changed(
            WEBSITE_CONTENT_ROOT / "paths" / f"{path_id}.yml",
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        )


def build_concepts() -> None:
    graph = {
        "concepts": [
            {
                "id": "drift-governance",
                "term": "Drift and Governance",
                "definition": "The operational reality that model catalogs, prices, latency envelopes, and business rules change faster than application releases.",
                "prerequisites": [],
                "sections": [
                    "why-tvl-exists/design-goals-at-a-glance",
                    "why-tvl-exists/running-example-campus-orientation-rag",
                ],
            },
            {
                "id": "tvars",
                "term": "Tuned Variables (TVARs)",
                "definition": "Typed parameters that define the search space for governed optimization.",
                "prerequisites": ["drift-governance"],
                "sections": [
                    "getting-fluent-in-tvl/minimal-working-spec",
                    "getting-fluent-in-tvl/tvl-types-and-domains",
                ],
            },
            {
                "id": "environment-snapshot",
                "term": "Environment Snapshot",
                "definition": "A snapshot ID plus optional bindings and numeric context that anchor a TVL module to the operating setting used during evaluation.",
                "prerequisites": ["drift-governance"],
                "sections": [
                    "why-tvl-exists/running-example-campus-orientation-rag",
                    "patterns-for-real-deployments/layered-specifications",
                ],
            },
            {
                "id": "evaluation-set",
                "term": "Evaluation Set",
                "definition": "The evaluation set and optional seed used to compare configurations consistently.",
                "prerequisites": ["drift-governance"],
                "sections": [
                    "why-tvl-exists/running-example-campus-orientation-rag",
                    "getting-fluent-in-tvl/minimal-working-spec",
                ],
            },
            {
                "id": "type-system",
                "term": "TVL Types and Domains",
                "definition": "Explicit domain shapes for TVARs such as bool, int, float, enum, tuple, and callable references.",
                "prerequisites": ["tvars"],
                "sections": [
                    "getting-fluent-in-tvl/tvl-types-and-domains",
                ],
            },
            {
                "id": "structural-constraints",
                "term": "Structural Constraints",
                "definition": "Typed formulas over TVARs that prune invalid assignments before trials run.",
                "prerequisites": ["tvars", "type-system"],
                "sections": [
                    "constraints-units-safety-nets/two-kinds-of-constraints",
                    "constraints-units-safety-nets/structural-constraint-syntax",
                ],
            },
            {
                "id": "derived-constraints",
                "term": "Operational Preconditions",
                "definition": "In TVL syntax, these are feasibility checks under `constraints.derived` over `env.context.*` symbols such as provider price, baseline latency, and request headroom.",
                "prerequisites": ["structural-constraints"],
                "sections": [
                    "constraints-units-safety-nets/operational-preconditions",
                    "constraints-units-safety-nets/analog-circuit-drill-watch-constraints-react",
                ],
            },
            {
                "id": "operational-checks",
                "term": "Operational Checks",
                "definition": "Runtime validation steps that gate feasibility budgets, environment constraints, and deployment readiness.",
                "prerequisites": ["derived-constraints"],
                "sections": [
                    "constraints-units-safety-nets/operational-preconditions",
                    "integration-patterns/tvl-cli-tools",
                ],
            },
            {
                "id": "satisfiability",
                "term": "Satisfiability Preflight",
                "definition": "The structural check that ensures at least one valid assignment exists before exploration.",
                "prerequisites": ["structural-constraints"],
                "sections": [
                    "constraints-units-safety-nets/testing-constraints",
                    "constraints-units-safety-nets/checklist-before-promotion",
                ],
            },
            {
                "id": "promotion-policy",
                "term": "Promotion Policy",
                "definition": "The governance contract that records practical-effect and statistical requirements for rollout decisions.",
                "prerequisites": ["drift-governance"],
                "sections": [
                    "why-tvl-exists/design-goals-at-a-glance",
                    "getting-fluent-in-tvl/minimal-working-spec",
                ],
            },
            {
                "id": "overlays",
                "term": "Overlays and Composition",
                "definition": "Preprocessing inputs that safely narrow or adapt a base TVL module into environment-specific variants.",
                "prerequisites": ["environment-snapshot", "structural-constraints"],
                "sections": [
                    "patterns-for-real-deployments/module-composition-with-tvl-compose",
                    "patterns-for-real-deployments/hotfix-playbook",
                ],
            },
            {
                "id": "safe-narrowing",
                "term": "Safe Narrowing",
                "definition": "The rule that overlays should remove options or tighten bounds rather than silently widen risk.",
                "prerequisites": ["overlays"],
                "sections": [
                    "patterns-for-real-deployments/override-rules",
                    "patterns-for-real-deployments/hotfix-playbook",
                ],
            },
            {
                "id": "provenance",
                "term": "Provenance",
                "definition": "The artifact trail that links composed specs, overlays, timestamps, and build identities for auditability.",
                "prerequisites": ["overlays"],
                "sections": [
                    "patterns-for-real-deployments/provenance-matters",
                    "integration-patterns/manifests-and-promotion",
                ],
            },
            {
                "id": "cli-toolchain",
                "term": "CLI Toolchain",
                "definition": "The deterministic sequence of parse, lint, validate, structural, and operational checks used locally and in CI.",
                "prerequisites": ["promotion-policy", "structural-constraints"],
                "sections": [
                    "getting-fluent-in-tvl/validation-warm-up",
                    "integration-patterns/tvl-cli-tools",
                ],
            },
            {
                "id": "validation-workflow",
                "term": "Validation Workflow",
                "definition": "The practical local-to-CI sequence for parsing, linting, schema validation, and feasibility checks.",
                "prerequisites": ["cli-toolchain"],
                "sections": [
                    "getting-fluent-in-tvl/validation-warm-up",
                    "constraints-units-safety-nets/testing-constraints",
                ],
            },
            {
                "id": "triagent-integration",
                "term": "Triagent/TVO Integration",
                "definition": "Triagent is the optimization platform, and TVO is the optimizer inside it that reads TVL, explores candidates, and produces promotion evidence.",
                "prerequisites": ["cli-toolchain", "promotion-policy"],
                "sections": [
                    "integration-patterns/field-notes-replay-the-optimization-story",
                    "integration-patterns/manifests-and-promotion",
                ],
            },
            {
                "id": "dvl-integration",
                "term": "DVL Integration",
                "definition": "DVL is the data-validation layer that checks whether evaluation datasets are still trustworthy before rollout decisions are accepted.",
                "prerequisites": ["triagent-integration"],
                "sections": [
                    "integration-patterns/manifests-and-promotion",
                ],
            },
            {
                "id": "opal-bridge",
                "term": "OPAL Bridge",
                "definition": "OPAL is the higher-level authoring layer that lowers into TVL plus runtime-side metadata for execution systems.",
                "prerequisites": ["triagent-integration"],
                "sections": [
                    "integration-patterns/manifests-and-promotion",
                ],
            },
            {
                "id": "promotion-manifest",
                "term": "Promotion Manifest",
                "definition": "The audit bundle that captures specs, validations, measurements, and rollout decisions.",
                "prerequisites": ["provenance", "triagent-integration"],
                "sections": [
                    "patterns-for-real-deployments/provenance-matters",
                    "integration-patterns/manifests-and-promotion",
                ],
            },
            {
                "id": "microsim-lab",
                "term": "Microsim Lab",
                "definition": "A focused interactive model that builds intuition for TVL trade-offs and constraint feedback.",
                "prerequisites": ["tvars", "structural-constraints"],
                "sections": [
                    "getting-fluent-in-tvl/analog-circuit-lab-explore-the-knobs",
                    "constraints-units-safety-nets/analog-circuit-drill-watch-constraints-react",
                    "integration-patterns/field-notes-replay-the-optimization-story",
                ],
            },
            {
                "id": "running-example",
                "term": "Running Example",
                "definition": "The Campus Orientation RAG system that ties the concepts, examples, and labs together across the book.",
                "prerequisites": ["drift-governance"],
                "sections": [
                    "why-tvl-exists/running-example-campus-orientation-rag",
                    "getting-fluent-in-tvl/analog-circuit-lab-explore-the-knobs",
                ],
            },
        ]
    }
    write_if_changed(
        WEBSITE_CONTENT_ROOT / "concepts" / "graph.yml",
        yaml.safe_dump(graph, sort_keys=False, allow_unicode=True),
    )


def main() -> int:
    ensure_dirs()
    build_chapters()
    build_paths()
    build_concepts()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
