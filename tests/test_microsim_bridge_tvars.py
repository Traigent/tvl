"""tvl-microsim-bridge reads ``tvars`` (current TVL), not only the legacy ``configuration_space``."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvl_tools.microsim_bridge.bridge import build_presets  # noqa: E402

MODULE = """\
tvl:
  module: corp.rag.orientation
tvl_version: "1.5"
tvars:
  - name: retriever_top_k
    type: int
    domain: {range: [8, 64], resolution: 4}
  - name: rerank_weight
    type: float
    domain: {range: [0.1, 0.9], resolution: 0.05}
  - name: model
    type: enum[str]
    domain: {set: [a, b]}
"""


def test_tvars_produce_defaults_sliders_and_presets(tmp_path):
    spec = tmp_path / "spec.yml"
    spec.write_text(MODULE, encoding="utf-8")
    payload = build_presets(spec)
    assert payload["source"] == {"spec_id": "corp.rag.orientation", "spec_version": "1.5"}
    assert payload["sliders"]["retriever_top_k"] == {"min": 8.0, "max": 64.0, "step": 4.0}
    assert payload["sliders"]["rerank_weight"] == {"min": 0.1, "max": 0.9, "step": 0.05}
    assert set(payload["defaults"]) == {"retriever_top_k", "rerank_weight"}  # the str enum is no slider
    assert payload["defaults"]["retriever_top_k"] == 36
    assert set(payload["presets"]) == {"baseline", "latency-spike", "budget-shift"}
    assert payload["presets"]["latency-spike"]["retriever_top_k"] != payload["defaults"]["retriever_top_k"]


def test_legacy_configuration_space_still_read(tmp_path):
    spec = tmp_path / "legacy.yml"
    spec.write_text(
        "spec: {id: old, version: '0.1.0'}\nconfiguration_space:\n  retriever_top_k: {type: integer, range: [8, 64]}\n",
        encoding="utf-8",
    )
    payload = build_presets(spec)
    assert payload["source"]["spec_id"] == "old"
    assert "retriever_top_k" in payload["defaults"]
