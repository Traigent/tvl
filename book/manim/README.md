# Rendering the book's animations

The scenes in `scenes/` are original Manim Community Edition programs (MIT). They
render into `website/client/public/book/media/<scene>/`: a WebM and an MP4 for the
web (dark theme), a poster PNG, and the print frames (light theme) that the PDF
shows as a frame sequence. `render.sh` does the rendering and then records the
hashes in `media-manifest.json`.

Rendering is local only. CI does not render; `tests/test_book_media.py` recomputes
the source and palette hashes and fails when a scene changed without a re-render.

## What you need

- Python 3.11 (the current media were rendered with 3.11.15 and `manim==0.22.0`, as
  pinned in `requirements.txt`).
- The pango and cairo **development** files. Manim's text engine, ManimPango 0.7.0,
  has no prebuilt wheel for Linux, so pip compiles it, and the compiler needs the
  pango, cairo and pkg-config files.
- ffmpeg is not needed separately: Manim writes video through PyAV, whose wheel
  bundles it.

On a machine where you can install system packages, install the pango and cairo
development packages (on Debian or Ubuntu: `libpango1.0-dev libcairo2-dev
pkg-config`) and skip to "Install Manim".

## Without system headers: a conda-forge prefix

If you cannot install system packages, put pango, cairo and pkg-config in a
conda-forge prefix with micromamba. Nothing is installed system-wide.

```bash
# 1. Get micromamba (a single static binary).
mkdir -p ~/micromamba && cd ~/micromamba
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba

# 2. Create a prefix with the libraries and their headers.
export MANIM_LIB_PREFIX="$HOME/micromamba/manim-libs"
~/micromamba/bin/micromamba create -y -p "$MANIM_LIB_PREFIX" -c conda-forge pango cairo pkg-config
```

## Install Manim

From the repository root:

```bash
python3.11 -m venv book/manim/.venv

# With a conda-forge prefix, point the build at it. Skip these two lines if the
# development packages are installed system-wide.
export PATH="$MANIM_LIB_PREFIX/bin:$PATH"                   # its pkg-config
export PKG_CONFIG_PATH="$MANIM_LIB_PREFIX/lib/pkgconfig"    # its .pc files

book/manim/.venv/bin/python -m pip install -r book/manim/requirements.txt
```

`book/manim/.venv` is ignored by git.

Check the build:

```bash
LD_LIBRARY_PATH="$MANIM_LIB_PREFIX/lib" book/manim/.venv/bin/python \
  -c "import manimpango; print(manimpango.__version__, manimpango.pango_version())"
```

## Render

```bash
MANIM_LIB_PREFIX="$HOME/micromamba/manim-libs" book/manim/render.sh
```

`render.sh` honours `MANIM_LIB_PREFIX`: when it is set, the script puts
`$MANIM_LIB_PREFIX/lib` first on `LD_LIBRARY_PATH`, so ManimPango loads the pango
and cairo it was compiled against. Leave it unset when the libraries are
system-wide.

The script renders into a temporary directory, copies the assets into
`website/client/public/book/media/<scene>/`, and runs `build_media_manifest.py`,
which writes the hashes, the Manim version, the render command and the provenance
into `media-manifest.json`. Commit the media and the manifest together.

## Rules for scenes

- One idea per scene, and motion that shows a change.
- Colours come from `palette.py` only. Each colour has one meaning (allowed,
  excluded, evidence, breach, unknown), shared with the book's CSS. Colour is never
  the only carrier of meaning: use marks and labels too.
- Original work only. Nothing is copied, adapted or traced from 3Blue1Brown's
  videos, code or characters.
- Each scene saves 2 to 4 light-theme snapshots (set `BOOK_THEME=light` and
  `BOOK_SNAP_DIR`) for the print frame sequence, and one dark snapshot as the poster.
