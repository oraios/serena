module TestProject.Helper

/// A helper function that adds two numbers
let add x y = x + y

/// A helper function that subtracts two numbers
let subtract x y = x - y

/// A helper function that multiplies two numbers
let multiply x y = x * y

/// A helper function that divides two numbers
let divide x y =
    if y = 0 then
        failwith "Division by zero"
    else
        x / y
