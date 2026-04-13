# TVL Website Content

This directory contains the canonical authored content for the TVL website and
book surfaces.

It is intentionally separated into:

- `chapters/`: canonical MDX-authored interactive book content, organized by
  chapter slug with chapter and section frontmatter
- `paths/`: guided reading paths consumed by the React book app
- `concepts/`: concept graph metadata for glossary/prerequisite links
- `book/`: authored TVL chapter content and supporting book pages
- `microsims/`: TVL-specific interactive assets
- `images/`: TVL-specific artwork
- `site_overrides/`: landing-page and navigation copy that was being used as
  local MkDocs site overrides

The primary web-book authoring surface is `chapters/`, plus the `paths/` and
`concepts/` metadata directories. This directory is a tracked source of truth
for website content.
