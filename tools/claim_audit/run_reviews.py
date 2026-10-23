#!/usr/bin/env python3
"""Drive the claim-audit review -> meta-review loop, one model call at a time.

Config: audit/runner.yml.  Logs: audit/runs/run-log.jsonl.  See PROTOCOL.md.
Exit codes: 0 nothing pending (or a requested limit/STOP was reached), 3 stopped on failures.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claim_audit as ca  # noqa: E402

PROMPTS = Path(__file__).resolve().parent / "prompts"
META_SPLIT = 60


# --------------------------------------------------------------------------- parsing
def extract_json_object(text: str):
    """First top-level JSON object in text (tolerates ```json fences and prose); prefers one with 'results'."""
    dec = json.JSONDecoder()
    first = None
    i = text.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
        except ValueError:
            i = text.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            if "results" in obj:
                return obj
            if first is None:
                first = obj
        i = text.find("{", end)
    return first


def parse_output(stdout: str) -> tuple[str, dict]:
    """Return (model text, usage dict). Claude --output-format json wraps text in .result."""
    usage: dict = {}
    text = stdout
    try:
        w = json.loads(stdout)
    except ValueError:
        w = None
    if isinstance(w, dict) and "result" in w:
        text = w["result"] if isinstance(w["result"], str) else json.dumps(w["result"])
        u = w.get("usage") or {}
        usage = {
            "input_tokens": u.get("input_tokens"),
            "output_tokens": u.get("output_tokens"),
            "total_cost_usd": w.get("total_cost_usd"),
        }
    else:
        m = re.search(r"tokens used\s*[:\n]?\s*([\d,]+)", stdout, re.I)
        if m:
            usage = {"tokens_used": int(m.group(1).replace(",", ""))}
    return text, usage


def usage_tokens(usage: dict) -> int:
    return int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0) + int(usage.get("tokens_used") or 0)


# --------------------------------------------------------------------------- runner
class Runner:
    def __init__(self, au: ca.Audit, cfg: dict, args):
        self.au, self.cfg, self.args = au, cfg, args
        self.runs = au.audit / "runs"
        self.runs.mkdir(parents=True, exist_ok=True)
        self.consec_fail = 0
        self.fail_reason = ""
        self.skipped: set[frozenset] = set()
        self.tokens = self._logged_tokens()

    # -- logging
    def _logged_tokens(self) -> int:
        return sum(usage_tokens(r.get("usage") or {}) for r in ca.read_jsonl(self.runs / "run-log.jsonl"))

    def log(self, **kw):
        kw["ts"] = ca.now_ts()
        ca.append_jsonl(self.runs / "run-log.jsonl", [kw])
        self.tokens += usage_tokens(kw.get("usage") or {})

    # -- planning helpers (call ca.cmd_plan quietly)
    def plan(self, role: str) -> list[Path]:
        before = set((self.au.audit / "batches").glob("*.json")) if (self.au.audit / "batches").exists() else set()
        self.au._units = None
        ns = argparse.Namespace(
            checks=",".join(self.cfg["review"]["checks"]), max_words=int(self.cfg["review"]["max_words"]), paths=None, role=role
        )
        with contextlib.redirect_stdout(io.StringIO()):
            ca.cmd_plan(self.au, ns)
        after = set((self.au.audit / "batches").glob("*.json"))
        return sorted(after - before)

    def pending_review_pairs(self) -> int:
        self.au._units = None
        ids = [canon for canon in self.cfg["review"]["checks"]]
        return sum(1 for s in self.au.pair_states(ids) if s["status"] == "pending")

    def reviewed_pairs(self) -> int:
        self.au._units = None
        ids = [c for c in self.cfg["review"]["checks"]]
        return sum(1 for s in self.au.pair_states(ids) if s["status"] == "reviewed")

    # -- prompt
    def build_prompt(self, role: str, batch_path: Path) -> str:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        checks_text = "\n".join(f"- {c['id']} (v{c['version']}) {c['title']}: {c['instructions']}" for c in batch["checks"])
        tpl = (PROMPTS / f"{role}.md").read_text(encoding="utf-8")
        reviewer = self.cfg[role]["reviewer"]
        for k, v in {
            "{reviewer}": reviewer, "{repo}": str(self.au.root), "{batch_path}": str(batch_path.resolve()),
            "{batch_id}": batch["batch_id"], "{checks_text}": checks_text,
        }.items():
            tpl = tpl.replace(k, v)
        return tpl

    # -- model call
    def call(self, role: str, prompt: str):
        c = self.cfg[role]
        cmd = [a.replace("{repo}", str(self.au.root)).replace("{prompt}", prompt) for a in c["command"]]
        full = list(self.cfg.get("wrapper") or []) + cmd
        stdin = prompt if c.get("prompt_via") == "stdin" else None
        t0 = time.time()
        try:
            p = subprocess.run(
                full, input=stdin, stdin=None if stdin is not None else (subprocess.DEVNULL if c.get("stdin_devnull") else None),
                capture_output=True, text=True, cwd=self.au.root, timeout=int(c.get("timeout_s", 1800)),
            )
            return p.returncode, p.stdout, p.stderr, time.time() - t0
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            return 124, out, "timeout", time.time() - t0

    # -- one batch: call, parse, record, retry once
    def run_batch(self, role: str, batch_path: Path) -> bool:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        bid = batch["batch_id"]
        reviewer = self.cfg[role]["reviewer"]
        prompt = self.build_prompt(role, batch_path)
        raw_path = self.runs / f"{bid}.raw.txt"
        raw_path.write_text("", encoding="utf-8")
        retry = False
        errs: list[str] = []
        for attempt in (0, 1):
            if (self.au.audit / "STOP").exists():
                return False
            p = prompt
            if attempt == 1:
                retry = True
                p = prompt + "\n\nYour previous output was rejected with these errors:\n" + "\n".join(f"- {e}" for e in errs) + (
                    "\n\nFix these and output the full corrected JSON object only.\n"
                )
            code, out, err, el = self.call(role, p)
            with raw_path.open("a", encoding="utf-8") as f:
                f.write(f"=== attempt {attempt} exit {code} ===\n{out}\n--- stderr ---\n{err}\n")
            text, usage = parse_output(out)
            if not usage:  # codex prints "tokens used\n<n>" on stderr
                usage = parse_output(err or "")[1]
            recorded = False
            data = extract_json_object(text) if code == 0 else None
            if data is None:
                errs = [f"exit code {code}" if code else "no JSON object found in output"]
            else:
                data.setdefault("batch_id", bid)
                data.setdefault("reviewer", reviewer)
                data.setdefault("role", role)
                (self.runs / f"{bid}.results.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
                recs, errs = ca.validate_results(self.au, data)
                if not errs:
                    ca.append_jsonl(self.au.audit / "ledger.jsonl", recs)
                    recorded = True
            self.log(
                batch_id=bid, role=role, reviewer=reviewer, units=len(batch["units"]), pairs=len(batch.get("pairs", [])),
                exit_code=code, elapsed_s=round(el, 1), recorded=recorded, retry=retry, usage=usage,
                **({} if recorded else {"errors": errs[:10]}),
            )
            if recorded:
                self.consec_fail = 0
                return True
        self.consec_fail += 1
        self.fail_reason = f"batch {bid} failed twice: " + "; ".join(errs[:3])
        print(f"FAILED {self.fail_reason}", file=sys.stderr)
        return False

    # -- meta
    def split_meta(self, paths: list[Path]) -> list[Path]:
        out: list[Path] = []
        for p in paths:
            b = json.loads(p.read_text(encoding="utf-8"))
            if len(b["pairs"]) <= META_SPLIT:
                out.append(p)
                continue
            p.unlink()
            by_unit: dict = {}
            for pr in b["pairs"]:
                by_unit.setdefault(pr[0], []).append(pr)
            chunk, n = [], 0
            groups = []
            for uid, prs in by_unit.items():
                if chunk and n + len(prs) > META_SPLIT:
                    groups.append(chunk)
                    chunk, n = [], 0
                chunk.append(uid)
                n += len(prs)
            if chunk:
                groups.append(chunk)
            for g in groups:
                gs = set(g)
                pairs = [pr for pr in b["pairs"] if pr[0] in gs]
                keys = {tuple(pr) for pr in pairs}
                nb = dict(b)
                nb["batch_id"] = ca.next_batch_id(self.au, "meta")
                nb["pairs"] = pairs
                nb["units"] = [u for u in b["units"] if u["unit_id"] in gs]
                nb["reviews"] = [r for r in b["reviews"] if (r["unit_id"], r["check_id"]) in keys]
                cids = {pr[1] for pr in pairs}
                nb["checks"] = [c for c in b["checks"] if c["id"] in cids]
                np_ = self.au.audit / "batches" / f"{nb['batch_id']}.json"
                np_.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
                out.append(np_)
        return out

    def run_meta(self) -> bool:
        """Meta-review everything currently 'reviewed'. Returns False if a stop condition hit."""
        if self.reviewed_pairs() == 0:
            return True
        paths = self.split_meta(self.plan("meta"))
        for p in paths:
            if (self.au.audit / "STOP").exists():
                return False
            if self.args.max_tokens and self.tokens >= self.args.max_tokens:
                return False
            b = json.loads(p.read_text(encoding="utf-8"))
            if frozenset(map(tuple, b["pairs"])) in self.skipped:
                continue
            ok = self.run_batch("meta", p)
            if not ok:
                self.skipped.add(frozenset(map(tuple, b["pairs"])))
                if self.consec_fail >= 2:
                    return False
        return True

    # -- main loop
    def loop(self) -> int:
        a = self.args
        every = a.meta_every or int(self.cfg["meta"].get("every_n_review_batches", 4))
        attempted = since_meta = 0
        while True:
            if (self.au.audit / "STOP").exists():
                print("STOP file present; stopping")
                return 0
            if a.max_tokens and self.tokens >= a.max_tokens:
                print(f"max-tokens reached ({self.tokens})")
                return 0
            if a.max_batches and attempted >= a.max_batches:
                break
            if self.consec_fail >= 2:
                print(f"two consecutive failures: {self.fail_reason}", file=sys.stderr)
                return 3
            paths = self.plan("review")
            todo = None
            for p in paths:
                b = json.loads(p.read_text(encoding="utf-8"))
                if frozenset(u["unit_id"] for u in b["units"]) not in self.skipped:
                    todo = (p, b)
                    break
            for p in paths:
                if todo is None or p != todo[0]:
                    p.unlink()
            if todo is None:
                if paths:
                    print(f"only failed batches remain: {self.fail_reason}", file=sys.stderr)
                    return 3
                break
            attempted += 1
            ok = self.run_batch("review", todo[0])
            if ok:
                since_meta += 1
            else:
                self.skipped.add(frozenset(u["unit_id"] for u in todo[1]["units"]))
            if self.consec_fail >= 2:
                print(f"two consecutive failures: {self.fail_reason}", file=sys.stderr)
                return 3
            if since_meta >= every:
                since_meta = 0
                if not self.run_meta():
                    if self.consec_fail >= 2:
                        print(f"two consecutive failures: {self.fail_reason}", file=sys.stderr)
                        return 3
                    return 0
        # end: final meta pass
        if not (self.au.audit / "STOP").exists():
            if not self.run_meta():
                return 3 if self.consec_fail >= 2 else 0
        if self.consec_fail >= 2:
            return 3
        if a.max_batches and attempted >= a.max_batches:
            return 0
        left = self.pending_review_pairs() + self.reviewed_pairs()
        if left and self.skipped:
            print(f"{left} model pairs left after skipped batches", file=sys.stderr)
            return 3
        return 0


def main(argv=None, root: Path | None = None, tracked: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--max-batches", type=int, default=0, help="stop after N review batches (0 = no limit)")
    ap.add_argument("--max-tokens", type=int, default=0, help="stop when logged usage reaches T tokens (0 = no limit)")
    ap.add_argument("--meta-every", type=int, default=0, help="override meta.every_n_review_batches")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    r = Path(args.root) if args.root else (root or Path(__file__).resolve().parents[2])
    au = ca.Audit(r, tracked)
    cfg = yaml.safe_load(Path(args.config or au.audit / "runner.yml").read_text(encoding="utf-8"))
    cfg["review"]["checks"] = [ca.canon_check_id(c) for c in cfg["review"]["checks"]]
    rn = Runner(au, cfg, args)
    if args.dry_run:
        paths = rn.plan("review")
        if not paths:
            print("nothing pending")
            return 0
        print(f"next batch: {paths[0]}  ({len(paths)} batches planned)")
        print("----- prompt -----")
        print(rn.build_prompt("review", paths[0]))
        for p in paths:
            p.unlink()
        return 0
    return rn.loop()


if __name__ == "__main__":
    sys.exit(main())
