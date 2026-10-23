#!/usr/bin/env python3
"""TVL claim audit: prove every paragraph was checked by every registered check.

See PROTOCOL.md next to this file.  Stdlib + PyYAML only.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any

import yaml

KINDS = ("prose", "code", "table", "heading")
VERDICTS = ("pass", "issue", "na")
ROLES = ("review", "meta")
BANNED = [
    r"guaranteed",
    r"provably[\s-]+safe",
    r"shield\w*",
    r"self[\s-]?healing",
    r"kill[\s-]?switch",
    r"autonomous",
    r"runtime[\s-]+enforcement",
    r"circuit[\s-]?breaker",
]
BANNED_RE = re.compile(r"\b(?:" + "|".join(BANNED) + r")\b", re.I)
EXEMPT_RE = re.compile(r"banned|never use|avoid", re.I)
MIN_WORDS = 4


# --------------------------------------------------------------------------- helpers
def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def norm_text(s: str) -> str:
    return " ".join(s.split())


def now_ts() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{n}: invalid JSON: {e}")
    return out


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")


def glob_to_re(pat: str) -> re.Pattern:
    i, out = 0, ""
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pat.startswith("**", i):
            out += ".*"
            i += 2
        elif c == "*":
            out += "[^/]*"
            i += 1
        elif c == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(c)
            i += 1
    return re.compile("^" + out + "$")


def glob_match(path: str, pats: list[str]) -> bool:
    return any(glob_to_re(p).match(path) for p in pats)


def canon_check_id(cid: str) -> str:
    cid = cid.strip()
    return cid if cid.upper().startswith("TVL-") else "TVL-" + cid.upper()


# --------------------------------------------------------------------------- unit parsing
def _mk(kind: str, start: int, end: int, lines: list[str], hp: list[str]) -> dict:
    text = "\n".join(lines).strip("\n")
    return {"kind": kind, "start_line": start, "end_line": end, "text": text, "heading_path": list(hp)}


FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
ADMON_RE = re.compile(r"^(!!!|\?\?\?\+?)\s")
LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
INDENT_RE = re.compile(r"^(?: {2,}|\t)\S")
JSX_STRIP_RE = re.compile(r"<[^>]*>")


def parse_markdown(text: str) -> list[dict]:
    lines = text.split("\n")
    n = len(lines)
    i = 0
    if n and lines[0].strip() == "---":
        j = 1
        while j < n and lines[j].strip() != "---":
            j += 1
        if j < n:
            i = j + 1
    units: list[dict] = []
    stack: list[tuple[int, str]] = []
    para: list[tuple[int, str]] = []

    def hp() -> list[str]:
        return [t for _, t in stack]

    def flush():
        nonlocal para
        if para:
            units.append(_mk("prose", para[0][0], para[-1][0], [l for _, l in para], hp()))
            para = []

    while i < n:
        line = lines[i]
        ln = i + 1
        if not line.strip():
            flush()
            i += 1
            continue
        m = FENCE_RE.match(line)
        if m:
            flush()
            fence = m.group(1)
            j = i + 1
            while j < n:
                mm = FENCE_RE.match(lines[j])
                if mm and mm.group(1)[0] == fence[0] and len(mm.group(1)) >= len(fence) and not lines[j].strip().lstrip(fence[0]):
                    break
                j += 1
            end = min(j, n - 1)
            units.append(_mk("code", ln, end + 1, lines[i:end + 1], hp()))
            i = end + 1
            continue
        m = HEAD_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            units.append(_mk("heading", ln, ln, [line], hp()))
            stack.append((level, m.group(2)))
            i += 1
            continue
        if line.lstrip().startswith("|"):
            flush()
            j = i
            while j < n and lines[j].lstrip().startswith("|"):
                j += 1
            units.append(_mk("table", ln, j, lines[i:j], hp()))
            i = j
            continue
        if ADMON_RE.match(line):
            flush()
            j = i + 1
            while j < n:
                if lines[j].strip() and not re.match(r"^(?: {4}|\t)", lines[j]):
                    break
                if not lines[j].strip():
                    k = j
                    while k < n and not lines[k].strip():
                        k += 1
                    if k < n and re.match(r"^(?: {4}|\t)", lines[k]):
                        j = k
                        continue
                    break
                j += 1
            units.append(_mk("prose", ln, j, lines[i:j], hp()))
            i = j
            continue
        if LIST_RE.match(line) and not para:
            j = i + 1
            while j < n:
                if lines[j].strip():
                    if HEAD_RE.match(lines[j]) or FENCE_RE.match(lines[j]) or lines[j].lstrip().startswith("|"):
                        break
                    j += 1
                else:
                    k = j
                    while k < n and not lines[k].strip():
                        k += 1
                    if k < n and (LIST_RE.match(lines[k]) or INDENT_RE.match(lines[k])):
                        j = k
                    else:
                        break
            end = j
            while end > i and not lines[end - 1].strip():
                end -= 1
            units.append(_mk("prose", ln, end, lines[i:end], hp()))
            i = j
            continue
        if re.match(r"^(import|export)\s", line) or re.match(r"^\s*<!--.*-->\s*$", line):
            flush()
            i += 1
            continue
        if line.strip().startswith("<") and not JSX_STRIP_RE.sub("", line).strip():
            flush()
            i += 1
            continue
        para.append((ln, line))
        i += 1
    flush()
    return units


TSX_PROP_RE = re.compile(
    r"""\b(?:title|description|label|children|alt|placeholder)\s*[=:]\s*(?:"([^"\n]*)"|'([^'\n]*)'|\{\s*"([^"\n]*)"\s*\}|\{\s*'([^'\n]*)'\s*\}|\{\s*`([^`\n$]*)`\s*\}|`([^`\n$]*)`)"""
)
TSX_CODE_START = re.compile(r"^(import|export|const|let|var|function|return|type|interface|if|else|for|while|case|switch)\b|^//|^/\*|^\*|^\}|^\)|^\]")


def parse_tsx(text: str) -> list[dict]:
    units: list[dict] = []
    buf: list[tuple[int, str]] = []

    def flush():
        nonlocal buf
        if buf:
            units.append(_mk("prose", buf[0][0], buf[-1][0], [t for _, t in buf], []))
            buf = []

    in_tpl = False
    for idx, raw in enumerate(text.split("\n"), 1):
        s = raw.strip()
        was_tpl = in_tpl
        if raw.count("`") % 2 == 1:
            in_tpl = not in_tpl
        if was_tpl or (in_tpl and not TSX_PROP_RE.search(raw)):
            flush()
            continue
        found = False
        for m in TSX_PROP_RE.finditer(raw):
            val = next((g for g in m.groups() if g is not None), "")
            flush()
            units.append(_mk("prose", idx, idx, [val], []))
            found = True
        if found:
            continue
        pieces: list[str] = []
        for m in re.finditer(r">([^<>{}]+)<", raw):
            pieces.append(m.group(1))
        m = re.search(r">([^<>{}]+)$", raw)
        if m and not pieces:
            pieces.append(m.group(1))
        m = re.match(r"^([^<>{}=;]+)<", s)
        if m and not pieces:
            pieces.append(m.group(1))
        if not pieces and s and not re.search(r"[<>{}=;]", s) and not TSX_CODE_START.match(s) and re.search(r"[A-Za-z]{2,}\s+[A-Za-z]", s) and not s.endswith(","):
            pieces.append(s)
        pieces = [p.strip() for p in pieces if p.strip()]
        if pieces:
            if buf and buf[-1][0] == idx - 1 or not buf:
                for p in pieces:
                    buf.append((idx, p))
            else:
                flush()
                for p in pieces:
                    buf.append((idx, p))
        else:
            flush()
    flush()
    return units


def parse_file(path: str, text: str) -> list[dict]:
    if path.endswith(".tsx"):
        raw = parse_tsx(text)
    else:
        raw = parse_markdown(text)
    out = []
    seen: Counter = Counter()
    for u in raw:
        norm = norm_text(u["text"])
        words = len(norm.split())
        if words < MIN_WORDS and u["kind"] != "heading":
            continue
        if not norm:
            continue
        th = sha(norm)
        ordinal = seen[th]
        seen[th] += 1
        u.update(
            {
                "unit_id": sha(f"{path}\0{th}\0{ordinal}")[:16],
                "path": path,
                "text_hash": th,
                "words": words,
            }
        )
        out.append(u)
    return out


# --------------------------------------------------------------------------- context
class Audit:
    def __init__(self, root: Path, tracked: list[str] | None = None):
        self.root = Path(root)
        self.audit = self.root / "audit"
        self._tracked = tracked
        self._units: list[dict] | None = None
        self._slug_cache: dict[str, set[str]] = {}

    # files
    def tracked(self) -> list[str]:
        if self._tracked is None:
            out = subprocess.run(
                ["git", "ls-files", "-z"], cwd=self.root, capture_output=True, check=True, timeout=60
            ).stdout.decode("utf-8")
            self._tracked = [p for p in out.split("\0") if p]
        return self._tracked

    def corpus_files(self) -> list[str]:
        cfg = yaml.safe_load((self.audit / "corpus.yml").read_text(encoding="utf-8"))
        inc, exc = cfg.get("include", []), cfg.get("exclude", [])
        return sorted(p for p in self.tracked() if glob_match(p, inc) and not glob_match(p, exc))

    def units(self) -> list[dict]:
        if self._units is None:
            us: list[dict] = []
            for p in self.corpus_files():
                f = self.root / p
                if not f.is_file():
                    continue
                us.extend(parse_file(p, f.read_text(encoding="utf-8", errors="replace")))
            self._units = us
        return self._units

    def checks(self) -> "OrderedDict[str, dict]":
        cfg = yaml.safe_load((self.audit / "checks.yml").read_text(encoding="utf-8"))
        out: OrderedDict = OrderedDict()
        for c in cfg["checks"]:
            for k in ("id", "version", "kind", "applies_to", "title", "instructions"):
                if k not in c:
                    raise SystemExit(f"checks.yml: check {c.get('id')} missing {k}")
            if c["kind"] not in ("model", "script") or not isinstance(c["version"], int):
                raise SystemExit(f"checks.yml: bad kind/version for {c['id']}")
            if not set(c["applies_to"]) <= set(KINDS):
                raise SystemExit(f"checks.yml: bad applies_to for {c['id']}")
            c.setdefault("meta_sample_mod", 5)
            c.setdefault("exclude_paths", [])
            if not isinstance(c["meta_sample_mod"], int) or c["meta_sample_mod"] < 1:
                raise SystemExit(f"checks.yml: bad meta_sample_mod for {c['id']}")
            if c["id"] in out:
                raise SystemExit(f"checks.yml: duplicate id {c['id']}")
            out[c["id"]] = c
        return out

    def ledger(self) -> list[dict]:
        return read_jsonl(self.audit / "ledger.jsonl")

    # status
    def pair_states(self, only_checks: list[str] | None = None) -> list[dict]:
        """One entry per applicable (unit, check) with status for current text/version."""
        checks = self.checks()
        led = self.ledger()
        reviews: dict[tuple, dict] = {}
        for r in led:
            if r.get("role") == "review":
                reviews[(r["unit_id"], r["text_hash"], r["check_id"], r["check_version"])] = r
        metas: dict[str, dict] = {}
        for r in led:
            if r.get("role") == "meta" and r.get("corrects"):
                metas[r["corrects"]] = r
        out = []
        for u in self.units():
            for cid, c in checks.items():
                if only_checks and cid not in only_checks:
                    continue
                if u["kind"] not in c["applies_to"]:
                    continue
                if c["exclude_paths"] and glob_match(u["path"], c["exclude_paths"]):
                    continue
                rev = reviews.get((u["unit_id"], u["text_hash"], cid, c["version"]))
                st = {"unit": u, "check": c, "review": rev, "meta": None, "status": "pending", "verdict": None, "disputed": False}
                if rev:
                    st["verdict"] = rev["verdict"]
                    if c["kind"] == "script":
                        st["status"] = "closed"
                    else:
                        meta = metas.get(rev["record_id"])
                        if meta:
                            st["status"] = "closed"
                            st["meta"] = meta
                            st["verdict"] = meta["verdict"]
                            st["disputed"] = meta["verdict"] != rev["verdict"]
                        else:
                            st["status"] = "reviewed"
                out.append(st)
        return out


def make_record(**kw) -> dict:
    rec = {
        "unit_id": kw["unit_id"],
        "text_hash": kw["text_hash"],
        "check_id": kw["check_id"],
        "check_version": kw["check_version"],
        "verdict": kw["verdict"],
        "role": kw["role"],
        "reviewer": kw["reviewer"],
        "batch_id": kw["batch_id"],
        "finding": kw.get("finding", "") or "",
        "evidence": kw.get("evidence", "") or "",
        "corrects": kw.get("corrects"),
    }
    if kw.get("sample_mod") is not None:  # only new auto-meta records; old records keep their ids
        rec["sample_mod"] = kw["sample_mod"]
    rec["record_id"] = sha(json.dumps(rec, sort_keys=True, ensure_ascii=False))[:16]
    rec["ts"] = now_ts()
    return rec


# --------------------------------------------------------------------------- script checks
def github_slugs(text: str) -> set[str]:
    slugs: set[str] = set()
    counts: Counter = Counter()
    in_fence = None
    for line in text.split("\n"):
        m = FENCE_RE.match(line)
        if m:
            if in_fence is None:
                in_fence = m.group(1)[0]
            elif m.group(1)[0] == in_fence:
                in_fence = None
            continue
        if in_fence:
            continue
        h = HEAD_RE.match(line)
        if h:
            t = h.group(2)
            t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
            t = t.replace("`", "").replace("*", "")
            t = re.sub(r"<[^>]+>", "", t)
            s = re.sub(r"[^\w\- ]", "", t.strip().lower()).replace(" ", "-")
            k = counts[s]
            counts[s] += 1
            slugs.add(s if k == 0 else f"{s}-{k}")
    for m in re.finditer(r"""\b(?:id|name)=["']([^"']+)["']""", text):
        slugs.add(m.group(1))
    return slugs


LINK_RE = re.compile(r"(?<!\!)\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
IMG_LINK_RE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")


def check_links(au: Audit, u: dict) -> tuple[str, str, str]:
    text = re.sub(r"`[^`\n]*`", "", u["text"])
    targets = LINK_RE.findall(text)
    tracked = set(au.tracked())
    problems: list[str] = []
    checked = 0
    for t in targets:
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", t) or t.startswith("/"):  # external or site-absolute route
            continue
        checked += 1
        pathpart, _, anchor = t.partition("#")
        pathpart = pathpart.split("?")[0]
        if pathpart:
            base = Path(u["path"]).parent
            target = base / pathpart
            parts: list[str] = []
            for part in target.parts:
                if part == "..":
                    if parts:
                        parts.pop()
                elif part != ".":
                    parts.append(part)
            tp = "/".join(parts)
            is_file = tp in tracked
            is_dir = any(p.startswith(tp.rstrip("/") + "/") for p in tracked) if tp else True
            if not (is_file or is_dir):
                problems.append(f"{t} (target {tp} is not a tracked file)")
                continue
        else:
            tp = u["path"]
            is_file = True
        if anchor and is_file and tp.endswith((".md", ".mdx")):
            if tp not in au._slug_cache:
                f = au.root / tp
                au._slug_cache[tp] = github_slugs(f.read_text(encoding="utf-8", errors="replace")) if f.is_file() else set()
            if anchor.lower() not in {s.lower() for s in au._slug_cache[tp]}:
                problems.append(f"{t} (anchor #{anchor} not found in {tp})")
    ev = f"{u['path']}:{u['start_line']}"
    if problems:
        return "issue", "Unresolved relative links in this unit: " + "; ".join(problems), ev
    if checked == 0:
        return "pass", "unit has no relative links to resolve", ev
    return "pass", f"all {checked} relative links and anchors resolve", ev


def check_banned(au: Audit, u: dict) -> tuple[str, str, str]:
    ev = f"{u['path']}:{u['start_line']}"
    hits = sorted({m.group(0).lower() for m in BANNED_RE.finditer(u["text"])})
    if not hits:
        return "pass", "no banned words found in unit", ev
    if EXEMPT_RE.search(u["text"]):
        return "pass", "banned words quoted inside a vocabulary rule: " + ", ".join(hits), ev
    return "issue", "Banned words used outside any vocabulary rule: " + ", ".join(hits), ev


SCRIPTS = {"TVL-S01": check_links, "TVL-S02": check_banned}


# --------------------------------------------------------------------------- commands
def cmd_inventory(au: Audit, args) -> int:
    us = au.units()
    write_jsonl(au.audit / "units.jsonl", us)
    byp: Counter = Counter()
    byk: Counter = Counter()
    words = 0
    for u in us:
        byp[u["path"]] += 1
        byk[u["kind"]] += 1
        words += u["words"]
    for p in sorted(byp):
        print(f"{byp[p]:5d}  {p}")
    print(f"files: {len(byp)}")
    print(f"units: {len(us)}  words: {words}")
    print("by kind: " + ", ".join(f"{k}={byk[k]}" for k in KINDS))
    return 0


def next_batch_id(au: Audit, role: str) -> str:
    """Globally unique: B-<yyyymmddHHMMSS>-<seq>-<role>. Every issued id is remembered in batches/ISSUED.txt."""
    bdir = au.audit / "batches"
    bdir.mkdir(parents=True, exist_ok=True)
    issued_f = bdir / "ISSUED.txt"
    used = set(issued_f.read_text().split()) if issued_f.exists() else set()
    used |= {p.stem for p in bdir.glob("*.json")}
    used |= {r.get("batch_id") for r in au.ledger()}
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    seq = 1
    while f"B-{ts}-{seq:03d}-{role}" in used:
        seq += 1
    bid = f"B-{ts}-{seq:03d}-{role}"
    with issued_f.open("a") as f:
        f.write(bid + "\n")
    return bid


def cut_batches(units: list[dict], max_words: int) -> list[list[dict]]:
    batches: list[list[dict]] = []
    cur: list[dict] = []
    w = 0
    for u in units:
        if cur and w + u["words"] > max_words:
            batches.append(cur)
            cur, w = [], 0
        cur.append(u)
        w += u["words"]
    if cur:
        batches.append(cur)
    return batches


def cmd_plan(au: Audit, args) -> int:
    checks = au.checks()
    want = [canon_check_id(c) for c in args.checks.split(",")] if args.checks else None
    if want:
        for c in want:
            if c not in checks:
                raise SystemExit(f"unknown check {c}")
    model = [cid for cid, c in checks.items() if c["kind"] == "model" and (not want or cid in want)]
    if want:
        skipped = [c for c in want if checks[c]["kind"] == "script"]
        if skipped:
            print(f"note: script checks are run with run-script-checks, not planned: {', '.join(skipped)}", file=sys.stderr)
    if not model:
        raise SystemExit("no model checks selected")
    states = au.pair_states(model)
    if args.paths:
        states = [s for s in states if fnmatch.fnmatch(s["unit"]["path"], args.paths) or glob_match(s["unit"]["path"], [args.paths])]
    role = args.role
    written = []
    if role == "review":
        pend = [s for s in states if s["status"] == "pending"]
        by_unit: "OrderedDict[str, list]" = OrderedDict()
        for s in pend:
            by_unit.setdefault(s["unit"]["unit_id"], []).append(s)
        units = [v[0]["unit"] for v in by_unit.values()]
        for chunk in cut_batches(units, args.max_words):
            bid = next_batch_id(au, "review")
            ids = {u["unit_id"] for u in chunk}
            pairs = [[s["unit"]["unit_id"], s["check"]["id"]] for s in pend if s["unit"]["unit_id"] in ids]
            cids = sorted({p[1] for p in pairs}, key=list(checks).index)
            batch = {
                "batch_id": bid,
                "role": "review",
                "checks": [{"id": c, "version": checks[c]["version"], "title": checks[c]["title"], "instructions": checks[c]["instructions"]} for c in cids],
                "pairs": pairs,
                "units": chunk,
            }
            p = au.audit / "batches" / f"{bid}.json"
            p.write_text(json.dumps(batch, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            written.append(p)
        print(f"pending pairs: {len(pend)}; units: {len(units)}")
    else:
        elig = [s for s in states if s["status"] == "reviewed"]
        sampled, auto = [], []
        for s in elig:
            r = s["review"]
            if r["verdict"] in ("issue", "na") or int(r["record_id"], 16) % s["check"]["meta_sample_mod"] == 0:
                sampled.append(s)
            else:
                auto.append(s)
        bid_auto = next_batch_id(au, "meta")
        recs = [
            make_record(
                unit_id=s["unit"]["unit_id"], text_hash=s["unit"]["text_hash"], check_id=s["check"]["id"],
                check_version=s["check"]["version"], verdict=s["review"]["verdict"], role="meta", reviewer="sampling",
                batch_id=bid_auto, finding=f"not sampled; review accepted under the 1-in-{s['check']['meta_sample_mod']} sampling rule", evidence="",
                corrects=s["review"]["record_id"], sample_mod=s["check"]["meta_sample_mod"],
            )
            for s in auto
        ]
        if recs:
            append_jsonl(au.audit / "ledger.jsonl", recs)
        print(f"reviewed pairs: {len(elig)}; sampled for meta-review: {len(sampled)}; auto-closed (not sampled): {len(auto)}")
        by_unit = OrderedDict()
        for s in sampled:
            by_unit.setdefault(s["unit"]["unit_id"], []).append(s)
        units = [v[0]["unit"] for v in by_unit.values()]
        for chunk in cut_batches(units, args.max_words):
            ids = {u["unit_id"] for u in chunk}
            sel = [s for s in sampled if s["unit"]["unit_id"] in ids]
            bid = next_batch_id(au, "meta")
            cids = sorted({s["check"]["id"] for s in sel}, key=list(checks).index)
            batch = {
                "batch_id": bid,
                "role": "meta",
                "checks": [{"id": c, "version": checks[c]["version"], "title": checks[c]["title"], "instructions": checks[c]["instructions"]} for c in cids],
                "pairs": [[s["unit"]["unit_id"], s["check"]["id"]] for s in sel],
                "reviews": [s["review"] for s in sel],
                "units": chunk,
            }
            p = au.audit / "batches" / f"{bid}.json"
            p.write_text(json.dumps(batch, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            written.append(p)
    for p in written:
        print(p)
    if not written:
        print("nothing to plan")
    return 0


def validate_results(au: Audit, data: dict) -> tuple[list[dict], list[str]]:
    errs: list[str] = []
    for k in ("batch_id", "reviewer", "role", "results"):
        if k not in data:
            errs.append(f"missing top-level field {k}")
    if errs:
        return [], errs
    bpath = au.audit / "batches" / f"{data['batch_id']}.json"
    if not bpath.exists():
        return [], [f"unknown batch {data['batch_id']}"]
    batch = json.loads(bpath.read_text(encoding="utf-8"))
    if data["role"] not in ROLES:
        errs.append(f"bad role {data['role']!r}")
    elif data["role"] != batch["role"]:
        errs.append(f"role {data['role']} does not match batch role {batch['role']}")
    if not str(data["reviewer"]).strip():
        errs.append("empty reviewer")
    checks = au.checks()
    cur_units = {u["unit_id"]: u for u in au.units()}
    batch_units = {u["unit_id"]: u for u in batch["units"]}
    batch_checks = {c["id"]: c for c in batch["checks"]}
    pairs = {tuple(p) for p in batch.get("pairs", [])}
    batch_reviews = {r["record_id"] for r in batch.get("reviews", [])}
    led = au.ledger()
    led_by_id = {r["record_id"]: r for r in led}
    recs: list[dict] = []
    seen = set()
    for i, r in enumerate(data["results"]):
        tag = f"results[{i}]"
        uid, cid, verdict = r.get("unit_id"), r.get("check_id"), r.get("verdict")
        if uid not in batch_units:
            errs.append(f"{tag}: unit {uid} is not in batch")
            continue
        if cid not in batch_checks:
            errs.append(f"{tag}: check {cid} is not in batch")
            continue
        if pairs and (uid, cid) not in pairs:
            errs.append(f"{tag}: pair ({uid}, {cid}) was not planned in this batch")
            continue
        if (uid, cid) in seen:
            errs.append(f"{tag}: duplicate result for ({uid}, {cid})")
            continue
        seen.add((uid, cid))
        cu = cur_units.get(uid)
        if cu is None or cu["text_hash"] != batch_units[uid]["text_hash"]:
            errs.append(f"{tag}: unit {uid} text changed since batch was planned (stale text hash)")
            continue
        chk = checks.get(cid)
        if chk is None or chk["version"] != batch_checks[cid]["version"]:
            errs.append(f"{tag}: check {cid} version changed since batch was planned")
            continue
        if chk["kind"] != "model":
            errs.append(f"{tag}: script check {cid} cannot be recorded; use run-script-checks")
            continue
        if cu["kind"] not in chk["applies_to"]:
            errs.append(f"{tag}: check {cid} does not apply to {cu['kind']} units")
            continue
        if verdict not in VERDICTS:
            errs.append(f"{tag}: verdict {verdict!r} not in {VERDICTS}")
            continue
        finding = (r.get("finding") or "").strip()
        evidence = (r.get("evidence") or "").strip()
        if verdict == "issue":
            if len(finding.split()) < 8:
                errs.append(f"{tag}: issue needs a finding of at least 8 words")
                continue
            if not evidence:
                errs.append(f"{tag}: issue needs evidence (file:line or command)")
                continue
        if verdict == "na" and not finding:
            errs.append(f"{tag}: na needs a reason in finding")
            continue
        if verdict == "pass" and cid == "TVL-C01" and not evidence:
            errs.append(f"{tag}: pass on TVL-C01 needs evidence (authority file:line or 'no factual claim')")
            continue
        corrects = r.get("corrects")
        if data["role"] == "meta":
            if not finding:
                errs.append(f"{tag}: meta record needs a finding explaining agreement or disagreement")
                continue
            tgt = led_by_id.get(corrects) if corrects else None
            if (
                not tgt or tgt.get("role") != "review" or tgt["unit_id"] != uid or tgt["check_id"] != cid
                or tgt["text_hash"] != cu["text_hash"] or tgt["check_version"] != chk["version"]
            ):
                errs.append(f"{tag}: corrects {corrects!r} does not reference a current review record for this unit and check")
                continue
            if batch_reviews and corrects not in batch_reviews:
                errs.append(f"{tag}: corrects {corrects} is not among the reviews in this batch")
                continue
        else:
            if corrects:
                errs.append(f"{tag}: review records must not set corrects")
                continue
            corrects = None
        recs.append(
            make_record(
                unit_id=uid, text_hash=cu["text_hash"], check_id=cid, check_version=chk["version"], verdict=verdict,
                role=data["role"], reviewer=data["reviewer"], batch_id=data["batch_id"], finding=finding,
                evidence=evidence, corrects=corrects,
            )
        )
    return recs, errs


def cmd_record(au: Audit, args) -> int:
    data = json.loads(Path(args.results).read_text(encoding="utf-8"))
    recs, errs = validate_results(au, data)
    if errs:
        print(f"REJECTED {args.results}: {len(errs)} error(s)", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 1
    append_jsonl(au.audit / "ledger.jsonl", recs)
    print(f"recorded {len(recs)} records from {args.results}")
    return 0


def cmd_run_script_checks(au: Audit, args) -> int:
    checks = au.checks()
    scripts = [cid for cid, c in checks.items() if c["kind"] == "script"]
    for cid in scripts:
        if cid not in SCRIPTS:
            raise SystemExit(f"script check {cid} has no implementation")
    states = [s for s in au.pair_states(scripts) if s["status"] == "pending"]
    d = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d")
    bid = f"S-{d}-script"
    recs = []
    tally: dict[str, Counter] = {cid: Counter() for cid in scripts}
    for s in states:
        cid = s["check"]["id"]
        verdict, finding, ev = SCRIPTS[cid](au, s["unit"])
        tally[cid][verdict] += 1
        recs.append(
            make_record(
                unit_id=s["unit"]["unit_id"], text_hash=s["unit"]["text_hash"], check_id=cid, check_version=s["check"]["version"],
                verdict=verdict, role="review", reviewer=f"script:{cid}", batch_id=bid, finding=finding, evidence=ev,
            )
        )
    append_jsonl(au.audit / "ledger.jsonl", recs)
    print(f"ran script checks on {len(recs)} pending pairs")
    for cid in scripts:
        t = tally[cid]
        print(f"  {cid}: pass={t['pass']} issue={t['issue']}")
    return 0


def binom_cdf(k: int, n: int, p: float) -> float:
    from math import lgamma, log, exp
    if p <= 0:
        return 1.0
    if p >= 1:
        return 1.0 if k >= n else 0.0
    tot = 0.0
    for i in range(0, k + 1):
        tot += exp(lgamma(n + 1) - lgamma(i + 1) - lgamma(n - i + 1) + i * log(p) + (n - i) * log(1 - p))
    return min(tot, 1.0)


def cp_upper(k: int, n: int, alpha: float = 0.05) -> float:
    """Exact one-sided (1-alpha) Clopper-Pearson upper bound: p with P(X<=k | n,p)=alpha (bisection on the binomial CDF)."""
    if n <= 0:
        return 1.0
    if k >= n:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if binom_cdf(k, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def coverage_data(au: Audit) -> dict:
    states = au.pair_states()
    keys = ("pending", "reviewed", "closed")
    byc: dict[str, Counter] = {}
    byp: dict[str, Counter] = {}
    tot: Counter = Counter()
    for s in states:
        byc.setdefault(s["check"]["id"], Counter())[s["status"]] += 1
        byp.setdefault(s["unit"]["path"], Counter())[s["status"]] += 1
        tot[s["status"]] += 1
    overturn = {}
    for cid, c in au.checks().items():
        if c["kind"] != "model":
            continue
        sampled = [s for s in states if s["check"]["id"] == cid and s["status"] == "closed" and s["meta"]
                   and s["meta"]["reviewer"] != "sampling" and s["review"]["verdict"] == "pass"]
        auto = sum(1 for s in states if s["check"]["id"] == cid and s["status"] == "closed" and s["meta"]
                   and s["meta"]["reviewer"] == "sampling" and s["review"]["verdict"] == "pass")
        n = len(sampled)
        k = sum(1 for s in sampled if s["meta"]["verdict"] == "issue")
        ub = cp_upper(k, n) if n else None
        overturn[cid] = {"k": k, "n": n, "rate": (k / n) if n else None, "upper95": ub, "auto_accepted_passes": auto,
                         "est_hidden_issues_upper": (ub * auto) if ub is not None else None, "meta_sample_mod": c["meta_sample_mod"]}
    meta_closed = [s for s in states if s["status"] == "closed" and s["meta"]]
    auto_n = sum(1 for s in meta_closed if s["meta"]["reviewer"] == "sampling")
    total = sum(tot.values())
    return {
        "by_check": {k: {x: v[x] for x in keys} for k, v in byc.items()},
        "by_path": {k: {x: v[x] for x in keys} for k, v in byp.items()},
        "totals": {"pairs": total, **{k: tot[k] for k in keys}},
        "meta_closed_sampled": len(meta_closed) - auto_n, "meta_closed_auto": auto_n,
        "script_closed": sum(1 for s in states if s["status"] == "closed" and s["check"]["kind"] == "script"),
        "disputed": sum(1 for s in states if s["disputed"]),
        "overturn": overturn,
        "all_closed": total > 0 and tot["closed"] == total,
    }


def cmd_coverage(au: Audit, args) -> int:
    d = coverage_data(au)
    if getattr(args, "json", False):
        print(json.dumps(d, indent=1, sort_keys=True))
    else:
        def table(title: str, groups: dict):
            print(f"\n{title}")
            print(f"{'':72s} {'pending':>8s} {'reviewed':>9s} {'closed':>7s} {'total':>7s}")
            for g in sorted(groups):
                c = groups[g]
                print(f"{g[:72]:72s} {c['pending']:8d} {c['reviewed']:9d} {c['closed']:7d} {sum(c.values()):7d}")

        table("By check", d["by_check"])
        table("By path", d["by_path"])
        t = d["totals"]
        print(f"\nTOTAL pairs={t['pairs']} pending={t['pending']} reviewed={t['reviewed']} closed={t['closed']}")
        print(f"model pairs closed by meta: sampled(real second review)={d['meta_closed_sampled']} auto(not sampled)={d['meta_closed_auto']}")
        print(f"script pairs closed: {d['script_closed']}")
        print(f"disputed (meta verdict differs from review): {d['disputed']}")
        print("\nMeta overturn of sampled review passes (k = passes the meta reviewer changed to issue, n = sampled passes)")
        print(f"{'check':10s} {'mod':>4s} {'k/n':>9s} {'rate':>7s} {'upper95':>8s} {'auto passes':>12s} {'hidden issues <='}")
        for cid, o in d["overturn"].items():
            if o["n"]:
                print(f"{cid:10s} {o['meta_sample_mod']:4d} {str(o['k']) + '/' + str(o['n']):>9s} {o['rate']:7.3f} {o['upper95']:8.4f} {o['auto_accepted_passes']:12d} {o['est_hidden_issues_upper']:.1f}")
            else:
                print(f"{cid:10s} {o['meta_sample_mod']:4d} {'0/0':>9s} {'n/a':>7s} {'n/a':>8s} {o['auto_accepted_passes']:12d} n/a")
    if args.strict:
        if not d["all_closed"]:
            print("STRICT: FAIL, not every applicable pair is closed", file=sys.stderr)
            return 1
        print("STRICT: OK")
    return 0


def open_issues(au: Audit) -> list[dict]:
    out = []
    for s in au.pair_states():
        if s["status"] != "pending" and s["verdict"] == "issue":
            rec = s["meta"] or s["review"]
            u = s["unit"]
            out.append(
                {
                    "path": u["path"], "start_line": u["start_line"], "end_line": u["end_line"], "unit_id": u["unit_id"],
                    "check_id": s["check"]["id"], "status": s["status"], "finding": rec["finding"],
                    "evidence": rec["evidence"] or (s["review"]["evidence"] if s["review"] else ""),
                    "disputed": s["disputed"], "review_finding": s["review"]["finding"] if s["review"] else "",
                }
            )
    out.sort(key=lambda r: (r["path"], r["start_line"], r["check_id"]))
    return out


def render_report_md(issues: list[dict]) -> str:
    lines = ["# TVL claim audit: open issues", "", f"Open issues: {len(issues)}", ""]
    cur = None
    for r in issues:
        if r["path"] != cur:
            cur = r["path"]
            lines += [f"## {cur}", ""]
        flag = " (DISPUTED: meta-review overrode the first review)" if r["disputed"] else ""
        lines.append(f"- lines {r['start_line']}-{r['end_line']}, {r['check_id']}, {r['status']}{flag}")
        lines.append(f"  - finding: {r['finding']}")
        lines.append(f"  - evidence: {r['evidence']}")
    return "\n".join(lines) + "\n"


def cmd_report(au: Audit, args) -> int:
    issues = open_issues(au)
    body = json.dumps(issues, indent=1, ensure_ascii=False) + "\n" if args.format == "json" else render_report_md(issues)
    print(body, end="")
    if args.write:
        (au.audit / "REPORT.md").write_text(render_report_md(issues), encoding="utf-8")
    return 0


def cmd_compact(au: Audit, args) -> int:
    checks = au.checks()
    cur = {(u["unit_id"], u["text_hash"]) for u in au.units()}
    led = au.ledger()
    keep, drop = [], []
    for r in led:
        c = checks.get(r["check_id"])
        if c and r["check_version"] == c["version"] and (r["unit_id"], r["text_hash"]) in cur:
            keep.append(r)
        else:
            drop.append(r)
    if drop:
        append_jsonl(au.audit / "ledger-history.jsonl", drop)
    write_jsonl(au.audit / "ledger.jsonl", keep)
    print(f"kept {len(keep)} current records; moved {len(drop)} history records to audit/ledger-history.jsonl")
    return 0


def main(argv: list[str] | None = None, root: Path | None = None, tracked: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="claim_audit", description=__doc__)
    ap.add_argument("--root", default=None, help="repository root (default: derived from this file)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inventory")
    p = sub.add_parser("plan")
    p.add_argument("--checks", default=None)
    p.add_argument("--max-words", type=int, default=3500)
    p.add_argument("--paths", default=None)
    p.add_argument("--role", choices=ROLES, default="review")
    p = sub.add_parser("record")
    p.add_argument("results")
    sub.add_parser("run-script-checks")
    p = sub.add_parser("coverage")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("report")
    p.add_argument("--format", choices=("md", "json"), default="md")
    p.add_argument("--write", action="store_true")
    sub.add_parser("compact")
    args = ap.parse_args(argv)
    r = Path(args.root) if args.root else (root or Path(__file__).resolve().parents[2])
    au = Audit(r, tracked)
    fn = {
        "inventory": cmd_inventory, "plan": cmd_plan, "record": cmd_record, "run-script-checks": cmd_run_script_checks,
        "coverage": cmd_coverage, "report": cmd_report, "compact": cmd_compact,
    }[args.cmd]
    return fn(au, args)


if __name__ == "__main__":
    sys.exit(main())
