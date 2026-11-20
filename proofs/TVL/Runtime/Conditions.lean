/- TVL 1.7 (DRAFT), RFC 0011 Part A, formal semantics §16.1-§16.5.
   Abstract step-function model of the merged input stream, external and schedule
   triggers, missed-tick coalescing, the pending queue with one open repair, and new-model
   admission. Facts the platform records (authentication, window verdicts, approvals) are
   inputs; no clock is read. Instants are whole seconds (RFC 0011 §2.2 item 1). The TVL admission construct is named `admitTvar` here because its
   keyword is a banned tactic name in this tree (CI rejects it). -/
import Mathlib

namespace TVL.Runtime.Conditions

universe u v

/-- Generic invariant rule for folding a step function over a list of inputs. -/
theorem foldl_invariant {α : Type u} {β : Type v} (P : β → Prop) (f : β → α → β)
    (hstep : ∀ b a, P b → P (f b a)) (b : β) (l : List α) (h : P b) :
    P (l.foldl f b) := by
  induction l generalizing b with
  | nil => exact h
  | cons a l ih => exact ih (f b a) (hstep b a h)

/-! ## 16.1 Event envelope, selector, admission checks (RFC 0011 §2.2, §2.3, §2.13 item 1) -/

inductive Family where
  | anthropic | openai | google | metaAI | mistral | amazon
  deriving DecidableEq, Repr

inductive Tier where
  | small | medium | large
  deriving DecidableEq, Repr

/-- The closed subject of a `model_released` event; `modelRef` is an opaque catalogue id. -/
structure Subject where
  modelRef : Nat
  family : Family
  tier : Tier
  deriving DecidableEq, Repr

/-- The closed envelope. `authentic` records the platform's signature verification (RFC 0011
§2.2 item 3); the evaluator does not recompute it. `issuedAt` is an integer number of seconds. -/
structure Event where
  issuer : Nat
  eid : Nat
  issuedAt : Int
  subject : Subject
  authentic : Bool
  deriving DecidableEq, Repr

/-- `ext_match`: an absent field is `none` and matches any value; a present field matches
only the listed values (so a present empty list matches nothing). -/
structure Selector where
  family : Option (List Family)
  tier : Option (List Tier)

def Selector.accepts (m : Selector) (s : Subject) : Bool :=
  (match m.family with | none => true | some l => decide (s.family ∈ l)) &&
  (match m.tier with | none => true | some l => decide (s.tier ∈ l))

/-- RFC 0011 §2.3: an absent selector field matches any value. -/
theorem selector_absent_matches_any (s : Subject) :
    (Selector.mk none none).accepts s = true := by
  simp [Selector.accepts]

/-- RFC 0011 §2.2 item 4: lateness bound, 72 hours in seconds. -/
def lateBound : Int := 72 * 3600

inductive EventResult where
  | rejectedUnauthenticated | redelivery | rejectedLate | admitted
  deriving DecidableEq, Repr

/-- Order of checks of §2.13 item 1: authentication, redelivery of an admitted
(issuer, event id), lateness, then (elsewhere) matching. -/
def classify (now : Int) (seen : List (Nat × Nat)) (e : Event) : EventResult :=
  if e.authentic = false then .rejectedUnauthenticated
  else if (e.issuer, e.eid) ∈ seen then .redelivery
  else if now - e.issuedAt > lateBound then .rejectedLate
  else .admitted

/-! ## 16.2 The merged, totally ordered input stream (§2.2 item 5, §2.13 item 2) -/

/-- Order of events arriving at one instant: (issued_at, issuer, event_id). -/
def evLE (a b : Event) : Prop :=
  a.issuedAt < b.issuedAt ∨
  (a.issuedAt = b.issuedAt ∧ (a.issuer < b.issuer ∨ (a.issuer = b.issuer ∧ a.eid ≤ b.eid)))

instance : DecidableRel evLE := fun a b => by unfold evLE; infer_instance

instance : Std.Total evLE := ⟨fun a b => by unfold evLE; omega⟩

instance : IsTrans Event evLE := ⟨fun a b c => by unfold evLE; omega⟩

/-- Events of one instant in the normative order (stable on ties). -/
def orderEvents (es : List Event) : List Event := es.insertionSort evLE

/-- The events of an instant are processed in a total order that loses and invents none. -/
theorem merged_order_total (es : List Event) :
    (orderEvents es).Perm es ∧ (orderEvents es).Pairwise evLE :=
  ⟨List.perm_insertionSort _ _, List.pairwise_insertionSort _ _⟩

/-- One instant of the stream: evaluations first (modelled by the other state machines), then
the events of that instant in the order above. -/
structure Step where
  now : Int
  events : List Event

/-! ## 16.3 External scope: one event, one occurrence (§2.3) -/

/-- Occurrence key of an external scope: (rule id, issuer, event id); occurrence index is 0. -/
abbrev ExtKey := Nat × Nat × Nat

structure ExtRule where
  id : Nat
  sel : Selector

structure ExtState where
  seen : List (Nat × Nat)
  fired : List ExtKey

def ExtState.init : ExtState := ⟨[], []⟩

/-- Processing one event: only an admitted event is remembered and fires; it fires each
matching rule exactly once, under the key (rule, issuer, event id). -/
def extStep (now : Int) (rules : List ExtRule) (s : ExtState) (e : Event) : ExtState :=
  match classify now s.seen e with
  | .admitted =>
    { seen := (e.issuer, e.eid) :: s.seen,
      fired := s.fired ++
        ((rules.filter (fun r => r.sel.accepts e.subject)).map
          (fun r => (r.id, e.issuer, e.eid))) }
  | _ => s

def extInstant (rules : List ExtRule) (s : ExtState) (st : Step) : ExtState :=
  (orderEvents st.events).foldl (extStep st.now rules) s

/-- Run a whole stream of instants. -/
def extRun (rules : List ExtRule) (steps : List Step) : ExtState :=
  steps.foldl (extInstant rules) ExtState.init

def ExtInv (s : ExtState) : Prop :=
  s.fired.Nodup ∧ ∀ k ∈ s.fired, (k.2.1, k.2.2) ∈ s.seen

theorem extStep_inv (now : Int) (rules : List ExtRule) (hr : (rules.map (·.id)).Nodup)
    (s : ExtState) (e : Event) (h : ExtInv s) : ExtInv (extStep now rules s e) := by
  unfold extStep
  split
  · rename_i hc
    obtain ⟨hnd, hseen⟩ := h
    have hnot : (e.issuer, e.eid) ∉ s.seen := by
      intro hm
      unfold classify at hc
      split_ifs at hc
    have hmap : ((rules.filter (fun r => r.sel.accepts e.subject)).map
          (fun r => (r.id, e.issuer, e.eid))) =
        ((rules.filter (fun r => r.sel.accepts e.subject)).map (·.id)).map
          (fun n => (n, e.issuer, e.eid)) := by
      rw [List.map_map]; rfl
    have hnew : ((rules.filter (fun r => r.sel.accepts e.subject)).map
          (fun r => (r.id, e.issuer, e.eid))).Nodup := by
      rw [hmap]
      apply List.Nodup.map
      · intro a b hab
        simpa using hab
      · exact List.Nodup.sublist ((List.filter_sublist).map _) hr
    refine ⟨?_, ?_⟩
    · rw [List.nodup_append]
      refine ⟨hnd, hnew, ?_⟩
      intro a ha b hb hab
      subst hab
      obtain ⟨r, _, rfl⟩ := List.mem_map.mp hb
      exact hnot (hseen _ ha)
    · intro k hk
      rcases List.mem_append.mp hk with hk | hk
      · exact List.mem_cons_of_mem _ (hseen k hk)
      · obtain ⟨r, _, rfl⟩ := List.mem_map.mp hk
        exact List.mem_cons_self
  · exact h

theorem extRun_inv (rules : List ExtRule) (hr : (rules.map (·.id)).Nodup)
    (steps : List Step) : ExtInv (extRun rules steps) := by
  unfold extRun
  apply foldl_invariant (P := ExtInv)
  · intro s st hs
    unfold extInstant
    exact foldl_invariant (P := ExtInv) _ (fun s' e hs' => extStep_inv _ rules hr s' e hs') s _ hs
  · exact ⟨List.nodup_nil, by simp [ExtState.init]⟩

/-- `external_event_unique` (RFC 0011 §2.2 item 4, §2.3; §4). In every stream, no occurrence
key (rule, issuer, event id) is fired twice: redeliveries of one (issuer, event id) produce
one occurrence per matching rule. Class: SUBSTANTIVE (induction over arbitrary streams). -/
theorem external_event_unique (rules : List ExtRule) (hr : (rules.map (·.id)).Nodup)
    (steps : List Step) :
    (extRun rules steps).fired.Nodup ∧
    ∀ k, (extRun rules steps).fired.count k ≤ 1 := by
  have h := (extRun_inv rules hr steps).1
  exact ⟨h, fun k => List.nodup_iff_count_le_one.mp h k⟩

/-- A redelivery, a late event and an unauthenticated copy fire nothing (§2.2, §2.13 item 1). -/
theorem nonadmitted_fires_nothing (now : Int) (rules : List ExtRule) (s : ExtState) (e : Event)
    (h : classify now s.seen e ≠ .admitted) : extStep now rules s e = s := by
  unfold extStep
  split
  · rename_i hc; exact absurd hc h
  · rfl

/-- An unauthenticated copy is not remembered, so a later authentic copy with the same id is
still admitted (§2.13 item 1). -/
theorem unauthenticated_not_remembered (now : Int) (rules : List ExtRule) (s : ExtState)
    (e : Event) (h : e.authentic = false) : (extStep now rules s e).seen = s.seen := by
  have : classify now s.seen e ≠ .admitted := by simp [classify, h]
  rw [nonadmitted_fires_nothing now rules s e this]

/-! ## 16.4 Schedule scope and missed-tick coalescing (§2.4) -/

/-- Latest tick index t_k = first + k * period that has passed at `now`, if any. -/
def latestTick (first period now : Nat) : Option Nat :=
  if now < first then none else some ((now - first) / period)

/-- `done` means every tick index below it has been decided (fired or skipped as coalesced). -/
structure SchedState where
  done : Nat
  fired : List Nat
  skipped : List Nat

def SchedState.init : SchedState := ⟨0, [], []⟩

/-- At a clock reading, only the latest passed tick fires, once; earlier undecided ticks
are recorded as `skipped(coalesced)`; ticks are never replayed. -/
def schedStep (first period : Nat) (s : SchedState) (now : Nat) : SchedState :=
  match latestTick first period now with
  | none => s
  | some L =>
    if L < s.done then s
    else { done := L + 1, fired := s.fired ++ [L],
           skipped := s.skipped ++ List.range' s.done (L - s.done) }

def schedRun (first period : Nat) (readings : List Nat) : SchedState :=
  readings.foldl (schedStep first period) SchedState.init

def SchedInv (s : SchedState) : Prop :=
  s.fired.Nodup ∧ s.skipped.Nodup ∧ (∀ k ∈ s.fired, k ∈ s.skipped → False) ∧
  (∀ k ∈ s.fired, k < s.done) ∧ (∀ k ∈ s.skipped, k < s.done) ∧
  (∀ k, k < s.done → k ∈ s.fired ∨ k ∈ s.skipped)

theorem schedStep_inv (first period : Nat) (s : SchedState) (now : Nat) (h : SchedInv s) :
    SchedInv (schedStep first period s now) := by
  unfold schedStep
  split
  · exact h
  · rename_i L _
    split
    · exact h
    · rename_i hL
      obtain ⟨hf, hs, hdis, hfd, hsd, hall⟩ := h
      have hLd : s.done ≤ L := by omega
      refine ⟨?_, ?_, ?_, ?_, ?_, ?_⟩ <;> dsimp only
      · rw [List.nodup_append]
        refine ⟨hf, List.nodup_singleton _, ?_⟩
        intro a ha b hb hab
        simp at hb; subst hb; subst hab
        have := hfd _ ha; omega
      · rw [List.nodup_append]
        refine ⟨hs, List.nodup_range', ?_⟩
        intro a ha b hb hab
        subst hab
        simp [List.mem_range'] at hb
        have := hsd _ ha; omega
      · intro k hk hk'
        simp only [List.mem_append, List.mem_singleton, List.mem_range'] at hk hk'
        rcases hk with hk | hk <;> rcases hk' with hk' | hk'
        · exact hdis k hk hk'
        · have := hfd _ hk; omega
        · have := hsd _ hk'; omega
        · omega
      · intro k hk
        simp only [List.mem_append, List.mem_singleton] at hk
        rcases hk with hk | hk
        · have := hfd _ hk; omega
        · omega
      · intro k hk
        simp only [List.mem_append, List.mem_range'] at hk
        rcases hk with hk | hk
        · have := hsd _ hk; omega
        · omega
      · intro k hk
        by_cases hk' : k < s.done
        · rcases hall k hk' with h | h
          · exact Or.inl (List.mem_append_left _ h)
          · exact Or.inr (List.mem_append_left _ h)
        · by_cases hkL : k = L
          · subst hkL; left; simp
          · right; apply List.mem_append_right
            rw [List.mem_range'_1]
            have : k < L + 1 := hk
            omega

theorem schedRun_inv (first period : Nat) (readings : List Nat) :
    SchedInv (schedRun first period readings) := by
  unfold schedRun
  apply foldl_invariant (P := SchedInv)
  · intro s a h; exact schedStep_inv first period s a h
  · simp [SchedInv, SchedState.init]

/-- `schedule_tick_unique` (RFC 0011 §2.4 item 1; §4). For every sequence of clock readings
(in any order, with repeats) each tick index fires at most once, and a tick that fired is
never also recorded as skipped. Class: SUBSTANTIVE (the `done` watermark guards the step). -/
theorem schedule_tick_unique (first period : Nat) (readings : List Nat) :
    (schedRun first period readings).fired.Nodup ∧
    (∀ k, (schedRun first period readings).fired.count k ≤ 1) ∧
    (∀ k, k ∈ (schedRun first period readings).fired →
      k ∉ (schedRun first period readings).skipped) := by
  have h := schedRun_inv first period readings
  refine ⟨h.1, fun k => List.nodup_iff_count_le_one.mp h.1 k, ?_⟩
  intro k hk hk'
  exact h.2.2.1 k hk hk'

/-- Coalescing (§2.4 item 2): after a reading at which tick `L` is the latest passed one,
every tick up to `L` has been decided exactly once (fired or skipped); ticks are never
replayed. -/
theorem schedule_coalesces (first period : Nat) (s : SchedState) (now L : Nat)
    (h : SchedInv s) (hL : latestTick first period now = some L) :
    ∀ k, k ≤ L → k ∈ (schedStep first period s now).fired ∨
      k ∈ (schedStep first period s now).skipped := by
  intro k hk
  have hi := (schedStep_inv first period s now h).2.2.2.2.2
  have hd : L < (schedStep first period s now).done := by
    unfold schedStep; rw [hL]
    by_cases hl : L < s.done
    · simp [hl]
    · simp [hl]
  exact hi k (by omega)

/-! ## 16.5 Pending occurrences and one open repair (§2.7) -/

/-- A trigger occurrence waiting to start: trigger instant, response name, rule id, and an
admission sequence number that breaks remaining ties. -/
structure Occ where
  instant : Nat
  response : Nat
  rule : Nat
  seq : Nat
  deriving DecidableEq, Repr

/-- Start order of pending occurrences: (trigger instant, response, rule id), then admission order. -/
def occLE (a b : Occ) : Prop :=
  a.instant < b.instant ∨ (a.instant = b.instant ∧ (a.response < b.response ∨
    (a.response = b.response ∧ (a.rule < b.rule ∨ (a.rule = b.rule ∧ a.seq ≤ b.seq)))))

instance : DecidableRel occLE := fun a b => by unfold occLE; infer_instance
instance : Std.Total occLE := ⟨fun a b => by unfold occLE; omega⟩
instance : IsTrans Occ occLE := ⟨fun a b c => by unfold occLE; omega⟩

/-- An attempt is the optimization AND its possible deploy (RFC 0004 §2.2); it is open while
it runs and while a deploy occurrence awaits acceptance. -/
inductive Status where
  | running | awaitingDeploy | closed
  deriving DecidableEq, Repr

structure Attempt where
  occ : Occ
  status : Status

def Attempt.isOpen (a : Attempt) : Bool := decide (a.status ≠ .closed)

structure RepairState where
  /-- true for an agent whose contract declares 1.7 or later (§2.7, §3) -/
  serialize : Bool
  attempts : List Attempt
  pending : List Occ

def RepairState.init (serialize : Bool) : RepairState := ⟨serialize, [], []⟩

def RepairState.openCount (s : RepairState) : Nat := s.attempts.countP Attempt.isOpen

inductive Input where
  /-- a trigger fires an `optimize` occurrence: it joins the pending queue -/
  | trigger (o : Occ)
  /-- the scope of a pending occurrence stopped requiring intervention -/
  | drop (seq : Nat)
  /-- optimization finished; `deploy` says a promoted candidate now awaits acceptance -/
  | optimizeFinished (deploy : Bool)
  /-- the deploy was written, refused, rejected, expired with its scope, or never took place -/
  | deployClosed
  /-- approval declined/expired, failure outcome, or an external or schedule scope that stopped
      requiring intervention while the attempt is open in any phase (RFC 0011 §2.13 item 6) -/
  | abort
  /-- start the next pending occurrence, if permitted -/
  | dispatch

def finishOpt (deploy : Bool) (a : Attempt) : Attempt :=
  if a.status = .running then ⟨a.occ, if deploy then .awaitingDeploy else .closed⟩ else a

def closeDeploy (a : Attempt) : Attempt :=
  if a.status = .awaitingDeploy then ⟨a.occ, .closed⟩ else a

def closeAny (a : Attempt) : Attempt := ⟨a.occ, .closed⟩

/-- Dispatch: under serialization nothing starts while any attempt is open (the occurrence
stays pending, `held(repair_open)`); otherwise the first pending occurrence in start order
starts. Contracts before 1.7 keep RFC 0003 meaning: every pending occurrence starts. -/
def dispatch (s : RepairState) : RepairState :=
  if s.serialize = true then
    if s.openCount = 0 then
      match s.pending with
      | [] => s
      | o :: rest => { s with attempts := s.attempts ++ [⟨o, .running⟩], pending := rest }
    else s
  else { s with attempts := s.attempts ++ s.pending.map (fun o => ⟨o, .running⟩), pending := [] }

def repairStep (s : RepairState) : Input → RepairState
  | .trigger o => { s with pending := s.pending.orderedInsert occLE o }
  | .drop q => { s with pending := s.pending.filter (fun o => o.seq ≠ q) }
  | .optimizeFinished d => { s with attempts := s.attempts.map (finishOpt d) }
  | .deployClosed => { s with attempts := s.attempts.map closeDeploy }
  | .abort => { s with attempts := s.attempts.map closeAny }
  | .dispatch => dispatch s

def repairRun (serialize : Bool) (inputs : List Input) : RepairState :=
  inputs.foldl repairStep (RepairState.init serialize)

def RepairInv (s : RepairState) : Prop :=
  (s.serialize = true → s.openCount ≤ 1) ∧ s.pending.Pairwise occLE

private theorem openCount_map (f : Attempt → Attempt) (hf : ∀ a, (f a).isOpen = true → a.isOpen = true)
    (l : List Attempt) : (l.map f).countP Attempt.isOpen ≤ l.countP Attempt.isOpen := by
  rw [List.countP_map]
  apply List.countP_mono_left
  intro x _ hx
  exact hf x hx

theorem repairStep_inv (s : RepairState) (i : Input) (h : RepairInv s) :
    RepairInv (repairStep s i) := by
  obtain ⟨h1, h2⟩ := h
  cases i with
  | trigger o =>
    exact ⟨h1, List.Pairwise.orderedInsert o _ h2⟩
  | drop q =>
    exact ⟨h1, h2.filter _⟩
  | optimizeFinished d =>
    refine ⟨fun hs => le_trans (openCount_map _ ?_ _) (h1 hs), h2⟩
    intro a ha
    unfold finishOpt Attempt.isOpen at *
    split_ifs at ha <;> simp_all
  | deployClosed =>
    refine ⟨fun hs => le_trans (openCount_map _ ?_ _) (h1 hs), h2⟩
    intro a ha
    unfold closeDeploy Attempt.isOpen at *
    split_ifs at ha <;> simp_all
  | abort =>
    refine ⟨fun hs => le_trans (openCount_map _ ?_ _) (h1 hs), h2⟩
    intro a ha
    unfold closeAny Attempt.isOpen at *
    simp at ha
  | dispatch =>
    simp only [repairStep, dispatch]
    split
    · rename_i hs
      split
      · rename_i h0
        split
        · exact ⟨h1, h2⟩
        · rename_i o rest hp
          refine ⟨fun _ => ?_, ?_⟩
          · simp only [RepairState.openCount, List.countP_append] at h0 ⊢
            simp [Attempt.isOpen, h0]
          · simp only [hp] at h2
            exact (List.pairwise_cons.mp h2).2
      · exact ⟨h1, h2⟩
    · rename_i hs
      exact ⟨fun h => absurd h hs, by simp⟩

theorem repairStep_serialize (s : RepairState) (i : Input) :
    (repairStep s i).serialize = s.serialize := by
  cases i <;> simp only [repairStep]
  unfold dispatch
  split
  · split
    · split <;> rfl
    · rfl
  · rfl

theorem repairRun_serialize (b : Bool) (inputs : List Input) :
    (repairRun b inputs).serialize = b := by
  unfold repairRun
  refine foldl_invariant (fun s => s.serialize = b) repairStep ?_ _ _ ?_
  · intro s i h; rw [repairStep_serialize]; exact h
  · rfl

theorem repairRun_inv (serialize : Bool) (inputs : List Input) :
    RepairInv (repairRun serialize inputs) := by
  unfold repairRun
  apply foldl_invariant (P := RepairInv)
  · intro s i h; exact repairStep_inv s i h
  · exact ⟨by intro _; simp [RepairState.init, RepairState.openCount], by simp [RepairState.init]⟩

/-- `one_open_repair` (RFC 0011 §2.7; §4). For an agent whose contract declares 1.7 or later,
in every sequence of inputs (triggers, drops, optimization results, deploy closures, aborts and
dispatches in any order), at most one optimize attempt is open at any point. The attempt
includes the deploy occurrence, so an attempt awaiting acceptance still holds the lock.
Class: SUBSTANTIVE (the dispatch guard is the only way an attempt opens). -/
theorem one_open_repair (inputs : List Input) :
    (repairRun true inputs).openCount ≤ 1 :=
  (repairRun_inv true inputs).1 (repairRun_serialize true inputs)

/-- While any attempt is open (including one awaiting its deploy acceptance), dispatch starts
nothing: the pending occurrences stay pending. -/
theorem held_while_open (s : RepairState) (hs : s.serialize = true) (ho : s.openCount ≠ 0) :
    dispatch s = s := by
  simp [dispatch, hs, ho]

/-- Scope end (or any abort) releases the one-open-repair lock (RFC 0011 §2.13 item 6): after
`abort` no attempt is open, so the next dispatch may start the head of the queue. -/
theorem abort_releases_lock (s : RepairState) : (repairStep s .abort).openCount = 0 := by
  simp only [repairStep, RepairState.openCount, List.countP_map]
  rw [List.countP_eq_zero]
  intro a _
  simp [closeAny, Attempt.isOpen]

/-- A result arriving for an attempt that already closed (for example after its scope ended)
changes nothing: it yields no deploy and starts nothing (RFC 0011 §2.13 items 6-7). -/
theorem result_after_close_is_ignored (d : Bool) (a : Attempt) (h : a.status = .closed) :
    finishOpt d a = a := by
  simp [finishOpt, h]

/-- Pending occurrences start in (trigger instant, response, rule id) order: the occurrence a
dispatch starts is minimal among the pending ones, given a sorted queue. -/
theorem dispatch_starts_minimal (s : RepairState)
    (hsorted : s.pending.Pairwise occLE) (o : Occ) (rest : List Occ)
    (hp : s.pending = o :: rest) : ∀ p ∈ rest, occLE o p := by
  rw [hp] at hsorted
  exact (List.pairwise_cons.mp hsorted).1

/-! ## 16.6 New-model admission (§2.5) -/

/-- Search domain of the admitted tvar for the occurrence fired by an event with `ref`:
domain(v) ∪ {ref}. -/
def searchDomain {β : Type} [DecidableEq β] (dom : List β) (ref : β) : List β :=
  if ref ∈ dom then dom else dom ++ [ref]

/-- The occurrence's search space: the declared space with `v` extended. The TVL construct is
the admission rule's tvar `v`; the Lean name avoids the banned tactic name. -/
def admitTvar {α β : Type} [DecidableEq α] [DecidableEq β]
    (declared : α → List β) (v : α) (ref : β) : α → List β :=
  fun x => if x = v then searchDomain (declared x) ref else declared x

/-- `admit_extends_only_named_tvar` (RFC 0011 §2.5 item 2; §4). The occurrence's space equals
the declared space at every tvar other than `v`; at `v` it contains exactly the declared
values and the event's model ref (so it only grows, and only by that ref). Class:
BY-CONSTRUCTION (follows from the shape of `admitTvar`; no step relation is involved). -/
theorem admit_extends_only_named_tvar {α β : Type} [DecidableEq α] [DecidableEq β]
    (declared : α → List β) (v : α) (ref : β) :
    (∀ x, x ≠ v → admitTvar declared v ref x = declared x) ∧
    (∀ b, b ∈ admitTvar declared v ref v ↔ b ∈ declared v ∨ b = ref) ∧
    (∀ b, b ∈ declared v → b ∈ admitTvar declared v ref v) := by
  refine ⟨?_, ?_, ?_⟩
  · intro x hx; simp [admitTvar, hx]
  · intro b
    by_cases hr : ref ∈ declared v
    · simp only [admitTvar, searchDomain, if_true, hr]
      constructor
      · intro hb; exact Or.inl hb
      · rintro (hb | rfl)
        · exact hb
        · exact hr
    · simp [admitTvar, searchDomain, hr, or_comm]
  · intro b hb
    by_cases hr : ref ∈ declared v
    · simp [admitTvar, searchDomain, hr, hb]
    · simp [admitTvar, searchDomain, hr, hb]

/-! ## 16.10 Conservative embedding (RFC 0011 §3) -/

/-- A module with no external or schedule rule fires no external occurrence on any stream. -/
theorem no_external_rules_no_firing (steps : List Step) : (extRun [] steps).fired = [] := by
  have h := extRun_inv [] (by simp) steps
  unfold extRun
  refine foldl_invariant (fun s : ExtState => s.fired = []) (extInstant []) ?_ ExtState.init steps rfl
  intro s st hs
  unfold extInstant
  refine foldl_invariant (fun s : ExtState => s.fired = []) (extStep st.now []) ?_ s _ hs
  intro s' e hs'
  unfold extStep
  split <;> simp_all

/-- A stream with no trigger never starts an attempt or queues an occurrence. -/
theorem no_trigger_no_attempt (serialize : Bool) (inputs : List Input)
    (hno : ∀ i ∈ inputs, ∀ o, i ≠ Input.trigger o) :
    (repairRun serialize inputs).attempts = [] ∧ (repairRun serialize inputs).pending = [] := by
  unfold repairRun
  suffices ∀ (l : List Input) (s : RepairState), (∀ i ∈ l, ∀ o, i ≠ Input.trigger o) →
      s.attempts = [] → s.pending = [] →
      (l.foldl repairStep s).attempts = [] ∧ (l.foldl repairStep s).pending = [] from
    this inputs _ hno rfl rfl
  intro l
  induction l with
  | nil => intro s _ h1 h2; exact ⟨h1, h2⟩
  | cons i l ih =>
    intro s hl h1 h2
    apply ih
    · intro j hj; exact hl j (List.mem_cons_of_mem _ hj)
    · cases i with
      | trigger o => exact absurd rfl (hl _ List.mem_cons_self o)
      | drop q => simpa [repairStep] using h1
      | optimizeFinished d => simp [repairStep, h1]
      | deployClosed => simp [repairStep, h1]
      | abort => simp [repairStep, h1]
      | dispatch =>
        unfold repairStep dispatch
        split <;> (try split) <;> simp_all
    · cases i with
      | trigger o => exact absurd rfl (hl _ List.mem_cons_self o)
      | drop q => simp [repairStep, h2]
      | optimizeFinished d => simpa [repairStep] using h2
      | deployClosed => simpa [repairStep] using h2
      | abort => simpa [repairStep] using h2
      | dispatch =>
        unfold repairStep dispatch
        split <;> (try split) <;> simp_all

end TVL.Runtime.Conditions
