module TestProject.Advanced

open TestProject.Types

/// Generic function that works with any comparable type
let max<'T when 'T : comparison> (a: 'T) (b: 'T) : 'T =
    if a > b then a else b

/// Generic list function
let first<'T> (list: 'T list) : 'T option =
    match list with
    | head :: _ -> Some head
    | [] -> None

/// Type abbreviation
type Vector = float * float

/// Tuple manipulation
let addVectors (v1: Vector) (v2: Vector) : Vector =
    let (x1, y1) = v1
    let (x2, y2) = v2
    (x1 + x2, y1 + y2)

/// Active pattern for even/odd
let (|Even|Odd|) n =
    if n % 2 = 0 then Even else Odd

/// Function using active pattern
let describeNumber n =
    match n with
    | Even -> sprintf "%d is even" n
    | Odd -> sprintf "%d is odd" n

/// Recursive function
let rec factorial n =
    if n <= 1 then 1
    else n * factorial (n - 1)

/// Higher-order function
let apply f x = f x

/// Curried function
let addThree x y z = x + y + z

/// Partially applied function
let addFive = addThree 5

/// Pipeline operator usage
let processNumber n =
    n
    |> (fun x -> x * 2)
    |> (fun x -> x + 10)
    |> (fun x -> x / 2)

/// Composition operator usage
let double x = x * 2
let addTen x = x + 10
let composed = double >> addTen

/// Async workflow
let asyncComputation x =
    async {
        do! Async.Sleep 100
        return x * 2
    }

/// Result type usage
let divide x y =
    if y = 0 then
        Error "Division by zero"
    else
        Ok (x / y)

/// Option type chaining
let tryGetFirst (list: 'T list) =
    list
    |> first
    |> Option.map (fun x -> x)

/// Union type for validation
type ValidationResult<'T> =
    | Valid of 'T
    | Invalid of string list

/// Validation function
let validatePositive n =
    if n > 0 then
        Valid n
    else
        Invalid ["Number must be positive"]

/// Discriminated union with multiple fields
type ContactInfo =
    | Email of address: string
    | Phone of countryCode: string * number: string
    | Both of email: string * phone: string

/// Pattern matching on ContactInfo
let describeContact info =
    match info with
    | Email address -> sprintf "Email: %s" address
    | Phone (code, number) -> sprintf "Phone: +%s %s" code number
    | Both (email, phone) -> sprintf "Email: %s, Phone: %s" email phone

/// Record with mutable field
type Counter = {
    mutable Count: int
    Name: string
}

/// Function that mutates record
let increment counter =
    counter.Count <- counter.Count + 1
    counter

/// Units of measure
[<Measure>] type meter
[<Measure>] type second

let distance = 100.0<meter>
let time = 10.0<second>
let speed = distance / time

/// Sequence expression
let numbers = seq {
    for i in 1 .. 10 do
        yield i * 2
}

/// Computation expression (list builder)
let evenNumbers = [
    for i in 1 .. 10 do
        if i % 2 = 0 then
            yield i
]

/// Interface definition
type IShape =
    abstract member Area : unit -> float
    abstract member Perimeter : unit -> float

/// Implementation of interface
type Square(side: float) =
    interface IShape with
        member this.Area() = side * side
        member this.Perimeter() = 4.0 * side

/// Function with type constraints
let inline add< ^T when ^T : (static member (+) : ^T * ^T -> ^T)> (x: ^T) (y: ^T) = x + y

/// Nested module
module Nested =
    let innerFunction x = x * 3

    module DeepNested =
        let veryInnerFunction x = x * 4
