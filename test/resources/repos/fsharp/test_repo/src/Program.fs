module TestProject.Program

open TestProject.Calculator
open TestProject.Types
open TestProject.Helper

[<EntryPoint>]
let main argv =
    // Create a calculator instance
    let calc = createCalculator()

    // Test basic operations
    printfn "5 + 3 = %d" (calc.Add(5, 3))
    printfn "10 - 4 = %d" (calc.Subtract(10, 4))
    printfn "6 * 7 = %d" (calc.Multiply(6, 7))
    printfn "20 / 5 = %d" (calc.Divide(20, 5))

    // Test sum and product
    let numbers = [1; 2; 3; 4; 5]
    printfn "Sum of %A = %d" numbers (calc.Sum(numbers))
    printfn "Product of %A = %d" numbers (calc.Product(numbers))

    // Test shapes
    let circle = Circle 5.0
    let rectangle = Rectangle (4.0, 6.0)
    let triangle = Triangle (3.0, 8.0)

    printfn "Area of circle with radius 5.0 = %.2f" (area circle)
    printfn "Area of rectangle 4.0 x 6.0 = %.2f" (area rectangle)
    printfn "Area of triangle with base 3.0 and height 8.0 = %.2f" (area triangle)

    // Test person
    let person = createPerson "Alice" 30 (Some "alice@example.com")
    printfn "Person: %s, Age: %d, Email: %A" person.Name person.Age person.Email

    // Test helper functions directly
    printfn "Direct add: %d" (add 10 20)
    printfn "Direct multiply: %d" (multiply 3 7)

    0 // Return success
