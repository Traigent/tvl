"""Editor schemas must remain byte-identical to the authored grammar schemas."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("directory", [
    "vscode-tvl/schemas", "editor_shared/vscode/schemas",
    "website/client/public/schemas", "website/client/public/docs",
])
def test_editor_schema_copies_match_grammar(directory):
    copies = {path.name: path for path in (ROOT / directory).glob("*.json")}
    required = {"tvl.schema.json"}
    if directory in {"vscode-tvl/schemas", "editor_shared/vscode/schemas"}:
        required.add("tvl-pack.schema.json")
    assert required <= copies.keys()
    for name, path in copies.items():
        assert path.read_bytes() == (ROOT / "spec/grammar" / name).read_bytes(), path


def _sync_module():
    """Load the website's canonical-resource sync script as a module.

    The test asserts against the script's own mapping rather than
    re-deriving it from filenames. Re-derivation is how this guard went
    blind: it globbed ``*.json``, so ``tvl.ebnf`` -- which is mirrored into
    the same directories -- could never be compared, and the published
    grammar drifted a full TVL version behind the published schema without
    a single test going red.
    """
    import importlib.util

    path = ROOT / "website" / "scripts" / "sync_canonical_resources.py"
    spec = importlib.util.spec_from_file_location("tvl_sync_canonical", path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_canonical_website_copy_is_in_sync():
    """Every file the sync script publishes must already match its source.

    This covers all mirrored file types -- ``.ebnf`` and ``.md`` as well as
    ``.json`` -- because it asks the script what it would write instead of
    guessing which extensions matter.
    """
    mismatches = _sync_module().run_sync(check=True)
    assert mismatches == [], (
        "website/client/public is stale; run "
        "`python website/scripts/sync_canonical_resources.py`:\n  "
        + "\n  ".join(mismatches)
    )


def test_the_sync_guard_covers_more_than_json():
    """The guard above must not silently narrow back to JSON.

    A regression here would not fail the test above -- a narrowed mapping
    simply checks fewer files and still returns no mismatches -- so the
    coverage itself is asserted.
    """
    pairs = _sync_module().iter_copy_pairs()
    published = {destination.suffix for _, destination in pairs}
    assert {".ebnf", ".md", ".json"} <= published, published
    ebnf = {d.as_posix() for _, d in pairs if d.suffix == ".ebnf"}
    assert len(ebnf) == 2, ebnf
