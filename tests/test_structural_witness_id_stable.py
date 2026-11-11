"""Issue #250: RepairCandidateValidated.witnessId is a stable digest, not a salted hash()."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODULE = """\
tvl: {module: example.audit}
environment: {snapshot_id: "2026-10-01T00:00:00Z"}
evaluation_set: {dataset: example.eval}
tvars:
  - {name: mode, type: "enum[str]", domain: ["fast", "slow"]}
  - {name: k, type: int, domain: {set: [0, 3, 5]}}
constraints:
  structural:
    - expr: "k <= 1"
    - expr: "k >= 3"
objectives: [{name: quality, direction: maximize}]
promotion_policy: {dominance: epsilon_pareto, alpha: 0.05, min_effect: {quality: 0.01}}
"""

CANDIDATE = {"id": "rc-1", "edits": [{"before": "k <= 1", "after": "k <= 3"}]}


def _witness_id(module: Path, candidate: Path, seed: str) -> str:
    env = {
        **os.environ,
        "PYTHONHASHSEED": seed,
        "PYTHONPATH": os.pathsep.join([str(ROOT / "python"), str(ROOT)]),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "tvl_tools.tvl_check_structural.cli", str(module), "--json",
         "--candidate-file", str(candidate)],
        capture_output=True, text=True, env=env, cwd=ROOT, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    first = json.JSONDecoder().raw_decode(proc.stdout)[0]
    assert first["kind"] == "RepairCandidateValidated" and first["status"] == "sat"
    return first["witnessId"]


def test_witness_id_is_identical_across_hash_seeds(tmp_path: Path) -> None:
    module = tmp_path / "m.tvl.yml"
    module.write_text(MODULE, encoding="utf-8")
    candidate = tmp_path / "cand.json"
    candidate.write_text(json.dumps(CANDIDATE), encoding="utf-8")
    ids = {_witness_id(module, candidate, seed) for seed in ("1", "2", "3")}
    assert len(ids) == 1


def test_witness_id_is_a_sha256_of_the_canonical_witness() -> None:
    from tvl_tools.tvl_check_structural import cli as structural

    witness = {"mode": "fast", "k": "3"}
    canonical = json.dumps(witness, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    expected = "w-" + hashlib.sha256(canonical.encode("ascii")).hexdigest()[:16]
    assert structural._build_witness_id(witness) == expected
    assert structural._build_witness_id({"k": "3", "mode": "fast"}) == expected
    assert structural._build_witness_id({"mode": "fast", "k": "5"}) != expected


def test_witness_id_for_a_lone_surrogate_value_is_stable_and_does_not_crash(tmp_path: Path) -> None:
    # YAML "\ud800" loads as a lone surrogate, which UTF-8 cannot encode.
    module = tmp_path / "m.tvl.yml"
    module.write_text(MODULE.replace('domain: ["fast", "slow"]', 'domain: ["\\ud800"]'), encoding="utf-8")
    assert "\\ud800" in module.read_text(encoding="utf-8")
    candidate = tmp_path / "cand.json"
    candidate.write_text(json.dumps(CANDIDATE), encoding="utf-8")
    ids = {_witness_id(module, candidate, seed) for seed in ("1", "2")}
    assert len(ids) == 1


def test_witness_id_for_a_non_ascii_value_is_stable_and_pinned(tmp_path: Path) -> None:
    # Issue #250: the digest is over the ASCII-escaped canonical form, so a witness with "café"
    # has this id in every process. Earlier builds hashed the UTF-8 form and gave w-855f44b1144ca7ba.
    module = tmp_path / "m.tvl.yml"
    module.write_text(MODULE.replace('domain: ["fast", "slow"]', 'domain: ["caf\\u00e9", "slow"]'), encoding="utf-8")
    candidate = tmp_path / "cand.json"
    candidate.write_text(json.dumps(CANDIDATE), encoding="utf-8")
    ids = {_witness_id(module, candidate, seed) for seed in ("1", "2", "3")}
    assert ids == {"w-03700caa42b41dbc"}
