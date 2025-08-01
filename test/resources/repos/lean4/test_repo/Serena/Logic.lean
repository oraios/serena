import Serena.Basic

/-!
# Logic Module

This module contains theorems and proofs.
-/

-- A simple theorem about addition
theorem add_comm (a b : Nat) : a + b = b + a := by
  exact Nat.add_comm a b

-- Using Calculator from Basic module
theorem calc_add_comm (c : Calculator) (a b : Nat) :
    (c.add a).add b = (c.add b).add a := by
  -- Uses add_comm theorem  
  simp only [Calculator.add]
  -- Now we need to show: { value := (c.value + a) + b } = { value := (c.value + b) + a }
  congr
  -- This reduces to: (c.value + a) + b = (c.value + b) + a
  rw [Nat.add_assoc, Nat.add_assoc, Nat.add_comm a]