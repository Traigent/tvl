# The TVL book: sources and licences

*TVL, Visually: specifying what an AI agent must do.* A short, visual book for
engineers who build AI agents. It is served at `/book` on the TVL website and
built into a downloadable PDF from the same source.

## Where things are

| What | Where |
|---|---|
| Chapters (MDX) | `website/client/src/book/chapters/` |
| Components | `website/client/src/book/components/` |
| Examples and their expected results | `spec/examples/book/` with `manifest.yaml`; run by `tests/test_book_examples.py` |
| Runnable support-bot project (synthetic data, simulated bot, gate decisions) | `book/support-bot/`; run by `tests/test_book_support_bot.py` |
| Animation scenes (Manim) | `book/manim/scenes/`, palette in `book/manim/palette.py` |
| Rendered media and hashes | `website/client/public/book/media/`, `book/manim/media-manifest.json` |
| PDF build and checks | `website/scripts/build_book_pdf.mjs`, `check_book_pdf.mjs` (`pnpm book:pdf`, `pnpm book:check`) |

Rendering animations stays local (`book/manim/render.sh`); CI recomputes the
source hashes (`tests/test_book_media.py`) and fails if a scene changed without
a re-render.

## Licences

- **Prose and figures** (the MDX chapters, rendered figures and the PDF) are
  licensed under CC-BY-4.0. The paths are listed in `LICENSE-content`.
- **Components** (the React code under `website/client/src/book/`) and
  **scene programs** (`book/manim/`) are licensed under Apache-2.0, like the rest
  of the repository.
- **Fonts** (Source Serif 4, Inter, JetBrains Mono) are licensed under the SIL
  Open Font License 1.1. Each font's `OFL.txt` sits next to its files in
  `website/client/public/fonts/`.
- **Animations are original, made with Manim Community Edition (MIT). No
  material from 3Blue1Brown's videos is used.** Nothing is copied, adapted or
  traced from `3b1b/videos` or its characters; we copy the teaching method
  (one idea per animation, fixed colour meaning), not the material.
