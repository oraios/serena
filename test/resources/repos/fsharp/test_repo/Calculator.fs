module Calculator

/// Simple calculator functions
let add a b = a + b

let subtract a b = a - b

let multiply a b = a * b

let divide a b =
    if b = 0 then
        failwith "Cannot divide by zero"
    else
        (float a) / (float b)

/// More complex operations
let square x = x * x

let factorial n =
    if n <= 0 then 1
    else
        let rec factorialHelper acc n =
            if n <= 1 then acc
            else factorialHelper (acc * n) (n - 1)
        factorialHelper 1 n

/// Calculator type with instance methods
type CalculatorClass() =
    member this.Add(a, b) = add a b
    member this.Subtract(a, b) = subtract a b
    member this.Multiply(a, b) = multiply a b
    member this.Divide(a, b) = divide a b