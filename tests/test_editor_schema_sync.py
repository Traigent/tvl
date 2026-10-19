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
