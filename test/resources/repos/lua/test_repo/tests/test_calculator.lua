-- test_calculator.lua: Unit tests for calculator module

local calculator = require("src.calculator")

local function assert_equals(actual, expected, message)
    if actual ~= expected then
        error(string.format("%s: expected %s, got %s", 
            message or "Assertion failed", tostring(expected), tostring(actual)))
    end
end

local function assert_error(func, message)
    local success = pcall(func)
    if success then
        error(string.format("%s: expected error but none was thrown", 
            message or "Assertion failed"))
    end
end

local function test_basic_operations()
    print("Testing basic operations...")
    assert_equals(calculator.add(2, 3), 5, "Addition test")
    assert_equals(calculator.add(-5, 5), 0, "Addition with negative")
    assert_equals(calculator.add(0, 0), 0, "Addition with zeros")
    
    assert_equals(calculator.subtract(10, 3), 7, "Subtraction test")
    assert_equals(calculator.subtract(5, 10), -5, "Subtraction negative result")
    
    assert_equals(calculator.multiply(4, 5), 20, "Multiplication test")
    assert_equals(calculator.multiply(-3, 4), -12, "Multiplication with negative")
    assert_equals(calculator.multiply(0, 100), 0, "Multiplication with zero")
    
    assert_equals(calculator.divide(10, 2), 5, "Division test")
    assert_equals(calculator.divide(7, 2), 3.5, "Division with decimal result")
    assert_error(function() calculator.divide(5, 0) end, "Division by zero")
    
    print("✓ Basic operations tests passed")
end

local function test_advanced_operations()
    print("Testing advanced operations...")
    assert_equals(calculator.power(2, 3), 8, "Power test")
    assert_equals(calculator.power(5, 0), 1, "Power of zero")
    assert_equals(calculator.power(10, -1), 0.1, "Negative exponent")
    
    assert_equals(calculator.factorial(0), 1, "Factorial of 0")
    assert_equals(calculator.factorial(1), 1, "Factorial of 1")
    assert_equals(calculator.factorial(5), 120, "Factorial of 5")
    assert_equals(calculator.factorial(10), 3628800, "Factorial of 10")
    assert_error(function() calculator.factorial(-1) end, "Factorial of negative")
    
    print("✓ Advanced operations tests passed")
end

local function test_statistics()
    print("Testing statistics functions...")
    
    -- Mean tests
    assert_equals(calculator.mean({1, 2, 3, 4, 5}), 3, "Mean of sequential numbers")
    assert_equals(calculator.mean({10}), 10, "Mean of single number")
    assert_equals(calculator.mean({-5, 5}), 0, "Mean with negatives")
    assert_equals(calculator.mean({}), nil, "Mean of empty array")
    
    -- Median tests
    assert_equals(calculator.median({1, 2, 3, 4, 5}), 3, "Median of odd count")
    assert_equals(calculator.median({1, 2, 3, 4}), 2.5, "Median of even count")
    assert_equals(calculator.median({5, 1, 3, 2, 4}), 3, "Median of unsorted")
    assert_equals(calculator.median({7}), 7, "Median of single number")
    assert_equals(calculator.median({}), nil, "Median of empty array")
    
    print("✓ Statistics tests passed")
end

-- Run all tests
local function run_all_tests()
    print("Running calculator tests...\n")
    test_basic_operations()
    test_advanced_operations()
    test_statistics()
    print("\n✅ All calculator tests passed!")
end

-- Execute tests if run directly
if arg and arg[0] and arg[0]:match("test_calculator%.lua$") then
    run_all_tests()
end

return {
    run_all_tests = run_all_tests,
    test_basic_operations = test_basic_operations,
    test_advanced_operations = test_advanced_operations,
    test_statistics = test_statistics
}