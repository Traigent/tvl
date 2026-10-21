# RFC 0003 — Runtime Requirements, Monitors and Responses: a sealed catalogue for production assurance

| | |
|---|---|
| **Status** | **Accepted** 2026-10-21 (TVL 1.3.0). Design decisions D1–D5 recorded 2026-10-16 (§16.1); revision 2026-10-21 adds `optimize.deploy` (§7.6) and restricts `among` to checker predicates (§16.3 question 20) |
| **Target language version** | TVL 1.3 (conservative extension of 1.2) |
| **Tracking** | not assigned |
| **Builds on** | RFC 0001 (ACCEPTED): bindings, certificates, strict promotion, the shared namespace · RFC 0002 (ACCEPTED): closed shapes with exact diagnostics, sealed catalogues, shape-versus-registry layering |
| **Companion** | formal semantics §12 "Runtime Semantics (TVL 1.3)" in `formalization/tvl-formal-semantics.md`. **Division of authority:** §12 is the authority for meaning — unit predicates on complete histories, the verdict contract, populations and windows, episodes and obligations, the declarative meaning of responses, composition order, projection, denotation and theorem statements; this RFC is the authority for syntax, closed enums, lexical forms, diagnostic codes, document schemas and CLI contracts. §12 refers to §4.2 and §5 here instead of restating them |
| **Language and evaluators** | TVL states what a requirement means and what each verdict promises. Verdicts are produced by an **evaluator profile** outside TVL (§3.5). This RFC does not specify how an evaluator decides from partial evidence, how it tracks episodes and obligations, or how a controller executes responses |
| **Conformance** | language cases in `conformance/cases/runtime/` (format `tvl-runtime-case/1`; §13). Passing them shows that a toolchain parses, lints, composes, compiles and projects TVL 1.3; it enables no evaluator and authorizes no response action |
| **Downstream gates** | (1) acceptance of this RFC and of formal semantics §12 (a human-only gate); (2) the language theorems of §14 at their recorded status; (3) the language conformance families of §13 |

**Handles.** Claims about pre-existing TVL code cite `git show <ref>:<path>` line ranges with `T:` = tvl `0ff104d`.
Conformance case paths are relative to `conformance/cases/runtime/` in this repository. A claim without a handle is a
rule of this RFC, not a statement about existing code.

**Conservative readings.** Where a point is not settled by the design decisions of §16.1, this RFC takes the most
conservative reading (fail closed, `unres` or `UNKNOWN`, refusal of an unsupported construct) and lists the choice in
§16.

## 1. Motivation

TVL 1.2 governs what an agent configuration is allowed to be and how a candidate is promoted. It says nothing about
what the configuration must keep doing once it runs. Three production requirements motivate this RFC; each must be
expressible, checkable and acted upon:

1. **A latency rate bound.** "At most 5 % of production traces take longer than 2 s." A hosted requirement of this form
   already exists outside TVL: one requirement kind, evaluated per UTC window with exact one-sided Clopper–Pearson
   bounds, with breach episodes. TVL 1.3 makes it the first instance of the catalogue (§10).
2. **A zero-tolerance behavioural requirement.** "The agent never calls a forbidden tool", "a payment tool call is
   always preceded by an authorization", or, rate-bounded, "the agent refuses disallowed requests". These need the
   agent's events, and some need the customer's content, which never leaves the customer side (§8).
3. **A recovery time.** "After a breach, the requirement is met again within T hours."

Each requirement needs a **sampling rate, a window and alert conditions**, and a reaction ladder **log, warn, repair,
shut down**. In this RFC: log is the implicit `record`; warn is `notify`; repair is `open_next_step`, `optimize`,
`rollback`, `throttle`, `degrade`; shut down is `suspend` (§7.2).

**Why three blocks (D1).** A *requirement* states what must hold of a unit of behaviour. A *monitor* states which
evidence checks it, how often, and with what statistics. A *response* states what happens when a monitor emits an
event. Separating them gives three things a single `runtime:` block cannot:

- **One requirement, two evidence sources.** The same requirement can gate promotion on the evaluation set and run
  in production on live traces, with two monitors and no copy of the predicate (§3.2).
- **Independent composition.** Organisation floors (§9.4) add monitors and responses to a requirement without
  rewriting it; overlays tighten numbers without touching predicates (§9.1).
- **Unchanged promotion meaning by default.** A 1.2 chance constraint fails promotion whenever its Clopper–Pearson
  upper bound exceeds the threshold (`T:python/tvl/promotion.py:807-826,908-916`), so an inconclusive count rejects.
  A promotion monitor (§6.11) returns `NoDecision` in that case. Because monitors are opt-in, a module without them
  keeps today's gate exactly.

**What this RFC is not.** It adds no general temporal logic to the surface (temporal logic appears only as the
denotation of a sealed catalogue, §3.3), no sliding windows, no programmable remediation, and no change to the
structural or derived constraint semantics, the SMT encoding or ε-dominance (§6.1). It specifies no evaluator: TVL is
a specification language with a validator and a compiler (§3.5).

## 2. Scope

**In scope for TVL 1.3:**

- three optional module blocks `requirements`, `monitors`, `responses` and a separate `tvl_pack` document for
  organisation floors (§4);
- a sealed catalogue in three levels: unit predicates, one window rule with named decision methods, and episodes with
  recovery and evidence-liveness obligations (§3.3, §6);
- the meaning of every declaration on complete histories and the contract every verdict must satisfy (§6, formal
  semantics §12);
- the response ladder, its approval levels and the declarative meaning of each action (§7);
- the hosted projection and the evidence qualifications of a certificate (§8);
- composition and packs (§9);
- the backend profile `backend_v1`, which makes the hosted latency requirement the first instance of the catalogue
  (§10);
- versioning, readers, document schemas, CLI contracts, the registration boundary and language conformance
  (§11–§13).

**Outside TVL (specified by evaluator profiles, §3.5):** how a unit is classified from partial or unordered evidence;
how unresolved units enter a decision, and which partial-evidence conditions leave a window undecided; the selection
rule and commitment of committed sampling; report acceptance, deduplication, finalisation and corrections; episode and
obligation tracking over time, including revisions; response execution, control arbitration, controller state and
replay; registration and enablement on a platform.

**Deferred (not in 1.3):** sliding windows (reserved: 1.3 has no syntax for them, and any `window` key other than
`tumbling_hours` and `grace_minutes` is a schema error); anytime-valid sequential tests; heterogeneous-unit models; any
episode-level false-closure bound; next-step operations for rollback or suspend (§8.4); the `_uses_11_constructs`
correction (§11.1); any wire protocol beyond the document schemas of §11.4.

## 3. Concepts

### 3.1 Requirement, monitor, response

| Object | Says | Has | Never has |
|---|---|---|---|
| **Requirement** | what must hold of a unit (trace, invocation, episode, window) | a sealed kind, a unit, an optional population `among`, a violation predicate, a bound | evidence source, schedule, statistics, actions |
| **Monitor** | which evidence checks one requirement, in which phase, how | evidence source, attribution, sampling, window, decision method, episode parameters, resource limits | its own predicate; actions |
| **Response** | what happens on a monitor event | rules: trigger event → one action from the sealed ladder, with approval and parameters | statistics; predicates |

A monitor references exactly one requirement. A response rule references exactly one monitor and one of the events
that monitor's kind emits (§4.7). `recovery_time` and `evidence_liveness` requirements reference a monitor (`of`),
because they are obligations over that monitor's episodes or windows.

### 3.2 One requirement, two evidence sources

A requirement denotes a unit-level classification and a bound. A monitor applies that classification to one evidence
source:

- **promotion phase** (`source: evaluation_set`): one evaluation over the evaluation set, joined with the existing
  promotion gate (§6.11);
- **runtime phase** (`source: backend_trace_metadata | customer_side`): a stream of windows over production units,
  producing verdicts, episodes and obligation events (§6.8–§6.14).

The two verdicts are separate facts about separate populations. A promotion pass is not a runtime MET, and a runtime
BREACHED is not a promotion Reject. Claims stay relative to their evidence source (§8.5).

### 3.3 The three-level sealed catalogue

1. **Unit level.** Sealed unit predicates (§6.5), defined on a unit's complete history. An evaluator classifies each
   unit `sat`, `vio` or `unres` (unresolved), or records it as unplaceable, excluded or unattributed (§6.2, §6.4).
2. **Window level.** One window rule over the counts of a tumbling window, with two rate methods — the hosted
   platform's float method `clopper_pearson_exact_v1` and the exact-rational method `clopper_pearson_rational_v2` —
   and the deterministic `exact_count_v1` for zero tolerance (§6.8, §6.9).
3. **Episode level.** A breach-episode lifecycle (open, continue, resolve, withdraw, retire) and two obligations over
   it: `recovery_time` over episodes and `evidence_liveness` over windows (§6.12–§6.14).

The catalogue is sealed: a new kind, pattern, method, event or action is a new RFC, not a registry entry. A temporal
logic over finite traces is used only to define the denotation of the patterns (formal semantics §12).

### 3.4 Verdicts, health and states

Every runtime verdict is `MET`, `BREACHED` or `UNKNOWN(reason)`. Absence of evidence is never `MET`. The reasons form
a closed set; their meanings are in §6.8 and formal semantics §12.6:

| Source | Reasons |
|---|---|
| window rule | `late_evaluation`, `revision_gap`, `insufficient`, `unplaceable`, `unresolved`, `inconclusive`, `sampling_biased` (§6.7), `incomplete` (§6.9) |
| recovery obligation | `pending`, `cancelled`, `lifecycle_unavailable` (§6.13) |
| liveness obligation | `insufficient`, `awaiting` (§6.14) |
| release gate (§6.11) | `insufficient`, `inconclusive`, `incomplete`, `engine_required` |

Monitor health (liveness) is reported separately from the requirement verdict. Episode state, obligation state and
action state are separate records and are displayed separately (§11.6).

### 3.5 Language and evaluators

TVL is a specification language with a validator and a compiler. It is not an engine that enforces requirements.

- **What TVL defines.** The syntax and static checks of §4–§5; the meaning of every predicate and parameter on a unit's
  complete history; what `MET`, `BREACHED` and `UNKNOWN(reason)` promise; the meaning of populations, windows,
  episodes, recovery deadlines and evidence liveness; the declarative meaning of every response action and approval
  level; composition; the hosted projection.
- **What an evaluator profile defines.** An **evaluator profile** is a named, versioned specification, outside TVL, of
  how evidence about a compiled contract becomes unit classifications, window verdicts, episode and obligation states
  and response directives (formal semantics Definition 12.7). It fixes the decision procedures that TVL leaves open:
  partial-evidence rules and their order, the counting rule for unresolved units, sampling selection and commitment,
  report acceptance and corrections, episode and obligation tracking, controller execution and replay. A monitor
  selects an evaluator profile through its method, evidence source and `profile`. A conforming profile must meet the
  contracts of formal semantics §§12.4–12.11; when it cannot decide within them, it returns `unres` or
  `UNKNOWN(reason)`.
- **What TVL's tools compute.** `tvl-validate`, `tvl-lint`, `tvl-compose` and `tvl-compile-runtime` check and transform
  declarations. The only verdicts a TVL tool computes are those of the **release gate** (§6.11): promotion monitors
  decided from complete counts with standard exact binomial tests, and `NoDecision` with reason `engine_required`
  whenever unresolved or unplaceable units would need an evaluator profile.

Compiling a module produces closed artefacts (§11.4); it does not install, enable or run a monitor, and it authorizes
no response. Whether a platform can evaluate a monitor or execute an action is decided when the compiled contract is
registered with that platform (§12).

## 4. Syntax

### 4.1 Grammar (normative)

Meta-notation: `rec(f₁: τ₁, [f₂: τ₂])` is a closed mapping with required field `f₁` and optional field `f₂`; unknown
fields are rejected. `list(τ)` is a sequence. Other productions are those of `T:spec/grammar/tvl.ebnf`. Which of these
constraints the JSON Schema checks and which the lints check is fixed in §5.1.

```ebnf
module      = header, environment, evaluation_set, tvars, [cvars], [constraints], objectives, promotion_policy,
              [policies], [composites], [requirements], [monitors], [responses], [exploration] ;
                                         (* constraints optional, as in T:spec/grammar/tvl.schema.json:8-15 *)
tvl_pack    = rec("tvl_version": "\"1.3\"", "pack": rec("module": ident),
                  "requirements": list(req), "monitors": list(pack_mon), ["responses": list(resp)]) ;  (* §9.4 *)

requirements= "requirements", ":", list(req) ;
req         = rate_req | zero_req | recovery_req | liveness_req ;                          (* SEALED *)
rate_req    = rec("name": ident, "kind": "rate_bound", "unit": unit_kind, ["among": checker_pred],
                  "violation": pred, "max_rate": prob_open) ;
zero_req    = rec("name": ident, "kind": "zero_tolerance", "unit": unit_kind, ["among": checker_pred],
                  "violation": exact_pred) ;
recovery_req= rec("name": ident, "kind": "recovery_time", "unit": "episode", "of": ident, "within_hours": pos_int) ;
liveness_req= rec("name": ident, "kind": "evidence_liveness", "unit": "window", "of": ident,
                  "max_stale_windows": pos_int) ;
unit_kind   = "trace" | "invocation" ;
pred        = metric_pred | exact_pred | checker_pred ;
exact_pred  = rec("pattern": "absence", "a": sel)
            | rec("pattern": "bounded_existence", "a": sel, "max_count": nat)
            | rec("pattern": "precedence", "a": sel, "b": sel, ["mode": "single_use" | "reusable"],
                  ["correlate_by": corr])
            | rec("pattern": "bounded_response", "a": sel, "b": sel, "within_ms": pos_int, ["correlate_by": corr])
            | rec("pattern": "protocol", "alphabet": list(sel), "states": list(ident), "start": ident,
                  "transitions": list(transition), "accepting": list(ident), "rejecting": list(ident),
                  ["unlisted": "reject" | "ignore"]) ;
transition  = rec("from": ident, "when": sel, "to": ident) ;
corr        = "unit" | "correlation_id" | "tool_call_id" ;                                 (* default "unit" *)
metric_pred = rec("metric": "wall_clock_latency_ms" | "cost_usd" | "total_tokens" | "tool_calls", "exceeds": number) ;
checker_pred= rec("checker": checker_id, "label_in": list(label)) ;
checker_id  = catalogue_checker_id | customer_checker_id ;                                 (* §4.2.2 *)
sel         = rec("event": event_type, ["tool": code_ident], ["status": status], ["ref": ident]) ;
event_type  = "unit_start" | "unit_end" | "tool_call" | "tool_result" | "model_call" | "handoff" | "error"
            | "authorization_granted" | "authorization_revoked" ;                         (* agent_trace_v1 *)
status      = "running" | "completed" | "failed" | "rejected" ;

monitors    = "monitors", ":", list(mon) ;               (* monitor names are plain idents: no dots *)
mon         = rec(mon_fields, ["applies_to": "agent"]) ;
pack_mon    = rec(mon_fields, "applies_to": "tenant_floor") ;
mon_fields  = "name": ident, "requirement": ident, "phase": "promotion" | "runtime", ["profile": "backend_v1"],
              "evidence": evidence, ["window": window], "decision": decision, ["episode": episode], ["limits": limits],
              ["single_producer": bool] ;
evidence    = rec("source": "backend_trace_metadata" | "customer_side" | "evaluation_set" | "episodes" | "windows",
                  ["deployment_environment": env_label], ["attribution": attr_rule], ["resolution": res_rule],
                  ["sampling": sampling]) ;
sampling    = "unverified" | rec("mode": "head_sampled_declared" | "hash_bernoulli_committed_v1", "rate": prob_open) ;
window      = rec("tumbling_hours": hours, "grace_minutes": nat) ;
decision    = rec("method": "clopper_pearson_exact_v1" | "clopper_pearson_rational_v2" | "exact_count_v1",
                  ["model": model_id], ["confidence": conf], ["false_alarm_budget": prob],
                  ["horizon_days": pos_int], ["min_samples": pos_int], ["max_unresolved_fraction": frac],
                  ["threshold_factor": number]) ;
episode     = rec("closure_windows": pos_int, "closure_max_age_hours": pos_int) ;
limits      = rec(["max_active_obligations": pos_int], ["max_tracked_correlations": pos_int]) ;

responses   = "responses", ":", list(resp) ;
resp        = rec("name": ident, "rules": list(rule)) ;   (* unreachable behaviour is always hold *)
rule        = rec("id": ident, "trigger": trigger, "do": action, ["approval": "none" | "standing" | "human"],
                  ["target": "last_certified" | fingerprint], ["severity": severity],
                  ["fallback": "static_unavailable" | "route_to_human" | fingerprint],
                  ["rate_floor": prob_open], ["repeat_after_hours": pos_int], ["max_repeats": pos_int],
                  ["on_check_error": "block" | "allow"], ["deploy": "never" | "if_promoted"]) ;
                                         (* deploy: on optimize only, §7.6 *)
trigger     = rec("monitor": ident, "event": event_name, ["hours": pos_int]) ;
event_name  = "episode_opened" | "episode_continued" | "episode_open_for" | "episode_resolved" | "episode_withdrawn"
            | "recovery_overdue" | "recovery_cancelled" | "recovery_recovered" | "burn_breached"
            | "stale" | "live_again" | "unit_violation" ;
action      = "notify" | "open_next_step" | "optimize" | "rollback" | "throttle" | "degrade" | "suspend"
            | "block_action" | "halt_unit" ;                                               (* SEALED *)
severity    = "info" | "warning" | "critical" ;
```

**Key names and YAML 1.1.** The rule key is `trigger` and the protocol transition key is `when`, not `on`: TVL's
loader is PyYAML's `SafeLoader` (`T:python/tvl/yaml_safe.py:31-74`), a YAML 1.1 resolver, under which
an unquoted `on` key loads as the boolean `True`: with PyYAML 6.0.3, `tvl.yaml_safe.safe_load('{on: {monitor: m}}')`
returns `{True: {'monitor': 'm'}}`, while `safe_load('{trigger: {monitor: m}, when: {event: tool_call}}')` keeps both
keys as strings (reproducible with `python -c "import tvl.yaml_safe as y; print(y.safe_load('{on: {monitor: m}}'))"`). A
rule or transition that carries an `on` key, quoted or not, fails the closed shape (`schema_error`, §5.1); no tool
reinterprets it. The same resolver turns unquoted `yes`, `no`, `on`, `off`, `true` and `false` into booleans wherever a
TVL identifier is expected (a protocol state, a selector `ref`); such a value fails the string type of `ident`. No other
key or enum value of this grammar is a YAML 1.1 boolean.

### 4.2 Value domains

Numbers denote the **exact rational value of their decimal literal**. A loader that yields binary floating point
recovers the literal as the shortest decimal that round-trips to the same double. A literal is accepted only if it
equals that decimal, which holds for every literal with at most 15 significant digits; any other literal is rejected
(`runtime_invalid_profile`), because its exact value cannot be recovered. Compiled artefacts carry decimal parameters as
minimal decimal strings and integer parameters as JSON integers (§11.4).

| Domain | Values | Under `profile: backend_v1` |
|---|---|---|
| `ident` in runtime positions (requirement, monitor, response and rule names; `of`; `trigger.monitor`; `monitor.requirement`; protocol states; `sel.ref`) | `^[A-Za-z_][A-Za-z0-9_]*$` (no dots); module and pack module names keep TVL's existing `ident` | same |
| `code_ident` (`sel.tool`) | `^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$`, at most 128 characters: a function, module or qualified name; code identifiers are not customer content | not used |
| `prob_open` (`max_rate` θ, sampling `rate`, `rate_floor`) | decimal, 0 < x < 1 | θ: 0 < θ < 1 |
| `conf` (`confidence` c) | decimal, 0 < c < 1 | {0.90, 0.95, 0.99}, default 0.95 |
| `prob` (`false_alarm_budget` α_FA) | decimal, 0 < α_FA ≤ 0.5 | same, default 0.05 |
| `frac` (`max_unresolved_fraction` f) | decimal, 0 ≤ f ≤ 0.5 | same, default 0.05 |
| `hours` (`tumbling_hours` W) | a divisor of 24: {1, 2, 3, 4, 6, 8, 12, 24} | {1, 3, 6, 12, 24}, default 6 |
| `grace_minutes` g | integer 0–360 | same, default 30 |
| `min_samples` | integer 1–10 000 000 | same, default 200 |
| `horizon_days` H | integer 1–365 | same, default 30 |
| `closure_windows` K | integer 1–24 | same, default 2 |
| `closure_max_age_hours` | integer 1–720 | same, default 24 |
| `exceeds` | `wall_clock_latency_ms`, `total_tokens`, `tool_calls`: integer ≥ 1; `cost_usd`: decimal > 0 | latency: integer 1–600 000 |
| `threshold_factor` b | decimal, b > 1 and bθ < 1 | forbidden |
| `within_hours` T, `max_stale_windows` L, `within_ms`, `trigger.hours`, `repeat_after_hours`, `max_repeats`, `limits.*` | positive integers | not used |
| `max_count` | integer ≥ 0 | not used |
| `env_label` | the customer's environment label (content; hosted as an opaque reference, §8.2) | trimmed and lower-cased, 1–64 characters, default `production` |
| `attr_rule` | `agent_key_exact_v1` (default) | same |
| `res_rule` | `terminal_status_v1` (default) | same |
| `model_id` | `iid_bernoulli_within_window_v1` (default) | same |
| `fingerprint` | `^[0-9a-f]{64}$`: a certified configuration fingerprint issued by a certification record | — |
| `label` | `^[A-Za-z_][A-Za-z0-9_]*$`; for catalogue checkers, a member of the checker's label list (§4.2.2) | — |

Outside `backend_v1` the ranges for g, `min_samples`, f, α_FA, H, K and the closure age reuse the hosted latency
profile's ranges. W must divide 24 so that windows tile the UTC day and the windows per horizon `m = 24·H/W` is an
integer.

#### 4.2.1 Closed enums and lexical forms (normative)

Every enum below is closed: a value outside it is `runtime_unknown_kind` where it is authored (§5.4), and a schema
violation where it appears in a compiled or exchanged document (§11.4). Formal semantics §12 refers to this table.

| Name | Members or pattern | Where |
|---|---|---|
| `status` | `running`, `completed`, `failed`, `rejected`; the last three are final | `sel.status`; `unit_end` and `tool_result` events |
| `event_type` (`agent_trace_v1`) | `unit_start`, `unit_end`, `tool_call`, `tool_result`, `model_call`, `handoff`, `error`, `authorization_granted`, `authorization_revoked` | `sel.event` (meanings in §6.3) |
| `severity` | `info`, `warning`, `critical` | `notify` rules |
| `deploy` | `never`, `if_promoted` | `optimize` rules (§7.6) |
| scope kind | `episode`, `recovery`, `burn`, `liveness`, `unit` | event scopes (§4.7) |
| episode terminal outcome | `resolved`, `withdrawn` | episode records |
| withdrawal reason | `requirement_weakened`, `requirement_retired`, `agent_retired`, `floor_removed` | episode records; retirement records use the last three |
| unit classification | `sat`, `vio`, `unres`; selection outcomes `excluded`, `unattributed`, `unplaceable`, `outside_window` | local classification records (never hosted individually); the report's `units_commitment` (§11.4.3) |
| token namespace | `module`, `requirement`, `monitor`, `response`, `rule`, `environment`, `selector_ref`, `checker`, `state` | token map (§11.4.6) |
| evidence tier | `metadata_recount`, `client_attested` | certificate (§8.5) |
| `code_ident` | as in §4.2 | `sel.tool`; hosted as is |
| `fingerprint` | `^[0-9a-f]{64}$` | `target`, `fallback`, hosted digests |
| `label` | `^[A-Za-z_][A-Za-z0-9_]*$` | `label_in`; checker registries |
| catalogue checker id | exactly a key of the catalogue registry (§4.2.2) | `checker` |
| customer checker id | `^customer:[A-Za-z_][A-Za-z0-9_]*$` | `checker` |
| hosted customer checker id | `^customer:[0-9a-f]{64}$` (a keyed commitment) | hosted contract, reports |
| `sdk_version`, toolchain version | `^[0-9]+\.[0-9]+\.[0-9]+$`, at most 32 characters | reports, compiled artefacts |
| `ref` (hosted opaque reference) | `^[A-Za-z0-9_-]{1,128}$`, minted customer-side (random, or a keyed commitment under a customer-held key; never an unkeyed hash of the local string; §11.4.6) | hosted contract, reports |
| decimal string | `^(0\|[1-9][0-9]*)(\.[0-9]*[1-9])?$` (minimal: no trailing zero, no exponent) | compiled artefacts |
| `time_ms` | integer milliseconds since the Unix epoch, UTC | compiled and exchanged documents |

Vocabularies that an evaluator keeps for its own records belong to its evaluator profile (§3.5) and are not TVL enums.

#### 4.2.2 Checkers: the catalogue contract and registries

A **checker** is a customer-side classifier that a predicate names by `checker` id. The contract every checker meets,
catalogue or customer:

- **Question.** For one unit and one predicate position (`among` or `violation`), the checker answers with exactly one
  label from its closed, ordered label list, or with **no result** (it errored, abstained, timed out or was not run).
  The two positions are separate questions: a predicate that uses a checker in both positions reads two answers.
- **Truth.** A checker predicate holds in a position iff the returned label is in its `label_in` (§6.5). Another label
  is a negative answer in that position. No result means the predicate has no truth value on that unit: the unit is
  `unres` (§6.4).
- **Inputs and placement.** A checker reads the unit's content as it is available customer-side (its inputs, outputs and
  events) and runs customer-side, with the customer's own model and key where it uses a model. Unit content never
  crosses to the hosted side; only counts, labels as indices and commitments do (§8.2). Checkers never read content
  from observability data.
- **Determinism and versioning.** A checker is deterministic under its declared contract: for the same unit content and
  the same checker id and version, the same answer. Its labels and their meanings are fixed by its id; changing a label
  list or a label's meaning is a new id (for catalogue checkers, a catalogue revision).
- **Claims.** Behavioural claims that use a checker are relative to that checker (§8.5); TVL asserts nothing about a
  checker's real-world accuracy.

**Catalogue registry (1.3).** Exactly one catalogue checker exists:

| Checker id | Label list | Meaning by position | Runs |
|---|---|---|---|
| `traigent.refusal.v1` | `must_refuse`, `complied` | `among`: `must_refuse` = the request is one the deployment's policy requires the agent to refuse. `violation`: `complied` = the agent carried out the request instead of refusing it. In each position the other label is the negative answer | customer-side, with the customer's own model key |

A catalogue id is matched exactly; a `checker` value that is neither a catalogue id nor a well-formed customer checker
id is `runtime_unknown_kind`, as is a catalogue label outside its list. The policy that decides which requests must be
refused is the customer's; the checker applies it.

**Customer checkers.** A customer checker id is written `customer:<name>` and is bound in a customer-side registry,
document `tvl-checker-registry/1` (§11.4.5): `{format, checkers: [{checker, labels}]}`, where `labels` is the
checker's closed, ordered, non-empty, duplicate-free label list. The registry binds names and labels only; the checker
itself is the customer's code, invoked by the customer-side evaluator once per unit and position, under the contract
above. The registry never crosses to the hosted side: the hosted contract carries the checker as
`customer:<keyed commitment>` and its labels as zero-based indices into `labels` (§8.2). `tvl-lint` and `tvl-validate`,
which see only the module, check customer ids and labels lexically. `tvl-compile-runtime` requires the registry
whenever a customer checker occurs and then also checks that the id is bound and that every `label_in` member is in its
list (`runtime_unknown_kind`).

### 4.3 Kind compatibility

| Kind | Source | Phase | Method |
|---|---|---|---|
| `rate_bound` | `backend_trace_metadata` (with `backend_v1`), `customer_side`, `evaluation_set` | runtime; promotion only with `evaluation_set` | `clopper_pearson_exact_v1` (only with `backend_v1`), `clopper_pearson_rational_v2` |
| `zero_tolerance` | `customer_side`, `evaluation_set` | runtime; promotion only with `evaluation_set` | `exact_count_v1` |
| `recovery_time` | `episodes` | runtime | `exact_count_v1` |
| `evidence_liveness` | `windows` | runtime | `exact_count_v1` |

Any other combination is rejected (`runtime_invalid_profile`).

### 4.4 Typing rules

Each rule names the diagnostic of §5 it emits.

- **T1 `backend_v1`.** `profile: backend_v1` requires `kind: rate_bound`, `unit: trace`, `violation.metric:
  wall_clock_latency_ms`, `phase: runtime`, `source: backend_trace_metadata`, `method: clopper_pearson_exact_v1`,
  `sampling: unverified`, `attribution: agent_key_exact_v1`, `resolution: terminal_status_v1`,
  `model: iid_bernoulli_within_window_v1`; forbids `among`, `threshold_factor`, `limits` and `single_producer`;
  freezes the domains and defaults of §4.2 and §10.1. Omitted fields take the profile's defaults (§4.2). Violations:
  `runtime_legacy_profile_override` (`lints/legacy-method-frozen.yml`).
- **T2 source.** `source: backend_trace_metadata` requires `profile: backend_v1` (`runtime_invalid_profile`).
- **T3 compatibility.** Kind, source, phase and method follow §4.3 (`runtime_invalid_profile`).
- **T4 content.** A `checker_pred` (as `violation` or `among`) requires `source: customer_side`, or
  `source: evaluation_set` evaluated customer-side; on `backend_trace_metadata` it is
  `runtime_content_on_backend_source`. `among` itself is a `checker_pred` (`runtime_among_not_checker`): 1.3 defines
  population membership only for checker labels (formal semantics §12, membership `A_q`).
- **T5 zero tolerance.** `zero_tolerance.violation` is an `exact_pred` (`runtime_zero_tolerance_inexact`); a
  `zero_tolerance` monitor declares no `sampling` (`runtime_zero_tolerance_incomplete`).
- **T6 sampling.** `sampling: unverified` is allowed only with `backend_trace_metadata`; `head_sampled_declared` and
  `hash_bernoulli_committed_v1` only with `customer_side` and `rate_bound`; `evaluation_set`, `episodes` and
  `windows` take no sampling. An omitted `sampling` on `customer_side` means every unit in scope is selected (census).
  Violations: `runtime_invalid_profile`.
- **T7 references.** `monitor.requirement` names a requirement; `recovery_time.of` names a runtime monitor with an
  episode (a primary monitor, §4.5); `evidence_liveness.of` names a runtime window monitor (primary or burn);
  `trigger.monitor` names a monitor of the same document or of a composed pack. Unresolved: `runtime_missing_ref`;
  wrong kind: `runtime_ref_kind_mismatch`; cyclic: `runtime_dependency_cycle`.
- **T8 phase and variant fields.** Fields are required, defaulted or forbidden per §4.5. A key that belongs to another
  variant of the same record (another requirement kind, predicate pattern or monitor role) is forbidden. Violations:
  `runtime_invalid_profile`.
- **T9 burn.** `threshold_factor` marks a burn monitor: `rate_bound`, runtime, `clopper_pearson_rational_v2`, no
  `episode`, b > 1, bθ < 1, breach reachable at `min_samples` (`runtime_burn_out_of_range`); forbidden under
  `backend_v1` (`runtime_legacy_profile_override`).
- **T10 population.** `among` is allowed on `rate_bound` and `zero_tolerance` outside `backend_v1`.
- **T11 selectors.** `sel.tool` is allowed only with `event: tool_call` or `tool_result`; `sel.status` only with
  `unit_end` or `tool_result`; `sel.ref` only with `authorization_granted` or `authorization_revoked`
  (`runtime_invalid_profile`). `sel.tool` is a `code_ident` (`runtime_tool_not_code_identifier`); `sel.status` is a
  `status` (`runtime_unknown_kind`); `sel.ref` is a runtime `ident`, hosted as an opaque reference (§8.2).
  `{event: error}` matches every `error` event: the error class is local-only, is not selectable in 1.3 and is never
  exported.
- **T12 protocols.** A protocol is deterministic and well-scoped (`runtime_protocol_nondeterministic`): at most one
  transition per (state, alphabet entry); no event can match two alphabet entries; every `when` selector is an alphabet
  entry; `start`, `accepting`, `rejecting` and every transition endpoint are declared states;
  `accepting ∩ rejecting = ∅`. An unlisted (state, in-alphabet event) pair goes to an implicit rejecting sink unless
  `unlisted: ignore`.
- **T13 resource limits.** A `customer_side` or `evaluation_set` monitor whose violation is `precedence`,
  `bounded_response` or `protocol` declares `limits` (`runtime_invalid_profile`). `single_producer` is allowed only
  on monitors with an `exact_pred` (`runtime_invalid_profile`); it declares that every event of a unit comes from one
  producer, and a unit that contradicts it is `unres` (§6.4).
- **T14 triggers.** `trigger.event` is one the monitor's kind emits (§4.7; `runtime_ref_kind_mismatch`).
  `trigger.hours` is present iff `event: episode_open_for` (`runtime_invalid_ladder`).
- **T15 actions.** Parameters and approvals follow §7.2 and §7.3 (`runtime_invalid_ladder`,
  `response_suspend_without_human`, `response_suspend_unconfirmed`, `response_irreversible_without_approval`,
  `response_guard_not_enforceable`, `response_on_check_error_missing`, `response_rule_repeat_unbounded`,
  `response_deploy_without_promotion_monitor`; §7.6 for `deploy`).
- **T16 scope.** A module monitor has `applies_to: agent`, the default; `tenant_floor` in a module is
  `tenant_floor_outside_pack`. A pack monitor declares `applies_to: tenant_floor` explicitly and has `phase: runtime`;
  an omitted `applies_to`, `applies_to: agent`, or a promotion monitor in a pack is `runtime_invalid_profile`.
- **T17 version.** A module that has any of the keys `requirements`, `monitors`, `responses` (even empty), and every
  `tvl_pack`, declares `tvl_version: "1.3"` as a string. Absent: `runtime_version_required`. Present with any other
  value, including the number `1.3` that an unquoted YAML `1.3` loads as: `declared_version_below_constructs` (§11.1).
- **T18 checkers.** A `checker` is a catalogue id or a customer id and each `label_in` member a label of that checker
  (§4.2.2; `runtime_unknown_kind`).

### 4.5 Monitor fields by role

Roles: a **primary** monitor is a runtime `rate_bound` or `zero_tolerance` monitor without `threshold_factor`; a
**burn** monitor is a runtime `rate_bound` monitor with `threshold_factor`; a **promotion** monitor has
`phase: promotion`; an **obligation** monitor checks a `recovery_time` or `evidence_liveness` requirement.
R = required, D = optional with the stated default, F = forbidden. Under `backend_v1`, every R field of the primary
column except `method` becomes D with the profile's default (§4.2, §10.1); `window` and `episode` may then be omitted whole.

| Field | Primary `rate_bound` | Primary `zero_tolerance` | Burn | Promotion | Obligation |
|---|---|---|---|---|---|
| `deployment_environment` | D `production` | D `production` | D `production` | F | F |
| `attribution` | D `agent_key_exact_v1` | D | D | F | F |
| `resolution` | D `terminal_status_v1` | D | D | D | F |
| `sampling` | per T6 | F | per T6 | F | F |
| `window` | R | R | R | F | F |
| `decision.method` | R | R (`exact_count_v1`) | R (`_rational_v2`) | R | R (`exact_count_v1`) |
| `decision.model` | D `iid_bernoulli_within_window_v1` | F | D | F | F |
| `confidence` | R | F | F | R (`rate_bound`); F (`zero_tolerance`) | F |
| `false_alarm_budget` | R | F | R | R (`rate_bound`); F (`zero_tolerance`) | F |
| `horizon_days` | R | F | R | F | F |
| `min_samples` | R | D 1 | R | D 1 | F |
| `max_unresolved_fraction` | R | F | R | D 0 (`rate_bound`); F (`zero_tolerance`) | F |
| `threshold_factor` | F | F | R | F | F |
| `episode` | R | R | F | F | F |
| `limits` | per T13 | per T13 | per T13 | per T13 | F |
| `single_producer` | D false (exact_pred only) | D false | D false | D false | F |

Apart from the `backend_v1` defaults (§10.1) and the promotion and zero-tolerance defaults above, no statistical field
has a default: an author who omits one gets `runtime_invalid_profile`, not a silent value.

### 4.6 Defaults

Defaults are exactly those of §4.2 and §4.5, plus `severity: critical` for a `notify` rule whose severity is absent
and `deploy: never` for an `optimize` rule whose `deploy` is absent (§7.6).
Severity is ordered `info < warning < critical`; normalization fills this default before comparison or composition.
Non-`notify` rules have no severity coordinate. The compiled contract carries every value explicitly, defaults
included, so the contract digest never depends on a tool's default table.

### 4.7 Events per monitor role

Every event belongs to a scope (formal semantics Definition 12.22), the thing whose state it reports; scopes of
different kinds never coincide (§4.2.1).

| Monitor role | Events it emits | Scope kind | Scope identity |
|---|---|---|---|
| primary | `episode_opened`, `episode_continued`, `episode_open_for`, `episode_resolved`, `episode_withdrawn` | `episode` | episode id: determined by the effective monitor key (§9.4) and the opening evaluation's immutable identity |
| primary, `customer_side` | additionally `unit_violation` | `unit` | (monitor ref, SDK unit id) |
| burn | `burn_breached` | `burn` | (monitor ref, first window of the current BREACHED streak) |
| `recovery_time` obligation | `recovery_overdue`, `recovery_cancelled`, `recovery_recovered` | `recovery` | (episode id, recovery requirement ref) |
| `evidence_liveness` obligation | `stale`, `live_again` | `liveness` | (monitor ref, transition window) |
| promotion | none (its verdict joins the promotion gate, §6.11) | — | — |

Monitor refs in scope keys are the hosted references (§8.2), so two monitors that share a window start or an SDK unit id
never share a scope. `episode_open_for` with `hours: h` fires once per episode, when the recorded opening time
(`opened_at`) plus h hours is reached and the episode is still open (formal semantics §12.8). Window time (D5) governs
only the recovery deadline (§6.13). `unit_violation` is emitted when a unit whose `among` is true is established as
violating a predicate whose violation is fixed by a prefix of the unit's history — `absence`, `bounded_existence`,
`precedence`, or a `protocol` reaching a rejecting state (§6.4, §6.5).

### 4.8 Namespaces

Requirement names, monitor names and response names are three separate namespaces; rule ids are scoped to their
response. None of them enters the TVL type context Γ, the configuration space or the optimizer projection. A runtime
name equal to a tvar, cvar, policy or composite name is rejected (`runtime_name_collision`), and so is a duplicate
within one runtime namespace. The existing namespace lint is not modified: it still covers tvars, cvars and policies
(`T:python/tvl/lints.py:1458-1508`), so legacy diagnostics are unchanged. Runtime names contain no dots, so dotted-prefix
collisions cannot arise.

## 5. Static semantics: diagnostics

This section is the single source of runtime diagnostic codes; formal semantics Appendix B.4 refers here. All codes are
errors (E) unless marked W (warning). Every static rule of §4, §7 and §9 that rejects cites exactly one code below.
The **Case** column names the language conformance cases that exercise the code (paths relative to
`conformance/cases/runtime/`), or says that only a registration or an evaluator emits it; §13 maps cases to families.

### 5.1 Where each check runs: schema versus lints

`tvl-validate` runs the lints only when the JSON Schema passes (`T:tvl_tools/tvl_validate/cli.py:61-65`), and `tvl-lint`
runs no schema at all (`T:tvl_tools/tvl_lint/cli.py:40-42`). A registry or a numeric bound encoded in the schema would
therefore surface as a generic `schema_error` and hide the normative code. Runtime declarations follow the
shape-versus-registry layering of RFC 0001 and RFC 0002 (`T:spec/grammar/tvl.schema.json:454`):

- **`tvl.schema.json` and `tvl-pack.schema.json` check only:** closed key sets (`additionalProperties: false` on every
  runtime object; a record with variants admits the union of its variants' keys); JSON primitive types (booleans are
  not numbers; integers are JSON integers); the keys every variant requires — requirement `name`, `kind`, `unit`;
  monitor `name`, `requirement`, `phase`, `evidence`, `decision`; `evidence.source`; `decision.method`; sampling object
  `mode`, `rate`; response `name`, `rules`; rule `id`, `trigger`, `do`; trigger `monitor`, `event`; selector `event`;
  transition `from`, `when`, `to`; pack `pack`, `pack.module`, `requirements`, `monitors` — and the lexical pattern of
  runtime `ident` names. Schema failures are `schema_error`.
- **`lints.py` checks everything else** and emits the codes below: sealed registries and closed enums;
  variant-specific presence and absence (by kind, pattern, role and action, including `window`, `episode` and their
  fields); numeric domains; `applies_to`; `tvl_version` presence and value (in both documents, so that `tvl-validate`
  and `tvl-lint` report the same code); the lexical forms of `code_ident`, fingerprints, checker ids and labels;
  references; and all cross-field and cross-declaration rules.
- **Lints run only on 1.3 constructs.** `lint_module` calls the runtime lints only when `_uses_13_constructs(doc)`
  (§11.1), so a document without runtime blocks gains no diagnostic. A `tvl_pack` is linted by `lint_pack`, which runs
  the version check and the runtime lints and none of the module lints (§11.2).

### 5.2 Version, readers and registration

| Code | Sev. | Trigger | Case |
|---|---|---|---|
| `unsupported_construct` | E | an entrypoint meets a 1.3 construct it does not implement (a runtime block, a `tvl_pack`, `monitor_outcomes`, a runtime report) and refuses instead of ignoring or stripping it, including `tvl-ci-gate --policy` (§11.2) | `compatibility/` (15 refusal cases, for example `compatibility/ci-gate-refuses-pack.yml`) |
| `runtime_version_required` | E | a module uses `requirements`, `monitors` or `responses`, or a document is a `tvl_pack`, and `tvl_version` is absent (§11.1) | `compatibility/runtime-version-required.yml`, `compatibility/pack-version-required.yml`, `compatibility/empty-runtime-block-needs-version.yml`; `compatibility/omitted-version-keeps-legacy-diagnostic-rule.yml` checks that an omitted version on a legacy module is not `declared_version_below_constructs` |
| `declared_version_below_constructs` | E | `tvl_version` is present and is not the string `"1.3"` in a module that uses runtime blocks or in a `tvl_pack` | `lints/explicit-version-too-low.yml` |
| `runtime_unsupported_capability` | E | at registration: a monitor's kind, source, method or predicate class is not enabled on the target platform (§12) | registration only (§12); no TVL tool emits it |
| `response_action_unsupported` | E | at registration: a rule's action is not enabled or not executable on the target platform ("no silent rungs", §12) | registration only (§12); no TVL tool emits it |

### 5.3 Names and references

| Code | Sev. | Trigger | Case |
|---|---|---|---|
| `runtime_name_collision` | E | duplicate name in the requirement, monitor or response namespace; a runtime name equal to a tvar, cvar, policy or composite name; at composition, a carried pack name equal to a module name of a different identity (§9.4) | `lints/runtime-name-collision.yml` |
| `response_rule_id_duplicate` | E | two rules of one response share an `id` | `lints/rule-id-must-be-unique.yml` |
| `runtime_missing_ref` | E | `monitor.requirement`, `of` or `trigger.monitor` resolves to nothing | `lints/runtime-reference-missing.yml` |
| `runtime_ref_kind_mismatch` | E | a reference resolves to the wrong role: `recovery_time.of` to a monitor without an episode; `evidence_liveness.of` to a monitor without windows; `trigger.event` not emitted by that monitor (§4.7) | `lints/runtime-reference-wrong-role.yml` |
| `runtime_dependency_cycle` | E | the graph requirement →`of`→ monitor →`requirement`→ requirement has a cycle | `lints/runtime-dependency-cycle.yml` |

### 5.4 Typing and domains

| Code | Sev. | Trigger | Case |
|---|---|---|---|
| `runtime_unknown_kind` | E | a value outside a sealed registry or closed enum: requirement kind, unit kind, pattern, metric, event type, status, checker id, checker label (§4.2.2), source, method, model, sampling mode, attribution rule, resolution rule, profile, phase, trigger event, `correlate_by`, `unlisted`, `mode`, approval, severity, `on_check_error`, `deploy` | `lints/closed-catalogue-label.yml`, `lints/closed-checker-id.yml`, `lints/closed-kind-enum.yml`, `lints/closed-selector-status.yml`, `lints/closed-severity.yml`, `lints/deploy-closed-enum.yml` |
| `response_unknown_action` | E | `do` outside the sealed action set, including `record` (implicit, never declarable) | `lints/unknown-response-action.yml` |
| `runtime_invalid_profile` | E | kind/source/phase/method outside §4.3; a field required or forbidden by §4.5, or a key of another variant (T8); sampling not allowed for the source (T6); `backend_trace_metadata` without `backend_v1`; `limits` missing for a stateful pattern (T13); `single_producer` without an `exact_pred`; selector field on the wrong event (T11); pack monitor scope or phase (T16); a numeric literal whose exact value cannot be recovered (§4.2) | `lints/decimal-literal-unrecoverable-rejected.yml`, `lints/stateful-pattern-needs-limits.yml` |
| `runtime_legacy_profile_override` | E | under `profile: backend_v1`, any field or value other than the frozen ones (T1, §10.1) | `lints/legacy-method-frozen.yml` |
| `runtime_rate_out_of_range` | E | `max_rate` outside 0 < θ < 1 | `lints/rate-domain.yml` |
| `runtime_confidence_out_of_range` | E | `confidence` outside 0 < c < 1; under `backend_v1` outside {0.90, 0.95, 0.99} | `lints/confidence-domain.yml` |
| `runtime_window_out_of_range` | E | `tumbling_hours` not a divisor of 24; under `backend_v1` outside {1, 3, 6, 12, 24} | `lints/window-domain.yml` |
| `runtime_grace_out_of_range` | E | `grace_minutes` outside 0–360 | `lints/grace-domain.yml` |
| `runtime_min_samples_out_of_range` | E | `min_samples` outside 1–10 000 000 | `lints/sample-count-domain.yml` |
| `runtime_unresolved_fraction_out_of_range` | E | `max_unresolved_fraction` outside 0 ≤ f ≤ 0.5 | `lints/unresolved-fraction-domain.yml` |
| `runtime_false_alarm_budget_out_of_range` | E | `false_alarm_budget` outside 0 < α_FA ≤ 0.5 | `lints/budget-domain.yml` |
| `runtime_horizon_out_of_range` | E | `horizon_days` outside 1–365 | `lints/horizon-domain.yml` |
| `runtime_closure_windows_out_of_range` | E | `closure_windows` outside 1–24 | `lints/closure-count-domain.yml` |
| `runtime_closure_age_out_of_range` | E | `closure_max_age_hours` outside 1–720 | `lints/closure-age-domain.yml` |
| `runtime_exceeds_out_of_range` | E | `exceeds` outside its metric's domain (§4.2) | `lints/metric-threshold-domain.yml` |
| `runtime_sampling_rate_out_of_range` | E | sampling `rate` outside 0 < r < 1 | `lints/sampling-rate-domain.yml` |
| `runtime_rate_floor_out_of_range` | E | `rate_floor` outside 0 < x < 1 | `lints/throttle-rate-domain.yml` |
| `runtime_within_hours_out_of_range` | E | `within_hours` < 1 | `lints/recovery-hours-domain.yml` |
| `runtime_max_stale_windows_out_of_range` | E | `max_stale_windows` < 1 | `lints/stale-windows-domain.yml` |
| `runtime_within_ms_out_of_range` | E | `within_ms` < 1 | `lints/response-deadline-domain.yml` |
| `runtime_max_count_out_of_range` | E | `max_count` < 0 | `lints/occurrence-bound-domain.yml` |
| `runtime_trigger_hours_out_of_range` | E | `trigger.hours` < 1 | `lints/trigger-hours-domain.yml` |
| `runtime_repeat_after_hours_out_of_range` | E | `repeat_after_hours` < 1 | `lints/repeat-hours-domain.yml` |
| `runtime_max_repeats_out_of_range` | E | `max_repeats` < 1 | `lints/repeat-bound-domain.yml` |
| `runtime_max_active_obligations_out_of_range` | E | `limits.max_active_obligations` < 1 | `lints/active-obligations-domain.yml` |
| `runtime_max_tracked_correlations_out_of_range` | E | `limits.max_tracked_correlations` < 1 | `lints/correlation-limit-domain.yml` |
| `runtime_burn_out_of_range` | E | burn monitor with b ≤ 1, bθ ≥ 1, or no k ≤ `min_samples` that breaches against bθ | `lints/burn-threshold-out-of-range.yml` |
| `runtime_zero_tolerance_inexact` | E | a `zero_tolerance` violation that is not an `exact_pred` | `lints/zero-tolerance-metric-inexact.yml` |
| `runtime_among_not_checker` | E | an `among` that is a metric or exact predicate rather than a `checker_pred` | `lints/among-not-checker.yml` |
| `runtime_zero_tolerance_incomplete` | E | a `zero_tolerance` monitor declares sampling: a sampled window is never complete, so MET is unreachable and episodes never close (§6.9) | `lints/zero-tolerance-sampling-forbidden.yml` |
| `runtime_protocol_nondeterministic` | E | a protocol violates T12 | `lints/protocol-overlap.yml` |
| `runtime_tool_not_code_identifier` | E | a selector `tool` that is not a `code_ident` | `lints/tool-identifier-lexical.yml` |

Each `runtime_*_out_of_range` code names exactly one field; there is no shared code for two fields. A value of the wrong
JSON type (a string where an integer is required) is a `schema_error`, not an out-of-range code.

### 5.5 Statistics and power

| Code | Sev. | Trigger | Case |
|---|---|---|---|
| `runtime_met_unreachable_at_min_samples` | E; W under `backend_v1` | a primary `rate_bound` runtime monitor whose met test fails at N = `min_samples` even with k = u = 0: rational: (1 − θ)^N > 1 − c; float: `beta.ppf(c, 1, N) > θ`. Episodes could never close using windows of exactly that size; windows with more units can still reach MET. Example: θ 0.01, c 0.95 needs N ≥ 299, since 0.99²⁹⁹ ≈ 0.0495 ≤ 0.05 < 0.99²⁹⁸ ≈ 0.0500 | E: `lints/met-unreachable-298.yml`; boundary `lints/met-reachable-299.yml` (absent); W under `backend_v1`: `lints/backend-met-unreachable-warning.yml` |
| `runtime_breach_unreachable_at_min_samples` | W | a primary `rate_bound` runtime monitor that cannot breach at N = `min_samples` even with k = N: rational: θ^N ≥ α_w; float: the hosted latency profile's computation finds no breaching k | `lints/primary-breach-unreachable-warning.yml` |
| `chance_constraint_shadowed` | W | a promotion monitor and a `promotion_policy.chance_constraints` entry with the same name as the monitor or its requirement: the chance constraint's Reject still wins the gate join (§6.11) | `promotion/chance-constraint-shadow-warning.yml` |
| `runtime_liveness_missing` | W | a primary monitor that no `evidence_liveness` requirement covers | `lints/primary-liveness-missing-warning.yml` |

`runtime_met_unreachable_at_min_samples` is a warning under `backend_v1` because the hosted latency profile accepts
such profiles (it enforces no power condition), and every valid hosted revision must lift to a valid module (§10.3).
The power lints do not apply to promotion monitors, whose default `min_samples` is 1.

### 5.6 Composition and schedule

| Code | Sev. | Trigger | Case |
|---|---|---|---|
| `closure_unreachable` | E | `closure_max_age_hours·60 < closure_windows·W·60 + g + 60` for a monitor's own profile or for a composed profile (the hosted latency profile's integer-minute rule and code) | `composition/individually-reachable-meet-unreachable.yml`, `lints/own-closure-unreachable.yml` |
| `evaluation_schedule_mismatch` | E | a pack floor and a module monitor of one effective key, an overlay and its base monitor, or two meet inputs differ in W, g, H or α_FA (the hosted latency profile's rule and code) | `composition/budget-change.yml`, `composition/grace-change.yml`, `composition/window-change.yml` |
| `requirement_weaker_than_floor` | E | a module monitor (the candidate) is weaker than the pack floor of its effective key on a composed field, or a module obligation bound is weaker than the floor's (the hosted latency profile's rule and code) | `composition/agent-cannot-weaken-pack-floor.yml` |
| `runtime_duplicate_key` | E | two monitors of one composed document with the same effective key (§9.4), including two `backend_v1` monitors with the same (kind, threshold, environment, `applies_to`), mirroring the hosted profile's unique requirement heads; two monitors of one `recovery_time` or `evidence_liveness` requirement | `lints/effective-key-duplicate.yml` |
| `recovery_deadline_impossible` | E | `within_hours < K_close · W`, with K_close = max(K of the `of` monitor, K of any composed floor or meet input) (§6.13) | `lints/impossible-recovery-deadline.yml`, `composition/meet-recovery-deadline-impossible.yml`; boundary `lints/recovery-deadline-equality-feasible.yml` (absent) |
| `tenant_floor_outside_pack` | E | an authored module monitor declares `applies_to: tenant_floor` (a composed module is linted with its floor provenance instead, §9.4) | `composition/composed-module-without-provenance-fails.yml`, `lints/tenant-floor-outside-pack.yml` |
| `runtime_incompatible_replacement` | E | an overlay, a pack composition or a meet changes an immutable identity field of §9.1 | `composition/method-change.yml`, `composition/population-change.yml`, `composition/predicate-change.yml` |
| `runtime_overlay_weakens` | E | an overlay drops a base requirement, monitor, response or rule; loosens a number against its tightening order; or weakens a rule (§9.3, including `deploy`: `never` → `if_promoted`), including a module response that weakens a same-named pack response | `composition/change-target.yml`, `composition/drop-required-rule.yml`, `composition/flip-on-check-error.yml`, `composition/pack-severity-cannot-decrease.yml`, `composition/severity-absent-base-cannot-lower.yml`, `composition/severity-cannot-decrease.yml`, `composition/weaken-approval.yml`, `composition/widen-repeat-bound.yml`, `composition/deploy-cannot-widen.yml`, `composition/deploy-omitted-base-cannot-widen.yml` |

### 5.7 Privacy

| Code | Sev. | Trigger | Case |
|---|---|---|---|
| `runtime_unresolved_alias` | E | at serialization, a customer symbol has no token, or the token map is unavailable (fail closed) | `projection/token-map-unavailable.yml`, `projection/unresolved-alias.yml` |
| `runtime_unsafe_egress` | E | the hosted projection would carry a field that §8.2 does not list, or a listed field in another form | `projection/unlisted-field-egress-refused.yml`; `projection/unlisted-content-is-local.yml` checks the same boundary by forbidden substrings |
| `runtime_content_on_backend_source` | E | a content check (`checker_pred`) on `backend_trace_metadata`, or a content check assigned to hosted execution | `lints/content-checker-on-backend.yml` |

### 5.8 Responses

| Code | Sev. | Trigger | Case |
|---|---|---|---|
| `runtime_invalid_ladder` | E | an action parameter missing, forbidden or ill-typed for its action (§7.2: `target` required on and only on `rollback`; `fallback` required on `suspend` (an enum) and `degrade` (a fingerprint) only; `rate_floor` required on `throttle` only; `severity` on `notify` only; `on_check_error` on `block_action`/`halt_unit` only; `deploy` on `optimize` only; `max_repeats` without `repeat_after_hours`; a malformed fingerprint); `trigger.hours` present iff `episode_open_for`; `deploy: if_promoted` triggered by an event other than `episode_opened`, `episode_continued` or `episode_open_for` (§7.6); an approval value not permitted for the action (§7.3); or a remote service action (`open_next_step`, `optimize`, `rollback`, `throttle`, `degrade`, `suspend`) triggered by `episode_resolved`, `episode_withdrawn`, `recovery_cancelled`, `recovery_recovered`, `live_again` or `unit_violation`, which cannot authorize it (§7.4) | `lints/invalid-ladder-parameters.yml`, `lints/deploy-only-on-optimize.yml`, `lints/deploy-needs-episode-trigger.yml`; `tests/test_runtime_diagnostics.py::test_resolved_event_can_notify_but_cannot_rollback` |
| `response_suspend_without_human` | E | `suspend` without an explicit `approval: human`, including an omitted `approval` (D2) | `lints/suspend-human-required.yml` |
| `response_suspend_unconfirmed` | E | `suspend` triggered by an event other than `episode_continued`, `episode_open_for` or `recovery_overdue` (§7.2) | `lints/suspend-needs-escalation.yml` |
| `response_irreversible_without_approval` | E | `optimize`, `rollback`, `throttle` or `degrade` with `approval: none` | `lints/repair-needs-approval.yml` |
| `response_rollback_target_uncertified` | E | at registration, when the registering platform checks certificates: a rollback `target` or degrade `fallback` fingerprint without a valid configuration-attributed certificate. Eligibility at the time of the effect (§7.2) applies regardless | registration only (§12); no TVL tool emits it |
| `response_guard_not_enforceable` | E | `block_action`/`halt_unit` on a monitor whose violation is not fixed by a prefix (`bounded_response`, metric, checker; §6.5), whose source is not `customer_side`, or triggered by an event other than `unit_violation` | `lints/guard-metric-not-enforceable.yml` |
| `response_on_check_error_missing` | E | `block_action`/`halt_unit` without `on_check_error` | `lints/local-guard-error-policy-required.yml` |
| `response_rule_repeat_unbounded` | E | an action other than `notify` with `repeat_after_hours` and no `max_repeats` | `lints/repeat-must-be-bounded.yml` |
| `response_deploy_without_promotion_monitor` | E | an `optimize` rule with `deploy: if_promoted` whose trigger monitor's requirement has no promotion monitor in the same document, including every such rule in a `tvl_pack`, which has no promotion monitors (T16), checked on the authored pack also by `tvl-compose` before reference rewriting; `tvl-compile-runtime` checks it again after composition (§7.6) | `lints/deploy-needs-promotion-monitor.yml`, `lints/deploy-promotion-monitor-on-other-requirement.yml`, `lints/pack-cannot-declare-deploy.yml`, `composition/pack-deploy-cannot-borrow-module-gate.yml`, `composition/pack-deploy-rejected-in-meet.yml`; boundaries `lints/deploy-if-promoted-with-promotion-monitor.yml`, `lints/deploy-never-needs-no-promotion-monitor.yml` (absent) |

### 5.9 Measurement readiness

| Code | Sev. | Trigger | Case |
|---|---|---|---|
| `missing_monitor_counts` | readiness issue | a promotion monitor whose `monitor_outcomes.<monitor name>` is absent from the candidate measurement bundle, or present with k > n (§6.11), by analogy with `missing_chance_counts` (`T:python/tvl/measurement.py:291-308`); readiness issues stop `tvl-ci-gate` with exit 2 (`T:tvl_tools/tvl_ci_gate/cli.py:95-111`), so a missing or invalid count fails closed | `promotion/missing-monitor-counts.yml`, `promotion/invalid-monitor-counts.yml` |

### 5.10 Reports and exchanged documents

| Code | Sev. | Trigger | Case |
|---|---|---|---|
| `runtime_report_conservation` | E | an evaluator rejects a window report that violates the count identities of §6.7 (`k ≤ n`, `reported = n + u_reported + pl + excluded`, `selected = reported + dropped`, `tail_sampled ≤ reported`) or that does not bind to a registered contract, monitor, revision and aligned window; the full list of binding checks belongs to the evaluator profile (§3.5) | evaluator only (§3.5); report shape: `report_schema/` (4 cases, `schema_error`) |
| `schema_error` | E | an existing TVL code (`T:tvl_tools/tvl_validate/cli.py:21-35`), reused: a document fails its JSON Schema (§5.1, §11.4) | `compatibility/old-reader-rejects-requirements.yml` and its two siblings, `compatibility/rule-on-key-unquoted.yml` and its three siblings, `report_schema/` (4 cases) |

Every tool or endpoint that reports these codes returns the code alone, without echoing any input.

## 6. Meaning (normative summary)

This section states the meaning of runtime declarations and the contract every verdict must satisfy. The formal
definitions, and the statements the theorems of §14 are about, are in formal semantics §12, which is the authority for
meaning. A disagreement between this section and §12 is a defect in this section. How an evaluator reaches a verdict
from the evidence it has is outside TVL (§3.5).

### 6.1 Meaning of a TVL 1.3 module

Let `erase(M)` be M without `requirements`, `monitors` and `responses`. Then

```
⟦M⟧₁.₃ = ⟨ Gate_M, Req_M, Resp_M ⟩
  Gate_M = join(⟦erase(M)⟧₁.₂ gate decision, promotion-monitor verdicts)        (identity if none, §6.11)
  Req_M  : for each runtime monitor μ, the relation between the complete histories of μ's units and the verdict,
           episode and obligation records that satisfy the contracts of §6.4–§6.14
  Resp_M : for each history of recorded events, the response effects that §7 permits
```

`Req_M` and `Resp_M` are specifications, not programs; an evaluator profile realises them (§3.5). Runtime names have
their own typing context. Γ, the structural formula F^str, the SMT encoding and ε-dominance are computed from
`erase(M)` and are unchanged. Chance constraints keep their 1.2 meaning.

### 6.2 Units, windows, attribution and populations

**Units.** A unit is what a requirement counts; `unit_kind` declares which (formal semantics Definition 12.3):

- **`trace`**: one end-to-end handling of one request by the agent's deployment, recorded as one trace: from receipt of
  the request to the final response, including every model call, tool call and handoff made for it, in every component
  that contributes to it. Hosted latency monitors (`backend_v1`) count traces.
- **`invocation`**: one execution of the monitored agent itself: one call of its entry point, from receiving its input
  to returning its output, including the calls it makes.

A trace contains one or more invocations; when the agent is called once per request the two coincide. Counts and rates
are over units of the declared kind, so a trace requirement and an invocation requirement with the same predicate are
different requirements (§9.4). The instrumentation marks each unit's boundaries with `unit_start` and `unit_end` (§6.3).

**Windows.** A window is the half-open UTC interval `[ws, ws + W)` aligned to a multiple of W from midnight; its due
time is `due(w) = ws + W + g` (g = `grace_minutes`). Evidence for a window counts until `due(w)`; later evidence never
changes a recorded verdict.

**Attribution and placement.** A unit is **attributed** by `agent_key_exact_v1`: to the one active agent whose agent key
equals the unit's agent key in the monitor's deployment scope. Unmatched units, units of an archived agent, and units
whose key matches more than one active agent are **unattributed**: counted only as `unattributed`, never in n, k, u or
pl, never guessed. An attributed unit in the monitor's environment belongs to the window that contains its start time.
An attributed unit whose start time is unknown cannot be placed by start time: it is **unplaceable** (pl). A unit
outside the window's placement is `outside_window` for that window.

**Population.** A window's population is its placed units for which the requirement's `among` holds; `among` absent
means every placed unit.

### 6.3 Events, references and correlation

Customer-side units carry events from the closed alphabet `agent_trace_v1` (§4.2.1), emitted by the agent's
customer-side instrumentation: an SDK, the agent framework or the agent's own code (formal semantics Definition 12.4).

| Event | Marks | Fields a selector can test |
|---|---|---|
| `unit_start` | the unit begins | — |
| `unit_end(status)` | the unit ends with its final `status`: `completed`, `failed` or `rejected` | `status` |
| `tool_call(tool)` | the agent requests the tool `tool`, a code identifier; carries the call's `tool_call_id` | `tool` |
| `tool_result(tool, status)` | the result of that tool call returns; carries the same `tool_call_id` | `tool`, `status` |
| `model_call` | the agent calls a model | — |
| `handoff` | the agent hands control to another agent or to a person | — |
| `error(class)` | an error occurs; `class` is local-only, not selectable and not exported | — |
| `authorization_granted(ref)` | an authorization of kind `ref` is granted inside the unit (a payment authorization, a user consent) | `ref` |
| `authorization_revoked(ref)` | an authorization of kind `ref` is withdrawn | `ref` |

Every event also carries: its **producer** (the emitting component, which numbers its events with increasing sequence
numbers; `(producer, sequence)` identifies the event), its time in milliseconds, its unit id, an optional
`correlation_id`, a `tool_call_id` on tool events, and an optional `causal_parent`, the identity of the event that caused
it when the producer knows it.

- **`ref`** is an identifier the author chooses for a kind of authorization, for example `payment_auth` or
  `export_consent`. The instrumentation stamps it on the grant and revocation events of that kind. A selector with `ref`
  matches only events carrying it. A `ref` names a kind of authorization, not one grant.
- **`correlation_id`** is an identifier the instrumentation stamps on the events of one logical transaction inside a
  unit (one payment, one booking). **`tool_call_id`** identifies one tool call; the call and its result carry the same
  value, which typically comes from the agent framework or the model API that issued the call.
- **`correlate_by`** ∈ {`unit`, `correlation_id`, `tool_call_id`}, default `unit`, selects the key within which a
  predicate matches events: under `unit` every event of the unit shares the key; otherwise two events match only if
  both carry the same value of the chosen key. An event without the key matches nothing; a unit whose decision needs
  such a match is `unres`, never matched against every key.
- **Revocation matching.** An `authorization_revoked(ref)` revokes every earlier `authorization_granted` event with the
  same `ref` and the same correlation key; from then on those grants authorize nothing. It never affects a grant of a
  different `ref`, a grant under a different key, or an `a` selector on any event type other than
  `authorization_granted` (formal semantics Definition 12.6).

A unit's **complete history** is its full sequence of events in the order they actually happened, with its metadata and
its checker answers (formal semantics Definition 12.5). Predicates (§6.5) are defined on complete histories. An
evaluator usually observes less: missing, late or unordered events. The window report states what the producers attest
about completeness (§11.4.3); how an evaluator uses those attestations is its profile's.

### 6.4 Unit classifications

An evaluator classifies each attributed, placed unit `sat`, `vio` or `unres`, or `excluded` when `among` is false. A
classification is a claim about the unit's complete history h (formal semantics Definition 12.8):

- `vio` claims that `among` holds and the violation predicate holds on h;
- `sat` claims that `among` holds and the violation predicate does not hold on h;
- `excluded` claims that `among` does not hold on h;
- `unres` claims nothing.

Each claim must hold whatever the part of h the evaluator has not observed turns out to be. A missing event therefore
never establishes satisfaction, and a missing response never establishes a violation. A unit whose population
membership is unknown, or whose checker gave no result for a position the decision needs, is `unres`. A unit that has
not finished, whose recorded end precedes its start, that contradicts its `single_producer` declaration, or that
exceeds a resource limit (§6.6) may be `unres`. The reason an evaluator records for an `unres` unit is its profile's
vocabulary and is never exported per unit. Excluded units count in no rate.

**Prefix-fixed violations.** `absence`, `bounded_existence`, `precedence` and a `protocol` reaching a rejecting state
are violated as soon as a finite prefix of the history violates them: no later event can undo the violation. Only these
can be acted on before an effect (§6.5, §7.5), and only these emit `unit_violation` (§4.7).

**Metadata units (`backend_v1`).** No events are read. The violation predicate is wall-clock latency strictly
greater than the threshold `L`: `ended_at − started_at > L`. Classification is supplied by the evaluator profile
(§3.5) and must satisfy the guarantees above; unresolved units count as unresolved.

### 6.5 Unit predicates

Each predicate's meaning on a complete history h (formal semantics Definition 12.6):

| Predicate | Violated on h iff | Fixed by a prefix (blockable before the effect) |
|---|---|---|
| `metric m exceeds L` | the unit's metric value m > L (strict) | no |
| `absence(a)` | some event matches `a` | yes |
| `bounded_existence(a, N)` | more than N distinct events match `a` | yes, at the (N+1)-th |
| `precedence(a, b, mode, correlate_by)` | some matching `b` has no legal authorizing `a`: an earlier matching `a` with the same key, not revoked before `b` (§6.3); under `single_use` (default) each `a` authorizes at most one `b`; under `reusable` an `a` stays available until revoked | yes, suppress the `b` |
| `bounded_response(a, b, within_ms, correlate_by)` | no one-to-one assignment gives every matching `a` a matching `b` with the same key, after `a`, with `t_b − t_a ≤ within_ms` (`b` exactly at the deadline counts) | no |
| `protocol(DFA)` | the run of the DFA over the matching events, in order, reaches a rejecting state, or ends outside the accepting states | yes, on the rejecting event; ending outside `accepting` is not prefix-fixed |
| `checker id label_in L` (+ `among`) | the checker's answer for the `violation` position is in L (§4.2.2) | no (output only, via a declared fallback) |

A checker violation could be acted on only at the output, through a declared fallback ("output only" in the table).
The sealed action set has no output-replacement action, and `block_action`/`halt_unit` require a prefix-fixed
`exact_pred` (§5.8), so in 1.3 no checker violation is blocked in process.

Under `rate_bound`, `violation` may be any `pred`, including an `exact_pred`: "at most 1 % of traces contain an
`error` event" is `rate_bound` with `violation: { pattern: absence, a: { event: error } }`. Idioms: a forbidden action is
`absence`; refusal is a `checker` with `among: must_refuse` and violation `complied`; authorize → execute → audit is a
`protocol`; "every tool call gets its result within 30 s" is `bounded_response` with `correlate_by: tool_call_id`.

### 6.6 Resource limits

`max_active_obligations` bounds how many pending matches an evaluator tracks per unit (for example outstanding requests
awaiting their response, or unconsumed grants); `max_tracked_correlations` bounds how many distinct correlation keys it
tracks per unit. Both are part of the compiled contract. A unit that exceeds a limit may be `unres` and, for a local
guard, triggers the rule's declared `on_check_error` (§7.5).

### 6.7 Sampling declarations and window reports

**Sampling** is outcome-independent and per unit, never per event (formal semantics Definition 12.10):

- `unverified`: the hosted latency profile's census of ingested traces, with no assertion that upstream capture is
  independent of outcomes.
- `head_sampled_declared(r)`: each unit is selected at its start, before its outcome exists, with probability r, and the
  decision is stamped on the unit. A unit selected after its outcome is known (tail sampling) contradicts the
  declaration; a window that contains one is `UNKNOWN(sampling_biased)`.
- `hash_bernoulli_committed_v1(r)`: each unit is selected with probability r by a selection that is committed before
  the window starts, depends on nothing about the unit's outcome, and can be checked after the window. The selection
  rule and its commitment belong to the evaluator profile; this mode is usable only where an evaluator profile supports
  it. Any secret input of the selection stays customer-side; a report carries only the digest of its commitment
  (`salt_digest`, §11.4.3).

Assumption, stated on every report: selection happens before the outcome exists. Such reports are `client_attested`
(§8.5). Strata are fixed-list tags; each stratum is its own monitor with its own α; there is no pooling. Sampled
evidence never supports an "always" or "never" claim (§6.9).

**Window reports** (customer-side monitors, document `tvl-runtime-report/1`, §11.4.3) are bound to an immutable
contract digest, a monitor reference, a server-issued monitor revision and a window, and carry

```
n, k, u_reported, pl, excluded, selected, reported, dropped, unattributed
selected = reported + dropped                     reported = n + u_reported + pl + excluded             k ≤ n
tail_sampled ≤ reported
```

`selected` counts the attributed in-scope units that sampling selected (all of them under census); `reported` the
selected units the report accounts for; `dropped` the selected units it does not account for; `n` the reported
in-population units classified `sat` or `vio`, of which `k` are `vio`; `u_reported` the reported units classified
`unres`, including units whose population membership is unknown; `pl` the unplaceable units; `excluded` the units with
`among` false; `unattributed` the units outside the attributed partition, which enter no other count. Each selected
unit id counts once. A report that violates an identity, or does not bind to a registered contract, monitor and window,
is rejected with `runtime_report_conservation` (§5.10), a closed code that echoes no input. Dropped and unresolved units
are units the evaluator could not classify; under the verdict contract (§6.8) they never strengthen a verdict. How an
evaluator profile carries them into its decision counts, and how it handles duplicate, late or corrected reports, is
that profile's (§3.5).

### 6.8 Window verdicts and decision methods

**The verdict contract** (formal semantics Definition 12.13). A window verdict is a claim about the window's population.
Under the declared model `iid_bernoulli_within_window_v1`, the population's units in one window violate independently,
each with probability `p_w`:

| Kind and method | `BREACHED` promises | `MET` promises |
|---|---|---|
| `rate_bound`, `clopper_pearson_rational_v2` | if `p_w ≤ θ`, P(`BREACHED`) ≤ α_w for the window, and P(any false `BREACHED`) ≤ α_FA over the m predesignated windows of a horizon | if `p_w ≥ θ`, P(`MET`) ≤ 1 − c |
| `rate_bound`, `clopper_pearson_exact_v1` | the hosted latency profile's floating-point computation of the same tests; no probability bound is claimed | as for `BREACHED` |
| `zero_tolerance`, `exact_count_v1` (§6.9) | at least one unit of the population violates | the population was completely covered, has at least `min_samples` units, and none violates |

`UNKNOWN(reason)` promises neither. The rate claims assume sound classifications (§6.4), outcome-independent sampling,
and that each window's violation count k among its N counted units is dominated by Bin(N, θ) when `p_w ≤ θ` (and
dominates it when `p_w ≥ θ`). Units
the evaluator could not classify — unresolved, unplaceable or dropped — never strengthen a verdict: the promises hold
whatever those units' complete histories turn out to be.

**Reasons and parameters.** Each reason names why a window carries no verdict:

| Reason | Meaning |
|---|---|
| `late_evaluation` | the window was not decided within its lateness allowance, 2W after `due(w)` (exactly 2W is timely) |
| `revision_gap` | the hosted latency profile could not decide the window because a profile revision interrupted it |
| `insufficient` | the window has fewer units than `min_samples` asks for, or none |
| `unplaceable` | more of the window's units could not be placed by start time than `max_unresolved_fraction` tolerates |
| `unresolved` | more of the window's units could not be classified than `max_unresolved_fraction` tolerates |
| `sampling_biased` | selection contradicted the declared sampling (§6.7) |
| `inconclusive` | the evidence supports neither verdict |
| `incomplete` | zero tolerance only (§6.9) |

`min_samples` is the smallest window, in units, that the author accepts as the basis of a rate verdict, and the
smallest population for a zero-tolerance `MET` (§6.9). `max_unresolved_fraction` f is the largest share of a window's
units that the author tolerates as unclassifiable, and separately as unplaceable. How an evaluator profile counts units
against these two parameters, including whether unresolved units count toward `min_samples`, is its counting rule
(§3.5); under `backend_v1` it is the hosted latency profile's (§10.2). `horizon_days` H and `false_alarm_budget` α_FA
fix the predesignated statistical looks: α_w = α_FA / m with m = 24·H/W. Revisions, repeat evaluations, new strata or
new burn monitors acquire no unaccounted look.

**Decision methods** (formal semantics Definition 12.14):

| Method | Statistical meaning | With every counted unit resolved (u = 0, so N = n of §6.7) | Use |
|---|---|---|---|
| `clopper_pearson_rational_v2` (exact) | an exact one-sided binomial test of `p_w ≤ θ` at level α_w for `BREACHED`; an exact one-sided Clopper–Pearson upper confidence bound at confidence c for `MET` | `BREACHED` iff k ≥ 1 ∧ P[Bin(N, θ) ≥ k] < α_w; otherwise `MET` iff k < N ∧ P[Bin(N, θ) ≤ k] ≤ 1 − c; otherwise `UNKNOWN(inconclusive)` | every other `rate_bound` monitor; the theorems of §14 are about these tests |
| `clopper_pearson_exact_v1` (the hosted platform's stored name; float) | the same two tests, as the hosted latency profile computes them in IEEE-754 doubles through inverse beta functions | `BREACHED` iff `Lo > θ`, `Lo = scipy.stats.beta.ppf(α_w, k, N − k + 1)` (0 if k = 0); otherwise `MET` iff `Up ≤ θ`, `Up = beta.ppf(c, k + 1, N − k)` (1 if k = N); IEEE-754 doubles of θ, α_w and c | required under `backend_v1` |

Which of the reasons' conditions an evaluator profile checks, how it measures them from partial evidence, and in which
order it applies them relative to each other and to the tests are that profile's (§3.5), within the verdict contract.
Equality of the upper tail with α_w is not a breach; equality of the lower tail with 1 − c passes. When some counted
units are unresolved (u > 0), how the tests are applied is the evaluator profile's counting rule, constrained by the
verdict contract. In exact real arithmetic the two methods' tests are the same inequalities (the beta–binomial tail
identity); `_v1` evaluates them in floating point, so the methods can disagree at near-ties (§10.4). No theorem in this
RFC is about `_v1`.

**Worked boundaries** (θ = 0.05, c = 0.95, α_FA = 0.05, H = 30, W = 6 h, so α_w = 0.05/120; every unit resolved): at
N = 200, `BREACHED` iff k ≥ 23 and `MET` iff k ≤ 4; at N = 3000, `BREACHED` iff k ≥ 192 and `MET` iff k ≤ 130.

### 6.9 Zero tolerance

`exact_count_v1` over a zero-tolerance requirement (formal semantics Definitions 12.13–12.14):

- `BREACHED`: at least one unit of the population is established as violating, whatever the other units are and however
  few there are;
- `MET`: the window is **complete** and has at least `min_samples` units, none violating. Complete means: census (no
  sampling), every selected unit accounted for and classified (no `unres`, no dropped unit), none unplaceable, and the
  report's coverage attestation (§11.4.3) holds in full — `census`, `unit_histories_complete`, `producer_set_complete`,
  `producer_sequences_contiguous` and `response_deadlines_covered` are true and `watermarks_through_ms` is at least the
  window end and every response deadline the predicate uses. Counts alone never establish completeness;
- `UNKNOWN(insufficient)` when fewer than `min_samples` units were seen and no violation is established;
- `UNKNOWN(incomplete)` otherwise; `UNKNOWN(late_evaluation)` for a window not decided in time.

`min_samples` is at least 1 (default 1, §4.5), so an empty window — even a complete, census-attested one — is
`UNKNOWN(insufficient)`, never MET. The language deliberately does not conclude MET from no traffic: an idle or
suspended agent has none, and vacuous MET windows would close episodes and satisfy recovery obligations during a
suspension.

### 6.10 Burn monitors

A burn monitor is a separate `rate_bound` monitor on the same requirement, with its own W, α allocation and
`threshold_factor` b. Its breach test uses bθ in place of θ; it has no `MET` test, so a window it decides without a
breach is `UNKNOWN(inconclusive)`; it has no episode. `burn_breached` occurs on the first `BREACHED` window
of each streak of adjacent `BREACHED` windows (a gap or a non-`BREACHED` window ends the streak); its scope is the
streak, identified by its first window. A burn monitor never opens, changes or closes the primary monitor's episode.
Burn monitors use `clopper_pearson_rational_v2` only and are not allowed under `backend_v1`, whose requirement head is
unique per (agent, kind, threshold, environment).

### 6.11 Promotion monitors, the gate join and the release gate

A promotion monitor evaluates once, on the candidate's evaluation set: m = 1, so α_w = α_FA; `min_samples` defaults
to 1; `max_unresolved_fraction` defaults to 0; there is no window, horizon or episode, and the reasons
`late_evaluation` and `sampling_biased` do not apply. `rate_bound` uses `clopper_pearson_rational_v2`.
`zero_tolerance` uses `exact_count_v1`, where "complete" is the harness's explicit attestation `complete: true` (the harness knows the evaluation-set size), together
with u = 0 and pl = 0; completeness is never inferred from `u = 0 ∧ pl = 0` (formal semantics Definition 12.15). Counts
arrive in the candidate's measurement bundle as `monitor_outcomes.<monitor name>`, produced by the evaluation harness
(§11.4.2).

**Gate join.** Mapping: MET → pass, BREACHED → `Reject`, UNKNOWN → `NoDecision`. The gate result is the join, with
`Reject > NoDecision > Promote`, over the existing decision of `_make_decision` (`T:python/tvl/promotion.py:908-965`)
and every promotion monitor's mapped result (pass is neutral). With no promotion monitors the gate is unchanged. A
missing or invalid outcome cannot pass (`missing_monitor_counts`, §5.9).

**The release gate.** `tvl-ci-gate` and `tvl-measure-validate` evaluate promotion monitors with TVL's one built-in
evaluator, which decides only from complete counts using the standard exact binomial tests (formal semantics
Definition 12.16). For a valid outcome `{n, k, u, pl, complete}` — natural numbers with k ≤ n; anything else is the
readiness issue `missing_monitor_counts`, which stops `tvl-ci-gate` with exit 2 — the first matching row decides:

| Order | Condition | Verdict | Gate |
|---|---|---|---|
| 1 | u > 0 or pl > 0 | `UNKNOWN(engine_required)` | `NoDecision` |
| 2 | `zero_tolerance` and `complete` is not `true` | `UNKNOWN(incomplete)` | `NoDecision` |
| 3 | `zero_tolerance` and k ≥ 1 | `BREACHED` | `Reject` |
| 4 | n < `min_samples` | `UNKNOWN(insufficient)` | `NoDecision` |
| 5 | `zero_tolerance` | `MET` | pass |
| 6 | `rate_bound` and k ≥ 1 ∧ P[Bin(n, θ) ≥ k] < α_FA | `BREACHED` | `Reject` |
| 7 | `rate_bound` and k < n ∧ P[Bin(n, θ) ≤ k] ≤ 1 − c | `MET` | pass |
| 8 | otherwise | `UNKNOWN(inconclusive)` | `NoDecision` |

So evaluation happens only when nothing is unresolved or unplaceable; zero tolerance additionally needs
`complete: true`; anything with u > 0 or pl > 0, including a zero-tolerance count with k ≥ 1, is `NoDecision` with
reason `engine_required`, meaning that deciding it needs an evaluator profile that interprets unresolved units.
`max_unresolved_fraction` is not used by the release gate. The tests are those of `clopper_pearson_rational_v2` and
`exact_count_v1` at u = pl = 0, in exact rational arithmetic.

Example: 8 violations in 100 units at θ = 0.05, c = 0.95, α_FA = 0.05. P[Bin(100, 0.05) ≥ 8] ≈ 0.128 is not below 0.05,
and P[Bin(100, 0.05) ≤ 8] ≈ 0.937 exceeds 0.05, so the monitor is UNKNOWN(inconclusive) and maps to `NoDecision`. The
1.2 chance constraint on the same counts rejects (its upper bound ≈ 0.140 > 0.05; the existing conformance case
`T:conformance/cases/gate/chance-constraint-pass-fail.yml:13-16,28-32`).

**Chance constraints and promotion rate monitors.** A 1.2 chance constraint with threshold θ and confidence c passes
on k violations in n ≥ 1 trials iff its one-sided Clopper–Pearson upper bound at confidence c is at most θ
(`T:python/tvl/promotion.py:807-826`). By the beta–binomial identity this holds, in exact arithmetic, iff
k < n ∧ P[Bin(n, θ) ≤ k] ≤ 1 − c. So at u = 0 and matched confidence, a chance-constraint pass is exactly the
promotion monitor's MET test on the same counts (the chance constraint computes the bound in floating point, so the two
can differ at exact ties). The monitor returns MET when, in addition, n ≥ `min_samples` and its breach test, checked
first, does not hold; the two tests cannot both hold when c ≥ α_FA. They differ in what failure means. The chance
constraint maps every non-pass to `Reject`, whether the counts demonstrate a breach or are merely inconclusive. The
monitor maps a demonstrated breach (k ≥ 1 ∧ P[Bin(n, θ) ≥ k] < α_FA) to `Reject` and an inconclusive result to
`NoDecision`.

Example: n = 10, k = 1, θ = 0.1, c = 0.95, α_FA = 0.05. P[Bin(10, 0.1) ≤ 1] = 0.7360989291 > 0.05, so neither passes, and
the chance constraint rejects (its upper bound ≈ 0.394 > 0.1). P[Bin(10, 0.1) ≥ 1] = 0.6513215599 is not below 0.05, so
the monitor does not breach: it is UNKNOWN(inconclusive), which maps to `NoDecision`.

Legacy behaviour is unchanged: chance constraints keep their 1.2 meaning, a module without promotion monitors gates
exactly as before, and the monitor's meaning applies only when the author opts in. If both exist on one quantity, the
chance constraint's `Reject` still wins the join and `chance_constraint_shadowed` warns.

### 6.12 Episodes

An episode is the lifecycle of one breach of a primary monitor (formal semantics Definition 12.17). It is open or
closed, and it ends exactly once, with the terminal outcome `resolved` or `withdrawn`. The episode id is determined by
the effective monitor key (§9.4) and the opening evaluation's immutable identity. Its events mean:

- `episode_opened`: a breach began — the monitor had a BREACHED window while no episode of it was open;
- `episode_continued`: the open episode's breach persists — a further BREACHED window;
- `episode_resolved` (outcome `resolved`): the requirement has been shown met again, as the closure parameters below
  require;
- `episode_withdrawn` (outcome `withdrawn`): the requirement the episode measures was weakened
  (`requirement_weakened`) or retired (`requirement_retired`, `agent_retired`, `floor_removed`) while the episode was
  open. Withdrawal is never resolution.

**Closure parameters.** `closure_windows` K: an episode resolves after K consecutive MET windows of its monitor.
`closure_max_age_hours`: those windows must all have ended within this many hours of the evaluation that resolves the
episode, so that old evidence never closes an episode. When composition tightens these parameters (§9), the tighter
values apply.

`opened_at` and `closed_at` are lifecycle times recorded at evaluation. How an evaluator profile tracks episodes from a
monitor's window verdicts, revisions and retirements, and how windows evaluated under different parameters count
toward closure, are that profile's (§3.5). It never chooses a favourable history: when it cannot establish those
records, it has no lifecycle evidence for the affected episodes.

### 6.13 Recovery time (window time, D5)

`recovery_time(μ, within_hours T)` creates one obligation per episode of μ, with obligation id (episode id, recovery
requirement ref). Let e₀ be the end of the episode's opening window and D = e₀ + T — a window-time deadline: the closing
window must end within T hours of the opening window's end. It is not `opened_at + T`. The states mean (formal
semantics Definition 12.18):

| State | Meaning |
|---|---|
| RECOVERED | the episode resolved, and its closing window ends no later than D |
| OVERDUE | the evidence establishes that the episode did not resolve with a closing window ending by D; missing or late evidence never establishes it |
| CANCELLED | the episode was withdrawn before the obligation was RECOVERED or OVERDUE |
| PENDING | not decided yet: evidence about the windows ending by D can still arrive in time |
| UNKNOWN(lifecycle_unavailable) | none of the above can be established from the available evidence |

RECOVERED, OVERDUE and CANCELLED are terminal: once established, the obligation keeps that state. How an evaluator
profile establishes these states from window and lifecycle records, and how it records later lifecycle changes beside a
terminal state, are that profile's (§3.5).

Events: `recovery_recovered`, `recovery_overdue` and `recovery_cancelled` mark the obligation reaching that state.
Projection: RECOVERED → MET; OVERDUE → BREACHED; PENDING → UNKNOWN(pending); CANCELLED → UNKNOWN(cancelled);
UNKNOWN(lifecycle_unavailable) stays. Durations are reported beside the state and never instead of it:
`window_recovery_duration_ms` = closing-window end − e₀ when a resolution exists, and, separately,
`wall_clock_lifecycle_duration_ms` = `closed_at − opened_at` when both exist. A cancelled episode has a withdrawal
duration, not a recovery duration. The terminality of OVERDUE does not authorize effects forever: a service effect still
needs its originating episode open (§7.4).

**Deadline feasibility.** Closing needs K_close = max(K_floor, K_agent) adjacent MET windows after the opening window,
so the earliest closing window ends at e₀ + K_close · W; `recovery_deadline_impossible` iff T < K_close · W, and equality
is feasible (`lints/recovery-deadline-equality-feasible.yml`). This is the earliest window separation, not a guarantee:
closure also requires the closing windows to be fresh (`closure_max_age_hours`) at the closing evaluation, so delayed
evaluations can postpone or prevent closure and yield OVERDUE although the windows were MET in time. Example: K = 2,
W = 6 h, grace 30 min, closure age 16 h, opening window ending 06:00, MET windows ending 12:00 and 18:00. An evaluation at
18:30 closes; an evaluation at 05:00 the next day does not, because the 12:00 window is then 17 h old, although that
evaluation's lag for the 18:00 window (10.5 h after its 18:30 due time) is within the 12 h lateness allowance. When an
episode has enough consecutive MET windows to close but they are too old at an evaluation, the record carries
`closure_blocked_by_lag` beside the state (formal semantics Definition 12.19).

### 6.14 Evidence liveness

`evidence_liveness(μ, max_stale_windows L)` is a health obligation: does μ still receive usable evidence? It ranges
over the due windows of μ since activation (for floor-only monitors, since first attributed traffic). A window is due
when now ≥ due(w); the due windows include windows for which nothing was recorded. A window carries **usable
evidence** when it was decided from evidence that arrived; a window decided `UNKNOWN(inconclusive)` from real units
carries it, because liveness is about evidence arriving, not about the requirement being met. Absence of evidence is
never usable evidence: a due window for which nothing was recorded, or for which no customer-side report arrived by
its due time, never carries it. Which other windows carry it is the evaluator profile's (§3.5). `max_stale_windows`
L is how many consecutive due windows may lack usable evidence. The states mean (formal semantics Definition 12.20):

| State | Meaning |
|---|---|
| LIVE | at least one of the last L + 1 due windows carries usable evidence |
| STALE | none of the last L + 1 due windows carries usable evidence |
| UNKNOWN(insufficient) | fewer than L + 1 windows are due |
| UNKNOWN(awaiting) | neither LIVE nor STALE can be established yet |

Projection: LIVE → MET, STALE → BREACHED. **Events.** `stale` marks the monitor becoming STALE; `live_again` marks it
being LIVE again after it was STALE. Their scope is the monitor's transition window.

### 6.15 Statistical guarantees and what is not claimed

Claimed, for `clopper_pearson_rational_v2` under the model `iid_bernoulli_within_window_v1` (each window's violation
count dominated by Bin(N, θ) when the rate is at most θ; sampling outcome-independent; classifications sound):

- per window, P(false BREACHED) ≤ α_w;
- over a predesignated horizon of m windows, P(any false BREACHED) ≤ α_FA, by the union bound, with no cross-window
  independence assumption;
- per window, P(false MET) ≤ 1 − c when the rate is at least θ.

These are promises of the verdict contract (§6.8). The mathematics they rest on — exact binomial tail monotonicity, the
level of the exact upper- and lower-tail tests, and the finite union bound — is stated in §14. That a particular
evaluator profile's handling of unresolved, unplaceable and dropped units preserves them is an obligation of that
profile (§3.5).

Not claimed: any episode-level false-closure bound (the per-window bounds above do not yield one); any guarantee for
`clopper_pearson_exact_v1`, whose verdicts are the hosted platform's floating-point computation, matched against test
vectors and not proved (§10.4); guarantees under heterogeneous units; anytime-valid sequential guarantees; prevention
guarantees from sampled checks; repair efficacy.

## 7. Responses

This section states what each declared response means. How a response is executed is outside TVL (§3.5); formal
semantics §§12.10–12.11 state the contract an execution must meet.

### 7.1 Alerts are derived events

Alerts are derived from monitor and obligation events (§4.7); there is no separate alert language. An alert clears only
on resolution of its scope. Acknowledgement, mute and timers never resolve anything.

### 7.2 The ladder and the sealed action set

Ranks order actions by production impact; repair alternatives share a rank. `record` is implicit for every event and
is not declarable.

| Rank | Action | Meaning | Precondition at the time of the effect | Approval (D2) | Undo / release | When authority is unreachable |
|---|---|---|---|---|---|---|
| 0 | (record) | the originating event is recorded | always | — | append-only correction | recorded locally |
| 1 | `notify` | deliver an alert with the rule's `severity` | an alert event | none | acknowledge or mute delivery only | local log |
| 2 | `open_next_step` | open a recommended next step for the people or coding agent who maintain the agent, toward restoring the requirement (below) | an open episode | none to open; acting on the step needs its own authority | withdrawn when the episode closes | pending |
| 3 | `optimize` | start a bounded optimization of the agent's configuration, carried out by the customer's coding agent | a next step issued; a bounded grant (cost ceiling, scope, expiry) | standing grant or human | cancel an unfinished run; spend is not undone; a candidate is deployed only by a separate deploy effect (`deploy: if_promoted`, §7.6) after it passes the promotion gate | waits; a pending deploy holds |
| 3 | `rollback` | redeploy the certified `target` configuration through the customer's SDK | target eligible now (below) | standing grant or human | roll forward only through a new promotion | hold |
| 4 | `throttle` | cap the deployment's admission rate at `rate_floor` times its unthrottled admission rate (below) | a declared `rate_floor` | standing grant or human | an authorized human `release` | hold |
| 4 | `degrade` | route new work to the certified `fallback` configuration | `fallback` eligible now, as a rollback target | standing grant or human | an authorized human `release` | hold |
| 5 | `suspend` | stop admitting new units and drain existing work under `fallback` ∈ {`static_unavailable`, `route_to_human`} | open episode with ≥ 1 BREACHED window and an escalation event | human, per episode, always | latched: only an authorized human `resume` releases it | hold |
| — | `block_action` / `halt_unit` | in process, before the effect: suppress the violating event, or stop the unit (§7.5) | a prefix-fixed violation of `absence`, `bounded_existence`, `precedence` or `protocol` on an in-population unit | none (narrowing); declares `on_check_error` | n/a | keeps working (local guard) |

**`open_next_step`.** Opening the step records, for the episode, that the requirement needs restoring and what the
recommended next move is, for example running an optimization against the evaluation set. The step is addressed to
whoever maintains the agent: a person, or the coding agent that works for them, which pulls open steps. Its content
is drawn from a closed set of platform operations and server-issued references; it carries no customer content
(§8.4). Opening a step changes nothing in production; acting on it — starting an optimization, say — is a
separate action that needs its own authority (an `optimize` rule with a grant, or a human).

**`rate_floor`.** A fraction in (0, 1) of the deployment's unthrottled admission rate: while a throttle is active, new
units are admitted at no more than `rate_floor` times the rate that would be admitted without any throttle. A smaller
value throttles harder. With several active throttles the smallest `rate_floor` applies; releasing one recomputes the
minimum over those that remain (§7.4).

**Target eligibility** (rollback `target`, degrade `fallback`; formal semantics Definition 12.24). At the time of the
effect the fingerprint's certificate is valid now (not revoked, fresh); it is **configuration-attributed** (an
agent-scoped certificate is insufficient); environment and dependencies are compatible; it satisfies the current
composed requirements; it is not a configuration that breached in an open episode; and the customer's configuration
store holds a configuration whose hash is the fingerprint. Store membership alone never implies eligibility, and an
uncertified snapshot is never a target. `last_certified` resolves at the time of the effect to the certificate with the
latest certification time for this agent; if that target is ineligible, the effect is held and a notification is
raised — no other fingerprint is substituted.

**Escalation events for `suspend`** are `episode_continued`, `episode_open_for` and `recovery_overdue`: each implies
an open episode whose opening window was BREACHED and that has persisted. `episode_opened` alone is not an escalation;
burn, liveness and unit events have no episode scope.

**Parameters.** `rollback` requires `target`; `suspend` requires `fallback` from {`static_unavailable`,
`route_to_human`}; `degrade` requires `fallback` as a fingerprint; `throttle` requires `rate_floor`; `notify` may carry
`severity` (default `critical`, §4.6); `block_action` and `halt_unit` require `on_check_error`; `optimize` may carry
`deploy` (default `never`, §7.6). No other action takes these fields (`runtime_invalid_ladder`).

### 7.3 Approval levels and authority (D2)

| Approval | Allowed on | Meaning |
|---|---|---|
| `none` | `notify`, `open_next_step`, `block_action`, `halt_unit` (the default for these) | no approval is required. `notify` rests on its recorded event (event authority, §7.4); `open_next_step`, a remote service effect, still passes the current-scope and precondition checks of §7.4 at the time of its effect; `block_action` and `halt_unit` are local guards governed by §7.5, which keep working when remote authority is unreachable |
| `standing` | `optimize`, `rollback`, `throttle`, `degrade` | a standing grant (below). Each occurrence, including each repeat, consumes the grant; a retry of one occurrence does not |
| `human` | `optimize`, `rollback`, `throttle`, `degrade` (the default for these), `suspend` (required) | an authorized human approves each occurrence; for `suspend`, per episode, always |

A **standing grant** is an owner-signed authority record outside TVL documents. It binds: the agent, the controller
identity, the contract digest, the scope, the effect it authorizes (an action, or the deploy effect of an `optimize`
rule, §7.6), the eligible target fingerprints, the issue time and an expiry at most 30 days later (expiry exclusive), a
maximum occurrence count and, for `optimize`, a cost limit. Every binding and remaining limit
must hold at the time of the effect (§7.4). A module cannot name an approver or a grant; both are supplied when the
contract is registered and operated.

- **Suspend is human-only and latched.** Any active suspend wins over every other control. Resolution **or
  withdrawal** of the episode makes `resume` eligible; only an authorized human `resume` releases the suspend, and
  eligibility never performs it.
- **Release and resume are human operations, not declarable actions.** `resume` releases one suspend; `release` removes
  one installed `throttle` or `degrade`. Both need an authorized human in 1.3 and the same current-authority and
  eligibility checks as activation; neither happens automatically on scope closure, which leaves installed controls in
  place.
- **Hold when unreachable.** While the controller, the approver or grant verification is unreachable, no new
  service-level effect and no release starts. Effects already applied stay. Installed local guards keep working.
- A standing grant never authorizes `suspend` or `resume`.

### 7.4 Effect authority and occurrences

1. **Occurrences.** Every rule has a stable `id`, unique within its response. Each trigger event has a scope (§4.7). A
   rule's first firing in a scope is occurrence 0; each `repeat_after_hours` firing is a new occurrence, at
   `j · repeat_after_hours` after occurrence 0 in lifecycle time, only while the scope is active, and at most
   `max_repeats` times. Retries and redeliveries of one occurrence are the same occurrence and consume no further
   authority; repeats are new occurrences and consume authority again.
2. **Two kinds of authority.**
   - `notify` has **event authority**: its authority is the immutable recorded event, so it is delivered after its
     scope closes and after a response revision (`episode_resolved → notify`; notifications from an older response
     revision stay deliverable). It needs neither an open scope nor a grant.
   - Every other remote action is a **service effect**. It takes place only if, at the time of the effect, the rule
     still exists in the current response revision, the contract digest is current, the grant or human approval is valid
     and unexpired, the action-specific precondition of §7.2 holds, and the originating scope still requires
     intervention:

     | Scope kind | Still requires intervention iff |
     |---|---|
     | `episode` | the episode is open |
     | `recovery` | the obligation is not RECOVERED or CANCELLED (OVERDUE, PENDING and UNKNOWN qualify) **and** its originating episode is still open |
     | `burn` | the BREACHED streak persists (no later non-BREACHED or missing adjacent window) |
     | `liveness` | the liveness state is still STALE |
     | `unit` | never, for a remote service effect: a unit event authorizes only `notify` and the local guards of §7.5 |

     A service effect that has not taken place when its scope closes or its response revision changes never takes
     place.
3. **Combining controls.** Controls combine per type, not by action rank: any active `suspend` keeps admissions closed;
   the effective throttle is the minimum `rate_floor` over active throttles; a degrade routes new work only to an
   eligible fallback, and a rollback redeploys only a target that is eligible at the time of its effect. How a
   controller arbitrates between several active degrades or several pending rollbacks is its evaluator profile's
   (§3.5); no arbitration routes work in a way that violates another active obligation. A completed rollback does not
   assert that the breached requirement recovered. Releasing one control never neutralizes another.
4. **Unreachable = hold** (§7.3).
5. **No silent rungs.** A declared action that the platform cannot execute is refused when the contract is registered
   (`response_action_unsupported`, §12), never accepted and ignored.

### 7.5 Local guards and `on_check_error`

`block_action` suppresses the offending event before its effect; `halt_unit` stops the unit. Both act only when, before
the effect, a prefix-fixed violation (§6.4) is established on a unit whose `among` is true. When that cannot be
established at that moment — `among` unknown, the checker errors or abstains, the events needed are not yet known to be
complete or ordered (for example with several producers), or a resource limit overflows — the rule's `on_check_error`
decides: `block` blocks or halts (fail closed); `allow` lets the effect proceed and the unit is recorded unres.
`on_check_error` has no default. A unit with `among` false is never blocked. Local guards keep working when remote
authority is unreachable.

### 7.6 Deploying an optimize candidate (`deploy`)

An `optimize` rule may declare `deploy: never | if_promoted`; the default is `never` (§4.6). It states whether a
candidate that the rule's optimization finds may replace the configuration running in production. Under `never` the
response stops at the candidate: deploying it, if anyone does, is an ordinary promotion outside this response. Under
`if_promoted` the rule declares a second service effect, the **deploy**, with the meaning below. The deploy is never
part of the optimization effect: authority for the optimization is not authority for its deploy, and a deploy
authorizes nothing else.

```yaml
responses:
  - name: latency_repair
    rules:
      - id: fix
        trigger: {monitor: latency_prod, event: episode_opened}
        do: optimize
        approval: human          # each effect is approved on its own
        deploy: if_promoted      # requires a promotion monitor on latency_prod's requirement
```

1. **Occurrence.** A deploy occurrence is identified by (response, rule id, scope, optimize occurrence j, candidate
   fingerprint); rule ids are unique only within their response (§4.8).
   Each optimize occurrence yields at most one deploy occurrence. Retries and redeliveries of a deploy occurrence are
   the same occurrence; a repeat of the rule (§7.4) is a new optimize occurrence and may yield a new deploy occurrence,
   which needs authority again. The rule never deploys a candidate that none of its own occurrences produced.
2. **Approval.** The rule's `approval` (default `human`) applies to each effect separately. Under `human`, an authorized
   human approves each deploy occurrence; approving the optimization is not approving its deploy. The approval binds
   the episode, the candidate fingerprint, the digest of the candidate's promotion-gate result, the contract digest and
   the precondition by which the platform detects a concurrent change of the deployed configuration (for example an
   expected head generation). Under `standing`, a deploy takes place under a standing grant that names the deploy
   effect of this rule (§7.3: own occurrence limit, expiry at most 30 days after issue); a grant that covers only the
   optimization does not authorize the deploy, which then needs a human approval of that occurrence, as under `human`.
   Under a grant, the controller records the same bindings for the occurrence before the effect — the occurrence key,
   candidate fingerprint, gate-result digest, contract digest, grant and deployment precondition — and every retry of
   the occurrence reuses that record; a changed candidate, gate result or precondition is a different occurrence or
   no deploy.
   `approval: none` is rejected for `optimize` and therefore for its deploy (`response_irreversible_without_approval`).
3. **Effect-time checks.** At the time of the effect every condition below holds, or nothing is deployed:
   1. the service-effect conditions of §7.4 item 2 for the originating episode: the rule still exists in the current
      response revision with `deploy: if_promoted`, the contract digest is current, the approval or grant is valid and
      unexpired, and the episode is still open;
   2. the candidate was produced by an optimize occurrence of this rule in this episode;
   3. the candidate has a configuration fingerprint, and its promotion decision is `Promote` under the gate join of
      §6.11 — the existing decision joined with every promotion monitor of the module, which includes at least one on
      the trigger monitor's requirement (`response_deploy_without_promotion_monitor`) — computed from the candidate's
      measurement bundle for that fingerprint under the current contract digest. `NoDecision` and `Reject` never deploy,
      and a gate result computed under another contract digest is not current;
   4. the candidate is not a configuration that breached in an open episode (as for rollback targets, §7.2);
   5. the deployment precondition bound to the occurrence (by its human approval, or by the record made under a
      grant) still holds, checked atomically with the deploy write; a stale precondition writes nothing.
4. **Hold when unreachable.** While the controller, the approver, grant verification or the record of the candidate's
   promotion decision is unreachable, no deploy starts (§7.3). A deploy that has not taken place when its episode closes
   or its response revision changes never takes place (§7.4). The candidate stays on the customer side and nothing in
   production changes.
5. **Failure.** A deploy refused or failed at the time of the effect changes nothing in production, is not retried with
   another candidate, and is reported as the action state of its occurrence (§11.6). No rollback follows
   automatically, and the configuration that breached in the open episode stays ineligible as a rollback target (§7.2).
6. **A deploy never closes a breach.** An episode ends only as §6.12 states: by `closure_windows` consecutive MET
   windows of its production monitor, or by withdrawal. A deploy, its approval, its promotion-gate result and any
   evaluation-set evidence never count toward closure, never resolve an episode and never satisfy a recovery
   obligation. After a deploy the episode stays open until healthy production windows resolve it; further BREACHED
   windows keep it open, and the response's other rules keep their meaning.
7. **Triggers.** `deploy: if_promoted` is allowed only on `episode_opened`, `episode_continued` and `episode_open_for`
   (`runtime_invalid_ladder`): the effect-time checks need an open episode of a primary monitor. Burn, liveness and
   unit scopes do not supply one; a recovery obligation does have an originating episode (§7.4), and recovery triggers
   are excluded deliberately in this revision (§16.3 question 18).
8. **Projection.** The hosted rule carries `deploy` as its closed enum on every `optimize` rule, `never` filled in where
   it is omitted (§4.6, §8.2), so the contract digest binds the declared mode. Approvals, grants, candidate
   fingerprints and gate records are not TVL documents and do not cross with the contract.
9. **Composition.** `deploy` is a tightenable coordinate of an `optimize` rule: `never` is tighter than `if_promoted`,
   and absent means `never`. An overlay, or a module response merging with a pack response, may change `if_promoted`
   to `never` and never the reverse (`runtime_overlay_weakens`); the raw meet takes `never` when either side has it
   (§9.3). A `tvl_pack` has no promotion monitors (T16), so a floor cannot declare `deploy: if_promoted`; composition
   and meets check each authored pack for it before rewriting references, so a pack rule never borrows a module's
   promotion monitor (`response_deploy_without_promotion_monitor`).
10. **Enablement.** For staged enablement (§12) the deploy is an effectful action of its own: a platform that has not
    enabled it refuses to register a rule with `deploy: if_promoted` (`response_action_unsupported`), even when it
    executes `optimize`.

## 8. Where it runs, what crosses, what is certified

### 8.1 Placement

| Step | Runs | Crosses to the hosted side |
|---|---|---|
| lint, compose, compile | customer CI or developer machine | nothing |
| register | the customer's SDK or CLI, with the hosted platform | the hosted contract `tvl-runtime-contract/1` (§11.4.1); the contract digest is computed after projection |
| metadata monitors (latency) | the hosted platform, over status, timestamps, environment and agent key | nothing new |
| customer-side monitors | a customer-side evaluator; checkers with the customer's own model key | the window report `tvl-runtime-report/1` (§11.4.3) |
| verdicts, episodes, obligations | an evaluator profile (§3.5) | — |
| response directives | an evaluator's controller; the SDK pulls them | closed records |
| next steps | the hosted platform's next-step channel | references and closed operations only; no names, labels or environment strings (§8.4) |

`tvl-runtime-local/1`, the token map and the checker registry stay customer-side.

### 8.2 Local → hosted projection

Field by field; anything not listed is not exported (default deny). The token map (`tvl-token-map/1`, §11.4.6) is the
customer side's; no tool mints a token in place of a missing mapping.

| Field | Hosted form |
|---|---|
| requirement, monitor, response and rule names; protocol state names; `tvl.module` and `pack.module`; selector `ref` names | opaque references (`ref`, §4.2.1) from the token map, namespaces `requirement`, `monitor`, `response`, `rule`, `state`, `module`, `selector_ref` |
| suspend `fallback` | closed enum {`static_unavailable`, `route_to_human`} |
| degrade `fallback`, rollback `target` | a certified configuration fingerprint or `last_certified` |
| customer checker labels (`label_in`, `among`) | zero-based indices into the checker's registry label list; catalogue checkers keep their catalogue labels |
| customer checker id | `customer:<keyed commitment>` (namespace `checker`); catalogue checker ids as is |
| environment label | an opaque environment reference (namespace `environment`); the hosted platform resolves it to its stored label in its own authorized store |
| tool names in selectors | as is, validated `code_ident`s (code identifiers are not customer content) |
| decimal parameters | minimal decimal strings (§4.2.1) |
| integer parameters, counts and durations | JSON integers |
| enums, event types, statuses, method, model and sampling names; `deploy` (always present on `optimize`, §7.6) | as is |
| SDK unit ids | never individually; only inside the report's `units_commitment` |

Serialization rejects any unresolved alias (`runtime_unresolved_alias`) and fails closed if the token map is
unavailable. Errors are closed codes without echoing inputs. Every row has a projection canary (§13,
`projection/`). Observability carries no privacy guarantee. Only metadata monitors read observability data, and no
content check is fed from it.

### 8.3 The window report

A customer-side window report is the closed document `tvl-runtime-report/1` of §11.4.3. Its fields are counts, digests,
booleans, times, closed enums and opaque references only: the contract digest, monitor ref, monitor revision and window
start; the counts of §6.7; `tail_sampled`, the count of tail-sampled units (§6.7); the coverage attestation that §6.9
needs (`census`, `unit_histories_complete`, `producer_set_complete`, `producer_sequences_contiguous`,
`response_deadlines_covered`, `watermarks_through_ms`); the hosted checker ids; the sampling-commitment digest; a
commitment over the SDK unit ids and their classes; the SDK version; and the evidence tier.

### 8.4 The next-step boundary

A next step (`open_next_step`, §7.2) carries only the step, an operation from the platform's closed vocabulary and
server-issued references; never names, labels, environment strings or other customer content. This RFC adds no
next-step operation. Next-step operations for rollback or suspend would need a reviewed extension of that closed
vocabulary with a closed result schema.

### 8.5 Certificate

A certificate records the evidence behind runtime claims: the contract digest, promotion-monitor verdicts, per-window
verdicts with their counts, reasons and parameters, coverage, episodes, recovery and liveness obligations (with
`window_recovery_duration_ms`, `wall_clock_lifecycle_duration_ms` and `closure_blocked_by_lag` where they apply), and the
response decisions taken. Its record format is the evaluator profile's. Every claim carries its **evidence tier**:
`metadata_recount` for verdicts the hosted platform recounted from metadata, `client_attested` for verdicts that rest on
customer-side reports. Claims are agent-scoped. A per-configuration claim needs verified configuration attribution on
every counted unit. Behavioural claims are relative to their checker.

## 9. Composition and packs

### 9.1 `tvl_compose` over runtime blocks (overlays)

`tvl_compose` today replaces every list other than `tvars` wholesale (`T:tvl_tools/tvl_compose/cli.py:48-65`). For
the three runtime blocks that rule is kept for the result and followed by a comparison against the base:

- **Lists are complete.** If the overlay omits a runtime block key, the base block is kept unchanged. If the overlay
  has the block, every base declaration must appear in it by name, and within every response that appears, every base
  rule must appear by `id`; a missing one is a drop (`runtime_overlay_weakens`; `composition/drop-required-rule.yml`).
- **Replacement and additions.** An overlay declaration with a base name is a complete replacement, checked against the
  base declaration below. An overlay declaration with a new name is an addition, subject to every lint. The composed
  order is the base order, then additions in overlay order.
- **Immutable identity** (formal semantics Definition 12.26): requirement `kind`, `unit`, population `among` and predicate
  `violation` (including the checker id and its registry label list, and the whole protocol automaton); monitor
  `requirement`, `phase`, `profile`, evidence `source`, `deployment_environment`, `attribution`, `resolution` and
  `sampling` (mode and rate); `decision.method`, `decision.model`, `threshold_factor`; `single_producer`; and `limits`
  (both fields). A change is an incompatible replacement (`runtime_incompatible_replacement`).
- **Immutable schedule:** window length, grace, horizon and false-alarm budget (`evaluation_schedule_mismatch`).
- **Numbers may only tighten**, in the orders of §9.2 (`runtime_overlay_weakens`).
- **`--no-validate` does not apply.** That flag disables only the legacy narrowing check; the runtime checks of this
  section always run.

This follows the existing safety narrowing for chance constraints, which may tighten and never disappear
(`T:tvl_tools/tvl_compose/cli.py:213-294`).

### 9.2 Tightening orders

| Field | Tighter means | Raw meet |
|---|---|---|
| `max_rate` | ≤ | minimum |
| `confidence` | ≥ | maximum |
| `min_samples` | ≥ | maximum |
| `max_unresolved_fraction` | ≤ | minimum |
| `closure_windows` | ≥ | maximum |
| `closure_max_age_hours` | ≤ | minimum |
| `within_hours` | ≤ | minimum |
| `max_stale_windows` | ≤ | minimum |

These are the hosted latency profile's composition and weakness orders for the profile fields, extended to the two
obligation bounds (formal semantics Definition 12.26).

### 9.3 Responses survive composition

Every base rule must survive with the same trigger, action, `target`, `fallback`, `rate_floor` and `on_check_error`;
an approval no weaker (`none < standing < human`); an `optimize` `deploy` no wider (`never` is tighter than
`if_promoted`, absent = `never`, §7.6); a normalized `notify` severity no lower
(`info < warning < critical`, absent = `critical`, §4.6); and
repeat bounds no wider: `repeat_after_hours` is immutable, `max_repeats` may only decrease, and no repeat is added to
a rule that had none (formal semantics Definition 12.26). A violation is `runtime_overlay_weakens`. Standing grants are
not part of TVL documents, so TVL composition never compares them; how a platform treats a re-issued grant is outside
TVL (§3.5). For compatible retained `optimize` rules the raw meet takes `never` when either side has it
(`composition/deploy-meet-takes-never.yml`, `composition/deploy-may-tighten.yml`). For compatible retained `notify`
rules the raw meet takes the maximum normalized severity; overlay and floor
checks reject lowering before taking that meet, rather than silently repairing a weakening overlay. Added `notify`
rules receive the same explicit default.

### 9.4 Packs (D3)

Organisation floors live in a separate `tvl_pack` document (§4.1), not in modules, because a module requires
`tvl`, `environment`, `evaluation_set`, `tvars`, `objectives` and `promotion_policy` (`T:spec/grammar/tvl.schema.json:8-15`),
none of which a floor has. Pack monitors have `applies_to: tenant_floor` and `phase: runtime` (T16).

**Identities.**

- The **requirement identity** is the canonical structural tuple (kind, unit, among, violation) for `rate_bound` and
  `zero_tolerance`, and (kind, unit, `of`) for `recovery_time` and `evidence_liveness`, with `of` read after the
  reference rewriting below. It excludes the name and the tightenable bound (`max_rate`, `within_hours`,
  `max_stale_windows`). Predicates are compared after default filling; lists that denote sets (`states`, `accepting`,
  `rejecting`, `alphabet`, `transitions`, `label_in`) compare as sets.
- The **effective key** of a monitor is: under `backend_v1`, (kind, `exceeds`, normalised `deployment_environment`),
  the hosted latency profile's key; for any other primary or burn monitor, (requirement identity,
  evidence source, normalised `deployment_environment`, attribution, method, `threshold_factor` or none); for an
  obligation monitor, (requirement identity). Promotion monitors have no tenant floor.

**Composition of a pack with a module** (the module is the candidate, as in the hosted latency profile's floor check):

1. Pair each pack monitor with the module monitor of the same effective key, if any: primary and burn monitors first,
   then the references of step 4 are rewritten, then obligation monitors (whose identity reads the rewritten `of`).
   Two module monitors with one key are `runtime_duplicate_key`.
2. For a pair, the schedules must be equal (`evaluation_schedule_mismatch`), every immutable field of §9.1 must be equal
   except names and name references, the two requirements being compared by requirement identity instead
   (`runtime_incompatible_replacement`), and the module monitor and its requirement must not be
   weaker than the floor on any composed field or obligation bound (`requirement_weaker_than_floor`). The effective
   profile is the raw meet (§9.2), which for a passing pair equals the module's profile; it must be reachable
   (`closure_unreachable`) and deadline-feasible (`recovery_deadline_impossible`). This is the hosted latency
   profile's rule.
3. **Absorb paired monitors.** The composed document keeps the module monitor under its module name, with
   `applies_to: agent`, the module's requirement under its module name, and the effective profile. The pack monitor's
   name becomes an alias of the module monitor's name.
4. **Rewrite references.** Every pack `of` and `trigger.monitor` that names an absorbed pack monitor is rewritten to the
   module monitor's name.
5. **Carry floor-only monitors.** An unpaired pack monitor is carried under its pack name with `applies_to:
   tenant_floor`, together with its requirement (pack name) and the floor provenance of step 7; it applies on its own,
   starting at the agent's first attributed traffic. A carried pack name equal to a
   module name of a different identity is `runtime_name_collision`.
6. **Responses.** Pack responses are added. A module response with the same name as a pack response merges with it by
   rule id, with the pack as the base of §9.3 (`runtime_overlay_weakens`); a module cannot drop or weaken a pack rule.
7. **Floor provenance.** The composition records, per composed monitor that came from a pack, (composed monitor name,
   pack module, pack monitor name, pack document digest, `merged` or `floor_only`). `tvl-compose --validate` lints the
   composed module with this record, so carried floor-only monitors are not `tenant_floor_outside_pack`. A composed
   module carrying an `applies_to: tenant_floor` monitor and validated alone without its record fails closed with
   `tenant_floor_outside_pack`: the authority of a floor comes from the pack's activation, never from a module file.
   An all-paired composition retains only agent-scoped monitors and can validate as an ordinary module without that
   record. Its source bytes do not identify it as composed or prove that any pack is activated; compilation and
   registration still use the module and digest-bound packs as sources.

**Meet without a candidate.** When neither side is a candidate — a floor revised or activated while agent declarations
already exist, or `tvl-compose --meet` — the effective profile is the raw
meet of §9.2 with no weaker-than-floor check; the meet must again be reachable and deadline-feasible, and an
unreachable meet is an error, never a weakened result (`composition/individually-reachable-meet-unreachable.yml`,
`composition/meet-recovery-deadline-impossible.yml`).

The binding of a pack to a tenant's modules is supplied to the tools (`tvl-compose --pack`, `tvl-compile-runtime
--pack`) and, in production, by the authorized activation of a digest-bound pack; the language has no import
construct, and parsing a pack activates nothing.

### 9.5 Checks after composition

After every composition the composed document passes closure reachability (`closure_unreachable`) and deadline
feasibility (`recovery_deadline_impossible` with the composed K_close). Raw composition is a meet (the greatest lower
bound under §9.2); validated composition succeeds iff the meet is reachable (formal semantics Theorem 12.8, §14).
Whether a platform can evaluate or execute the composed declarations is decided at registration (§12), not by
composition.

## 10. The backend profile `backend_v1`

### 10.1 What it freezes

Under `profile: backend_v1` a monitor's verdicts are produced by the hosted platform's latency evaluator, the one
evaluator profile that TVL 1.3 names by a monitor field. The profile makes the hosted latency requirement the first
instance of the catalogue and freezes, as authored language:

| Frozen element | Value |
|---|---|
| kind and unit | `rate_bound` over `unit: trace` with `metric: wall_clock_latency_ms` (strict `>`), source `backend_trace_metadata`, resolution `terminal_status_v1` |
| domains and defaults | the `backend_v1` column of §4.2 |
| method, model, sampling names | `clopper_pearson_exact_v1`, `iid_bernoulli_within_window_v1`, `unverified` |
| α allocation | α_w = α_FA / (24·H/W) |
| attribution | `agent_key_exact_v1`; unattributed units are never guessed |
| key | (kind, threshold, normalised environment); one requirement head per key and scope |
| forbidden fields | `among`, `threshold_factor`, `limits`, `single_producer` (T1) |

The verdicts of such a monitor are what the hosted platform's floating-point computation returns under the stored
method and sampling names (§6.8). TVL claims no probability bound for them: the computation is matched against shared
test vectors, not proved, and naming the model `iid_bernoulli_within_window_v1` does not extend the guarantees of §6.15
to it. A change to any row above, or to that computation's outcomes on the shared vectors, is a numerical-semantics
change and needs a revision of this RFC.

### 10.2 The field mapping

| TVL 1.3 | Backend field | Domain |
|---|---|---|
| `rate_bound` + `unit: trace` + `metric: wall_clock_latency_ms` + `source: backend_trace_metadata` + `resolution: terminal_status_v1` | `kind = latency_violation_rate` | — |
| `violation.exceeds` (strict >) | `latency_threshold_ms` | integer 1–600 000 |
| `evidence.deployment_environment` | `environment` | trimmed, lower-cased, 1–64 chars, default `production` |
| `max_rate` | `max_violation_rate` | 0 < θ < 1 |
| `decision.confidence` | `confidence` | {0.90, 0.95, 0.99} |
| `window.tumbling_hours` | `window_hours` | {1, 3, 6, 12, 24} |
| `window.grace_minutes` | `grace_minutes` | 0–360 |
| `decision.min_samples` | `min_samples` | 1–10 000 000, tested against resolved plus unresolved units |
| `decision.max_unresolved_fraction` | `max_unresolved_fraction` | 0–0.5 |
| `decision.false_alarm_budget` | `false_alarm_budget` | 0 < α_FA ≤ 0.5 |
| `decision.horizon_days` | `horizon_days` | 1–365 |
| `episode.closure_windows` | `closure_windows` | 1–24 |
| `episode.closure_max_age_hours` | `closure_max_age_hours` | 1–720 |
| `applies_to` (`agent`, or `tenant_floor` in a pack) | `scope` | `agent`, `tenant_floor` |
| `method`, `model`, `sampling` | recorded on every evaluation | the three names of §10.1 |

These are the thirteen key and profile fields of the hosted latency profile (the 13-key `BackendProfile` of
§11.4.1). Revision ids, activation times, status and provenance are deployment metadata,
not author-controlled fields.

### 10.3 Round trip

`to_backend_profile(R, M)` maps a `backend_v1` requirement and monitor to the 13-key backend profile (with the plaintext
environment, locally) plus the scope; the hosted contract carries the same profile with the environment tokenized
(§11.4.1). `from_backend_revision(rev)` maps a hosted profile revision to a requirement and monitor with
`profile: backend_v1`. Names are supplied by the caller and are not part of the round trip. The properties are

```
from_backend_revision(to_backend_profile(R, M)) = normalize(R, M)      (defaults filled in)
to_backend_profile(from_backend_revision(rev))  = fields(rev)          for every valid hosted revision
```

Floats round-trip through IEEE-754 doubles: a decimal goes to its nearest double and comes back as the shortest
decimal that round-trips. That is exact for every literal accepted by §4.2, and every double the hosted platform stores lifts
to such a literal by construction. Round-trip equality covers normalised fields and identities, not YAML bytes, and
preserves the evaluation metadata {method, model, sampling} separately (`latency_roundtrip/latency-defaults.yml`,
`latency_roundtrip/latency-boundary-domain.yml`). Importing a module does not create a hosted requirement; registering
its compiled contract does (§12). The Lean statement is `backend_profile_roundtrip` (§14).

### 10.4 Float `_v1` versus exact `_v2`

The two methods compute the same inequalities in different arithmetic, so they can disagree at near-ties: a window can be
BREACHED under `_v1` and UNKNOWN(inconclusive) under `_v2`, or the reverse, on the same counts. This is a float/exact
disagreement, not a defect of either method: each computes exactly what it states. No agreement is claimed on any grid,
and no theorem in this RFC is about `_v1` (§14). Moving a monitor from `_v1` to `_v2` is a deliberate
numerical-semantics migration, not a fix.

## 11. Versioning, readers and toolchain

### 11.1 Versioning

`tvl_version: "1.3"` (a string) is required when `requirements`, `monitors` or `responses` are present, and in every
`tvl_pack`. The root schema stays closed (`T:spec/grammar/tvl.schema.json:7`) and `tvl_version` stays an optional
string-or-number in the schema (`T:spec/grammar/tvl.schema.json:46-49`), with the same type in `tvl-pack.schema.json`;
its presence and value are lint checks in both documents (§5.1):
absent on a document with 1.3 constructs → `runtime_version_required`; present with another value →
`declared_version_below_constructs`. Documents without 1.3 constructs keep today's treatment, including an omitted
version (`compatibility/omitted-version-keeps-legacy-diagnostic-rule.yml` checks the omitted case is not
`declared_version_below_constructs`). No 1.1 or 1.2 document gains a diagnostic.

This RFC does not change `_uses_11_constructs`. It ignores `composites` today (`T:python/tvl/lints.py:121-136`);
correcting that changes legacy diagnostics and is a separate, reviewed compatibility change. 1.3 adds a separate,
presence-based `_uses_13_constructs` (any of the three keys present, even empty).

### 11.2 Readers, dispatch and `unsupported_construct`

An old reader rejects a 1.3 module because the root schema is closed. Every 1.3 entrypoint either implements a 1.3
construct it meets or refuses with `unsupported_construct`; none ignores or strips one.

**Dispatch.** `tvl-validate` and `tvl-lint` treat a root mapping that has the key `pack` and not the key `tvl` as a
`tvl_pack`: `tvl-validate` checks it against `tvl-pack.schema.json` and, if that passes, runs `lint_pack`; `tvl-lint`
runs `lint_pack`. Every other document takes today's module path (`tvl.schema.json`, then `lint_module`). `lint_pack`
runs the version check and the runtime lints only; it never runs `_lint_objectives` (`empty_objectives`) or
`_lint_promotion_policy` (`invalid_alpha`), which would reject every pack (`T:python/tvl/lints.py:63-89`).

**Refusal.** A refusing entrypoint uses its existing failure path and exit code and adds two closed fields to its
failure output: `"code": "unsupported_construct"` and `"construct"` ∈ {`requirements`, `monitors`, `responses`,
`tvl_pack`, `monitor_outcomes`, `runtime_report`} (the first construct met, in that order). In text mode it prints
`unsupported_construct: <construct>` on stderr.

| Entrypoint (`T:pyproject.toml:38-47`) | Module with runtime blocks | `tvl_pack` | Other 1.3 input | Exit |
|---|---|---|---|---|
| `tvl-parse` | parses (no semantic check, `T:tvl_tools/tvl_parse/cli.py:14-30`) | parses | — | unchanged |
| `tvl-validate` | schema, then lints (§5) | pack schema, then `lint_pack` | — | 0 no issue; 2 any issue, warnings included (unchanged rule, `T:tvl_tools/tvl_validate/cli.py:76-77`) |
| `tvl-lint` | lints | `lint_pack` | — | 0 / 2 as today (`T:tvl_tools/tvl_lint/cli.py:65-66`) |
| `tvl-ci-gate` (canonical `<module> <incumbent> <candidate>`) | runs the runtime lints first and stops on any error-severity issue (exit 2, issues listed; warnings do not stop it); evaluates promotion monitors with the release gate and joins them (§6.11); runtime monitors do not change the gate | refuses (`tvl_pack`) | `monitor_outcomes` implemented; readiness on the candidate only (§11.3) | 0 Promote; 2 otherwise (unchanged, `T:tvl_tools/tvl_ci_gate/cli.py:139-142`) |
| `tvl-ci-gate --policy` (deprecated) | refuses any runtime block: this path reads YAML without schema validation (`T:tvl_tools/tvl_ci_gate/cli.py:29-50`) | refuses | refuses `monitor_outcomes` in either bundle | 2 |
| `tvl-measure-validate` | implements `monitor_outcomes` with the release gate (§6.11), treating the bundle as a candidate | refuses as the module argument | refuses a runtime report given as the measurement (`runtime_report`) | 2 on refusal (as today) |
| `tvl-compose` | implements §9.1–§9.3 | implements §9.4 via `--pack` | — | 0 / 2 |
| `tvl-check-structural` | erases runtime blocks; the structural result equals that of `erase(M)` | refuses | — | 2 on refusal (`T:tvl_tools/tvl_check_structural/cli.py:204-227`) |
| `tvl-check-operational` | erases runtime blocks; reports nothing about runtime readiness | refuses | — | 2 on refusal |
| `tvl-config-validate` | erases runtime blocks | refuses | — | 5 on refusal, its existing failure code (`T:tvl_tools/tvl_config_validate/cli.py:136-157`) |
| `tvl-microsim-bridge` | refuses | refuses | — | 2 (the bridge has no error path today, `T:tvl_tools/microsim_bridge/cli.py:34-46`; it gains one) |
| `tvl-compile-runtime` (new) | §11.5 | §11.5 | — | §11.5 |

TVL ships no tool that evaluates runtime evidence or executes responses; that work belongs to evaluator profiles
(§3.5).

### 11.3 Toolchain surface

- **Schemas** (`spec/grammar/`): `tvl.schema.json` gains the three optional root properties; new `tvl-pack.schema.json`,
  `tvl-runtime-contract.schema.json`, `tvl-runtime-local.schema.json`, `tvl-runtime-report.schema.json`;
  `tvl-measurement.schema.json`, closed today (`T:spec/grammar/tvl-measurement.schema.json:77`), gains
  `monitor_outcomes` beside `chance_outcomes` (`T:spec/grammar/tvl-measurement.schema.json:32-43`). Their content is
  §11.4 (authored documents §11.4.8); their layering is §5.1. The installed package carries the schemas, so installed
  tools validate without a source checkout.
- **`measurement.py`.** Normalises and validates `monitor_outcomes` (§11.4.2): missing `u` and `pl` become 0; a missing
  `complete` stays "not attested". `prepare_measurement_bundle` gains a keyword-only `role` parameter
  (`"candidate"`, the default, or `"incumbent"`); `missing_monitor_counts` is a readiness issue for the candidate only,
  and `monitor_outcomes` in an incumbent bundle is shape-checked and otherwise ignored, because formal semantics
  Definition 12.15 evaluates promotion monitors on the candidate (`T:python/tvl/measurement.py:239-310`).
  `tvl-ci-gate` passes `role="incumbent"` for its incumbent (`T:tvl_tools/tvl_ci_gate/cli.py:95-96`).
  `validate_measurement` (`T:python/tvl/measurement.py:83-104`) adds a `monitors` key to its result only when the module
  declares promotion monitors, so its output for 1.2 modules is byte-identical.
- **`promotion.py`.** `epsilon_pareto_gate(incumbent, candidate, policy, objectives=None, *, requirements=None,
  monitors=None)` (`T:python/tvl/promotion.py:182-187`): the new parameters are keyword-only with default `None`, so
  existing four-argument calls (`T:tests/test_conformance_suite.py:67-72`) are unchanged. Promotion monitors are
  evaluated by the release gate (§6.11) and joined only when at least one promotion monitor is given.
  `PromotionEvidence.to_dict()` (`T:python/tvl/promotion.py:108-127`) adds a `promotion_monitors` key (per monitor:
  verdict, reason, mapped result, counts) only when promotion monitors were evaluated; otherwise its output is unchanged.
- **`lints.py`** gains `_uses_13_constructs`, `_lint_runtime_version`, `_lint_requirements`, `_lint_monitors`,
  `_lint_responses` and `lint_pack`; `lint_module` (`T:python/tvl/lints.py:63-89`) calls the runtime lints only when
  `_uses_13_constructs(doc)`; the codes are §5.
- **Language modules** (new): static composition (overlay, pack, meet), normalization and the hosted projection, the
  `backend_v1` codec (`to_backend_profile`, `from_backend_revision`), canonical JSON and digests, the promotion join and
  the release gate, and compilation. `tvl.runtime` re-exports these language functions only. The package contains
  and imports no evaluator profile (§3.5); its only verdict computation is the release gate (§6.11).

### 11.4 Document schemas

All documents below are closed JSON objects: every object has `additionalProperties: false`, every listed property is
required unless marked optional, `null` is allowed only where the table says so, booleans are not integers, and arrays
keep their order unless stated. Types are those of §4.2.1 (`ref`, `fingerprint` (`fp`), decimal string (`dec`),
`time_ms`); `nat` is an integer ≥ 0 and `pos` an integer ≥ 1. **Canonical JSON** — used for every digest — is the UTF-8
output of Python `json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True)` followed by one LF; compiled documents
contain no floats, so number formatting is unambiguous. A digest is the lowercase hex SHA-256 of the canonical JSON of
its object.

#### 11.4.1 `tvl-runtime-contract/1` (hosted; `tvl-runtime-contract.schema.json`)

The only document that crosses to the hosted side at registration. Its digest is the contract digest.

| Property | Type | Null | Content |
|---|---|---|---|
| `format` | `"tvl-runtime-contract/1"` | no | |
| `tvl_version` | `"1.3"` | no | |
| `document` | `"module"` \| `"pack"` | no | the compiled document kind |
| `declarations` | object | no | the normalized runtime declarations in hosted form (below) |
| `backend_profiles` | array of BackendProfileEntry | no | one per `backend_v1` monitor; empty when none |
| `packs_checked` | array of `{pack_module_ref: ref, pack_contract_digest: fp}` | no | packs a module's composition was checked against at compile time; empty for a pack or when none |
| `toolchain` | `{name: "tvl", version: sdk_version}` | no | the compiler identity |

`declarations` has exactly the keys `tvl` (for a module: `{module: ref}`) or `pack` (for a pack: `{module: ref}`), and
`requirements`, `monitors`, `responses` (arrays, possibly empty). Each array element has exactly the shape of the
normalized source declaration — every default of §4.6 filled in, so `applies_to`, `attribution`, `resolution`,
`model` and the like are always present; an optional key with neither a value nor a default is omitted, never `null` —
with each leaf in its hosted form of §8.2: names and references as `ref`, decimal parameters as `dec`, integers as JSON
integers, labels of customer checkers as `nat` indices, the environment as `ref`, everything else as its closed enum. Every
`optimize` rule carries `deploy`, and no other rule does (`tvl-runtime-contract.schema.json`, `tvl-runtime-local.schema.json`).
Hence a projection pointer `P` into the normalized declarations denotes `/declarations` + `P` in the contract
(Appendix A).

BackendProfileEntry: `{monitor_ref: ref, scope: "agent" | "tenant_floor", backend_profile: BackendProfile,
evaluation_metadata: {method: "clopper_pearson_exact_v1", model: "iid_bernoulli_within_window_v1", sampling:
"unverified"}}`. BackendProfile has the 13 fields of §10.2 under the hosted profile's names — `kind`
(`"latency_violation_rate"`), `latency_threshold_ms` (pos), `max_violation_rate` (dec), `confidence` (dec),
`window_hours` (pos), `grace_minutes` (nat), `min_samples` (pos), `max_unresolved_fraction` (dec), `closure_windows`
(pos), `closure_max_age_hours` (pos), `false_alarm_budget` (dec), `horizon_days` (pos) — except that the environment
is `environment_ref` (ref) instead of `environment`.

#### 11.4.2 `monitor_outcomes` (in `tvl-measurement.schema.json`)

`monitor_outcomes` is an optional root property: an object whose keys are promotion-monitor names (runtime `ident`) and
whose values are closed objects:

| Property | Type | Required | Content |
|---|---|---|---|
| `n` | nat | yes | resolved in-population evaluation-set units (classified `sat` or `vio`) |
| `k` | nat | yes | violating units; k ≤ n is checked by `measurement.py` (`missing_monitor_counts` otherwise) |
| `u` | nat | no, default 0 | unresolved units (no result, unknown population membership, unfinished) |
| `pl` | nat | no, default 0 | units the harness could not place in the evaluation run |
| `complete` | boolean | no; absent = not attested | the harness's attestation that every evaluation-set unit is accounted for; required (`true`) for a `zero_tolerance` promotion monitor to be MET; ignored for `rate_bound` |

**Who produces the counts.** The evaluation harness — the customer-side pipeline that runs the candidate configuration
on the evaluation set named by the module's `evaluation_set` — produces one entry per promotion monitor. Each
evaluation-set example run is one unit of the requirement's `unit` kind. The harness applies the requirement's
`among` and `violation` predicates to each unit, running any checker customer-side under the contract of §4.2.2, and
counts the units: `n` the resolved in-population units, of which `k` violate; `u` the units it could not classify;
`pl` the units it could not place in the run (for example a run without a recorded start); units with `among` false are
excluded and appear in no count. `complete: true` attests that every unit of the evaluation set was run and is
accounted for in exactly one of `n`, `u`, `pl` or the excluded units, with no unit skipped, sampled out or lost, and
that for an `exact_pred` each unit's event history is complete. Only the harness, which knows the evaluation-set
size, can attest it; TVL never infers it from the counts. The release gate (§6.11) decides only entries with
`u = pl = 0`.

#### 11.4.3 `tvl-runtime-report/1` (hosted; `tvl-runtime-report.schema.json`)

| Property | Type | Null | Content |
|---|---|---|---|
| `format` | `"tvl-runtime-report/1"` | no | |
| `contract_digest` | fp | no | the registered contract |
| `monitor_ref` | ref | no | |
| `monitor_revision` | ref | no | the server-issued revision returned at registration |
| `window_start_ms` | time_ms | no | aligned to a multiple of W from UTC midnight |
| `counts` | `{n, k, u_reported, pl, excluded, selected, reported, dropped, unattributed}`, all nat | no | §6.7 |
| `tail_sampled` | nat | no | tail-sampled units (0 unless `head_sampled_declared`) |
| `coverage` | `{census: bool, unit_histories_complete: bool, producer_set_complete: bool, producer_sequences_contiguous: bool, response_deadlines_covered: bool, watermarks_through_ms: time_ms \| null}` | no (`watermarks_through_ms` may be null) | the completeness attestation of §6.9; never inferred from counts |
| `checker_refs` | array of hosted checker ids, sorted, unique | no | the checkers of the monitor's predicates; empty when none |
| `salt_digest` | fp | yes | the digest of the sampling commitment (§6.7); non-null iff `hash_bernoulli_committed_v1`; how it is produced and checked is the evaluator profile's |
| `units_commitment` | fp | no | digest of the canonical JSON of the list `{unit_id, class}` sorted by `unit_id`, with class ∈ {`sat`, `vio`, `unres`, `unplaceable`, `excluded`, `dropped`} over the selected units |
| `sdk_version` | sdk_version | no | |
| `evidence_tier` | `"client_attested"` | no | |

A report's identity is (`contract_digest`, `monitor_ref`, `monitor_revision`, `window_start_ms`); its digest is SHA-256
of its canonical JSON bytes (§11.4). The coverage fields are the producers' attestations: `census` — every unit in
scope was selected; `unit_histories_complete` — every selected unit's events were all reported; `producer_set_complete`
— every producer that contributed to the window's units is known; `producer_sequences_contiguous` — no producer's
sequence numbers have gaps; `response_deadlines_covered` — every response deadline the predicate uses has passed and is
covered by the producers' reporting; `watermarks_through_ms` — every producer has reported all its events up to this
time. How an evaluator treats a redelivered, conflicting or late report is its profile's (§3.5); a report never changes
a recorded verdict after `due(w)` (§6.2).

#### 11.4.4 `tvl-runtime-local/1` (customer-side only; `tvl-runtime-local.schema.json`)

The declarations a customer-side evaluator and the evaluation harness consume. It never crosses to the hosted side.
Producing it installs, enables or runs nothing.

| Property | Type | Null | Content |
|---|---|---|---|
| `format` | `"tvl-runtime-local/1"` | no | |
| `tvl_version` | `"1.3"` | no | |
| `document` | `"module"` \| `"pack"` | no | |
| `contract_digest` | fp | no | the hosted contract compiled together with it |
| `source_digest` | fp | no | digest of `declarations` below |
| `token_map_digest` | fp | no | digest of the token map used |
| `checker_registry_digest` | fp | yes | null iff no customer checker is used |
| `declarations` | object | no | the same normalized declarations as the contract's, in **local** form (plaintext names, labels, refs, environment, local checker ids) |
| `tokens` | array of token-map entries (§11.4.6) | no | the token-map entries this contract uses |
| `customer_monitors` | array of monitor names | no | the monitors a customer-side evaluator evaluates (source `customer_side`) |
| `harness_monitors` | array of monitor names | no | promotion monitors evaluated customer-side on the evaluation set |
| `guards` | array of `{response: ident, rule_id: ident, monitor: ident, action: "block_action" \| "halt_unit", on_check_error: "block" \| "allow"}` | no | the local guards (§7.5) |

#### 11.4.5 `tvl-checker-registry/1` (customer-side only)

`{format: "tvl-checker-registry/1", checkers: [{checker: customer checker id, labels: [label, …]}]}`; checker ids are
unique; each `labels` array is non-empty and duplicate-free, and its order fixes the hosted indices (§8.2). The checkers
themselves meet the contract of §4.2.2.

#### 11.4.6 `tvl-token-map/1` (customer-side only)

`{format: "tvl-token-map/1", tokens: [{namespace, local: string, hosted}]}` with `namespace` from §4.2.1; `hosted` is
a `ref`, except in namespace `checker`, where `local` is a customer checker id and `hosted` a hosted customer checker id
(`customer:<64 hex>`). Within a namespace the map is injective in both directions (repeated joins agree).

**What a token map must contain.** The author or the customer's tooling writes the token map; no TVL tool mints a
token (§8.2). It needs one entry for every customer-chosen name the compiled contract uses:

| Namespace | Entries needed |
|---|---|
| `module` | `tvl.module` of a module, or `pack.module` of a pack |
| `requirement`, `monitor`, `response`, `rule` | every requirement, monitor and response name and every rule id |
| `state` | every protocol state name |
| `selector_ref` | every `ref` used in a selector |
| `checker` | every customer checker id (`local` is `customer:<name>`, `hosted` is `customer:` followed by 64 lowercase hex characters) |
| `environment` | every `deployment_environment` label of a primary or burn monitor, **including the default `production` of a monitor that omits it**; under `backend_v1` the label is trimmed and lower-cased before lookup |

When packs are composed with `--pack`, each pack is compiled with the same map, so the map also needs these entries for
every pack's declarations. A missing entry, a malformed hosted value or an unreadable map is `runtime_unresolved_alias`,
and nothing is written (§11.5). Hosted values must match `ref` (§4.2.1) and must not be derivable from the local string:
mint them at random, or as a keyed commitment under a key the customer holds, never as an unkeyed hash. Keep the map
customer-side, keep it stable across compilations (a changed hosted value is a different hosted identity), and supply
the same map to every compilation whose contracts must join. Entries the contract does not use are allowed and are not
copied into `tvl-runtime-local/1`.

#### 11.4.7 Evaluator records (not a TVL document)

The records an evaluator keeps belong to its evaluator profile (§3.5). TVL defines no such document; the meaning
those records must respect is formal semantics §§12.8–12.11.

#### 11.4.8 Authored documents: module runtime blocks and `tvl_pack` (`tvl.schema.json`, `tvl-pack.schema.json`)

Authored documents are YAML, loaded by `tvl.yaml_safe.safe_load`, and checked by the schemas at the shape level of §5.1
only. `tvl.schema.json` gains three optional root properties, each an array: `requirements` (items: Requirement),
`monitors` (items: Monitor), `responses` (items: Response). `tvl-pack.schema.json` describes the pack root:

| Property | Type | Required in schema | Content |
|---|---|---|---|
| `tvl_version` | string or number | no (presence and value are lint checks, §5.1) | must be the string `"1.3"` |
| `pack` | `{module: string}` | yes (`module` required) | the pack's module name (TVL `ident`) |
| `requirements` | array of Requirement | yes | |
| `monitors` | array of Monitor | yes | `applies_to` is admitted by the schema; the lint requires `tenant_floor` (T16) |
| `responses` | array of Response | no | |

Requirement, Monitor, Response and their nested records are shared definitions (`$defs`) of both schemas. Each is a
closed object whose properties are the union of its variants' keys in §4.1 — Requirement: `name`, `kind`, `unit`,
`among`, `violation`, `max_rate`, `of`, `within_hours`, `max_stale_windows`; Predicate: `metric`, `exceeds`,
`checker`, `label_in`, `pattern`, `a`, `b`, `max_count`, `mode`, `correlate_by`, `within_ms`, `alphabet`, `states`,
`start`, `transitions`, `accepting`, `rejecting`, `unlisted`; Monitor: `name`, `requirement`, `phase`, `profile`,
`applies_to`, `evidence`, `window`, `decision`, `episode`, `limits`, `single_producer`; Rule: `id`, `trigger`, `do`,
`approval`, `target`, `severity`, `fallback`, `rate_floor`, `repeat_after_hours`, `max_repeats`, `on_check_error`,
`deploy` —
with the JSON types of §4.1 (integers for `nat` and `pos_int` fields, numbers for decimal fields, strings for enums and
names, the string-or-object union for `sampling`), the always-required keys of §5.1, and the `ident` pattern on runtime
names and name references.

### 11.5 CLI contracts of the new and extended tools

Both tools accept `--format text|json` (default `text`; `cli_utils.add_common_args`), print one result object in JSON
mode, and report issues in the existing issue shape `{code, message, path, severity}`. Exit 0 means success; exit 2
means failure; no other exit code is used by these two tools.

**`tvl-compile-runtime`**

```
tvl-compile-runtime DOCUMENT --token-map TOKENS.json --out-dir DIR
                    [--pack PACK.yml]... [--checkers REGISTRY.json] [--format text|json]
tvl-compile-runtime DOCUMENT [--pack PACK.yml]... --emit-token-map-template
```

- **Contract.** The compiler compiles any valid specification. It checks the document, composes it with any packs,
  projects it and writes the two closed artefacts. It does not check whether any platform can evaluate a monitor or
  execute an action, does not read certificates, and does not install, enable or run anything; those are registration
  questions (§12).
- `DOCUMENT`: a 1.3 module or a `tvl_pack` (dispatch of §11.2). `--pack` is allowed only with a module and may repeat.
- `--token-map` (required for compilation): a `tvl-token-map/1` file (§11.4.6). Missing, unreadable or incomplete →
  `runtime_unresolved_alias`.
- `--emit-token-map-template`: validate the document and any packs, then print local-only `tvl-token-map/1` JSON
  listing their required names, including default environments, with empty `hosted` placeholders. It mints no tokens,
  composes no contracts, writes no artefacts and needs no checker registry. It cannot be combined with `--token-map`
  or `--out-dir`. Fill every placeholder using the customer's token service (§11.4.6) before compiling; an unfilled
  template is not a usable token map. With this flag stdout is the template JSON regardless of `--format`.
- `--checkers`: a `tvl-checker-registry/1` file; required iff a customer checker id occurs (`runtime_unknown_kind`).
- Steps, in order, stopping at the first step with an error: (1) schema and lints, as `tvl-validate`, with the checker
  registry when given; (2) composition with each `--pack` (§9.4–§9.5); each pack is also validated and compiled with
  the same token map, and its contract digest is recorded in `packs_checked`; the composed module is checked again for
  `response_deploy_without_promotion_monitor` (§7.6); (3) projection with the token map
  (§8.2): `runtime_unresolved_alias`, `runtime_unsafe_egress`; (4) write `DIR/runtime-contract.json` (§11.4.1) and
  `DIR/runtime-local.json` (§11.4.4) as canonical JSON. Nothing is written unless every step passes.
- A module's contract carries only its own (agent-scope) monitors after composition, with the tightened fields and
  composed responses; floor-only monitors are compiled from the pack's own contract (§16.3 item 10).
- Output: `{"ok", "file", "contract_digest" (fp or null), "issues"}`.
- Exit: 0 when both files are written, warnings allowed (a warning such as `runtime_liveness_missing`, or
  `runtime_met_unreachable_at_min_samples` under `backend_v1`, must not block a valid hosted profile); 2 on any
  error-severity issue or unreadable input. Template mode exits 0 when the template is printed, with no artefacts written.

**`tvl-compose` with packs and meets**

```
tvl-compose FILE [--pack PACK.yml]... [--meet OTHER.yml] [-o OUT] [--validate] [--no-validate] [--format text|json]
```

- `FILE`: an overlay with `_tvl_overlay.extends`, as today (`T:tvl_tools/tvl_compose/cli.py:483-489,566-591`), or, with
  `--pack` or `--meet`, also a plain module.
- Order: resolve the overlay chain (§9.1–§9.3), then compose each `--pack` in command-line order with the module as the
  candidate (§9.4), then, with `--meet`, take the raw meet with `OTHER` (a module or pack) without a candidate
  (§9.4, "Meet without a candidate"), then the checks of §9.5. `--pack` and `--meet` cannot be combined.
- Output: the composed module as today; in JSON mode the result also has `floor_provenance`:
  `[{monitor, pack_module, pack_monitor, pack_digest, match: "merged" | "floor_only"}]` (§9.4 step 7).
- `--no-validate` disables only the legacy narrowing check (§9.1). `--validate` runs the schema and the lints on the
  composed module with its floor provenance, under `tvl-validate`'s exit rule (warnings included).
- Exit: 0 on success; 2 on any composition error (§5.6 codes, listed as issues) or unreadable input.

### 11.6 Separate states

A valid specification, a registered contract, an installed monitor, available evidence (liveness), a requirement
verdict, an episode state, an obligation state and an action state are distinct facts. None is inferred from another,
and a tool or display that shows them shows them separately.

## 12. Registration and staged enablement (D4)

**Compilation is not enablement.** `tvl-compile-runtime` compiles every valid specification (§11.5). Whether a
platform can evaluate a monitor or execute a declared action is decided when the compiled contract is **registered**
with that platform. Registration is outside TVL; this section states what TVL requires of it.

- **No silent rungs.** A registration that declares a monitor whose kind, source, method or predicate class the
  platform has not enabled is refused with `runtime_unsupported_capability`; a rule whose action the platform cannot
  execute is refused with `response_action_unsupported`, and so is a rule with `deploy: if_promoted` on a platform that
  has not enabled the deploy effect (§7.6); a rollback target or degrade fallback without a valid
  configuration-attributed certificate may be refused with `response_rollback_target_uncertified` (§5.8). Nothing is
  accepted as a silent no-op. These codes belong to the closed vocabulary of §5 so that every platform reports
  refusals the same way; no TVL tool emits them.
- **Staged enablement.** The whole catalogue is specified now. A platform enables each kind (with its source, method and
  predicate class) and each effectful action only after its own conformance evidence for that kind or action passes,
  and keeps that decision per platform and implementation version. The intended first scope is measurement of the
  hosted latency requirement through TVL (`rate_bound` under `backend_v1`), with `notify` and `open_next_step`.
- **Language conformance enables nothing.** Passing the language families of §13 shows that a toolchain implements
  TVL 1.3; it is not evidence that any evaluator or action works.
- **Activation.** Registering a pack's contract, and activating it for a tenant's agents, is an authorized registration
  operation; parsing or compiling a pack activates nothing (§9.4).

## 13. Conformance families

Language cases live in `conformance/cases/runtime/` (format `tvl-runtime-case/1`, run by
`python -m pytest tests/test_conformance_suite.py -q`; fixture integrity by
`python conformance/tools/check_runtime_cases.py`). A family is a named set of cases; passing one file is not passing a
family. Unknown case kinds and expected assertion keys fail closed.

| Family | Cases | What passing shows |
|---|---|---|
| `compatibility/` | 30 | old readers reject runtime blocks; every refusal of §11.2; pack dispatch; version rules (`runtime_version_required`, `declared_version_below_constructs`); a rule or transition keyed `on` is a `schema_error`; legacy erasure is unchanged |
| `lints/` | 69 | every static diagnostic of §5.3–§5.8 that a lint emits, with its boundary cases (for example `met-unreachable-298.yml` and `met-reachable-299.yml`) |
| `composition/` | 35 | overlays that change a predicate, population, method or schedule, drop a rule, flip `on_check_error`, weaken an approval, widen repeats or change a target; widen or tighten `deploy`, its meet, and its compilation; severity order and meet; pack floor tightening; module weaker than floor; floor-only carriage and reference rewriting; unreachable meets; post-composition deadline feasibility |
| `projection/` | 15 | a canary per projection row of §8.2, unresolved alias, unavailable token map, unlisted-field refusal, closed errors without echo |
| `latency_roundtrip/` | 2 | the `backend_v1` codec round trip of §10.3 |
| `promotion/` | 10 | `monitor_outcomes` normalization and readiness, `missing_monitor_counts`, `chance_constraint_shadowed`, and the gate join over supplied verdicts (§6.11) |
| `report_schema/` | 4 | the closed shape of `tvl-runtime-report/1` (§11.4.3) |

The release gate's verdicts (§6.11) are covered by the public test suite as well as by the `promotion/` cases. The
existing 1.2 corpus and its results are unchanged. Conformance of evaluator behaviour belongs to evaluator profiles
and their own conformance (§3.5, §12).

## 14. Metatheory

All theorems carry well-formedness hypotheses (0 < θ < 1, 0 < α ≤ 1, 0 ≤ c ≤ 1, valid profiles; probabilities cast
to `NNReal` for `PMF.binomial`). They are statements about the language and about exact binomial tests; obligations of
evaluator profiles are not listed here (§3.5). The statement authority is formal semantics §12.14; the column "§12"
gives its number. The last column names the Lean declarations (paths under `proofs/TVL/`) and the class that
`proofs/PROOF_SUMMARY.md` records for each — SUBSTANTIVE, BY-CONSTRUCTION, WEAKER or OPEN — at this revision.
`proofs/PROOF_SUMMARY.md` is the authority for proof status; a disagreement is a defect in this table. A row marked
**paper result** has no Lean declaration: its argument is given in prose (formal semantics §12.14) and is not
mechanised.

| Statement | §12 | Gloss | Lean declarations and recorded class |
|---|---|---|---|
| `conservative_extension` | 12.1 | a 1.2 module means the same under 1.3 | `conservative_extension`, `no_promotion_monitors` (`Runtime/Extension.lean`): BY-CONSTRUCTION |
| `structural_projection` | 12.2 | runtime blocks leave the TVAR context, configuration space and SAT encoding unchanged | `structural_projection` (`Runtime/Extension.lean`): BY-CONSTRUCTION; it covers the stored legacy fields, while the exclusion of runtime names from Γ and from generated variables is not modelled |
| `promotion_refinement`, `join_promote_iff`, `join_empty` | 12.3 | the gate join promotes iff the legacy gate promotes and every promotion monitor is MET; any Reject dominates; no monitors = the legacy gate | `promotion_refinement` (`Runtime/Extension.lean`): SUBSTANTIVE; `join_promote_iff` (`Gate.lean`): SUBSTANTIVE; `join_empty` (`Gate.lean`): BY-CONSTRUCTION |
| `tail_mono_p` | 12.4 | exact binomial tails are monotone in p and in the count | `tail_mono_p`, `upper_mono_count`, `lower_mono_count`, `upper_mono_parameter`, `lower_antitone_parameter` (`Runtime/BinomialGeneric.lean`): SUBSTANTIVE |
| exact upper-tail test level | 12.5 | under a good window (count dominated by Bin(N, θ)), P[k ≥ 1 ∧ P_θ(≥ k) < α] ≤ α | **paper result**, not mechanised. Mechanised ingredients: `upper_mono_count` (`Runtime/BinomialGeneric.lean`) and `binomial_good_window` (`Runtime/BinomialLaw.lean`), both SUBSTANTIVE; the good-window hypothesis is the definition `GoodWindow` |
| exact lower-tail test level | 12.6 | under a bad window, P[k < N ∧ P_θ(≤ k) ≤ 1 − c] ≤ 1 − c | **paper result**, not mechanised. Mechanised ingredients: `bad_lower_bound`, `lower_mono_count` (`Runtime/BinomialGeneric.lean`) and `binomial_bad_window` (`Runtime/BinomialLaw.lean`), all SUBSTANTIVE |
| `horizon_false_alarm` | 12.7 | finite union bound over predesignated looks, without independence | `horizon_false_alarm` (`Runtime/BinomialGeneric.lean`): SUBSTANTIVE |
| `compose_partial` | 12.8 | the raw meet is the greatest lower bound; validated composition succeeds iff the meet is reachable | `compose_partial_statement` (`Runtime/Compose.lean`): OPEN; its numeric-bounds part `raw_bounds_glb`: SUBSTANTIVE; `checked_bounds_meet_iff`: BY-CONSTRUCTION |
| `severity_meet_glb` | 12.9 | absent `notify` severity is `critical`; the severity meet is the greatest lower bound | `severity_meet_glb` (`Runtime/Declarations.lean`): SUBSTANTIVE; `absent_notify_severity` (same file): BY-CONSTRUCTION |
| `deploy_meet_glb` | 12.8 | absent `optimize` deploy is `never`; the deploy meet is the greatest lower bound; a deploy coordinate is valid only on `optimize` | `deploy_meet_glb` (`Runtime/Declarations.lean`): SUBSTANTIVE; `absent_deploy` (same file): BY-CONSTRUCTION; the coordinate is part of `RuleTightens`, `rawRuleMeet` and `ValidReachableContract` (`Runtime/Compose.lean`), whose statement stays OPEN |
| `backend_profile_roundtrip` | 12.10 | lift ∘ lower = id on valid hosted profiles | `backend_profile_roundtrip` (`Runtime/Backend.lean`): BY-CONSTRUCTION, under supplied bijective codecs |
| `compiled_contract_correct_statement` | 12.11 | compilation preserves normalized declarations (an open target) | `compiled_contract_correct_statement` (`Runtime/Compiler.lean`): OPEN |
| float `_v1` versus rational `_v2` agreement | deferred | — | — |
| episode false-closure bound; heterogeneous units; anytime-valid sequences | not claimed | — | — |

**Not claimed.** No theorem about `clopper_pearson_exact_v1`; none about the Python implementation (it is checked by
the conformance cases and tests); none about any evaluator's classification, counting, lifecycle or execution
procedures; none about wire-level privacy (canaries are tests); none about repair efficacy.

## 15. Examples

### 15.1 The three required cases

```yaml
tvl: { module: acme.support_bot }
tvl_version: "1.3"
environment: { snapshot_id: "2026-10-16T00:00:00Z" }
evaluation_set: { dataset: support_eval_v4 }
tvars: [ { name: model, type: "enum[str]", domain: [m_small, m_large] } ]
objectives: [ { name: quality, direction: maximize } ]
promotion_policy: { dominance: epsilon_pareto, alpha: 0.05, min_effect: { quality: 0.02 } }

requirements:
  - name: latency_2s                         # (i) the existing backend requirement
    kind: rate_bound
    unit: trace
    violation: { metric: wall_clock_latency_ms, exceeds: 2000 }
    max_rate: 0.05
  - name: refuses_disallowed                 # (ii) behavioural, checked customer-side
    kind: rate_bound
    unit: invocation
    among:     { checker: traigent.refusal.v1, label_in: [must_refuse] }
    violation: { checker: traigent.refusal.v1, label_in: [complied] }
    max_rate: 0.01
  - name: latency_recovers                   # (iii) recover within T after a breach
    kind: recovery_time
    unit: episode
    of: latency_2s_prod
    within_hours: 48

monitors:
  - name: latency_2s_prod
    requirement: latency_2s
    phase: runtime
    profile: backend_v1
    applies_to: agent
    evidence: { source: backend_trace_metadata, deployment_environment: production,
                attribution: agent_key_exact_v1, resolution: terminal_status_v1, sampling: unverified }
    window: { tumbling_hours: 6, grace_minutes: 30 }
    decision: { method: clopper_pearson_exact_v1, model: iid_bernoulli_within_window_v1, confidence: 0.95,
                false_alarm_budget: 0.05, horizon_days: 30, min_samples: 200, max_unresolved_fraction: 0.05 }
    episode: { closure_windows: 2, closure_max_age_hours: 24 }
  - name: latency_2s_gate                    # same requirement on evaluation-set evidence (§3.2)
    requirement: latency_2s
    phase: promotion
    evidence: { source: evaluation_set }
    decision: { method: clopper_pearson_rational_v2, confidence: 0.95, false_alarm_budget: 0.05 }
  - name: refuses_disallowed_prod
    requirement: refuses_disallowed
    phase: runtime
    applies_to: agent
    evidence: { source: customer_side, deployment_environment: production, attribution: agent_key_exact_v1,
                sampling: { mode: hash_bernoulli_committed_v1, rate: 0.10 } }
    window: { tumbling_hours: 24, grace_minutes: 120 }
    decision: { method: clopper_pearson_rational_v2, model: iid_bernoulli_within_window_v1, confidence: 0.95,
                false_alarm_budget: 0.05, horizon_days: 30, min_samples: 300, max_unresolved_fraction: 0.10 }
    episode: { closure_windows: 2, closure_max_age_hours: 72 }
  - name: latency_recovers_check
    requirement: latency_recovers
    phase: runtime
    evidence: { source: episodes }
    decision: { method: exact_count_v1 }

responses:
  - name: latency_ladder
    rules:
      - { id: warn_open, trigger: { monitor: latency_2s_prod, event: episode_opened }, do: notify, severity: warning }
      - { id: next_step, trigger: { monitor: latency_2s_prod, event: episode_opened }, do: open_next_step }
      - { id: rollback_6h, trigger: { monitor: latency_2s_prod, event: episode_open_for, hours: 6 },
          do: rollback, target: last_certified, approval: standing }
      - { id: suspend_overdue, trigger: { monitor: latency_recovers_check, event: recovery_overdue },
          do: suspend, approval: human, fallback: static_unavailable }
      - { id: info_resolved, trigger: { monitor: latency_2s_prod, event: episode_resolved }, do: notify,
          severity: info }
```

Checks:

- deadline: 48 h ≥ K_close · W = 2 · 6 h = 12 h;
- closure reachability: `latency_2s_prod` 24 · 60 = 1440 ≥ 2 · 6 · 60 + 30 + 60 = 810; `refuses_disallowed_prod`
  72 · 60 = 4320 ≥ 2 · 24 · 60 + 120 + 60 = 3060;
- refusal MET is reachable at `min_samples` 300 for θ 0.01, c 0.95 (needs N ≥ 299). At 10 % sampling that is at least
  3000 eligible invocations per 24 h window; with fewer the window is UNKNOWN(insufficient);
- `runtime_liveness_missing` (W) fires for `latency_2s_prod` and `refuses_disallowed_prod`: the example has no
  `evidence_liveness` requirement (§15.2 shows one in a pack). `tvl-validate` therefore exits 2 on this module (its
  unchanged rule: any issue, warnings included), while `tvl-compile-runtime` compiles it (warnings allowed, §11.5);
- `latency_2s_gate` uses the promotion defaults `min_samples` 1 and `max_unresolved_fraction` 0, and is evaluated on the
  candidate bundle's `monitor_outcomes.latency_2s_gate`;
- `traigent.refusal.v1` is a catalogue checker (§4.2.2): no customer registry is needed;
- the ladder: on opening, warn and issue the restore step; still open 6 h after opening, roll back to the last
  certified configuration under a standing grant; OVERDUE at 48 h, suspend after a human approves; on resolution,
  notify (delivered although the episode is closed).

### 15.2 An organisation pack

```yaml
tvl_version: "1.3"
pack: { module: acme.org_floors }
requirements:
  - name: latency_floor_2s
    kind: rate_bound
    unit: trace
    violation: { metric: wall_clock_latency_ms, exceeds: 2000 }
    max_rate: 0.10
  - name: latency_floor_live
    kind: evidence_liveness
    unit: window
    of: latency_floor_2s_prod
    max_stale_windows: 4
monitors:
  - name: latency_floor_2s_prod
    requirement: latency_floor_2s
    phase: runtime
    profile: backend_v1
    applies_to: tenant_floor
    evidence: { source: backend_trace_metadata, deployment_environment: production,
                attribution: agent_key_exact_v1, resolution: terminal_status_v1, sampling: unverified }
    window: { tumbling_hours: 6, grace_minutes: 30 }
    decision: { method: clopper_pearson_exact_v1, model: iid_bernoulli_within_window_v1, confidence: 0.95,
                false_alarm_budget: 0.05, horizon_days: 30, min_samples: 200, max_unresolved_fraction: 0.05 }
    episode: { closure_windows: 2, closure_max_age_hours: 24 }
  - name: latency_floor_live_check
    requirement: latency_floor_live
    phase: runtime
    applies_to: tenant_floor
    evidence: { source: windows }
    decision: { method: exact_count_v1 }
responses:
  - name: floor_alerts
    rules:
      - { id: floor_open, trigger: { monitor: latency_floor_2s_prod, event: episode_opened }, do: notify,
          severity: warning }
      - { id: floor_stale, trigger: { monitor: latency_floor_live_check, event: stale }, do: notify,
          severity: critical }
```

`tvl-compose --pack org_floors.yml support_bot.yml` composes it with §15.1 by §9.4:

- `latency_floor_2s_prod` and `latency_2s_prod` share the `backend_v1` effective key (latency, 2000 ms, production)
  and the schedule (6 h, 30 min, 30 days, 0.05). The module monitor is not weaker than the floor (θ 0.05 ≤ 0.10, other
  fields equal), so the pair passes and the effective profile is the module's. The pack monitor is absorbed: the
  composed module keeps `latency_2s_prod` (and `latency_2s`), with `latency_floor_2s_prod` as an alias.
- The pack references are rewritten: `latency_floor_live.of` and the `floor_open` trigger now name `latency_2s_prod`.
- `latency_floor_live_check` has no module counterpart: it is carried as a floor-only monitor with `applies_to:
  tenant_floor`, with `latency_floor_live` and the floor provenance `match: floor_only`; `floor_alerts` is added.
- For an agent without its own latency monitor, the floor monitor itself is floor-only and applies alone from the
  agent's first attributed trace. The liveness requirement reports STALE when none of the last five due windows (30 h)
  carries usable evidence.

### 15.3 A zero-tolerance requirement with a local guard

```yaml
requirements:
  - name: payment_needs_authorization
    kind: zero_tolerance
    unit: invocation
    violation: { pattern: precedence, a: { event: authorization_granted, ref: payment_auth },
                 b: { event: tool_call, tool: payments.charge }, mode: single_use, correlate_by: correlation_id }
monitors:
  - name: payment_needs_authorization_prod
    requirement: payment_needs_authorization
    phase: runtime
    evidence: { source: customer_side, deployment_environment: production }
    window: { tumbling_hours: 24, grace_minutes: 60 }
    decision: { method: exact_count_v1 }
    episode: { closure_windows: 1, closure_max_age_hours: 48 }
    limits: { max_active_obligations: 64, max_tracked_correlations: 1024 }
responses:
  - name: payment_guard
    rules:
      - { id: block_charge, trigger: { monitor: payment_needs_authorization_prod, event: unit_violation },
          do: block_action, on_check_error: block }
      - { id: page, trigger: { monitor: payment_needs_authorization_prod, event: episode_opened },
          do: notify, severity: critical }
```

A `payments.charge` call with no earlier, unrevoked, unconsumed `payment_auth` grant under the same `correlation_id`
violates the requirement as soon as it occurs: the violation is fixed by a prefix (§6.4). When the customer-side
evaluator establishes that before the call takes effect, the guard suppresses the call, the unit is vio and the window
is BREACHED. When it cannot establish it at that moment (for example, a second producer's events whose order relative
to the call is not yet known), `on_check_error: block` blocks the call. MET needs a complete, non-empty window: census,
every selected unit accounted for and classified, and the report's coverage attestation in full (§6.9); a window
without traffic is UNKNOWN(insufficient). Closure reachability: 48 · 60 = 2880 ≥ 1 · 24 · 60 + 60 + 60 = 1560.

## 16. Design decisions, resolutions and open questions

### 16.1 Design decisions (recorded 2026-10-16)

| Decision | Choice |
|---|---|
| D1 structure | three optional TVL 1.3 blocks `requirements` / `monitors` / `responses`, with opt-in promotion monitors, rather than one runtime block |
| D2 response authority | `suspend` needs a human per episode and stays latched until a human resume; hold when authority is unreachable; rollback, restriction (`throttle`, `degrade`) and `optimize` run only under a bounded standing grant of at most 30 days, or a human approval |
| D3 organisation floors | a separate `tvl_pack` document, composed by tightening only |
| D4 first scope | specify the whole catalogue; ship measurement, `notify` and `open_next_step` first; enable each kind and each effectful action only after its conformance evidence passes |
| D5 recovery clock | window time — "the closing window ends within T of the opening window's end", reproducible from the records and unaffected by scheduling; wall-clock duration shown beside it |
| Language and evaluator boundary | TVL states complete-history meaning, parameter meanings and the verdict contract; partial-evidence decision rules, applied counting rules, lifecycle tracking and execution belong to evaluator profiles (§3.5). TVL's statistics are the named methods and generic probability results (§14). The release gate evaluates promotion monitors only when nothing is unresolved (§6.11) |

D2's "restriction" is `throttle` and `degrade` here. D5's "unaffected by scheduling" holds for how the deadline is
measured; closure itself can still be delayed by evaluation lag, which §6.13 reports as `closure_blocked_by_lag`.

### 16.2 Resolved design points

| # | Point | Resolution | Where |
|---|---|---|---|
| 1 | YAML key `on` | rule key renamed `trigger` and transition key renamed `when`; quoting is no longer used | §4.1 |
| 2 | Window-report attestations | `tail_sampled` and a six-field `coverage` record, not a single `complete` boolean | §8.3, §11.4.3 |
| 3 | Statistical defaults | none outside `backend_v1` and the promotion and zero-tolerance defaults | §4.5 |
| 4 | Domains outside `backend_v1` | the hosted profile's ranges | §4.2 |
| 5 | Clock for `episode_open_for` and repeats | lifecycle time | §4.7, §7.4 |
| 6 | Escalation events for `suspend` | `episode_continued`, `episode_open_for`, `recovery_overdue` | §7.2 |
| 7 | `resume` eligibility | after resolution or withdrawal; always human | §7.3 |
| 8 | Missing customer report | no usable evidence for liveness; never a silent gap | §6.14 |
| 9 | Tail sampling | `UNKNOWN(sampling_biased)` | §6.7 |
| 10 | Customer checker binding | `customer:` id namespace and the `tvl-checker-registry/1` document | §4.2.2, §11.4.5 |
| 11 | `status`, `error(class)`, `severity` | `status` = {`running`, `completed`, `failed`, `rejected`}; `error` class not selectable; `severity` kept; all closed enums in one table | §4.2.1, T11 |
| 12 | Non-`backend_v1` effective key; overlay additions | requirement identity and effective key defined; pack normalization specified | §9.1, §9.4 |
| 13 | `runtime_met_unreachable_at_min_samples` under `backend_v1` | warning there, error elsewhere | §5.5 |
| 14 | Source of `unit_violation` | customer-side primary monitors only | §4.7 |
| 15 | Rank-reversal lint | not adopted | — |
| 16 | Empty census-complete zero-tolerance window | `UNKNOWN(insufficient)`, never MET | §6.9 |
| 17 | No dots in runtime names | accepted | §4.2 |
| 18 | Codes | §5 is the single source; every out-of-range code names one field | §5 |
| 19 | In-process blocking of checker violations | none in 1.3 | §6.5 |
| 20 | Zero-tolerance promotion completeness | explicit `complete: true`; never inferred from u = pl = 0 | §6.11, §11.4.2 |
| 21 | Throttle and degrade release | an authorized human, as for `resume` | §7.3 |
| 22 | Severity under composition | ordered `info < warning < critical`, absent = `critical`; maximum in a raw meet; no lowering | §4.6, §9.3 |
| 23 | `last_certified` | the latest certificate for the agent at the time of the effect; hold and notify if ineligible, never a fallback | §7.2 |
| 24 | `optimize` candidates | deploying a candidate is a separate effect, declared by `deploy: if_promoted`, that passes the joined promotion gate and its own authority checks; it never closes an episode | §7.2, §7.6 |
| 25 | Legacy CLIs | for pre-1.3 documents every existing CLI keeps its exact prior behaviour | §11.2 |
| 26 | Compilation and enablement | the compiler compiles any valid specification; capability, certificate and enablement checks happen at registration | §11.5, §12 |

### 16.3 Open questions (this revision)

Each is settled here by the most conservative reading and needs confirmation at review.

1. **Version omitted.** An omitted `tvl_version` on a module with runtime blocks is `runtime_version_required`, not
   `declared_version_below_constructs`, so that omission keeps legacy version handling on legacy modules.
2. **Catalogue labels.** `traigent.refusal.v1` has exactly two labels (`must_refuse`, `complied`), each the negative
   answer of the other's position (§4.2.2). Whether the entry needs explicit complementary labels (for example for
   requests that need no refusal, or for refusals) is a catalogue revision.
3. **Who releases a throttle or degrade.** An authorized human, with current authority and eligibility of the resulting
   route, as for `resume`; scope closure never releases controls.
4. **Severity under composition.** `info < warning < critical`, absence normalized to `critical`, the maximum in a raw
   meet, no lowering in an overlay or below a pack rule.
5. **Composed modules validated alone** fail with `tenant_floor_outside_pack` only when they carry tenant-floor
   monitors without provenance (§9.4 step 7). All-paired agent-only previews can validate as ordinary modules; this
   proves no pack activation. Compilation takes the module and the packs as sources.
6. **Untrusted clock.** A deadline comparison across producers without a trusted common time basis cannot establish a
   `bounded_response` violation or satisfaction; the unit is `unres`.
7. **Invalid promotion counts.** k > n in `monitor_outcomes` is reported as `missing_monitor_counts` rather than under a
   new code.
8. **Report binding failures** (§5.10) share `runtime_report_conservation` rather than a new code.
9. **Registration records.** The certificate, grant and enablement records a registering platform uses are outside this
   RFC.
10. **Contract scope for floors.** A module's contract carries only its own (agent-scope) monitors and records the packs
    it was checked against; floor monitors are registered from the pack's own contract and composed by the platform at
    evaluation.
11. **Trace and invocation.** §6.2 defines a trace as one end-to-end handling of one request and an invocation as one
    execution of the agent's entry point. These definitions are the reading under which every 1.3 example and lint is
    unchanged.
12. **`rate_floor`.** Defined as a fraction of the unthrottled admission rate, so a smaller value throttles harder and
    the minimum over active throttles is the most restrictive (§7.2). This is the reading consistent with the domain
    (0, 1) and the minimum rule.
13. **Revocation scope.** A revocation matches grants of the same `ref` under the predicate's correlation key (§6.3); a
    revocation without that key revokes nothing.
14. **Metrics other than latency.** `cost_usd`, `total_tokens` and `tool_calls` are the unit's values as its producer
    records them; TVL does not define how they are measured.
15. **Release-gate reason for zero tolerance without `complete: true`.** For valid counts with u = 0 and pl = 0, the
    release gate reports `UNKNOWN(incomplete)` (not `engine_required`; with u > 0 or pl > 0 the first row of §6.11
    applies and the reason is `engine_required`): completeness is the harness's attestation, and no evaluator can
    supply it.
16. **Lateness allowance.** 2W after `due(w)` for every evaluator profile in 1.3 (§6.8); a different allowance would be
    a revision of this RFC.
17. **One approval for optimize and deploy.** A rule's single `approval` governs both effects, each approved separately;
    under `standing`, a deploy without a grant naming it needs a human (§7.6). A separate `deploy_approval` field is
    not added; "optimize automatically, deploy only after a human approves" is expressed by a grant that covers only
    the optimization.
18. **Deploy triggers.** Only episode events may carry `deploy: if_promoted` (§7.6 item 7); a deploy from a
    `recovery_overdue` trigger, whose scope also has an episode, is not admitted in this revision.
19. **Contract digests of existing `optimize` rules.** Filling `deploy: never` changes the compiled form, and so the
    contract digest, of every module with an `optimize` rule compiled before this revision. The first scope enables only
    `notify` and `open_next_step` (§12), so a platform that follows it has registered no such contract.
20. **Population membership.** `among` admits only a `checker_pred` (`runtime_among_not_checker`, §4.4 T4). For metric
    and exact predicates the violation reading and the satisfaction reading select opposite populations (for
    `absence` of `error`, units with an error versus units without one), and no 1.3 example needs either. A later
    revision may admit them with an explicit membership definition.

## Appendix A. Spelling decisions

The table lists user-visible spellings that were considered and not adopted, with the spelling this RFC uses and the
reason; in each case this RFC's choice stands.

| # | Spelling not adopted | This RFC | Reason |
|---|---|---|---|
| A1 | rule key `on` | `trigger` | YAML 1.1 loads an unquoted `on` as `True` (§4.1) |
| A2 | protocol transition key `on` | `when` | same reason |
| A3 | `runtime_weaker_than_floor` for a module weaker than a pack floor | `requirement_weaker_than_floor` | the hosted latency profile's code |
| A4 | `runtime_weaker_than_floor` for an overlay that drops or weakens a rule | `runtime_overlay_weakens` | an overlay against its base is not a floor |
| A5 | `runtime_schedule_mismatch` | `evaluation_schedule_mismatch` | the hosted latency profile's code |
| A6 | `runtime_composed_closure_unreachable` | `closure_unreachable` | the hosted latency profile's code |
| A7 | `runtime_invalid_profile` for a changed predicate, population or method | `runtime_incompatible_replacement` | a dedicated code for immutable-identity changes (§9.1) |
| A8 | projection pointers at the document root (`/tvl/module`, `/requirements/0/…`) | the hosted contract nests the projected declarations under `/declarations` | §11.4.1 adds format, digests and backend profiles beside the declarations |
| A9 | hosted backend profile with a plaintext `environment` | `environment_ref` (opaque) | the environment label is content (§8.2) |
| A10 | a window input `sampling_biased: Bool` | report field `tail_sampled: Nat`, with `UNKNOWN(sampling_biased)` iff `tail_sampled > 0` | a count is checkable against `reported` (§5.10) |
| A11 | omitted `tvl_version` on a runtime module: no dedicated code | `runtime_version_required` | T17 |
| A12 | `runtime_met_unreachable_at_min_samples` always an error | an error, and a warning under `backend_v1` | valid hosted profiles must lift to valid modules (§5.5) |
| A13 | `applies_to` optional on pack monitors | a pack monitor declares `applies_to: tenant_floor` explicitly | T16 |
| A14 | compose operations `overlay` and `meet` | `tvl-compose --pack` and `tvl-compose --meet` | §11.5 |
