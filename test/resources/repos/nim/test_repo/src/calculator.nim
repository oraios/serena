## calculator.nim: A simple calculator module for testing LSP features

proc add*(a, b: int): int =
  ## Add two integers
  a + b

proc subtract*(a, b: int): int =
  ## Subtract b from a
  a - b

proc multiply*(a, b: int): int =
  ## Multiply two integers
  a * b

proc divide*(a, b: float): float =
  ## Divide a by b
  if b == 0.0:
    raise newException(ValueError, "Division by zero")
  a / b

proc factorial*(n: int): int =
  ## Compute factorial of n
  if n < 0:
    raise newException(ValueError, "Factorial is not defined for negative numbers")
  elif n == 0 or n == 1:
    1
  else:
    var result = 1
    for i in 2..n:
      result = result * i
    result

proc power*(base, exponent: int): int =
  ## Compute base raised to exponent
  var result = 1
  for _ in 1..exponent:
    result = result * base
  result
