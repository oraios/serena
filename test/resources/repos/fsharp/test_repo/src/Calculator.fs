module TestProject.Calculator

open TestProject.Helper
open TestProject.Types

/// A calculator class that performs basic arithmetic operations
type Calculator() =

    /// Add two numbers
    member this.Add(x, y) = add x y

    /// Subtract two numbers
    member this.Subtract(x, y) = subtract x y

    /// Multiply two numbers
    member this.Multiply(x, y) = multiply x y

    /// Divide two numbers
    member this.Divide(x, y) = divide x y

    /// Calculate the sum of a list of numbers
    member this.Sum(numbers: int list) =
        List.fold (fun acc n -> add acc n) 0 numbers

    /// Calculate the product of a list of numbers
    member this.Product(numbers: int list) =
        List.fold (fun acc n -> multiply acc n) 1 numbers

/// Create a calculator instance
let createCalculator() = Calculator()

/// Evaluate an expression using the calculator
let evaluate (calc: Calculator) op x y =
    match op with
    | "add" -> calc.Add(x, y)
    | "subtract" -> calc.Subtract(x, y)
    | "multiply" -> calc.Multiply(x, y)
    | "divide" -> calc.Divide(x, y)
    | _ -> failwith "Unknown operation"
