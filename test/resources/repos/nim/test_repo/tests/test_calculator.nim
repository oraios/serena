## Tests for the calculator module.

import ../src/calculator

proc testBasicOperations() =
  assert add(2.0, 3.0) == 5.0
  assert subtract(10.0, 4.0) == 6.0
  assert multiply(3.0, 7.0) == 21.0
  assert divide(15.0, 3.0) == 5.0
  echo "Basic operations: PASSED"

proc testAdvancedOperations() =
  assert factorial(0) == 1
  assert factorial(1) == 1
  assert factorial(5) == 120
  echo "Advanced operations: PASSED"

proc testMean() =
  assert mean(@[1.0, 2.0, 3.0]) == 2.0
  assert mean(@[10.0]) == 10.0
  echo "Mean operations: PASSED"

when isMainModule:
  testBasicOperations()
  testAdvancedOperations()
  testMean()
  echo "All tests passed!"
