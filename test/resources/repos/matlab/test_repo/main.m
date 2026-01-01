% MAIN Main script demonstrating Calculator and mathUtils usage
%
% This script shows how to use the Calculator class and mathUtils
% functions together for various mathematical operations.

% Add lib folder to path
addpath('lib');

%% Section 1: Basic Calculator Operations
% Create a calculator instance and perform basic operations

calc = Calculator();

% Perform some calculations
sum_result = calc.add(10, 5);
fprintf('10 + 5 = %d\n', sum_result);

diff_result = calc.subtract(10, 3);
fprintf('10 - 3 = %d\n', diff_result);

prod_result = calc.multiply(4, 7);
fprintf('4 * 7 = %d\n', prod_result);

quot_result = calc.divide(20, 4);
fprintf('20 / 4 = %d\n', quot_result);

%% Section 2: Static Method Usage
% Use the static power method

power_result = Calculator.power(2, 10);
fprintf('2^10 = %d\n', power_result);

%% Section 3: Math Utilities
% Test the mathUtils functions

% Factorial
fact5 = mathUtils('factorial', 5);
fprintf('5! = %d\n', fact5);

% Fibonacci
fib10 = mathUtils('fibonacci', 10);
fprintf('Fibonacci(10) = %d\n', fib10);

% Prime check
is17prime = mathUtils('isPrime', 17);
fprintf('Is 17 prime? %s\n', mat2str(is17prime));

% Statistics
data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
[dataMean, dataStd] = mathUtils('stats', data);
fprintf('Mean: %.2f, Std: %.2f\n', dataMean, dataStd);

%% Section 4: Display History
% Show all calculations performed by the calculator

calc.displayHistory();

%% Section 5: Error Handling
% Demonstrate error handling with division by zero

try
    calc.divide(10, 0);
catch ME
    fprintf('Caught expected error: %s\n', ME.message);
end

fprintf('\nAll tests completed successfully!\n');
