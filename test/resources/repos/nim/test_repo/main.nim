# Main module for testing Nim language server functionality

import std/[strutils, sequtils, json]
import utils
import types

proc greet(name: string): string =
  ## Greets a person with their name
  result = "Hello, " & name & "!"

proc calculate(a, b: int): int =
  ## Adds two integers
  result = a + b

proc processData(data: JsonNode): string =
  ## Processes JSON data and returns a formatted string
  let name = data["name"].getStr()
  let age = data["age"].getInt()
  result = "$1 is $2 years old" % [name, $age]

type
  Person* = object
    name*: string
    age*: int
    email*: string

proc newPerson*(name: string, age: int, email: string = ""): Person =
  ## Creates a new Person object
  result = Person(name: name, age: age, email: email)

proc describe*(p: Person): string =
  ## Returns a description of a person
  result = "$1 ($2 years old)" % [p.name, $p.age]
  if p.email != "":
    result.add(", email: " & p.email)

type
  Animal* = object
    name*: string
    species*: string

proc newAnimal*(name: string, species: string): Animal =
  ## Creates a new Animal object
  result = Animal(name: name, species: species)

proc speak*(self: Animal): string =
  ## Returns the sound the animal makes
  case self.species
  of "dog": "Woof!"
  of "cat": "Meow!"
  else: "..."

when isMainModule:
  echo greet("World")
  echo "2 + 3 = ", calculate(2, 3)

  let john = newPerson("John Doe", 30, "john@example.com")
  echo describe(john)

  let jsonData = %* {"name": "Alice", "age": 25}
  echo processData(jsonData)

  # Test utils module
  echo formatNumber(1234567)
  echo reverseString("Hello")

  # Test types module
  let point = newPoint(10.0, 20.0)
  echo "Point: ", point.toString()