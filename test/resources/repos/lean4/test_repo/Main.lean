import Helper

def multiply (x y : Nat) : Nat :=
  x * y

def calculate (c : Calculator) (op : String) (x y : Nat) : Option Int :=
  match op with
  | "add" => some (Int.ofNat (add x y))
  | "subtract" => some (subtract x y)
  | "multiply" => some (Int.ofNat (multiply x y))
  | _ => none

def main : IO Unit := do
  let c : Calculator := { name := "TestCalc", version := 1 }
  IO.println s!"Using {c.name} version {c.version}"
  let result1 := add 5 3
  IO.println s!"5 + 3 = {result1}"
  let result2 := subtract 10 4
  IO.println s!"10 - 4 = {result2}"
  match calculate c "multiply" 6 7 with
  | some result => IO.println s!"6 * 7 = {result}"
  | none => IO.println "Calculation failed"
  IO.println s!"Is 5 positive? {isPositive 5}"
  IO.println s!"Absolute of -10: {absolute (-10)}"
