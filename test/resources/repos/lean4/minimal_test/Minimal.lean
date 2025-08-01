-- Simple Lean 4 file without external dependencies

def hello : String := "world"

structure Point where
  x : Nat
  y : Nat

def Point.add (p1 p2 : Point) : Point :=
  { x := p1.x + p2.x, y := p1.y + p2.y }

def factorial : Nat → Nat
  | 0 => 1
  | n + 1 => (n + 1) * factorial n