module TestProject.Types

/// A record type representing a point in 2D space
type Point = {
    X: float
    Y: float
}

/// A discriminated union representing different shapes
type Shape =
    | Circle of radius: float
    | Rectangle of width: float * height: float
    | Triangle of base_: float * height: float

/// Calculate the area of a shape
let area shape =
    match shape with
    | Circle radius -> System.Math.PI * radius * radius
    | Rectangle (width, height) -> width * height
    | Triangle (base_, height) -> 0.5 * base_ * height

/// A record type representing a person
type Person = {
    Name: string
    Age: int
    Email: string option
}

/// Create a new person
let createPerson name age email =
    { Name = name; Age = age; Email = email }
