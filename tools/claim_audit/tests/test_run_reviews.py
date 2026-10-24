import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import claim_audit as ca  # noqa: E402
import run_reviews as rr  # noqa: E402

FILES = {
    "a.md": "# Title\n\nFirst paragraph has quite enough words.\n\nSecond paragraph also has enough words.\n",
    "b.md": "Third paragraph lives in another file ok.\n\nFourth paragraph lives in another file ok.\n",
}
# meta_sample_mod 1: every pass is sampled, so meta calls do not depend on record-id hashes
# (record_id hashes the batch_id, which contains a timestamp).
CHECKS = {"checks": [
    {"id": "TVL-C01", "version": 1, "kind": "model", "applies_to": ["prose", "code", "table", "heading"], "title": "Accuracy", "instructions": "x", "meta_sample_mod": 1},
    {"id": "TVL-C05", "version": 1, "kind": "model", "applies_to": ["prose", "table", "heading"], "title": "Clarity", "instructions": "y", "meta_sample_mod": 1},
]}


def setup(tmp_path, mode, max_words=8, every=2, meta_mode=None, sample_mod=1):
    for p, t in FILES.items():
        (tmp_path / p).write_text(t)
    a = tmp_path / "audit"
    a.mkdir()
    (a / "corpus.yml").write_text(yaml.safe_dump({"include": ["*.md"], "exclude": []}))
    chk = json.loads(json.dumps(CHECKS))
    for c in chk["checks"]:
        c["meta_sample_mod"] = sample_mod
    (a / "checks.yml").write_text(yaml.safe_dump(chk))
    (a / "ledger.jsonl").write_text("")
    fake = str(HERE / "fake_model.py")
    cfg = {
        "review": {"reviewer": "sonnet", "checks": ["C01", "C05"], "max_words": max_words,
                   "command": [sys.executable, fake, mode], "prompt_via": "stdin", "timeout_s": 60},
        "meta": {"reviewer": "sol", "every_n_review_batches": every,
                 "command": [sys.executable, fake, meta_mode or "ok", "{prompt}"], "prompt_via": "arg", "stdin_devnull": True, "timeout_s": 60},
        "wrapper": [],
    }
    (a / "runner.yml").write_text(yaml.safe_dump(cfg))
    return ca.Audit(tmp_path, tracked=sorted(FILES))


def run(tmp_path, *extra, monkeypatch=None):
    monkeypatch.setenv("FAKE_STATE", str(tmp_path / "state.txt"))
    return rr.main(["--root", str(tmp_path)] + list(extra), tracked=sorted(FILES))


def log(tmp_path):
    return ca.read_jsonl(tmp_path / "audit" / "runs" / "run-log.jsonl")


def statuses(tmp_path):
    au = ca.Audit(tmp_path, tracked=sorted(FILES))
    return {s["status"] for s in au.pair_states(["TVL-C01", "TVL-C05"])}


def test_happy_path_completes_everything(tmp_path, monkeypatch):
    setup(tmp_path, "ok", max_words=100)
    assert run(tmp_path, monkeypatch=monkeypatch) == 0
    assert statuses(tmp_path) == {"closed"}
    roles = [r["role"] for r in log(tmp_path)]
    assert roles[0] == "review" and all(r["recorded"] for r in log(tmp_path))
    assert (tmp_path / "audit" / "runs" / f"{log(tmp_path)[0]['batch_id']}.raw.txt").exists()
    assert (tmp_path / "audit" / "runs" / f"{log(tmp_path)[0]['batch_id']}.results.json").exists()


def test_retry_then_success(tmp_path, monkeypatch):
    setup(tmp_path, "bad_then_ok", max_words=100, meta_mode="ok")
    assert run(tmp_path, "--max-batches", "1", monkeypatch=monkeypatch) == 0
    rev = [r for r in log(tmp_path) if r["role"] == "review"]
    assert [r["retry"] for r in rev] == [False, True]
    assert [r["recorded"] for r in rev] == [False, True]
    assert "errors" in rev[0]


def test_two_failures_skip_and_exit3(tmp_path, monkeypatch):
    setup(tmp_path, "bad", max_words=8)
    assert run(tmp_path, monkeypatch=monkeypatch) == 3
    assert "pending" in statuses(tmp_path)
    assert not any(r["recorded"] for r in log(tmp_path))
    assert len(log(tmp_path)) == 4  # two batches x (call + retry)


def test_garbage_output_fails(tmp_path, monkeypatch):
    setup(tmp_path, "garbage", max_words=100)
    assert run(tmp_path, monkeypatch=monkeypatch) == 3


def test_meta_cadence(tmp_path, monkeypatch):
    setup(tmp_path, "ok", max_words=8, every=2)
    assert run(tmp_path, monkeypatch=monkeypatch) == 0
    roles = [r["role"] for r in log(tmp_path)]
    first_meta = roles.index("meta")
    assert roles[:first_meta].count("review") == 2
    assert statuses(tmp_path) == {"closed"}


def test_meta_every_override_and_max_batches(tmp_path, monkeypatch):
    setup(tmp_path, "ok", max_words=8, every=99)
    assert run(tmp_path, "--max-batches", "1", "--meta-every", "1", monkeypatch=monkeypatch) == 0
    roles = [r["role"] for r in log(tmp_path)]
    assert roles.count("review") == 1
    assert "pending" in statuses(tmp_path)


def test_stop_file(tmp_path, monkeypatch):
    setup(tmp_path, "ok", max_words=8)
    (tmp_path / "audit" / "STOP").write_text("")
    assert run(tmp_path, monkeypatch=monkeypatch) == 0
    assert log(tmp_path) == []


def test_max_tokens_and_claude_json(tmp_path, monkeypatch):
    setup(tmp_path, "claudejson", max_words=8, every=99)
    assert run(tmp_path, "--max-tokens", "15", monkeypatch=monkeypatch) == 0
    lg = log(tmp_path)
    assert lg[0]["usage"]["input_tokens"] == 10 and lg[0]["usage"]["total_cost_usd"] == 0.01
    assert len([r for r in lg if r["role"] == "review"]) == 1


def test_dry_run_calls_no_model(tmp_path, monkeypatch, capsys):
    setup(tmp_path, "ok", max_words=100)
    assert run(tmp_path, "--dry-run", monkeypatch=monkeypatch) == 0
    out = capsys.readouterr().out
    assert "Batch file (absolute path" in out and "TVL-C01" in out
    assert log(tmp_path) == []
    assert not (tmp_path / "state.txt").exists()


def test_extract_json_from_fence_and_prose():
    assert rr.extract_json_object('x {"a":1} y ```json\n{"results": [], "k": 2}\n```') == {"results": [], "k": 2}
    assert rr.extract_json_object("no json here") is None
    assert rr.parse_output('{"result": "hi {\\"results\\": []}", "usage": {"input_tokens": 3, "output_tokens": 4}}')[1]["output_tokens"] == 4
    assert rr.parse_output("done\ntokens used\n12,345")[1] == {"tokens_used": 12345}


def test_codex_usage_from_stderr(tmp_path, monkeypatch):
    setup(tmp_path, "ok", max_words=100)
    import subprocess
    real = subprocess.run

    def fake_run(cmd, **kw):
        p = real(cmd, **kw)
        if "{prompt}" in str(kw) or p.returncode != 0:
            return p
        return subprocess.CompletedProcess(p.args, p.returncode, p.stdout.split("tokens used")[0], p.stdout.split("tokens used")[-1].join(["tokens used", ""]) if "tokens used" in p.stdout else "")

    monkeypatch.setattr(rr.subprocess, "run", fake_run)
    run(tmp_path, "--max-batches", "1", "--meta-every", "1", monkeypatch=monkeypatch)
    assert any((r.get("usage") or {}).get("tokens_used") == 1234 for r in log(tmp_path))


def test_resample_only_loop(tmp_path, monkeypatch):
    # huge mod: the normal run closes every pass by auto-meta and makes no meta call
    setup(tmp_path, "ok", max_words=100, sample_mod=10**9)
    assert run(tmp_path, monkeypatch=monkeypatch) == 0
    assert [r["role"] for r in log(tmp_path)].count("meta") == 0
    n_before = len(log(tmp_path))
    assert run(tmp_path, "--resample", "C01", monkeypatch=monkeypatch) == 0
    new = log(tmp_path)[n_before:]
    assert new and all(r["role"] == "meta" and r["recorded"] for r in new)  # no review batches
    au = ca.Audit(tmp_path, tracked=sorted(FILES))
    c01 = [s for s in au.pair_states(["TVL-C01"])]
    assert c01 and all(s["resampled"] and s["meta"]["reviewer"] == "sol" for s in c01)
    c05 = au.pair_states(["TVL-C05"])
    assert all(s["meta"]["reviewer"] == "sampling" and not s["resampled"] for s in c05)
    # idempotent: nothing left to resample
    n = len(log(tmp_path))
    assert run(tmp_path, "--resample", "C01", monkeypatch=monkeypatch) == 0
    assert len(log(tmp_path)) == n
