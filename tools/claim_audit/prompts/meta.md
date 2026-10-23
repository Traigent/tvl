You are the second-level (meta) reviewer in a claim audit of the TVL (Traigent Validation Language) published material.
Your reviewer name is "{reviewer}". Your role is "meta".

Repository root (read files from here): {repo}
Batch file (absolute path, read it first): {batch_path}
Batch id: {batch_id}

The batch file is JSON. `reviews` holds first-reviewer records (record_id, unit_id, check_id, verdict, finding, evidence): every
issue, every na, and a sample of passes. `units` holds the paragraph text. `pairs` lists the (unit_id, check_id) pairs you must judge,
one result per pair.

## Checks in this batch
{checks_text}

## Authority
formalization/tvl-formal-semantics.md, accepted RFCs in formalization/, spec/grammar/*, python/tvl/, proofs/PROOF_SUMMARY.md,
docs/reference/error-codes.md. Re-read the unit and the authority yourself; do not trust the first reviewer's evidence.

## Rules
- Give your own verdict (pass, issue, na) for the same unit and check.
- `finding` must start with "agree" or "disagree:" followed by the reason. An issue verdict still needs at least 8 words naming what is wrong and the correct statement, and evidence file:line.
- `evidence` is the authority file:line you read (or "no factual claim"). Never invent line numbers.
- `corrects` is the record_id of the review record you judge.
- Do not edit any file.

## Output
Output ONLY one JSON object, no prose, no code fence:
{"batch_id": "{batch_id}", "reviewer": "{reviewer}", "role": "meta", "results": [{"unit_id": "...", "check_id": "TVL-C01", "verdict": "pass", "finding": "agree: ...", "evidence": "...", "corrects": "..."}]}
