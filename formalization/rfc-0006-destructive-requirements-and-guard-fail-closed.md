# RFC 0006 — Destructive requirements: a guard on a destructive action must fail closed

| | |
|---|---|
| **Status** | **DRAFT** — not accepted; syntax, codes and meaning may change before acceptance |
| **Target language version** | TVL 1.6 (conservative extension of 1.5) |
| **Tracking** | not assigned |
| **Builds on** | RFC 0003 (Accepted, TVL 1.3), RFC 0004 (Accepted, TVL 1.4) |
| **Companion** | [formal semantics §12](tvl-formal-semantics.md) (local guards, `on_check_error`); no new section is written yet |
| **Conformance** | `conformance/cases/runtime/lints/` (cases sketched in §5; none exist yet) |

## 1. Motivation

A local guard (`block_action`, `halt_unit`) carries a mandatory `on_check_error`: `block` fails closed, `allow`
lets the action proceed and records the unit as unresolved (RFC 0003 §7.5). Both values are valid for every rule.

For a guard in front of a destructive action (deleting a customer, running a write query), `allow` means that
whenever the guard cannot establish the unit's population or the violation, the destructive action goes ahead. Today
nothing in TVL can tell such a rule from a harmless one, so nothing can refuse the unsafe combination. A reviewer has
to notice it by eye.

TVL has no way to say that a tool is destructive. The existing constructs do not cover it: `response_irreversible_without_approval`
concerns remote service effects such as `rollback` and `optimize`, not the tool a requirement watches; a requirement
selects tools only by name (`a: { event: tool_call, tool: crm.delete_customer }`), with no attribute on the tool.
A lint on tool names would be a guess, so this RFC proposes an explicit marker.

## 2. Design

### 2.1 The marker

A requirement whose predicate selects tool events may declare which of the selected tools are destructive. Proposed
form (names open, see §7):

```yaml
requirements:
  - name: no_crm_delete
    kind: zero_tolerance
    unit: invocation
    violation: { pattern: absence, a: { event: tool_call, tool: crm.delete_customer } }
    destructive: true        # proposed: the actions this requirement guards are destructive or irreversible
```

`destructive` is an optional boolean on a requirement, default `false`. It is a declaration by the author about the
world; TVL does not verify it. It adds no authority and changes no verdict.

### 2.2 The refusal

A response rule with `do: block_action` or `do: halt_unit` whose trigger monitor's requirement has `destructive: true`
must declare `on_check_error: block`. `on_check_error: allow` is refused with a new error,
`response_guard_destructive_requires_block` (proposed code), pointing at the rule's `on_check_error`.

The boolean cannot say which selected tools are destructive. Marking a requirement forces all of its local guards to use `on_check_error: block`, including guards on selected tools that are not destructive.

Rules on requirements without the marker are unchanged. The check is made where the existing `response_on_check_error_*`
checks are made (`python/tvl/lints.py`, local-guard branch near the `on_check_error` handling).

### 2.3 What is not changed

Evaluators already honour `on_check_error` (the Traigent SDK guard module and its JS port). This RFC adds no runtime
behaviour; for marked requirements it makes the unsafe document unrepresentable.

## 3. Compatibility

Conservative extension in syntax: every TVL 1.5 document that does not use `destructive` is valid with the same
meaning. Documents that use `destructive: true` are valid TVL 1.6 only. A document that declares `destructive: true`
and also has `on_check_error: allow` on a guard of that requirement is invalid in 1.6 by design; no 1.5 document can be
affected because the marker does not exist there. Tools that do not know the field must reject it as an unknown
requirement field (check against the schema's `additionalProperties` handling before acceptance).

## 4. Semantics and proofs

No change to Definitions 12.6-12.8. The marker has no semantics; it is an input to a static check. No Lean change is
proposed. The check is a syntactic property of the document, and this RFC does not claim it is formalized.

## 5. Conformance

Cases to add under `conformance/cases/runtime/lints/` (none written yet):

- positive: `destructive: true`, `block_action`, `on_check_error: block` is valid;
- positive: `destructive: true`, `halt_unit`, `on_check_error: block` is valid;
- positive: no marker, `on_check_error: allow` is valid (unchanged behaviour);
- negative: `destructive: true`, `block_action`, `on_check_error: allow` produces `response_guard_destructive_requires_block`;
- negative: same with `halt_unit`;
- negative: `destructive` not a boolean produces `schema_error` (documented in `docs/reference/error-codes.md`).

Schema, grammar, `docs/reference/error-codes.md`, the language reference and the requirements-monitors-responses guide
are updated when accepted.

## 6. Alternatives considered

- **A lint on tool-name patterns** (`delete`, `drop`, `write`): rejected; it guesses, misses `crm.purge` and flags
  `report.delete_draft`.
- **A marker on the tool event selector** (`a: { event: tool_call, tool: x, destructive: true }`): finer grained, but
  every protocol and precedence rule names tools in several places, so one requirement could disagree with itself.
- **Make `block` the only value for every guard**: removes a legitimate choice for non-destructive guards, and
  `allow` is the accepted behaviour of RFC 0003 §7.5.
- **Convention only, no TVL change**: leaves the unsafe combination expressible.

## 7. Open questions

- Name and level of the marker: a boolean on the requirement (proposed), a field on the tool selector, or an enum
  (`effect: read | write | destructive`) that could later serve other checks.
- Should a `destructive` requirement also forbid guard-less coverage, that is, require at least one `block_action` or
  `halt_unit` response? This RFC does not propose it.
- Should the check be an error (proposed) or a warning for one release?
