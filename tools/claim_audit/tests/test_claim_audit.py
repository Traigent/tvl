import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import claim_audit as ca  # noqa: E402


# ------------------------------------------------------------------ fixtures
CHECKS = {
    "checks": [
        {"id": "TVL-C01", "version": 1, "kind": "model", "applies_to": ["prose", "code", "table", "heading"], "title": "Accuracy", "instructions": "x"},
        {"id": "TVL-C05", "version": 1, "kind": "model", "applies_to": ["prose", "table", "heading"], "title": "Clarity", "instructions": "y"},
        {"id": "TVL-S01", "version": 1, "kind": "script", "applies_to": ["prose", "table", "heading"], "title": "Links", "instructions": "z"},
        {"id": "TVL-S02", "version": 1, "kind": "script", "applies_to": ["prose", "code", "table", "heading"], "title": "Banned", "instructions": "z"},
    ]
}


def make_repo(tmp_path, files: dict, include=("*.md", "**/*.md", "*.tsx")):
    for p, t in files.items():
        f = tmp_path / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(t, encoding="utf-8")
    (tmp_path / "audit").mkdir(exist_ok=True)
    (tmp_path / "audit" / "corpus.yml").write_text(yaml.safe_dump({"include": list(include), "exclude": []}))
    (tmp_path / "audit" / "checks.yml").write_text(yaml.safe_dump(CHECKS))
    (tmp_path / "audit" / "ledger.jsonl").write_text("")
    return ca.Audit(tmp_path, tracked=sorted(files))


def parse(text, path="a.md"):
    return ca.parse_file(path, text)


def run(tmp_path, files, argv):
    return ca.main(["--root", str(tmp_path)] + argv, tracked=sorted(files))


# ------------------------------------------------------------------ splitting
def test_code_fence_with_blank_lines_is_one_unit():
    us = parse("Intro words go right here now.\n\n```yaml\na: 1\n\nb: 2\n```\n\nAfter the fence we have words again.\n")
    kinds = [u["kind"] for u in us]
    assert kinds == ["prose", "code", "prose"]
    assert "b: 2" in us[1]["text"]


def test_table_heading_and_path():
    us = parse("# Title\n\n## Sub head\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nSome prose that is long enough.\n")
    assert [u["kind"] for u in us] == ["heading", "heading", "table", "prose"]
    assert us[2]["heading_path"] == ["Title", "Sub head"]
    assert us[2]["start_line"] == 5 and us[2]["end_line"] == 7


def test_admonition_is_one_unit():
    us = parse('!!! note "Careful"\n    first body line here\n\n    second body paragraph here\n\nNext paragraph is separate and long.\n')
    assert len(us) == 2
    assert "second body" in us[0]["text"]


def test_list_is_one_unit():
    us = parse("- item one has words\n- item two has words\n\n- item three has words\n\nTrailing paragraph with enough words.\n")
    assert len(us) == 2 and us[0]["text"].count("item") == 3


def test_mdx_import_and_jsx_skipped_and_front_matter():
    text = "---\ntitle: x y z w v\n---\nimport Foo from './foo'\n\n<Foo bar=\"1\" />\n\nReal sentence with enough words in it.\n"
    us = parse(text, "a.mdx")
    assert [u["text"] for u in us] == ["Real sentence with enough words in it."]


def test_short_units_skipped_but_headings_kept():
    us = parse("# V1\n\nToo short.\n")
    assert [u["kind"] for u in us] == ["heading"]


def test_tsx_extraction():
    tsx = (
        'import X from "x";\n'
        'export default function A() {\n'
        '  return (\n'
        '    <div className="a b c d e">\n'
        '      <Card title="A card title here" />\n'
        '      <p>\n'
        '        This is a human visible sentence\n'
        '        that continues on a second line.\n'
        '      </p>\n'
        '      <span>too short</span>\n'
        '    </div>\n'
        '  );\n'
        '}\n'
    )
    texts = [u["text"] for u in parse(tsx, "p.tsx")]
    assert "A card title here" in texts
    assert "This is a human visible sentence\nthat continues on a second line." in texts
    assert not any("className" in t or "import" in t for t in texts)


# ------------------------------------------------------------------ ids
def test_id_stable_under_move_and_changes_under_edit():
    a = "Paragraph alpha has several words.\n\nParagraph beta has several words.\n"
    b = "Paragraph beta has several words.\n\nParagraph alpha has several words.\n"
    ida = {u["text"]: u["unit_id"] for u in parse(a)}
    idb = {u["text"]: u["unit_id"] for u in parse(b)}
    assert ida == idb
    c = parse("Paragraph alpha has several words!\n\nParagraph beta has several words.\n")
    assert c[0]["unit_id"] != ida["Paragraph alpha has several words."]
    assert c[1]["unit_id"] == ida["Paragraph beta has several words."]


def test_duplicate_ordinal():
    us = parse("Same words repeated here now.\n\nSame words repeated here now.\n")
    assert us[0]["text_hash"] == us[1]["text_hash"] and us[0]["unit_id"] != us[1]["unit_id"]


# ------------------------------------------------------------------ plan / record
FILES = {
    "a.md": "# Title\n\nFirst paragraph has quite enough words.\n\nSecond paragraph also has enough words.\n",
    "b.md": "Third paragraph lives in another file ok.\n",
}


def last_batch(tmp_path):
    # newest by issue order (names sort by role within one second, so do not sort by name)
    issued = (tmp_path / "audit" / "batches" / "ISSUED.txt").read_text().split()
    for bid in reversed(issued):
        p = tmp_path / "audit" / "batches" / f"{bid}.json"
        if p.exists():
            return p


def test_plan_respects_max_words_and_pending_only(tmp_path):
    make_repo(tmp_path, FILES)
    assert run(tmp_path, FILES, ["plan", "--checks", "C01", "--max-words", "10"]) == 0
    batches = sorted((tmp_path / "audit" / "batches").glob("*.json"))
    assert len(batches) >= 2
    for b in batches:
        d = json.loads(b.read_text())
        assert d["role"] == "review"
        assert sum(u["words"] for u in d["units"]) <= 10 or len(d["units"]) == 1
    # record one unit, replan: it is no longer pending
    d = json.loads(batches[0].read_text())
    uid = d["units"][0]["unit_id"]
    res = {"batch_id": d["batch_id"], "reviewer": "sonnet", "role": "review",
           "results": [{"unit_id": uid, "check_id": "TVL-C01", "verdict": "pass", "finding": "", "evidence": "no factual claim"}]}
    rp = tmp_path / "r.json"
    rp.write_text(json.dumps(res))
    assert run(tmp_path, FILES, ["record", str(rp)]) == 0
    for b in batches:
        b.unlink()
    run(tmp_path, FILES, ["plan", "--checks", "C01", "--max-words", "1000"])
    nb = json.loads(last_batch(tmp_path).read_text())
    assert uid not in [u["unit_id"] for u in nb["units"]]
    assert all(p[1] == "TVL-C01" for p in nb["pairs"])


def planned(tmp_path, checks="C01"):
    run(tmp_path, FILES, ["plan", "--checks", checks, "--max-words", "1000"])
    return json.loads(last_batch(tmp_path).read_text())


def submit(tmp_path, batch, results, role="review", reviewer="sonnet"):
    rp = tmp_path / "res.json"
    rp.write_text(json.dumps({"batch_id": batch["batch_id"], "reviewer": reviewer, "role": role, "results": results}))
    return run(tmp_path, FILES, ["record", str(rp)])


def test_record_rejections(tmp_path, capsys):
    make_repo(tmp_path, FILES)
    b = planned(tmp_path)
    u0 = b["units"][0]["unit_id"]
    ok = {"unit_id": u0, "check_id": "TVL-C01", "verdict": "pass", "finding": "", "evidence": "e"}
    bad = [
        dict(ok, unit_id="deadbeefdeadbeef"),                        # unknown unit
        dict(ok, check_id="TVL-C05"),                                 # check not in batch
        dict(ok, verdict="issue", finding="too short", evidence="x"),  # missing finding
        dict(ok, verdict="issue", finding="this finding has clearly more than eight words", evidence=""),
        dict(ok, verdict="maybe"),
        dict(ok, evidence=""),                                        # C01 pass needs evidence
        dict(ok, corrects="abc"),                                     # review must not correct
    ]
    for r in bad:
        assert submit(tmp_path, b, [r]) == 1, r
    assert (tmp_path / "audit" / "ledger.jsonl").read_text() == ""
    # one bad among good rejects the whole file
    assert submit(tmp_path, b, [ok, bad[0]]) == 1
    assert (tmp_path / "audit" / "ledger.jsonl").read_text() == ""
    assert submit(tmp_path, b, [ok]) == 0


def test_record_rejects_stale_hash(tmp_path):
    make_repo(tmp_path, FILES)
    b = planned(tmp_path)
    u0 = b["units"][0]
    (tmp_path / u0["path"]).write_text((tmp_path / u0["path"]).read_text().replace("quite enough", "really enough").replace("Title", "Title"))
    r = {"unit_id": u0["unit_id"], "check_id": "TVL-C01", "verdict": "pass", "finding": "", "evidence": "e"}
    # only fails if the unit actually changed
    changed = u0["unit_id"] not in {u["unit_id"] for u in ca.Audit(tmp_path, tracked=sorted(FILES)).units()}
    if not changed:  # first unit is the heading; pick the paragraph
        u0 = b["units"][1]
        r["unit_id"] = u0["unit_id"]
    assert submit(tmp_path, b, [r]) == 1


def test_meta_requires_valid_corrects_and_meta_wins(tmp_path):
    make_repo(tmp_path, FILES)
    b = planned(tmp_path)
    u0 = b["units"][0]["unit_id"]
    assert submit(tmp_path, b, [{"unit_id": u0, "check_id": "TVL-C01", "verdict": "issue",
                                 "finding": "this statement clearly contradicts the formal semantics document", "evidence": "x.md:1"}]) == 0
    rev = json.loads((tmp_path / "audit" / "ledger.jsonl").read_text().splitlines()[0])
    au = ca.Audit(tmp_path, tracked=sorted(FILES))
    st = [s for s in au.pair_states(["TVL-C01"]) if s["unit"]["unit_id"] == u0][0]
    assert st["status"] == "reviewed" and st["verdict"] == "issue"
    run(tmp_path, FILES, ["plan", "--checks", "C01", "--role", "meta"])
    mb = json.loads(last_batch(tmp_path).read_text())
    assert mb["role"] == "meta" and mb["reviews"][0]["record_id"] == rev["record_id"]
    mres = {"unit_id": u0, "check_id": "TVL-C01", "verdict": "pass", "finding": "reviewer misread the sentence", "evidence": "e"}
    assert submit(tmp_path, mb, [dict(mres, corrects="nonexistent")], role="meta", reviewer="sol") == 1
    assert submit(tmp_path, mb, [dict(mres, corrects=rev["record_id"])], role="meta", reviewer="sol") == 0
    st = [s for s in ca.Audit(tmp_path, tracked=sorted(FILES)).pair_states(["TVL-C01"]) if s["unit"]["unit_id"] == u0][0]
    assert st["status"] == "closed" and st["verdict"] == "pass" and st["disputed"]
    assert ca.open_issues(ca.Audit(tmp_path, tracked=sorted(FILES))) == []


def test_coverage_states_and_auto_meta(tmp_path, capsys):
    make_repo(tmp_path, FILES)
    b = planned(tmp_path)
    results = [{"unit_id": u["unit_id"], "check_id": "TVL-C01", "verdict": "pass", "finding": "", "evidence": "no factual claim"} for u in b["units"]]
    assert submit(tmp_path, b, results) == 0
    au = ca.Audit(tmp_path, tracked=sorted(FILES))
    assert {s["status"] for s in au.pair_states(["TVL-C01"])} == {"reviewed"}
    assert {s["status"] for s in au.pair_states(["TVL-C05"])} == {"pending"}
    run(tmp_path, FILES, ["plan", "--checks", "C01", "--role", "meta"])
    st = ca.Audit(tmp_path, tracked=sorted(FILES)).pair_states(["TVL-C01"])
    auto = [s for s in st if s["status"] == "closed"]
    assert all(s["meta"]["reviewer"] == "sampling" for s in auto)
    left = [s for s in st if s["status"] == "reviewed"]  # sampled ones await a real second review
    assert len(auto) + len(left) == len(st)
    capsys.readouterr()
    assert run(tmp_path, FILES, ["coverage", "--strict"]) == 1
    assert "auto(not sampled)=" in capsys.readouterr().out


# ------------------------------------------------------------------ script checks
def test_s01_links_and_anchors(tmp_path):
    files = {
        "docs/x.md": "# Big Title\n\n## Sub: Part `two`\n\nBody text is long enough here.\n",
        "docs/y.md": (
            "See [good](x.md#sub-part-two) and [ok](x.md) and [self](#local-head) for this.\n\n"
            "See [bad file](nope.md) for this paragraph now.\n\n"
            "See [bad anchor](x.md#missing) for this paragraph now.\n\n"
            "See [web](https://example.com/a) for this paragraph now.\n\n"
            "## Local head\n"
        ),
    }
    au = make_repo(tmp_path, files)
    units = {u["start_line"]: u for u in au.units() if u["path"] == "docs/y.md"}
    assert ca.check_links(au, units[1])[0] == "pass"
    assert ca.check_links(au, units[3])[0] == "issue"
    assert ca.check_links(au, units[5])[0] == "issue"
    assert ca.check_links(au, units[7])[0] == "pass"
    assert len(ca.check_links(au, units[3])[1].split()) >= 8


def test_s02_vocabulary_exemption(tmp_path):
    files = {"a.md": "TVL is guaranteed to be a shield for you.\n\nThe banned words are guaranteed and shield here.\n\nA clean sentence with enough words.\n"}
    au = make_repo(tmp_path, files)
    us = au.units()
    assert ca.check_banned(au, us[0])[0] == "issue"
    assert ca.check_banned(au, us[1])[0] == "pass"
    assert ca.check_banned(au, us[2])[0] == "pass"
    assert run(tmp_path, files, ["run-script-checks"]) == 0
    led = ca.read_jsonl(tmp_path / "audit" / "ledger.jsonl")
    assert {r["reviewer"] for r in led} == {"script:TVL-S01", "script:TVL-S02"}
    st = ca.Audit(tmp_path, tracked=sorted(files)).pair_states(["TVL-S02"])
    assert {s["status"] for s in st} == {"closed"}
    assert len(ca.open_issues(ca.Audit(tmp_path, tracked=sorted(files)))) == 1


# ------------------------------------------------------------------ compact
def test_compact(tmp_path):
    files = {"a.md": "Alpha paragraph has plenty of words.\n"}
    make_repo(tmp_path, files)
    run(tmp_path, files, ["run-script-checks"])
    n = len(ca.read_jsonl(tmp_path / "audit" / "ledger.jsonl"))
    assert n == 2
    files2 = {"a.md": "Alpha paragraph has changed words now.\n"}
    (tmp_path / "a.md").write_text(files2["a.md"])
    run(tmp_path, files2, ["compact"])
    assert ca.read_jsonl(tmp_path / "audit" / "ledger.jsonl") == []
    assert len(ca.read_jsonl(tmp_path / "audit" / "ledger-history.jsonl")) == 2
    # check version bump also moves records
    run(tmp_path, files2, ["run-script-checks"])
    cfg = yaml.safe_load((tmp_path / "audit" / "checks.yml").read_text())
    cfg["checks"][3]["version"] = 2
    (tmp_path / "audit" / "checks.yml").write_text(yaml.safe_dump(cfg))
    run(tmp_path, files2, ["compact"])
    assert len(ca.read_jsonl(tmp_path / "audit" / "ledger.jsonl")) == 1


# ------------------------------------------------------------------ v2: sampling, exclusions, bound, ids
def _beta_cdf_numeric(x, a, b, steps=20000):
    """Regularized incomplete beta I_x(a,b) by Simpson integration of the pdf (independent of the binomial sum)."""
    from math import lgamma, exp, log
    if x <= 0:
        return 0.0
    c = lgamma(a + b) - lgamma(a) - lgamma(b)
    def f(t):
        return exp(c + (a - 1) * log(t) + (b - 1) * log(1 - t)) if 0 < t < 1 else 0.0

    h = x / steps
    tot = f(1e-300 if a < 1 else 0) + f(x)
    for i in range(1, steps):
        tot += (4 if i % 2 else 2) * f(i * h)
    return tot * h / 3


def _cp_upper_beta(k, n, alpha=0.05):
    # P(X<=k | n, p) = I_{1-p}(n-k, k+1); solve for p by bisection
    lo, hi = 0.0, 1.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if _beta_cdf_numeric(1 - mid, n - k, k + 1) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@pytest.mark.parametrize("k,n", [(0, 10), (1, 10), (9, 121), (3, 47), (0, 1)])
def test_clopper_pearson_cross_check(k, n):
    assert abs(ca.cp_upper(k, n) - _cp_upper_beta(k, n)) < 2e-4


def test_clopper_pearson_known_values():
    assert round(ca.cp_upper(0, 10), 4) == 0.2589          # 1 - 0.05**(1/10)
    assert abs(ca.cp_upper(0, 59) - (1 - 0.05 ** (1 / 59))) < 1e-9
    assert ca.cp_upper(5, 5) == 1.0 and ca.cp_upper(0, 0) == 1.0


def test_per_check_sampling_mod_auto_record_and_exclusions(tmp_path):
    files = {"CHANGELOG.md": "Changelog entry with plenty of words.\n", "a.md": "Alpha paragraph has plenty of words.\n\nBeta paragraph has plenty of words.\n"}
    make_repo(tmp_path, files)
    cfg = yaml.safe_load((tmp_path / "audit" / "checks.yml").read_text())
    for c in cfg["checks"]:
        if c["id"] == "TVL-C05":
            c["exclude_paths"] = ["CHANGELOG.md"]
            c["meta_sample_mod"] = 1  # every pass sampled
        if c["id"] == "TVL-C01":
            c["meta_sample_mod"] = 1000000007  # almost none sampled
    (tmp_path / "audit" / "checks.yml").write_text(yaml.safe_dump(cfg))
    st = ca.Audit(tmp_path, tracked=sorted(files)).pair_states(["TVL-C05"])
    assert {s["unit"]["path"] for s in st} == {"a.md"}
    ca.main(["--root", str(tmp_path), "plan", "--checks", "C01,C05"], tracked=sorted(files))
    for b in sorted((tmp_path / "audit" / "batches").glob("*.json")):
        d = json.loads(b.read_text())
        res = [{"unit_id": u, "check_id": c, "verdict": "pass", "finding": "", "evidence": "no factual claim"} for u, c in d["pairs"]]
        rp = tmp_path / "r.json"
        rp.write_text(json.dumps({"batch_id": d["batch_id"], "reviewer": "s", "role": "review", "results": res}))
        assert ca.main(["--root", str(tmp_path), "record", str(rp)], tracked=sorted(files)) == 0
    ca.main(["--root", str(tmp_path), "plan", "--checks", "C01,C05", "--role", "meta"], tracked=sorted(files))
    led = ca.read_jsonl(tmp_path / "audit" / "ledger.jsonl")
    autos = [r for r in led if r["role"] == "meta"]
    assert autos and all(r["reviewer"] == "sampling" and r["sample_mod"] == 1000000007 and r["check_id"] == "TVL-C01" for r in autos)
    assert not any(r.get("check_id") == "TVL-C05" and r["role"] == "meta" for r in led)  # C05 all sampled, none auto
    assert "sample_mod" not in [r for r in led if r["role"] == "review"][0]


def test_coverage_overturn_and_json(tmp_path, capsys):
    files = {"a.md": "Alpha paragraph has plenty of words.\n\nBeta paragraph has plenty of words.\n"}
    au = make_repo(tmp_path, files)
    recs = []
    for i, u in enumerate(au.units()):
        rev = ca.make_record(unit_id=u["unit_id"], text_hash=u["text_hash"], check_id="TVL-C01", check_version=1, verdict="pass",
                             role="review", reviewer="s", batch_id="b", evidence="e")
        meta = ca.make_record(unit_id=u["unit_id"], text_hash=u["text_hash"], check_id="TVL-C01", check_version=1,
                              verdict="issue" if i == 0 else "pass", role="meta", reviewer="sol", batch_id="m",
                              finding="disagree: the claim is wrong against the authority text", evidence="x:1", corrects=rev["record_id"])
        recs += [rev, meta]
    ca.append_jsonl(tmp_path / "audit" / "ledger.jsonl", recs)
    d = ca.coverage_data(ca.Audit(tmp_path, tracked=sorted(files)))
    o = d["overturn"]["TVL-C01"]
    assert (o["k"], o["n"]) == (1, 2) and abs(o["upper95"] - ca.cp_upper(1, 2)) < 1e-12
    assert d["overturn"]["TVL-C05"]["n"] == 0
    ca.main(["--root", str(tmp_path), "coverage", "--json"], tracked=sorted(files))
    assert json.loads(capsys.readouterr().out)["overturn"]["TVL-C01"]["k"] == 1


def test_batch_ids_never_reused(tmp_path):
    au = make_repo(tmp_path, {"a.md": "Alpha paragraph has plenty of words.\n"})
    ids = []
    for _ in range(5):
        bid = ca.next_batch_id(au, "review")
        assert len(bid.split("-")[1]) == 14
        ids.append(bid)
        # even if a batch file is deleted, the id is not reissued
    assert len(set(ids)) == 5


# ------------------------------------------------------------------ second round (resample)
def _seed_reviews(tmp_path, files, verdicts):
    """verdicts: {(check_id, index): ('pass'|'issue', 'auto'|None)}; returns (au, review records by (check, idx))."""
    au = ca.Audit(tmp_path, tracked=sorted(files))
    units = au.units()
    recs, revs = [], {}
    for (cid, i), (verdict, auto) in verdicts.items():
        u = units[i]
        rev = ca.make_record(unit_id=u["unit_id"], text_hash=u["text_hash"], check_id=cid, check_version=1, verdict=verdict,
                             role="review", reviewer="s", batch_id="b", finding="this finding has more than eight words in it",
                             evidence="e")
        recs.append(rev)
        revs[(cid, i)] = rev
        if auto:
            recs.append(ca.make_record(unit_id=u["unit_id"], text_hash=u["text_hash"], check_id=cid, check_version=1, verdict=verdict,
                                       role="meta", reviewer="sampling", batch_id="m", finding="not sampled", corrects=rev["record_id"],
                                       sample_mod=5))
    ca.append_jsonl(tmp_path / "audit" / "ledger.jsonl", recs)
    return au, revs


RS_FILES = {"a.md": "Alpha paragraph has plenty of words.\n\nBeta paragraph has plenty of words.\n\nGamma paragraph has plenty of words.\n"}


def test_resample_selection_supersession_and_counts(tmp_path, capsys):
    make_repo(tmp_path, RS_FILES)
    _, revs = _seed_reviews(tmp_path, RS_FILES, {
        ("TVL-C01", 0): ("pass", "auto"),   # selected
        ("TVL-C01", 1): ("pass", "auto"),   # selected
        ("TVL-C01", 2): ("pass", None),     # reviewed only: not a resample candidate
        ("TVL-C05", 0): ("pass", "auto"),   # check not listed
    })
    ca.main(["--root", str(tmp_path), "plan", "--role", "meta", "--resample", "C01"], tracked=sorted(RS_FILES))
    b = json.loads(last_batch(tmp_path).read_text())
    assert b["role"] == "meta" and len(b["pairs"]) == 2 and {p[1] for p in b["pairs"]} == {"TVL-C01"}
    assert {r["record_id"] for r in b["reviews"]} == {revs[("TVL-C01", 0)]["record_id"], revs[("TVL-C01", 1)]["record_id"]}
    # no new auto-meta records were written by the resample plan
    assert len([r for r in ca.read_jsonl(tmp_path / "audit" / "ledger.jsonl") if r["role"] == "meta"]) == 3
    # real metas: one agrees, one overturns
    res = [
        {"unit_id": revs[("TVL-C01", 0)]["unit_id"], "check_id": "TVL-C01", "verdict": "pass", "finding": "agree: fine", "evidence": "e", "corrects": revs[("TVL-C01", 0)]["record_id"]},
        {"unit_id": revs[("TVL-C01", 1)]["unit_id"], "check_id": "TVL-C01", "verdict": "issue", "finding": "disagree: the statement is wrong and the authority says otherwise", "evidence": "x:1", "corrects": revs[("TVL-C01", 1)]["record_id"]},
    ]
    rp = tmp_path / "r.json"
    rp.write_text(json.dumps({"batch_id": b["batch_id"], "reviewer": "sol", "role": "meta", "results": res}))
    assert ca.main(["--root", str(tmp_path), "record", str(rp)], tracked=sorted(RS_FILES)) == 0
    au = ca.Audit(tmp_path, tracked=sorted(RS_FILES))
    st = {s["unit"]["start_line"]: s for s in au.pair_states(["TVL-C01"])}
    assert st[1]["status"] == "closed" and st[1]["meta"]["reviewer"] == "sol" and st[1]["resampled"] and st[1]["verdict"] == "pass"
    assert st[3]["verdict"] == "issue" and st[3]["disputed"] and st[3]["resampled"]
    d = ca.coverage_data(au)
    o = d["overturn"]["TVL-C01"]
    assert (o["k"], o["n"], o["resampled"], o["sampled_first_round"], o["auto_accepted_passes"]) == (1, 2, 2, 0, 0)
    assert d["meta_closed_resampled"] == 2 and d["meta_closed_auto"] == 1
    assert d["overturn"]["TVL-C05"]["auto_accepted_passes"] == 1
    # planning again selects nothing for C01; the reviewed-only pair is untouched
    before = len(list((tmp_path / "audit" / "batches").glob("*.json")))
    ca.main(["--root", str(tmp_path), "plan", "--role", "meta", "--resample", "C01"], tracked=sorted(RS_FILES))
    assert len(list((tmp_path / "audit" / "batches").glob("*.json"))) == before
    capsys.readouterr()
    ca.main(["--root", str(tmp_path), "coverage"], tracked=sorted(RS_FILES))
    out = capsys.readouterr().out
    assert "resampled=2" in out and "resampled" in out.split("Meta overturn")[1]


def test_resample_requires_meta_role(tmp_path):
    make_repo(tmp_path, RS_FILES)
    with pytest.raises(SystemExit):
        ca.main(["--root", str(tmp_path), "plan", "--resample", "C01"], tracked=sorted(RS_FILES))


def test_auto_meta_never_supersedes_real_meta(tmp_path):
    make_repo(tmp_path, RS_FILES)
    au, revs = _seed_reviews(tmp_path, RS_FILES, {("TVL-C01", 0): ("pass", None)})
    rev = revs[("TVL-C01", 0)]
    real = ca.make_record(unit_id=rev["unit_id"], text_hash=rev["text_hash"], check_id="TVL-C01", check_version=1, verdict="issue",
                          role="meta", reviewer="sol", batch_id="m1", finding="disagree: wrong", evidence="x", corrects=rev["record_id"])
    auto = ca.make_record(unit_id=rev["unit_id"], text_hash=rev["text_hash"], check_id="TVL-C01", check_version=1, verdict="pass",
                          role="meta", reviewer="sampling", batch_id="m2", finding="not sampled", corrects=rev["record_id"], sample_mod=5)
    ca.append_jsonl(tmp_path / "audit" / "ledger.jsonl", [real, auto])  # auto written after the real one
    s = ca.Audit(tmp_path, tracked=sorted(RS_FILES)).pair_states(["TVL-C01"])[0]
    assert s["meta"]["reviewer"] == "sol" and s["verdict"] == "issue" and s["resampled"]


# ------------------------------------------------------------------ fix phase: adjudicate / confirm / gate
AJ_FILES = {"a.md": "Alpha paragraph has plenty of words.\n\nBeta paragraph has plenty of words.\n\nGamma paragraph has plenty of words.\n"}
ISSUE_F = "this statement clearly contradicts the formal semantics document"


def _issue_setup(tmp_path):
    """Three units, TVL-C01 issue on each (closed by auto-style meta agreeing); other pairs left pending."""
    make_repo(tmp_path, AJ_FILES)
    au = ca.Audit(tmp_path, tracked=sorted(AJ_FILES))
    recs, closing = [], {}
    for u in au.units():
        rev = ca.make_record(unit_id=u["unit_id"], text_hash=u["text_hash"], check_id="TVL-C01", check_version=1, verdict="issue",
                             role="review", reviewer="s", batch_id="b", finding=ISSUE_F, evidence="x:1")
        meta = ca.make_record(unit_id=u["unit_id"], text_hash=u["text_hash"], check_id="TVL-C01", check_version=1, verdict="issue",
                              role="meta", reviewer="sol", batch_id="m", finding="agree: " + ISSUE_F, evidence="x:1", corrects=rev["record_id"])
        recs += [rev, meta]
        closing[u["start_line"]] = (u, meta)
    ca.append_jsonl(tmp_path / "audit" / "ledger.jsonl", recs)
    return closing


def _adj(tmp_path, items, reviewer="opus"):
    f = tmp_path / "disp.json"
    f.write_text(json.dumps(items))
    return ca.main(["--root", str(tmp_path), "adjudicate", str(f), "--reviewer", reviewer], tracked=sorted(AJ_FILES))


def _item(u, disp, **kw):
    d = {"unit_id": u["unit_id"], "check_id": "TVL-C01", "path": u["path"], "disposition": disp, "note": "the text is right", "evidence": "x.md:5"}
    d.update(kw)
    return d


def _states(tmp_path):
    return {s["unit"]["start_line"]: s for s in ca.Audit(tmp_path, tracked=sorted(AJ_FILES)).pair_states(["TVL-C01"])}


def test_adjudicate_records_rejected_and_owner_not_fixed(tmp_path):
    cl = _issue_setup(tmp_path)
    (u1, m1), (u3, m3), (u5, _) = cl[1], cl[3], cl[5]
    assert _adj(tmp_path, [_item(u1, "rejected"), _item(u3, "owner_decision"), _item(u5, "fixed")]) == 0
    led = [r for r in ca.read_jsonl(tmp_path / "audit" / "ledger.jsonl") if r["role"] == "adjudicate"]
    assert len(led) == 2
    by = {r["adjudication"]: r for r in led}
    assert by["rejected"]["verdict"] == "pass" and by["rejected"]["corrects"] == m1["record_id"]
    assert by["owner_decision"]["verdict"] == "issue" and by["owner_decision"]["corrects"] == m3["record_id"]
    assert by["rejected"]["finding"] == "the text is right" and by["rejected"]["evidence"] == "x.md:5"


def test_adjudicate_rejects_whole_file_on_error(tmp_path, capsys):
    cl = _issue_setup(tmp_path)
    u1, u3 = cl[1][0], cl[3][0]
    bad = [_item(u1, "rejected"), _item(u3, "rejected", unit_id="deadbeefdeadbeef"), _item(u3, "owner_decision", note=""),
           _item(u3, "weird")]
    assert _adj(tmp_path, bad) == 1
    err = capsys.readouterr().err
    assert err.count("  - ") == 3
    assert not [r for r in ca.read_jsonl(tmp_path / "audit" / "ledger.jsonl") if r["role"] == "adjudicate"]
    # a fixed item whose unit changed/unknown is fine
    assert _adj(tmp_path, [_item(u1, "fixed", unit_id="0000000000000000")]) == 0


def test_rejection_open_until_confirmed_then_pass(tmp_path, capsys):
    cl = _issue_setup(tmp_path)
    u1 = cl[1][0]
    _adj(tmp_path, [_item(u1, "rejected")])
    assert _states(tmp_path)[1]["verdict"] == "issue"            # unconfirmed rejection still counts as open
    assert len([i for i in ca.open_issues(ca.Audit(tmp_path, tracked=sorted(AJ_FILES))) if i["unit_id"] == u1["unit_id"]]) == 1
    ca.main(["--root", str(tmp_path), "plan", "--role", "confirm"], tracked=sorted(AJ_FILES))
    b = json.loads(last_batch(tmp_path).read_text())
    assert b["role"] == "confirm" and b["pairs"] == [[u1["unit_id"], "TVL-C01"]]
    adj_id = b["reviews"][0]["record_id"]
    res = {"unit_id": u1["unit_id"], "check_id": "TVL-C01", "verdict": "disagree", "finding": "short", "evidence": "e", "corrects": adj_id}
    rp = tmp_path / "c.json"
    def sub(r):
        rp.write_text(json.dumps({"batch_id": b["batch_id"], "reviewer": "sol", "role": "confirm", "results": [r]}))
        return ca.main(["--root", str(tmp_path), "record", str(rp)], tracked=sorted(AJ_FILES))
    assert sub(res) == 1                                           # disagree needs a real finding
    assert sub(dict(res, verdict="agree", finding="agree: fixer is right", corrects="nope")) == 1
    assert sub(dict(res, verdict="disagree", finding="the original issue stands because the semantics file says otherwise")) == 0
    s = _states(tmp_path)[1]
    assert s["verdict"] == "issue" and s["confirm"]["verdict"] == "issue"       # disagree: stays issue
    # a fresh adjudication replaces; confirm again with agree
    _adj(tmp_path, [_item(u1, "rejected", note="the text is right, see section")])
    assert _states(tmp_path)[1]["confirm"] is None
    ca.main(["--root", str(tmp_path), "plan", "--role", "confirm"], tracked=sorted(AJ_FILES))
    b = json.loads(last_batch(tmp_path).read_text())
    res = {"unit_id": u1["unit_id"], "check_id": "TVL-C01", "verdict": "agree", "finding": "agree: rejection is right", "evidence": "e", "corrects": b["reviews"][0]["record_id"]}
    rp.write_text(json.dumps({"batch_id": b["batch_id"], "reviewer": "sol", "role": "confirm", "results": [res]}))
    assert ca.main(["--root", str(tmp_path), "record", str(rp)], tracked=sorted(AJ_FILES)) == 0
    assert _states(tmp_path)[1]["verdict"] == "pass"
    assert u1["unit_id"] not in [i["unit_id"] for i in ca.open_issues(ca.Audit(tmp_path, tracked=sorted(AJ_FILES)))]
    # nothing left to confirm
    n = len(list((tmp_path / "audit" / "batches").glob("*.json")))
    ca.main(["--root", str(tmp_path), "plan", "--role", "confirm"], tracked=sorted(AJ_FILES))
    assert len(list((tmp_path / "audit" / "batches").glob("*.json"))) == n


def test_owner_decision_reported_separately_and_not_open(tmp_path, capsys):
    cl = _issue_setup(tmp_path)
    u3 = cl[3][0]
    _adj(tmp_path, [_item(u3, "owner_decision", note="needs the owner to pick wording")])
    au = ca.Audit(tmp_path, tracked=sorted(AJ_FILES))
    assert u3["unit_id"] not in [i["unit_id"] for i in ca.open_issues(au)]
    od = ca.owner_decisions(au)
    assert [o["unit_id"] for o in od] == [u3["unit_id"]]
    capsys.readouterr()
    ca.main(["--root", str(tmp_path), "report", "--format", "json"], tracked=sorted(AJ_FILES))
    j = json.loads(capsys.readouterr().out)
    assert len(j["owner_decisions"]) == 1 and len(j["open_issues"]) == 2
    ca.main(["--root", str(tmp_path), "report", "--write"], tracked=sorted(AJ_FILES))
    assert "# Owner decisions" in (tmp_path / "audit" / "REPORT.md").read_text()


def test_strict_gate_needs_no_open_issues(tmp_path, capsys):
    """Single check, single unit: closed pair with an issue fails strict; owner_decision passes and is printed."""
    files = {"a.md": "Alpha paragraph has plenty of words.\n"}
    make_repo(tmp_path, files)
    cfg = yaml.safe_load((tmp_path / "audit" / "checks.yml").read_text())
    cfg["checks"] = [c for c in cfg["checks"] if c["id"] == "TVL-C01"]
    (tmp_path / "audit" / "checks.yml").write_text(yaml.safe_dump(cfg))
    au = ca.Audit(tmp_path, tracked=sorted(files))
    u = au.units()[0]
    rev = ca.make_record(unit_id=u["unit_id"], text_hash=u["text_hash"], check_id="TVL-C01", check_version=1, verdict="issue",
                         role="review", reviewer="s", batch_id="b", finding=ISSUE_F, evidence="x:1")
    meta = ca.make_record(unit_id=u["unit_id"], text_hash=u["text_hash"], check_id="TVL-C01", check_version=1, verdict="issue",
                          role="meta", reviewer="sol", batch_id="m", finding="agree: " + ISSUE_F, evidence="x:1", corrects=rev["record_id"])
    ca.append_jsonl(tmp_path / "audit" / "ledger.jsonl", [rev, meta])
    def run():
        return ca.main(["--root", str(tmp_path), "coverage", "--strict"], tracked=sorted(files))

    assert run() == 1
    f = tmp_path / "d.json"
    f.write_text(json.dumps([{"unit_id": u["unit_id"], "check_id": "TVL-C01", "path": "a.md", "disposition": "owner_decision", "note": "owner picks", "evidence": "e"}]))
    assert ca.main(["--root", str(tmp_path), "adjudicate", str(f)], tracked=sorted(files)) == 0
    capsys.readouterr()
    assert run() == 0
    assert "OWNER DECISION" in capsys.readouterr().out


def _s02(text):
    return ca.check_banned(None, {"path": "a.md", "start_line": 1, "text": text})[0]


def test_s02_ignores_urls_but_flags_prose():
    badge = '[![x](https://img.shields.io/badge/a-b-green)](https://example.com/shield) <img src="https://img.shields.io/x.svg"> https://shields.io/q'
    assert _s02(badge) == "pass"
    assert _s02("TVL is a shield for your specs.") == "issue"
    assert _s02("See [the shield page](https://example.com/p) for more.") == "issue"
