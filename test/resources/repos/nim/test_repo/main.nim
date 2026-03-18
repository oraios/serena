## Main entry point demonstrating cross-module usage.

import src/calculator
import src/utils

proc printBanner*() =
  ## Print a welcome banner.
  echo repeat_string("=", 40)
  echo "  Nim Calculator Demo"
  echo repeat_string("=", 40)

proc testCalculator*() =
  ## Run calculator tests.
  echo "Testing calculator..."
  echo "add(2, 3) = ", add(2.0, 3.0)
  echo "subtract(10, 4) = ", subtract(10.0, 4.0)
  echo "multiply(3, 7) = ", multiply(3.0, 7.0)
  echo "divide(15, 3) = ", divide(15.0, 3.0)
  echo "factorial(5) = ", factorial(5)
  echo "mean(@[1.0, 2.0, 3.0, 4.0, 5.0]) = ", mean(@[1.0, 2.0, 3.0, 4.0, 5.0])

proc testUtils*() =
  ## Run utility tests.
  let logger = newLogger("test")
  logger.log("Testing utilities...")
  echo "trim('  hello  ') = '", trim("  hello  "), "'"
  echo "split_words('hello world') = ", split_words("hello world")
  echo "starts_with('hello', 'he') = ", starts_with("hello", "he")
  echo "ends_with('hello', 'lo') = ", ends_with("hello", "lo")
  logger.info("Utility tests complete")

when isMainModule:
  printBanner()
  testCalculator()
  testUtils()
