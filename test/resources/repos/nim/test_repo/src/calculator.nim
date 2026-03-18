## Calculator module with basic and advanced arithmetic operations.

proc add*(a, b: float): float =
  ## Add two numbers.
  result = a + b

proc subtract*(a, b: float): float =
  ## Subtract b from a.
  result = a - b

proc multiply*(a, b: float): float =
  ## Multiply two numbers.
  result = a * b

proc divide*(a, b: float): float =
  ## Divide a by b. Raises DivByZeroDefect if b is zero.
  if b == 0.0:
    raise newException(DivByZeroDefect, "Cannot divide by zero")
  result = a / b

proc factorial*(n: int): int =
  ## Compute factorial of a non-negative integer.
  if n < 0:
    raise newException(ValueError, "Factorial not defined for negative numbers")
  if n <= 1:
    return 1
  result = n * factorial(n - 1)

proc mean*(values: seq[float]): float =
  ## Compute the arithmetic mean of a sequence of floats.
  if values.len == 0:
    raise newException(ValueError, "Cannot compute mean of empty sequence")
  var total = 0.0
  for v in values:
    total += v
  result = total / float(values.len)
