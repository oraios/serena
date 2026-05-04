module Shapes

[<AbstractClass>]
type Shape() =
    abstract member Area: unit -> float

type Circle(radius: float) =
    inherit Shape()

    override _.Area() = System.Math.PI * radius * radius
