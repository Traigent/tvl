# TVL claim audit protocol

## Purpose
Prove that every paragraph of TVL's published material was checked by every registered check,
record who checked what, and on reruns schedule only the (paragraph, check) pairs that are new
or stale. Everything lives under `audit/`; the tool is `tools/claim_audit/claim_audit.py`.

## Units and checks
- A **unit** is one paragraph, heading, table, code block, list or admonition of a corpus file
  (`audit/corpus.yml`, resolved over `git ls-files`). Its id is a hash of path + normalized text +
  a duplicate ordinal. Moving unchanged text keeps its id. Editing the text creates a new id, so
  all its pairs become pending again.
- A **check** is an entry in `audit/checks.yml` with an id, an integer version, a kind (`model`
  for a reviewer, `script` for code) and the unit kinds it applies to.
- A ledger record for an older text hash or older check version is history, never coverage.

## Adding or rerunning a check
Append a new check with a new id to `checks.yml`, or bump the `version` of an existing one to
force every unit to be rechecked. Nothing else needs to change; `plan` finds the new pending pairs.

## Flow
1. `claim_audit.py inventory` regenerates `audit/units.jsonl`.
2. `claim_audit.py run-script-checks` records the script checks (S01 links, S02 banned words).
   Script pairs are closed by their review record and need no meta-review.
3. `claim_audit.py plan --checks C01,C02,C03,C04,C05` writes `audit/batches/B-<date>-<seq>-review.json`.
   A first reviewer (for example "sonnet") judges every listed unit and check and writes a results
   file: `{batch_id, reviewer, role, results:[{unit_id, check_id, verdict, finding, evidence}]}`.
   `claim_audit.py record <results.json>` validates it (the whole file is rejected on any error)
   and appends to `audit/ledger.jsonl`.
4. `claim_audit.py plan --role meta` selects second-level review. A second reviewer of a different
   vendor (for example "sol") judges every `issue`, every `na`, and a deterministic sample of
   passes: a pass is sampled when `int(record_id, 16) % meta_sample_mod == 0`, where `meta_sample_mod` is set per check in
   `checks.yml` (currently C01 2, C02 2, C03 3, C04 5, C05 5; default 5). The rule replaces "all passes". Pairs that were not sampled are closed by `plan --role meta` itself with
   an `auto-meta` record (reviewer "sampling", role meta, verdict equal to the review verdict,
   finding "not sampled; review accepted under the 1-in-N sampling rule", and a `sample_mod` field recording N; older auto-meta records written under the former flat 1-in-5 rule have no such field and stay valid as history of that rule). `coverage` prints how many
   closed pairs were really sampled and how many were closed automatically.
   Meta results set `corrects` to the review `record_id` they judge and carry their own verdict;
   on disagreement the meta verdict wins and reports mark the pair `disputed`.

Status of a pair: pending (no matching review), reviewed (model check with no meta), closed
(script review, or model review with a meta record).

## Second round: resampling auto-accepted passes
Why: sampling accepts most passes without a second look, and `coverage` bounds how many issues may hide there
(the "hidden issues <=" column, upper bound x auto-accepted passes). When that bound is high for a check, because
the sampled overturn rate is high or because n is small (a wide Clopper-Pearson interval), spend more meta
review on that check rather than accepting the bound.

How: `claim_audit.py plan --role meta --resample TVL-C01,TVL-C02,TVL-C05` selects current review records with
verdict `pass` whose only meta is an auto-meta (reviewer "sampling") and plans real meta batches for them
(same split into batches of about 60 records). It writes no ledger records. Record the results as usual
(`record`), or run `run_reviews.py --resample TVL-C01,TVL-C02,TVL-C05`, which runs only these meta batches
(no review batches) with the normal meta prompt, logging and stop rules (`--max-batches` then counts meta batches).

Supersession: a real meta record for the same review supersedes the auto-meta. Closure and verdict use the latest
real meta (an auto-meta written later never replaces a real one); a differing verdict is marked `disputed`.
`coverage` prints sampled / resampled / auto per check: sampled = real meta from the first round, resampled =
real meta that superseded an auto-meta, auto = still only auto-accepted. The overturn estimate (k/n, upper
bound) uses all real metas, sampled and resampled. Resampled passes were chosen because they were not sampled,
so pooling them is an approximation, but it can only tighten the bound on the remaining auto-accepted passes.

## Per-check path exclusions
`exclude_paths` (globs) in `checks.yml` removes a check from matching files entirely (for example C05 is not applied to CHANGELOG.md, whose terseness is by design). Excluded pairs are not counted in coverage; existing records stay in the ledger.

## Batch ids
Batch ids are `B-<yyyymmddHHMMSS>-<seq>-<role>` and are never reused: every issued id is appended to `audit/batches/ISSUED.txt` and ids in the ledger or batch folder are skipped.

## Fixing issues
Edit the text. The edited unit gets a new id, its pairs become pending, and only those are
re-planned. Run `compact` afterwards to move history records to `audit/ledger-history.jsonl`.

## Fix phase: dispositions, adjudication, confirmation, owner decisions
1. A fixer works through the open issues and writes a dispositions file: a JSON list of
   `{unit_id, check_id, path, disposition, note, evidence}` with `disposition` one of `fixed`, `rejected`
   (the finding is wrong, the text stands) or `owner_decision` (needs the owner).
2. `claim_audit.py adjudicate <dispositions.json> --reviewer opus` records `rejected` and `owner_decision` items as
   role `adjudicate` records (`rejected` becomes verdict pass, `owner_decision` verdict issue; `adjudication` field;
   `corrects` = the closing meta or review record; finding = note). The whole file is rejected, with every error listed,
   if an item's unit text changed (only `fixed` items may refer to changed units), the pair has no closed issue,
   or note or evidence is missing. `fixed` items are not recorded: the edited unit gets a new id and is re-reviewed.
3. A rejection is final only after a second check. `plan --role confirm` lists rejections with no confirm record;
   a second reviewer (for example "sol") answers agree or disagree per item (`run_reviews.py --confirm` does this with
   `prompts/confirm.md`) and `record` stores role `confirm` (agree stores verdict pass, disagree stores issue and needs a
   finding of at least 8 words). Agree turns the pair's verdict into pass. Disagree leaves it an issue. Until confirmed,
   a rejected pair counts as an open issue.
4. `owner_decision` pairs are listed in an "Owner decisions" section of `report` (and REPORT.md; `report --format json`
   returns `{open_issues, owner_decisions}`). They do not count as open issues for the gate, and `coverage --strict`
   prints them.
5. Gate: `coverage --strict` passes only when no pair is pending or reviewed and there are no open issues
   (issues that are neither owner_decision nor a confirmed rejection).

## Release gate
`claim_audit.py coverage --strict` exits 0 (every applicable pair closed) and `claim_audit.py report`
shows zero open issues, or each remaining issue is carried as an explicit owner decision in
`audit/REPORT.md` (`report --write`).

## What this does not prove
A pass is a reviewer's judgment at one commit, not truth. Sampling means most passes
are second-checked only statistically; `coverage` reports, per model check, how many sampled passes the meta reviewer overturned (k/n), the exact one-sided 95% Clopper-Pearson upper bound on that rate, and the implied upper bound on hidden issues among auto-accepted passes. Pooling sampled passes across rule changes is an approximation. Script checks are syntactic: S01 confirms a link target
exists, not that it says what the text claims; S02 matches words, not meaning.
