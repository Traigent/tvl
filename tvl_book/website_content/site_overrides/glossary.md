# Glossary of Terms for mkdocs for Intelligent Textbooks

> **Archived page.** Generic MkDocs glossary from a retired build of the TVL site, not published on tvl-lang.org.
> It defines textbook-tooling terms, not TVL terms; the site book's glossary is
> [`98-glossary.mdx`](../../../website/client/src/book/chapters/98-glossary.mdx).

#### Admonition

A section of text that is separate from the main flow of text.

Admonitions are designed so that they can be quickly skipped over
if the user is not concerned with the topic.

In mkdocs-material, the admonition types include abstract, note, info, tip, success, question, warning, failure,
danger, bug, example and quote.

[mkdocs-material admonitions documentation](https://squidfunk.github.io/mkdocs-material/reference/admonitions/)

* Also known as: "call outs"

#### Automatic Build

Using an automatic process that generates HTML from the markdown files.

The process regenerates and redeploys the documentation whenever source files change, typically triggered by a
continuous integration (CI) tool or build server. For mkdocs, a build can run whenever any part of `mkdocs.yml` or the
files in the `docs` directory change. On GitHub, a GitHub Action (an automated workflow) can be configured to do this.
*Helps keep documentation current without manual rebuilds, as long as the triggers are configured and each build and deployment succeeds.*


#### Code Highlighting

The process of rendering source code with visually distinct styles to enhance readability and comprehension.

Mkdocs material allows this feature to be enabled by changing the mkdocs.yml configuration file.

A feature that applies syntax-specific color schemes and formatting to code blocks within the documentation.
*Improves readability and comprehension of code examples by distinguishing keywords, variables, and other language constructs.*

#### Concept Graph

A structured representation of concepts and their interrelationships, typically organized as nodes connected by edges.

Concept Graphs are used to create lesson plans and learning roadmaps that are customized to a student's learning objectives.

A visual representation of the relationships between topics, concepts, and terms within the documentation.
*Helps users navigate complex material, see how ideas interconnect, and discover related information.*

#### Deep Linking

The ability to send a link to another person in a chat or e-mail that links
directly to a subsection of a document.

**Example:** You can send a link directly to a specific term in the [Glossary of Terms](#glossary)

#### Embedding

A numeric vector representation of text that encodes semantic meaning, enabling large language models and semantic search systems to compare and rank content based on conceptual similarity rather than just keyword matching.

**Example in an Intelligent Textbook:**
When a student highlights a concept, the intelligent textbook generates embeddings for that concept and searches its database of content for related topics that share similar embeddings. As a result, it can suggest complementary reading sections, practice questions, or simulations that align with the student’s current focus, thus enhancing personalized learning.

#### Favicon
A small icon associated with a webpage, displayed by web browsers in tabs, bookmarks, or address bars.

#### Formulas
Mathematical expressions that represent relationships between variables, constants, and functions.

Mathematical or scientific expressions integrated into the documentation, often rendered using tools such as LaTeX or MathJax.
*Enables precise and readable presentation of equations, enhancing clarity in technical and scholarly content.*

#### GitHub Actions

Scripts that perform build processes on GitHub servers.

GitHub actions can automatically be run when any new content is updated in the docs directory or the mkdocs.yml file.

A workflow automation service integrated into GitHub that executes predefined tasks in response to repository events.

#### Glossary

A controlled vocabulary that lists specialized terms and their definitions to ensure consistent understanding.

* Also known as: Glossary of Terms

#### Hyper-Personalization

The ability for a textbook to be customized to the needs of an individual learner.

Modern textbooks allow hyper-personalization to be done in real-time using chatbots and agents.

#### Edit Icon

A control at the top of each page that links readers to an interface for editing the page's source text.

In mkdocs-material, clicking the Edit icon opens the page's source text in an editing form. When the reader saves a
change, a configured GitHub Action (an automated workflow) can be triggered to rebuild the HTML of the site.

This feature lets non-technical staff change text and preview the result without having to set up a build process on their own computer or server.

#### Keyword Search

A retrieval method that matches documents against user-supplied words or phrases to identify relevant content.

See also: [semantic search](#semantic-search)

#### Glossary of Terms

A dedicated section that provides definitions and explanations of key terms, jargon, and acronyms used throughout the documentation.
*Serves as a quick reference to ensure consistent understanding of terminology across readers.*

#### Edit from GitHub

An integrated link within the documentation that directs users to the corresponding source file on GitHub.

Edit links encourage community involvement by allowing readers to propose edits, corrections, or improvements through pull requests (proposals to merge their changes into the source).  Users do not need to understand how the build process works on their local systems to generate an updated web page.

#### Intelligent Textbook

A textbook that has the ability to respond to the needs of each student.

See Also: [Levels of Intelligent Textbook](#levels-of-intelligent-textbooks)

#### ISO Definition Criteria

A term definition is considered to be consistent with ISO/IEC 11179 (the standard of the International Organization for Standardization (ISO) and the International Electrotechnical Commission (IEC) for metadata registries) if it meets the following criteria:

1. Precise
2. Concise
3. Distinct
4. Non-circular
5. Unencumbered with business rules

#### Learning Graph

A directed graph of concepts that reflects the order that concepts should be learned to master a new concept.

#### Levels of Intelligent Textbooks

A five level classification of intelligent textbooks.

* See [Five Levels of Intelligent Textbooks](https://dmccreary.medium.com/five-levels-of-intelligent-textbooks-b81a4c1525a0)

#### License

A legal instrument specifying permissions, conditions, and restrictions for using, modifying, or redistributing content or software.

`Material for MkDocs` allows you to place your license link on the footer of each page.

Clarifies permissions and restrictions, providing guidance to users and contributors.

Textbook pages can be generated with links in their footer to the Creative Commons licenses.

#### Link Checker

A tool that verifies the validity and accessibility of hyperlinks within a given set of documents or webpages.

With mkdocs material, link checking - both internal links and links to external pages - can be done as part of the build process or a separate process.

*Link checking helps keep references accurate and working, which improves the reader's experience.*

#### Markdown

A lightweight markup language with plain text formatting syntax designed to be easy to read and write. It is primarily used for creating formatted documents and web content, converting plain text to structured formats such as HTML or PDF through a rendering process.

**Example:** Markdown syntax allows for the creation of structured content. For instance:

- To create a header: `# Header 1` or `## Header 2`
- To format text in bold: `**bold text**`
- To create a link: `[Link text](https://example.com)`
- To include an image: `![Alt text](image-url.png)`

For example, to write a numbered list:

```markdown
1. Item 1
1. Item 2
1. Item 3
```

Markdown will be rendered as the following:

1. Item 1
1. Item 2
1. Item 3

Note that the item counter is automatically calculated.

#### Material

A popular theme for the [mkdocs](#mkdocs) build system.

The Material theme is maintained on [GitHub](https://github.com/squidfunk/mkdocs-material/).

#### Mkdocs

A documentation build system that leverages [Markdown](#markdown) syntax for generating textbooks and websites.

#### MicroSim

A small-scale, embedded interactive simulation designed to illustrate a concept interactively within educational content.

MicroSims are a core element of intelligent interactive textbooks.

A MicroSim is self-contained and embedded within the documentation, so readers can interact with or test a concept in a controlled environment.

See the [MicroSims for Education Website](https://dmccreary.github.io/microsims/)

#### MicroSite

A website that runs on a web server using only its own files, with no need to call the application programming interfaces (APIs, the programmatic access points) of complex or expensive external services such as a hosted search engine.

#### Navigation

The organized structure of menus, sections, and links that guide readers through the documentation.
*Facilitates ease of use, enabling readers to find information efficiently.*

In our textbooks we focus on left-side navigation systems since these
are the default navigation system and they are both intuitive and
familiar to our users.  Our users also tend to be using
screens that are wide landscape displays.  We discourage top navigation.

#### p5.js

The JavaScript library most commonly used to render MicroSims.

Many other JavaScript libraries could be used; p5.js is a common choice for MicroSims.

Other specialized libraries such as [vis.js](#visjs) are used for tasks such
as simulating graph traversal algorithms.

#### Quiz Management

Quiz management lets pages include self-assessments with revealable answers: the answers are hidden until the user
clicks a "Show Answer" control.

Quiz management also supports lettered labels (A. B. C. D.) for multiple-choice answers.

#### Scaffolding

An instructional strategy where support is provided to learners at the beginning of a learning process and then gradually removed as they gain confidence and competence. 

Scaffolding allows students to build on what they already know and reach higher levels of understanding.

#### Search

Search is a feature, created as part of the build process, that finds the pages matching a reader's query.

The mkdocs material theme generates a reverse index: a JSON (JavaScript Object Notation, a plain-text data format)
file that maps each keyword to the pages containing it. The search feature uses this file to list the pages that match
the search keywords.

Note that standard mkdocs search matches keywords and does not use embeddings, so it does not
retrieve or rank documents by semantic similarity; it finds related pages only when they share words.

#### Semantic Search

A retrieval method that interprets the contextual meaning of search terms to improve the relevance of search results.

Intelligent textbooks frequently create [embeddings](#embedding) for words, phrases, paragraphs and pages so you can quickly find similar content.

#### Social Media Previews

Summaries automatically generated when a webpage link is shared on social platforms, often including a title, description, and image.

Page metadata supplies the title, description, and image used in these previews when a link is shared on social media platforms.

Social media preview increases the appeal and clarity of shared links, encouraging users to engage with and disseminate the documentation.

Social media previews can be generated automatically by a configuration in the mkdocs.yml file.

#### Table of Contents

A structured list of document sections and headings, enabling users to locate and navigate to specific topics easily.

It is typically displayed as a hierarchical listing in a sidebar or at the start of a page.
*Helps users quickly understand the scope of the content and jump directly to areas of interest.*

#### Vis.js

A JavaScript library for rendering graph networks.

Vis.js is used to view and edit [learning graphs](#learning-graph) used by intelligent textbooks.

#### Website Analytics

The process of analyzing who is coming to your website, when they are visiting and what pages are being accessed.

The mkdocs material system provides a way to integrate free Google Analytics by adding four lines to your mkdocs.yml file.

See: Tutorial on Google Analytics (a page of the retired MkDocs build; not in this repository)

## Knowledge Graph Terms

#### Terms List {#terms-list}

A simple inventory of business terms and acronyms without definitions. This is typically the starting point - a raw collection of vocabulary used within an organization, often inconsistently defined or understood by different teams.

#### Business Glossary {#business-glossary}

Terms with informal, human-readable definitions. These definitions may vary between departments and lack the precision needed for technical implementation, but they establish a common understanding of business vocabulary.

#### Controlled Vocabulary {#controlled-vocabulary}

Terms with approved, standardized definitions following ISO-11179 naming conventions. Each term has a single, authoritative definition that everyone in the organization agrees to use, reducing ambiguity and improving communication.

#### Taxonomy {#taxonomy}

A hierarchical classification system where terms have broader/narrower relationships. This creates a tree-like structure showing how concepts relate in terms of generalization and specialization, making it easier to navigate and understand the conceptual landscape.

#### Ontology {#ontology}

A formal representation of concepts with more detailed relationships including synonyms, related terms, and part-whole relationships. This richer structure captures the complexity of how business concepts interconnect beyond simple hierarchies.

#### Semantic Ontology {#semantic-ontology}

All relationships between terms have formally approved types with clear semantics. Each connection has a defined meaning (e.g., 'partOf', 'causedBy', 'requires'), enabling precise logical reasoning about concepts and their relationships.

#### Knowledge Graph {#knowledge-graph}

A formal, typed graph of concepts optimized for graph traversal algorithms. This structure enables powerful queries and analytics, allowing you to discover insights by exploring paths and patterns across interconnected concepts.

#### Enterprise Knowledge Graph (EKG) {#enterprise-knowledge-graph}

Concepts used consistently by both people and AI agents across the entire enterprise, governed by a central data governance process. With consistent adoption, this supports organizational alignment and enterprise-wide analytics and decision-making.

#### AI Enhanced EKG {#ai-enhanced-ekg}

An EKG that is continuously created, enhanced, and monitored by AI agents. Machine learning systems can propose new relationships and improvements and help monitor quality; how much this speeds up knowledge graph evolution, and whether quality holds, must be evaluated in each case.

#### Real-Time EKG {#real-time-ekg}

A dynamic knowledge graph that continuously monitors products, customers, sales, competitors, and market changes. This lets AI agents provide timely insights and recommendations, as fresh as data ingestion and processing allow, supporting faster response to market opportunities and threats.
