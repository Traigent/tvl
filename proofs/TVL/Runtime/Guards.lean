/- RFC 0004 §4: notification guards. These are static semantic properties,
   not a proof of a controller or of delivery mechanics. -/
import TVL.Runtime.Declarations

namespace TVL.Runtime.Reactive

inductive Truth where
  | yes | no | undecided
  deriving DecidableEq, Repr

def kleeneAnd : Truth → Truth → Truth
  | .no, _ | _, .no => .no
  | .yes, .yes => .yes
  | _, _ => .undecided

def kleeneOr : Truth → Truth → Truth
  | .yes, _ | _, .yes => .yes
  | .no, .no => .no
  | _, _ => .undecided

def allGuards (xs : List Truth) : Truth := xs.foldr kleeneAnd .yes

def anyGuards (xs : List Truth) : Truth := xs.foldr kleeneOr .no

theorem and_not_no (a b : Truth) : kleeneAnd a b ≠ .no ↔ a ≠ .no ∧ b ≠ .no := by
  cases a <;> cases b <;> decide

theorem or_not_yes (a b : Truth) : kleeneOr a b ≠ .yes ↔ a ≠ .yes ∧ b ≠ .yes := by
  cases a <;> cases b <;> decide

theorem all_not_no (xs : List Truth) : allGuards xs ≠ .no ↔ ∀ x ∈ xs, x ≠ .no := by
  induction xs with
  | nil => simp [allGuards]
  | cons a xs ih => simpa only [allGuards, List.foldr_cons, and_not_no, List.mem_cons, forall_eq_or_imp] using and_congr_right (fun _ => ih)

theorem any_not_yes (xs : List Truth) : anyGuards xs ≠ .yes ↔ ∀ x ∈ xs, x ≠ .yes := by
  induction xs with
  | nil => simp [anyGuards]
  | cons a xs ih => simpa only [anyGuards, List.foldr_cons, or_not_yes, List.mem_cons, forall_eq_or_imp] using and_congr_right (fun _ => ih)

structure Conditions (G : Type) where
  onlyWhile : List G
  unlessGuards : List G

def delivered {G : Type} (c : Conditions G) (v : G → Truth) : Prop :=
  allGuards (c.onlyWhile.map v) ≠ .no ∧ anyGuards (c.unlessGuards.map v) ≠ .yes

theorem delivered_iff {G : Type} (c : Conditions G) (v : G → Truth) :
    delivered c v ↔ (∀ g ∈ c.onlyWhile, v g ≠ .no) ∧ (∀ g ∈ c.unlessGuards, v g ≠ .yes) := by
  simp [delivered, all_not_no, any_not_yes]

/-- SUBSTANTIVE: arbitrary guard valuation, arbitrary position (even shared by both lists). -/
theorem undecided_never_suppresses {G : Type} [DecidableEq G]
    (c : Conditions G) (v : G → Truth) (g : G) (h : delivered c v) :
    delivered c (Function.update v g .undecided) := by
  rw [delivered_iff] at h ⊢
  constructor
  · intro x hx
    by_cases he : x = g
    · subst x; simp
    · simpa [Function.update, he] using h.1 x hx
  · intro x hx
    by_cases he : x = g
    · subst x; simp
    · simpa [Function.update, he] using h.2 x hx

/-- Validated reactive syntax has a single action constructor. -/
structure NotifyRule (G I S : Type) where
  conditions : Conditions G
  identity : I
  scope : S

def NotifyRule.action {G I S : Type} (_ : NotifyRule G I S) : Action := .notify

theorem notify_only {G I S : Type} (r : NotifyRule G I S) : r.action = .notify := rfl

/-- Evaluating guards adds a recorded decision to the original occurrence. -/
def evaluate {G I S : Type} (r : NotifyRule G I S) (v : G → Truth) :=
  (r.identity, r.scope, delivered r.conditions v)

theorem guards_preserve_identity {G I S : Type} (r : NotifyRule G I S) (v : G → Truth) :
    (evaluate r v).1 = r.identity ∧ (evaluate r v).2.1 = r.scope := ⟨rfl, rfl⟩

inductive Guard (M R : Type) where
  | episodeOpen : M → Guard M R
  | attemptOpen : R → Guard M R

/-- Exactly §2.4: source monitor → episode_open monitor in unless; attempts add no edge. -/
def unlessEdge {M R : Type} (source : R → M) (conditions : R → Conditions (Guard M R))
    (a b : M) : Prop :=
  ∃ r, source r = a ∧ Guard.episodeOpen b ∈ (conditions r).unlessGuards

/-- SUBSTANTIVE: acyclicity is absence of a nonempty directed path to itself.
    S is a finite nonempty set of rules triggered by one evaluation. -/
theorem no_mutual_silencing {M R : Type} [DecidableEq R]
    (source : R → M) (conditions : R → Conditions (Guard M R))
    (v : Guard M R → Truth) (S : Finset R) (hne : S.Nonempty)
    (acyclic : ∀ m, ¬ Relation.TransGen (unlessEdge source conditions) m m)
    (only_ok : ∀ r ∈ S, ∀ g ∈ (conditions r).onlyWhile, v g ≠ .no)
    (attempt_ok : ∀ r ∈ S, ∀ a, Guard.attemptOpen a ∈ (conditions r).unlessGuards →
      v (.attemptOpen a) ≠ .yes)
    (internal : ∀ r ∈ S, ∀ m, Guard.episodeOpen m ∈ (conditions r).unlessGuards →
      ∃ r' ∈ S, source r' = m) :
    ∃ r ∈ S, delivered (conditions r) v := by
  classical
  let E := unlessEdge source conditions
  let reversePath := fun a b => Relation.TransGen E b a
  letI : IsStrictOrder M reversePath := {
    irrefl := acyclic
    trans := fun _ _ _ hab hbc => hbc.trans hab
  }
  let monitors : Set M := source '' (↑S : Set R)
  have finite : monitors.Finite := S.finite_toSet.image source
  have nonempty : monitors.Nonempty := by
    obtain ⟨r, hr⟩ := hne
    exact ⟨source r, r, hr, rfl⟩
  obtain ⟨m, hm, minimal⟩ := (Set.wellFoundedOn_iff.mp (finite.wellFoundedOn (r := reversePath))).has_min monitors nonempty
  have source_mem := hm
  obtain ⟨r, hr, hsource⟩ := hm
  refine ⟨r, hr, (delivered_iff _ _).2 ⟨only_ok r hr, ?_⟩⟩
  intro g hg
  cases g with
  | attemptOpen a => exact attempt_ok r hr a hg
  | episodeOpen target =>
    obtain ⟨r', hr', heq⟩ := internal r hr target hg
    have target_mem : target ∈ monitors := ⟨r', hr', heq⟩
    have edge : E m target := ⟨r, hsource, hg⟩
    exact False.elim (minimal target target_mem ⟨Relation.TransGen.single edge, target_mem, source_mem⟩)

end TVL.Runtime.Reactive
