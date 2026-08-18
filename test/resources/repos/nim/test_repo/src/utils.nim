import std/math

proc calculateArea*(radius: float): float =
  PI * radius * radius

proc formatGreeting*(name: string, age: int): string =
  "Hello, my name is " & name & " and I am " & $age & " years old."
