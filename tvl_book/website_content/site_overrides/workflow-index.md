# Book Generation Workflow

> **Archived page.** Written for a retired MkDocs build of the TVL site, not published on tvl-lang.org. The workflow
> step pages and the embedded `book-gen-workflow` simulation are not in this repository, so the steps are not links.

<iframe src="../sims/book-gen-workflow/main.html" height="610px" scrolling="no"
  style="overflow: hidden;"></iframe>

This section is an overview of some of the workflows we use to generate intelligent textbooks from a course description.

## Steps

### Course Description

### Bloom's Taxonomy

Classify each learning objective by Bloom's taxonomy, a standard ordering of cognitive levels from remembering
and understanding up to evaluating and creating.

### Concept Enumeration

List the concepts the course must cover, one per line, before ordering them by dependency.

### Concept Dependency

### Learning Graph

A learning graph has one node per concept and a directed edge from each concept to the concepts it depends on,
so lessons can be ordered so that prerequisites come first.
