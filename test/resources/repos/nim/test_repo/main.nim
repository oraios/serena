## main.nim: Entry point demonstrating usage of calculator and utils modules

import src/calculator
import src/utils

proc printBanner() =
  ## Print a simple banner
  echo "=== Nim Test Project ==="

proc testCalculator() =
  ## Test basic calculator operations
  let sum = add(5, 3)
  echo "5 + 3 = ", sum

  let diff = subtract(10, 4)
  echo "10 - 4 = ", diff

  let prod = multiply(6, 7)
  echo "6 * 7 = ", prod

  let quot = divide(15.0, 4.0)
  echo "15 / 4 = ", quot

  let fact = factorial(5)
  echo "5! = ", fact

  let pw = power(2, 8)
  echo "2^8 = ", pw

proc testUtils() =
  ## Test string utility functions
  let trimmed = trim("  hello world  ")
  echo "Trimmed: '", trimmed, "'"

  let hasPrefix = startsWith("hello world", "hello")
  echo "Starts with 'hello': ", hasPrefix

  let hasSuffix = endsWith("hello world", "world")
  echo "Ends with 'world': ", hasSuffix

  let parts = split("one,two,three", ",")
  echo "Split parts: ", parts

  let joined = join(parts, " | ")
  echo "Joined: ", joined

when isMainModule:
  printBanner()
  testCalculator()
  testUtils()
