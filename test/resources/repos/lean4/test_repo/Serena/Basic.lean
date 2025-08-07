/-!
# Basic Module

This module contains basic definitions and structures for testing.
-/

-- A simple structure
structure Calculator where
  value : Nat
  
-- Method for Calculator
def Calculator.add (c : Calculator) (n : Nat) : Calculator :=
  { value := c.value + n }
  
def Calculator.multiply (c : Calculator) (n : Nat) : Calculator :=
  { value := c.value * n }

def Calculator.new : Calculator := { value := 0 }

-- Some basic functions
def square (n : Nat) : Nat := n * n

def factorial : Nat → Nat
  | 0 => 1
  | n + 1 => (n + 1) * factorial n

def fibonacci : Nat → Nat  
  | 0 => 0
  | 1 => 1
  | n + 2 => fibonacci (n + 1) + fibonacci n