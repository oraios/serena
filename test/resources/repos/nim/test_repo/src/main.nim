import utils

type
  Calculator* = object

  User* = object
    name*: string
    age*: int

proc add*(self: Calculator, a, b: int): int =
  a + b

proc multiply*(self: Calculator, a, b: int): int =
  a * b

proc greet*(self: User): string =
  formatGreeting(self.name, self.age)

proc isAdult*(self: User): bool =
  self.age >= 18

when isMainModule:
  let calc = Calculator()
  echo "Result: ", calc.add(5, 3)

  let user = User(name: "Alice", age: 30)
  echo user.greet()

  echo "Circle area: ", calculateArea(5.0)
