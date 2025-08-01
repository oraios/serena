/-!
# Main Module

The entry point of the application.
-/

import Serena.Basic
import Serena.Data
import Serena.Logic

def main : IO Unit := do
  -- Using Calculator from Basic.lean
  let calc := Calculator.new
  let result := calc.add 5
  let final := result.multiply 3
  
  IO.println s!"Calculator result: {final.value}"
  
  -- Using Tree from Data.lean
  let tree := exampleTree
  IO.println s!"Tree size: {tree.size}"
  
  -- Reference to theorem from Logic.lean
  -- This is just a comment showing we know about add_comm