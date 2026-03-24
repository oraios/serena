structure Calculator where
  name : String
  version : Nat
  deriving Repr

def add (x y : Nat) : Nat :=
  x + y

def subtract (x y : Nat) : Int :=
  Int.ofNat x - Int.ofNat y

def isPositive (x : Int) : Bool :=
  x > 0

def absolute (x : Int) : Int :=
  if isPositive x then x else -x
