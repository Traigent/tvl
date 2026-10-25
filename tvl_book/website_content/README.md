# TVL Website Content

This directory contains the canonical authored content for the TVL website and
book surfaces.

It is intentionally separated into:

- `chapters/`: canonical MDX-authored interactive book content, organized by
  chapter slug with chapter and section frontmatter
- `paths/`: authored guided reading paths (metadata; the React book app does not read them today)
- `concepts/`: authored concept graph metadata for glossary/prerequisite links (also not read by the app today)
- `book/`: authored TVL chapter content and supporting book pages
- `microsims/`: TVL-specific interactive assets
- `images/`: TVL-specific artwork
- `site_overrides/`: landing-page and navigation copy that was being used as
  local MkDocs site overrides

The primary web-book authoring surface is `chapters/`, plus the `paths/` and
`concepts/` metadata directories. This directory is a tracked source of truth
for website content. The React book app builds its chapters from its own
files in `website/client/src/book/chapters/`, not from this directory.
