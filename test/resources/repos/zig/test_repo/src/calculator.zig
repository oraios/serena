const std = @import("std");

pub const CalculatorError = error{
    DivisionByZero,
    Overflow,
};

pub const Calculator = struct {
    const Self = @This();

    pub fn init() Self {
        return .{};
    }

    pub fn add(self: Self, a: i32, b: i32) i32 {
        _ = self;
        return a + b;
    }

    pub fn subtract(self: Self, a: i32, b: i32) i32 {
        _ = self;
        return a - b;
    }

    pub fn multiply(self: Self, a: i32, b: i32) i32 {
        _ = self;
        return a * b;
    }

    pub fn divide(self: Self, a: i32, b: i32) !f64 {
        _ = self;
        if (b == 0) {
            return CalculatorError.DivisionByZero;
        }
        return @as(f64, @floatFromInt(a)) / @as(f64, @floatFromInt(b));
    }

    pub fn power(self: Self, base: i32, exponent: u32) i64 {
        _ = self;
        return std.math.pow(i64, base, exponent);
    }
};

test "Calculator add" {
    const calc = Calculator.init();
    try std.testing.expectEqual(@as(i32, 7), calc.add(3, 4));
    try std.testing.expectEqual(@as(i32, 0), calc.add(-5, 5));
}

test "Calculator subtract" {
    const calc = Calculator.init();
    try std.testing.expectEqual(@as(i32, -1), calc.subtract(3, 4));
    try std.testing.expectEqual(@as(i32, 10), calc.subtract(15, 5));
}

test "Calculator multiply" {
    const calc = Calculator.init();
    try std.testing.expectEqual(@as(i32, 12), calc.multiply(3, 4));
    try std.testing.expectEqual(@as(i32, -25), calc.multiply(-5, 5));
}

test "Calculator divide" {
    const calc = Calculator.init();
    try std.testing.expectEqual(@as(f64, 2.0), try calc.divide(10, 5));
    try std.testing.expectError(CalculatorError.DivisionByZero, calc.divide(10, 0));
}