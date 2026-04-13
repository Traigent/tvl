# TVL Website Content

This directory contains TVL-owned website content extracted from the ignored
`tvl/tvl_book/intelligent-textbooks/` working clone on March 13, 2026.

It is intentionally separated into:

- `chapters/`: canonical MDX-authored interactive book content, organized by
  chapter slug with chapter and section frontmatter
- `paths/`: guided reading paths consumed by the React book app
- `concepts/`: concept graph metadata for glossary/prerequisite links
- `book/`: authored TVL chapter content and supporting book pages
- `microsims/`: TVL-specific interactive assets
- `images/`: TVL-specific artwork copied from the nested clone
- `site_overrides/`: landing-page and navigation copy that was being used as
  local MkDocs site overrides

The `book/` directory remains as migration input from the extracted textbook
copy. The canonical web-book authoring surface is now `chapters/`, plus the
`paths/` and `concepts/` metadata directories.

This directory is a tracked source-of-truth. The ignored
`intelligent-textbooks/` clone should no longer be treated as an authoring or
canonical home for this content.
