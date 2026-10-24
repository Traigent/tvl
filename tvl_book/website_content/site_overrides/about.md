# About This Site

> **Archived page.** Written for a retired MkDocs build of the TVL site and not published on tvl-lang.org; the site
> book lives in [`website/client/src/book/chapters/`](../../../website/client/src/book/chapters/). Kept as source notes.

This site accompanied Traigent Labs' TVL Intelligent Textbook, a guide to the Tuned Variables Language (TVL), TVO
(the TVL Optimizer in the Traigent platform), and workflows that help teams take AI agents toward production. We
built it so practitioners can move from concept to implementation without jumping between repos, docs, and slide decks.

## How the Site Is Organized

- **TVL Chapters** mirror the LaTeX book and provide a narrative foundation.
- **Labs & Walkthroughs** ([labs](../book/labs.md), [walkthrough](../book/walkthrough.md)) point to runnable examples in
  the [`Traigent/examples`](https://github.com/nimrodbusany/Traigent/tree/master/examples) directory.
- **Playground** content highlights the Streamlit control center for monitoring optimization runs.
- **Reference Sections** collect authoring workflows, prompt libraries, and glossary entries that
  support day-to-day operations.

The former site build used MkDocs Material for its navigation, built-in search, and theme system. All pages
are stored in version control so engineers can author content the same way they ship code.

## From Book to Practice

TVL isn't just theory. Every chapter links to concrete assets:

- TVL specs under `tvl_book/examples/`
- CLI commands that exercise `tvl_tools` plug-ins
- Integration manifests that wire Triagent, TVO, and DVL together
- Future labs sourced from `Traigent/examples/core` and `Traigent/playground`

Treat this site as your control center: read a chapter, run the associated script, and capture notes or
playground logs alongside the specs you promote.

## Contributing

We welcome pull requests that improve clarity, add new labs, or document emerging best practices. Open an
issue if you have a pattern worth documenting or want to contribute a walkthrough.
