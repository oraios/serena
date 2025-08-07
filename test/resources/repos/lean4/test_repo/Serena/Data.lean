/-!
# Data Structures

This module contains data structure definitions.
-/

-- An inductive tree type
inductive Tree (α : Type) where
  | leaf : Tree α
  | node : α → Tree α → Tree α → Tree α

-- Size function for trees
def Tree.size : Tree α → Nat
  | Tree.leaf => 0
  | Tree.node _ left right => 1 + left.size + right.size

-- Example of using the Tree type
def exampleTree : Tree Nat :=
  Tree.node 1
    (Tree.node 2 Tree.leaf Tree.leaf)
    (Tree.node 3 Tree.leaf Tree.leaf)