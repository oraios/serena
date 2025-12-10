module Program

open Calculator
open Models

[<EntryPoint>]
let main argv =
    printfn "Hello, F# World!"
    
    // Test calculator functions
    let result1 = add 5 3
    printfn "5 + 3 = %d" result1
    
    let result2 = subtract 10 4
    printfn "10 - 4 = %d" result2
    
    let result3 = multiply 6 7
    printfn "6 * 7 = %d" result3
    
    let result4 = divide 15 3
    printfn "15 / 3 = %.2f" result4
    
    // Test calculator class
    let calc = CalculatorClass()
    let classResult = calc.Add(20, 5)
    printfn "Calculator class: 20 + 5 = %d" classResult
    
    // Test person module
    let person = PersonModule.createPerson "Alice Smith" 25 (Some "alice@example.com")
    printfn "Person: %s" (PersonModule.getDisplayName person)
    printfn "Is adult: %b" (PersonModule.isAdult person)
    
    // Test factorial
    let fact5 = factorial 5
    printfn "5! = %d" fact5
    
    0 // return success