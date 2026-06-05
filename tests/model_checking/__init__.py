"""Finite small-scope models of RFC 0001 (knob bindings: cvars + policies).

Each module here encodes one slice of the RFC's formal semantics as a tiny,
exhaustively-enumerable Python model, then checks the RFC's property claims
(P1-P8) over ALL instances up to a small scope bound — the small-scope
hypothesis in executable form. Where a property is claimed to be violable
(rejections R2-R8, collisions, staleness), the checker also EXHIBITS a
counterexample and exports it as a conformance fixture under
spec/examples/validation-phase6-cvars/ so the Phase 4 validators inherit
failing-by-design inputs.

No new dependencies: plain pytest + itertools (deterministic, no hypothesis).
The real tvl package is used directly where the property concerns real code
(P5 SAT preservation runs the actual compile_constraints encoder).
"""
