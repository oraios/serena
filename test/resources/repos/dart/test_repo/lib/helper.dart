/// Helper functions for mathematical operations
library helper;

/// Performs subtraction of two integers
int subtract(int a, int b) {
  return a - b;
}

/// Multiplies two numbers
double multiply(double x, double y) {
  return x * y;
}

/// A utility class for mathematical operations
class MathHelper {
  /// Calculates the power of a number
  static double power(double base, int exponent) {
    double result = 1.0;
    for (int i = 0; i < exponent; i++) {
      result *= base;
    }
    return result;
  }

  /// Calculates the square root approximation
  double sqrt(double number) {
    if (number < 0) {
      throw ArgumentError('Cannot calculate square root of negative number');
    }
    
    double guess = number / 2;
    for (int i = 0; i < 10; i++) {
      guess = (guess + number / guess) / 2;
    }
    return guess;
  }
}

/// An enumeration for operation types
enum OperationType {
  addition,
  subtraction,
  multiplication,
  division
}

/// A record for representing mathematical operations
typedef Operation = ({OperationType type, double operand1, double operand2});