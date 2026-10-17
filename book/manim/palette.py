"""Book palette: one fixed meaning per colour, shared by the CSS and the Manim scenes.

The same hex values appear as CSS variables in
website/client/src/book/book.css (--book-allowed, ...); tests/test_book_media.py
checks that they agree. Colour is never the only carrier of meaning: scenes also
use marks and labels.
"""

# meaning -> hex, for the dark (screen) and light (print) themes
DARK = {
    "bg": "#0f1115",
    "fg": "#e6e8ee",
    "muted": "#a3a9b8",
    "line": "#2c313c",
    "allowed": "#3fb68b",
    "excluded": "#8a8f98",
    "evidence": "#4c8dff",
    "breach": "#e5534b",
    "unknown": "#e3a33b",
}

LIGHT = {
    "bg": "#ffffff",
    "fg": "#1b1d22",
    "muted": "#5a6070",
    "line": "#d9dce3",
    "allowed": "#1e8e66",
    "excluded": "#6b7280",
    "evidence": "#2563eb",
    "breach": "#c62828",
    "unknown": "#b7791f",
}

MEANINGS = ("allowed", "excluded", "evidence", "breach", "unknown")
