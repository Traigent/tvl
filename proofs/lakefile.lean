import Lake
open Lake DSL

package «tvl» where
  -- Mathlib required for DecidableEq derivation and omega tactic

require mathlib from git
  "https://github.com/leanprover-community/mathlib4.git" @ "6a596ab93c06c66333edc70d52d8955648f6669c"

lean_lib «TVL» where
  -- add library configuration options here

@[default_target]
lean_exe «tvl» where
  root := `Main
