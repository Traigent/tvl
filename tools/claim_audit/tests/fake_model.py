"""Fake model for runner tests. argv: mode [prompt]. Prompt comes from stdin or argv[2]."""
import json
import os
import re
import sys

mode = sys.argv[1]
prompt = sys.argv[2] if len(sys.argv) > 2 else sys.stdin.read()
m = re.search(r"Batch file \(absolute path, read it first\): (\S+)", prompt)
with open(m.group(1)) as fh:
    batch = json.load(fh)
state = os.environ["FAKE_STATE"]
n = 0
if os.path.exists(state):
    with open(state) as fh:
        n = int(fh.read())
with open(state, "w") as fh:
    fh.write(str(n + 1))
role = batch["role"]
results = []
if role == "review":
    for uid, cid in batch["pairs"]:
        results.append({"unit_id": uid, "check_id": cid, "verdict": "pass", "finding": "", "evidence": "no factual claim"})
elif role == "confirm":
    for r in batch["reviews"]:
        results.append({"unit_id": r["unit_id"], "check_id": r["check_id"], "verdict": "agree",
                        "finding": "agree: fixer is right", "evidence": "e", "corrects": r["record_id"]})
else:
    for r in batch["reviews"]:
        results.append({"unit_id": r["unit_id"], "check_id": r["check_id"], "verdict": r["verdict"],
                        "finding": "agree: matches the authority", "evidence": r["evidence"] or "e", "corrects": r["record_id"]})
out = {"batch_id": batch["batch_id"], "reviewer": "x", "role": role, "results": results}
bad = {"batch_id": batch["batch_id"], "reviewer": "x", "role": role,
       "results": [{"unit_id": "nope", "check_id": "TVL-C01", "verdict": "pass", "evidence": "e"}]}
retry = "previous output was rejected" in prompt
if mode == "bad" or (mode == "bad_then_ok" and not retry):
    out = bad
if mode == "garbage":
    print("I cannot do this")
    sys.exit(0)
text = "Here you go:\n```json\n" + json.dumps(out) + "\n```\n"
if mode == "claudejson":
    print(json.dumps({"result": text, "usage": {"input_tokens": 10, "output_tokens": 5}, "total_cost_usd": 0.01}))
else:
    print(text + "\ntokens used\n1,234")
