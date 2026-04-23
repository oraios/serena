import test_repo/utils

/// A simple calculator type.
pub type Calculator {
  Calculator(name: String)
}

/// Adds two integers and returns the result.
pub fn add(a: Int, b: Int) -> Int {
  a + b
}

/// Subtracts b from a.
pub fn subtract(a: Int, b: Int) -> Int {
  a - b
}

/// Multiplies two integers.
pub fn multiply(a: Int, b: Int) -> Int {
  a * b
}

/// Formats the result of an operation using the utils module.
pub fn format_result(label: String, value: Int) -> String {
  utils.format_output(label, value)
}

/// Returns the description of a calculator.
pub fn describe(calc: Calculator) -> String {
  "Calculator: " <> calc.name
}
