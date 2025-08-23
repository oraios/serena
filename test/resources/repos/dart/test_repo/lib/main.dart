import 'helper.dart';

/// Main calculator class demonstrating various Dart features
class Calculator {
  /// Private field for storing history
  final List<String> _history = [];

  /// Getter for accessing calculation history
  List<String> get history => List.unmodifiable(_history);

  /// Adds two integers and records the operation
  int add(int a, int b) {
    final result = a + b;
    _history.add('$a + $b = $result');
    return result;
  }

  /// Subtracts two integers using the helper function
  int performSubtract(int a, int b) {
    final result = subtract(a, b); // Reference to imported function
    _history.add('$a - $b = $result');
    return result;
  }

  /// Multiplies two numbers using helper class
  double performMultiply(double x, double y) {
    final result = multiply(x, y); // Reference to imported function
    _history.add('$x * $y = $result');
    return result;
  }

  /// Divides two numbers with error handling
  double divide(double dividend, double divisor) {
    if (divisor == 0) {
      throw ArgumentError('Division by zero is not allowed');
    }
    final result = dividend / divisor;
    _history.add('$dividend / $divisor = $result');
    return result;
  }

  /// Clears the calculation history
  void clearHistory() {
    _history.clear();
  }

  /// Performs a complex calculation using multiple operations
  double complexCalculation(double a, double b, double c) {
    final step1 = add(a.toInt(), b.toInt()).toDouble(); // Reference to add method
    final step2 = MathHelper.power(step1, 2); // Reference to helper class method
    final result = step2 + c;
    _history.add('Complex: ($a + $b)^2 + $c = $result');
    return result;
  }
}

/// A mixin for providing logging functionality
mixin LoggerMixin {
  void log(String message) {
    print('[${DateTime.now()}] $message');
  }
}

/// An abstract class for defining calculators
abstract class CalculatorInterface {
  int add(int a, int b);
  int subtract(int a, int b);
}

/// Advanced calculator that extends Calculator and uses mixin
class AdvancedCalculator extends Calculator
    with LoggerMixin
    implements CalculatorInterface {
  
  /// Performs scientific calculation with logging
  double scientificOperation(Operation operation) {
    log('Performing ${operation.type} operation');
    
    switch (operation.type) {
      case OperationType.addition:
        return operation.operand1 + operation.operand2;
      case OperationType.subtraction:
        return operation.operand1 - operation.operand2;
      case OperationType.multiplication:
        return operation.operand1 * operation.operand2;
      case OperationType.division:
        if (operation.operand2 == 0) {
          throw ArgumentError('Division by zero');
        }
        return operation.operand1 / operation.operand2;
    }
  }

  /// Factory constructor for creating calculators
  factory AdvancedCalculator.withLogger() {
    return AdvancedCalculator();
  }
}

/// Program entry point
class Program {
  /// Main method demonstrating calculator usage
  static void main(List<String> args) {
    final calc = Calculator();
    final result1 = calc.add(5, 3); // Reference to add method
    final result2 = calc.performSubtract(10, 4); // Reference to performSubtract method
    final result3 = calc.performMultiply(2.5, 4.0); // Reference to performMultiply method
    
    print('Addition result: $result1');
    print('Subtraction result: $result2');
    print('Multiplication result: $result3');
    
    // Using advanced calculator
    final advancedCalc = AdvancedCalculator.withLogger();
    final operation = (
      type: OperationType.multiplication,
      operand1: 3.14,
      operand2: 2.0
    );
    
    final scientificResult = advancedCalc.scientificOperation(operation);
    print('Scientific result: $scientificResult');
    
    // Display calculation history
    print('Calculation History:');
    for (final entry in calc.history) {
      print('  $entry');
    }
  }
}