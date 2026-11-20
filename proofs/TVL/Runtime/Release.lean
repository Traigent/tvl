/- TVL 1.7 (DRAFT), RFC 0012, formal semantics §16.7-§16.9.
   The agent head, acceptance consumption with an atomic compare, generation-scoped episode
   closure. Release rollback is deferred out of TVL 1.7 (RFC 0012 §2.5) and is not modelled.
   Authentication, approver authority and gate re-evaluation are recorded inputs, never
   recomputed (as in the reference relation). -/
import Mathlib

namespace TVL.Runtime.Release

/-! ## 16.7 Head, acceptance record, deploy (RFC 0012 §2.1-§2.3) -/

/-- The head of one (agent, environment): serving fingerprint and generation (§2.1). -/
structure Head where
  fp : Nat
  gen : Nat
  deriving DecidableEq, Repr

/-- The deploy occurrence awaiting an acceptance, with the bindings an acceptance must equal
(§2.3). `code` is the agent code version the candidate and incumbent were measured on. `holdout` is the bundle's holdout digest when the module declares one. -/
structure Awaiting where
  agent : Nat
  env : Nat
  occ : Nat
  cand : Nat
  gate : Nat
  contract : Nat
  code : Nat
  holdout : Option Nat
  deriving DecidableEq, Repr

/-- `tvl-release-acceptance/1`, restricted to the fields the semantics reads (§2.2). -/
structure Accept where
  id : Nat
  agent : Nat
  env : Nat
  occ : Nat
  cand : Nat
  gate : Nat
  contract : Nat
  code : Nat
  holdout : Option Nat
  expGen : Nat
  rbTarget : Nat
  repairs : Option Nat
  accept : Bool
  decidedAt : Nat
  expiresAt : Nat
  deriving DecidableEq, Repr

/-- Equal bindings of §2.3. The holdout digest is compared as an option: when the module
declares none, the record carries none. -/
def Binds (a : Accept) (w : Awaiting) : Prop :=
  a.agent = w.agent ∧ a.env = w.env ∧ a.occ = w.occ ∧ a.cand = w.cand ∧
  a.gate = w.gate ∧ a.contract = w.contract ∧ a.code = w.code ∧ a.holdout = w.holdout

instance (a : Accept) (w : Awaiting) : Decidable (Binds a w) := by unfold Binds; infer_instance

/-- Seven days, in seconds (§2.2). -/
def maxLifetime : Nat := 604800

/-- Usable for an effect at `t`: `decided_at ≤ t < expires_at` and lifetime at most 7 days. -/
def Usable (a : Accept) (t : Nat) : Prop :=
  a.decidedAt ≤ t ∧ t < a.expiresAt ∧ a.expiresAt - a.decidedAt ≤ maxLifetime

instance (a : Accept) (t : Nat) : Decidable (Usable a t) := by unfold Usable; infer_instance

/-- A head move, with the evidence it was written under. -/
inductive Move where
  | deploy (a : Accept) (w : Awaiting) (t : Nat) (newGen : Nat)
  deriving DecidableEq, Repr

/-- A consumed accept that wrote the head (a release): the generation it wrote, the
rollback target it bound and the episode it repaired. -/
structure Rel where
  gen : Nat
  rbTarget : Nat
  repairs : Option Nat
  deriving DecidableEq, Repr

structure RState where
  head : Head
  /-- fingerprint of every generation the head has had -/
  history : List (Nat × Nat)
  consumed : List Nat
  moves : List Move
  releases : List Rel

def RState.init (h : Head) : RState := ⟨h, [(h.gen, h.fp)], [], [], []⟩

def fpAt (s : RState) (g : Nat) : Option Nat := (s.history.find? (fun p => p.1 = g)).map (·.2)

/-- Facts recorded outside TVL at the instant of one acceptance: effect time, platform
authentication, approver authority, the gate re-evaluation at effect time (RFC 0011 §2.13 item
4), the agent code version serving at effect time (`serving`) and the configurations that breached in an open episode (§2.13 item 5). -/
structure Ctx where
  now : Nat
  authentic : Bool
  authorized : Bool
  gatePromote : Bool
  serving : Nat
  breached : List Nat

inductive Result where
  | consumedRecord | invalid | ignored | rejectRecorded
  | refusedStale | refusedRollbackMismatch | refusedCode | refusedGate | refusedBreached
  | written
  deriving DecidableEq, Repr

/-- Checks that precede any look at the awaiting occurrence: consumed, authentication and
authority, usable at the effect time, and `rollback_target` equal to the head fingerprint at
`expected_head_generation`. -/
def pre (c : Ctx) (s : RState) (a : Accept) : Option Result :=
  if a.id ∈ s.consumed then some .consumedRecord
  else if c.authentic = false ∨ c.authorized = false then some .invalid
  else if ¬ Usable a c.now then some .invalid
  else if fpAt s a.expGen ≠ some a.rbTarget then some .invalid
  else none

/-- Effect of an acceptance that passed `pre` against its awaiting deploy occurrence: equal
bindings; a reject is recorded and consumed; for an accept, the effect-time gate recheck and
the atomic compare of §2.3 (generation, head fingerprint against `rollback_target`, serving agent code version against the accepted one), the
breached-configuration refusal, and only then the write of head, generation + 1 and the
consumption of the record. -/
def effect (c : Ctx) (w : Awaiting) (s : RState) (a : Accept) : Result × RState :=
  if ¬ Binds a w then (.invalid, s)
  else if a.accept = false then (.rejectRecorded, { s with consumed := a.id :: s.consumed })
  else if c.gatePromote = false then (.refusedGate, s)
  else if s.head.gen ≠ a.expGen then (.refusedStale, s)
  else if s.head.fp ≠ a.rbTarget then (.refusedRollbackMismatch, s)
  else if c.serving ≠ a.code then (.refusedCode, s)
  else if a.cand ∈ c.breached then (.refusedBreached, s)
  else
    (.written,
      { head := ⟨a.cand, s.head.gen + 1⟩,
        history := (s.head.gen + 1, a.cand) :: s.history,
        consumed := a.id :: s.consumed,
        moves := .deploy a w c.now (s.head.gen + 1) :: s.moves,
        releases := ⟨s.head.gen + 1, a.rbTarget, a.repairs⟩ :: s.releases })

/-- Processing one acceptance against the (at most one) deploy occurrence awaiting it. -/
def acceptStep (c : Ctx) (w : Option Awaiting) (s : RState) (a : Accept) : Result × RState :=
  match pre c s a with
  | some r => (r, s)
  | none =>
    match w with
    | none => (.ignored, s)
    | some w' => effect c w' s a

inductive Cmd where
  | acceptance (c : Ctx) (w : Option Awaiting) (a : Accept)

def cmdStep (s : RState) : Cmd → RState
  | .acceptance c w a => (acceptStep c w s a).2

def releaseRun (h : Head) (cmds : List Cmd) : RState :=
  cmds.foldl cmdStep (RState.init h)

private theorem foldl_invariant {α β : Type} (P : β → Prop) (f : β → α → β)
    (hstep : ∀ b a, P b → P (f b a)) (b : β) (l : List α) (h : P b) :
    P (l.foldl f b) := by
  induction l generalizing b with
  | nil => exact h
  | cons a l ih => exact ih (f b a) (hstep b a h)

def deployIds (ms : List Move) : List Nat :=
  ms.filterMap (fun m => match m with | .deploy a _ _ _ => some a.id)

/-- Invariants of every reachable state. -/
def RInv (s : RState) : Prop :=
  -- every deploy move is backed by a matching, usable accept record that is consumed
  (∀ a w t g, Move.deploy a w t g ∈ s.moves →
      Binds a w ∧ a.accept = true ∧ Usable a t ∧ a.id ∈ s.consumed) ∧
  -- no acceptance authorized two writes
  (deployIds s.moves).Nodup ∧
  -- no release is ahead of the head
  (∀ r ∈ s.releases, r.gen ≤ s.head.gen)

theorem RInv_init (h : Head) : RInv (RState.init h) := by
  simp [RInv, RState.init, deployIds]

theorem pre_none {c : Ctx} {s : RState} {a : Accept} (h : pre c s a = none) :
    a.id ∉ s.consumed ∧ c.authentic = true ∧ c.authorized = true ∧ Usable a c.now ∧
    fpAt s a.expGen = some a.rbTarget := by
  unfold pre at h
  by_cases h1 : a.id ∈ s.consumed
  · rw [if_pos h1] at h; cases h
  rw [if_neg h1] at h
  by_cases h2 : c.authentic = false ∨ c.authorized = false
  · rw [if_pos h2] at h; cases h
  rw [if_neg h2] at h
  by_cases h3 : ¬ Usable a c.now
  · rw [if_pos h3] at h; cases h
  rw [if_neg h3] at h
  by_cases h4 : fpAt s a.expGen ≠ some a.rbTarget
  · rw [if_pos h4] at h; cases h
  have h2' := h2
  simp at h2'
  exact ⟨h1, h2'.1, h2'.2, not_not.mp h3, not_not.mp h4⟩

theorem effect_inv (c : Ctx) (w : Awaiting) (s : RState) (a : Accept)
    (hnc : a.id ∉ s.consumed) (hu : Usable a c.now) (h : RInv s) :
    RInv (effect c w s a).2 := by
  obtain ⟨hA, hB, hC⟩ := h
  unfold effect
  by_cases h5 : ¬ Binds a w
  · rw [if_pos h5]; exact ⟨hA, hB, hC⟩
  rw [if_neg h5]
  have h5' : Binds a w := not_not.mp h5
  by_cases h6 : a.accept = false
  · rw [if_pos h6]
    refine ⟨?_, hB, hC⟩
    intro a' w' t g hm
    obtain ⟨x1, x2, x3, x4⟩ := hA a' w' t g hm
    exact ⟨x1, x2, x3, List.mem_cons_of_mem _ x4⟩
  rw [if_neg h6]
  have h6' : a.accept = true := by simpa using h6
  by_cases h7 : c.gatePromote = false
  · rw [if_pos h7]; exact ⟨hA, hB, hC⟩
  rw [if_neg h7]
  by_cases h8 : s.head.gen ≠ a.expGen
  · rw [if_pos h8]; exact ⟨hA, hB, hC⟩
  rw [if_neg h8]
  by_cases h9 : s.head.fp ≠ a.rbTarget
  · rw [if_pos h9]; exact ⟨hA, hB, hC⟩
  rw [if_neg h9]
  by_cases h9c : c.serving ≠ a.code
  · rw [if_pos h9c]; exact ⟨hA, hB, hC⟩
  rw [if_neg h9c]
  by_cases h10 : a.cand ∈ c.breached
  · rw [if_pos h10]; exact ⟨hA, hB, hC⟩
  rw [if_neg h10]
  refine ⟨?_, ?_, ?_⟩
  · intro a' w'' t g hm
    rcases List.mem_cons.mp hm with hm | hm
    · injection hm with e1 e2 e3 e4
      subst e1; subst e2; subst e3
      exact ⟨h5', h6', hu, List.mem_cons_self⟩
    · obtain ⟨x1, x2, x3, x4⟩ := hA a' w'' t g hm
      exact ⟨x1, x2, x3, List.mem_cons_of_mem _ x4⟩
  · show (deployIds (Move.deploy a w c.now (s.head.gen + 1) :: s.moves)).Nodup
    simp only [deployIds, List.filterMap_cons]
    show (a.id :: deployIds s.moves).Nodup
    rw [List.nodup_cons]
    refine ⟨?_, hB⟩
    intro hmem
    simp only [deployIds, List.mem_filterMap] at hmem
    obtain ⟨m, hm, hm2⟩ := hmem
    cases m with
    | deploy a' w' t g =>
      simp at hm2
      have := (hA a' w' t g hm).2.2.2
      rw [hm2] at this
      exact hnc this
  · intro r hr
    rcases List.mem_cons.mp hr with hr | hr
    · subst hr; simp
    · have := hC r hr; simp only []; omega

theorem acceptStep_inv (c : Ctx) (w : Option Awaiting) (s : RState) (a : Accept)
    (h : RInv s) : RInv (acceptStep c w s a).2 := by
  unfold acceptStep
  cases hp : pre c s a with
  | some r => exact h
  | none =>
    cases w with
    | none => exact h
    | some w' =>
      obtain ⟨hnc, _, _, hu, _⟩ := pre_none hp
      exact effect_inv c w' s a hnc hu h

theorem releaseRun_inv (h : Head) (cmds : List Cmd) : RInv (releaseRun h cmds) := by
  unfold releaseRun
  apply foldl_invariant (P := RInv)
  · intro s c hs
    cases c with
    | acceptance c w a => exact acceptStep_inv c w s a hs
  · exact RInv_init h

/-- `deploy_needs_matching_acceptance` (RFC 0012 §2.3; §4). In every reachable state, every
head move by a deploy is backed by an accept record with bindings equal to the awaiting deploy
occurrence's, usable at the effect time, and consumed; and no acceptance authorizes two
writes. Class: SUBSTANTIVE (induction over arbitrary command sequences). -/
theorem deploy_needs_matching_acceptance (h : Head) (cmds : List Cmd) :
    (∀ a w t g, Move.deploy a w t g ∈ (releaseRun h cmds).moves →
      Binds a w ∧ a.accept = true ∧ Usable a t ∧ a.id ∈ (releaseRun h cmds).consumed) ∧
    (deployIds (releaseRun h cmds).moves).Nodup :=
  ⟨(releaseRun_inv h cmds).1, (releaseRun_inv h cmds).2.1⟩

/-- A consumed record never authorizes a second write (§2.3). -/
theorem consumed_record_writes_nothing (c : Ctx) (w : Option Awaiting) (s : RState)
    (a : Accept) (h : a.id ∈ s.consumed) : acceptStep c w s a = (.consumedRecord, s) := by
  simp [acceptStep, pre, h]

theorem pre_ne_written {c : Ctx} {s : RState} {a : Accept} {r : Result}
    (h : pre c s a = some r) : r ≠ .written := by
  unfold pre at h
  split_ifs at h <;> (injection h with h; subst h; simp)

theorem effect_stale (c : Ctx) (w : Awaiting) (s : RState) (a : Accept)
    (hstale : s.head.gen ≠ a.expGen) :
    (effect c w s a).1 ≠ .written ∧ (effect c w s a).2.head = s.head ∧
    (effect c w s a).2.moves = s.moves ∧ (effect c w s a).2.releases = s.releases := by
  unfold effect
  by_cases h5 : ¬ Binds a w
  · rw [if_pos h5]; simp
  rw [if_neg h5]
  by_cases h6 : a.accept = false
  · rw [if_pos h6]; simp
  rw [if_neg h6]
  by_cases h7 : c.gatePromote = false
  · rw [if_pos h7]; simp
  rw [if_neg h7, if_pos hstale]; simp

/-- `stale_acceptance_writes_nothing` (RFC 0012 §2.3; §4). If the head is not at the
generation the approver saw, the acceptance step changes neither the head, the move log, the
releases, nor reports a write. Class: BY-CONSTRUCTION (the refusal guard is part of the
definition of `effect`; the proof is a case analysis of its branches). -/
theorem stale_acceptance_writes_nothing (c : Ctx) (w : Option Awaiting) (s : RState)
    (a : Accept) (hstale : s.head.gen ≠ a.expGen) :
    (acceptStep c w s a).1 ≠ .written ∧
    (acceptStep c w s a).2.head = s.head ∧
    (acceptStep c w s a).2.moves = s.moves ∧
    (acceptStep c w s a).2.releases = s.releases := by
  cases hp : pre c s a with
  | some r =>
    have : acceptStep c w s a = (r, s) := by simp [acceptStep, hp]
    rw [this]; exact ⟨pre_ne_written hp, rfl, rfl, rfl⟩
  | none =>
    cases w with
    | none =>
      have : acceptStep c none s a = (.ignored, s) := by simp [acceptStep, hp]
      rw [this]; simp
    | some w' =>
      have : acceptStep c (some w') s a = effect c w' s a := by simp [acceptStep, hp]
      rw [this]; exact effect_stale c w' s a hstale

/-- A valid accept for a stale generation is refused with `stale_generation` (the earlier
checks having passed). -/
theorem stale_generation_refused (c : Ctx) (w' : Awaiting) (s : RState) (a : Accept)
    (hp : pre c s a = none) (h6 : Binds a w') (h7 : a.accept = true)
    (h8 : c.gatePromote = true) (hstale : s.head.gen ≠ a.expGen) :
    (acceptStep c (some w') s a).1 = .refusedStale := by
  simp [acceptStep, hp, effect, h6, h7, h8, hstale]

/-- A valid accept whose agent code version differs from the one serving at effect time is
refused with `code_version_mismatch`, and writes nothing (RFC 0012 §2.3). -/
theorem code_version_refused (c : Ctx) (w' : Awaiting) (s : RState) (a : Accept)
    (hp : pre c s a = none) (h6 : Binds a w') (h7 : a.accept = true)
    (h8 : c.gatePromote = true) (hg : s.head.gen = a.expGen) (hf : s.head.fp = a.rbTarget)
    (hc : c.serving ≠ a.code) :
    acceptStep c (some w') s a = (.refusedCode, s) := by
  simp [acceptStep, hp, effect, h6, h7, h8, hg, hf, hc]

theorem effect_written (c : Ctx) (w : Awaiting) (s : RState) (a : Accept)
    (h : (effect c w s a).1 = .written) :
    (effect c w s a).2.head = ⟨a.cand, s.head.gen + 1⟩ ∧ s.head.gen = a.expGen := by
  unfold effect at h ⊢
  by_cases h5 : ¬ Binds a w
  · rw [if_pos h5] at h; simp at h
  rw [if_neg h5] at h ⊢
  by_cases h6 : a.accept = false
  · rw [if_pos h6] at h; simp at h
  rw [if_neg h6] at h ⊢
  by_cases h7 : c.gatePromote = false
  · rw [if_pos h7] at h; simp at h
  rw [if_neg h7] at h ⊢
  by_cases h8 : s.head.gen ≠ a.expGen
  · rw [if_pos h8] at h; simp at h
  rw [if_neg h8] at h ⊢
  by_cases h9 : s.head.fp ≠ a.rbTarget
  · rw [if_pos h9] at h; simp at h
  rw [if_neg h9] at h ⊢
  by_cases h9c : c.serving ≠ a.code
  · rw [if_pos h9c] at h; simp at h
  rw [if_neg h9c] at h ⊢
  by_cases h10 : a.cand ∈ c.breached
  · rw [if_pos h10] at h; simp at h
  rw [if_neg h10]
  exact ⟨rfl, by simpa using h8⟩

/-- A write advances the generation by exactly one, installs the candidate, and happens
only when the head is at the generation the approver saw (§2.1, §2.3). -/
theorem write_advances_head (c : Ctx) (w : Option Awaiting) (s : RState) (a : Accept)
    (h : (acceptStep c w s a).1 = .written) :
    (acceptStep c w s a).2.head = ⟨a.cand, s.head.gen + 1⟩ ∧ s.head.gen = a.expGen := by
  cases hp : pre c s a with
  | some r =>
    have : acceptStep c w s a = (r, s) := by simp [acceptStep, hp]
    rw [this] at h; exact absurd h (pre_ne_written hp)
  | none =>
    cases w with
    | none =>
      have : acceptStep c none s a = (.ignored, s) := by simp [acceptStep, hp]
      rw [this] at h; simp at h
    | some w' =>
      have : acceptStep c (some w') s a = effect c w' s a := by simp [acceptStep, hp]
      rw [this] at h ⊢; exact effect_written c w' s a h

/-! ## 16.8 Generation-scoped recovery (RFC 0012 §2.4) -/

inductive Verdict where
  | met | breached | unknown
  deriving DecidableEq, Repr

inductive ClosureScope where
  | anyGeneration | sinceHeadMove
  deriving DecidableEq, Repr

/-- A window report: start (aligned), verdict, the reported head generation, and the head
generation at the window's start. -/
structure Win where
  start : Nat
  verdict : Verdict
  gen : Nat
  startGen : Nat

/-- Mixed: the reported generation differs from the generation at the window's start. -/
def Win.mixed (w : Win) : Prop := w.gen ≠ w.startGen

/-- Counts towards closure. Under `since_head_move`: MET, not mixed, and of a generation
greater than the generation at the opening of the episode. -/
def Qual (sc : ClosureScope) (openGen : Nat) (w : Win) : Prop :=
  w.verdict = .met ∧ (sc = .sinceHeadMove → ¬ w.mixed ∧ openGen < w.gen)

instance (sc : ClosureScope) (openGen : Nat) (w : Win) : Decidable (Qual sc openGen w) := by
  unfold Qual Win.mixed; infer_instance

structure EpState where
  seen : List Nat
  run : Nat
  last : Option Nat
  /-- the generation of the last counted window -/
  lastGen : Option Nat

def EpState.init : EpState := ⟨[], 0, none, none⟩

/-- One window report. A second report for the same window start is a redelivery that changes
nothing (§2.13 item 9 of RFC 0011). Any non-qualifying window resets the count; a qualifying
window extends it only when its start is `width` after the previous counted start
(consecutive) and, under `since_head_move`, its generation equals the previous counted
window's generation; else it starts a new count of one (a change of generation resets the
count). Windows are half-open `[start, start+width)`. -/
def winStep (sc : ClosureScope) (openGen width : Nat) (e : EpState) (w : Win) : EpState :=
  if w.start ∈ e.seen then e
  else if Qual sc openGen w then
    { seen := w.start :: e.seen,
      run := (match e.last with
              | some l => if w.start = l + width ∧ (sc = .sinceHeadMove → e.lastGen = some w.gen)
                          then e.run + 1 else 1
              | none => 1),
      last := some w.start,
      lastGen := some w.gen }
  else { seen := w.start :: e.seen, run := 0, last := none, lastGen := none }

def closureRun (sc : ClosureScope) (openGen width : Nat) (ws : List Win) : EpState :=
  ws.foldl (winStep sc openGen width) EpState.init

/-- The episode is closed when `need` consecutive qualifying windows have been counted. -/
def Closed (need : Nat) (e : EpState) : Prop := 0 < need ∧ need ≤ e.run

theorem winStep_run_le (sc : ClosureScope) (openGen width : Nat) (e : EpState) (w : Win) :
    (winStep sc openGen width e w).run ≤ e.run + (if Qual sc openGen w then 1 else 0) := by
  by_cases h1 : w.start ∈ e.seen
  · simp [winStep, h1]
  · by_cases hq : Qual sc openGen w
    · simp only [winStep, h1, hq, if_false, if_true]
      cases e.last with
      | none => simp
      | some l => dsimp only; split_ifs <;> omega
    · simp [winStep, h1, hq]

theorem closure_run_le (sc : ClosureScope) (openGen width : Nat) (ws : List Win) :
    ∀ e : EpState, (ws.foldl (winStep sc openGen width) e).run ≤
      e.run + (ws.filter (fun w => decide (Qual sc openGen w))).length := by
  induction ws with
  | nil => intro e; simp
  | cons w ws ih =>
    intro e
    have h1 := ih (winStep sc openGen width e w)
    have h2 := winStep_run_le sc openGen width e w
    simp only [List.foldl_cons, List.filter_cons]
    by_cases hq : Qual sc openGen w <;> simp [hq] at h2 ⊢ <;> omega

/-- A window of an old generation resets the count (§2.4). -/
theorem old_generation_resets (openGen width : Nat) (e : EpState) (w : Win)
    (hnew : w.start ∉ e.seen) (hold : w.gen ≤ openGen) :
    (winStep .sinceHeadMove openGen width e w).run = 0 := by
  unfold winStep
  have : ¬ Qual .sinceHeadMove openGen w := by
    intro ⟨_, h⟩
    have := (h rfl).2
    omega
  simp [hnew, this]

/-- A redelivered window report changes no count. -/
theorem window_redelivery_noop (sc : ClosureScope) (openGen width : Nat) (e : EpState) (w : Win)
    (h : w.start ∈ e.seen) : winStep sc openGen width e w = e := by
  simp [winStep, h]

/-- Under `since_head_move`, a qualifying window of a generation different from the previous
counted window's restarts the count at one (RFC 0012 §2.4 Counting). -/
theorem generation_change_resets (openGen width : Nat) (e : EpState) (w : Win) (l : Nat)
    (hnew : w.start ∉ e.seen) (hq : Qual .sinceHeadMove openGen w)
    (hl : e.last = some l) (hg : e.lastGen ≠ some w.gen) :
    (winStep .sinceHeadMove openGen width e w).run = 1 := by
  unfold winStep
  simp [hnew, hq, hl, hg]

theorem qual_sinceHeadMove_iff (openGen : Nat) (w : Win) :
    Qual .sinceHeadMove openGen w ↔ w.verdict = .met ∧ ¬ w.mixed ∧ openGen < w.gen := by
  simp [Qual]

/-- `since_head_move_closure` (RFC 0012 §2.4; §4). Under `since_head_move`, closing the
episode from any sequence of window reports needs at least `closure_windows` reports that are
MET, not mixed and of a generation greater than the opening generation (first conjunct). So no
window from a generation at or below the opening generation contributes: if every report is
from such a generation the episode cannot close (second conjunct). Class: SUBSTANTIVE (count
bound over arbitrary report sequences, with redelivery and gaps). Closure's age bound
`closure_max_age_hours` only restricts further and is not modelled. -/
theorem since_head_move_closure (openGen width need : Nat) (ws : List Win) :
    (Closed need (closureRun .sinceHeadMove openGen width ws) →
      need ≤ (ws.filter (fun w => decide (Qual .sinceHeadMove openGen w))).length) ∧
    ((∀ w ∈ ws, w.gen ≤ openGen) → ¬ Closed need (closureRun .sinceHeadMove openGen width ws)) := by
  have h := closure_run_le .sinceHeadMove openGen width ws EpState.init
  have hrun : (closureRun .sinceHeadMove openGen width ws).run ≤
      (ws.filter (fun w => decide (Qual .sinceHeadMove openGen w))).length := by
    unfold closureRun
    simpa [EpState.init] using h
  refine ⟨fun ⟨_, hle⟩ => le_trans hle hrun, ?_⟩
  intro hold ⟨hpos, hle⟩
  have hz : (ws.filter (fun w => decide (Qual .sinceHeadMove openGen w))).length = 0 := by
    rw [List.length_eq_zero_iff, List.filter_eq_nil_iff]
    intro w hw hq
    have := hold w hw
    simp only [decide_eq_true_eq] at hq
    have := (hq.2 rfl).2
    omega
  omega
