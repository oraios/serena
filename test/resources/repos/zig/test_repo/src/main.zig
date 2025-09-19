const std = @import("std");
const calculator = @import("calculator.zig");
const math_utils = @import("math_utils.zig");

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();

    const calc = calculator.Calculator.init();
    
    const sum = calc.add(10, 5);
    const diff = calc.subtract(10, 5);
    const prod = calc.multiply(10, 5);
    const quot = calc.divide(10, 5) catch |err| {
        try stdout.print("Division error: {}\n", .{err});
        return;
    };

    try stdout.print("10 + 5 = {}\n", .{sum});
    try stdout.print("10 - 5 = {}\n", .{diff});
    try stdout.print("10 * 5 = {}\n", .{prod});
    try stdout.print("10 / 5 = {}\n", .{quot});

    const factorial_result = math_utils.factorial(5);
    try stdout.print("5! = {}\n", .{factorial_result});

    const is_prime = math_utils.isPrime(17);
    try stdout.print("Is 17 prime? {}\n", .{is_prime});
}

pub fn greeting(name: []const u8) []const u8 {
    return std.fmt.allocPrint(std.heap.page_allocator, "Hello, {s}!", .{name}) catch "Hello!";
}