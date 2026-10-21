import TVL.TypeSoundness
import TVL.SMTEncoding
import TVL.Dominance
import TVL.OPALCore
import TVL.Gate
import TVL.Runtime.History
import TVL.Runtime.Declarations
import TVL.Runtime.Guards
import TVL.Runtime.BinomialGeneric
import TVL.Runtime.Compiler
import TVL.Runtime.Compose
import TVL.Runtime.Extension
import TVL.Runtime.Backend
import TVL.Runtime.BinomialLaw

def main : IO Unit :=
  IO.println "TVL proof library built; open obligations are listed in PROOF_SUMMARY.md"
