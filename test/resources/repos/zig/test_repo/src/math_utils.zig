const std = @import("std");

pub fn factorial(n: u32) u64 {
    if (n == 0 or n == 1) {
        return 1;
    }
    var result: u64 = 1;
    var i: u32 = 2;
    while (i <= n) : (i += 1) {
        result *= i;
    }
    return result;
}

pub fn isPrime(n: u32) bool {
    if (n <= 1) return false;
    if (n <= 3) return true;
    if (n % 2 == 0 or n % 3 == 0) return false;
    
    var i: u32 = 5;
    while (i * i <= n) : (i += 6) {
        if (n % i == 0 or n % (i + 2) == 0) {
            return false;
        }
    }
    return true;
}

pub fn gcd(a: u32, b: u32) u32 {
    var x = a;
    var y = b;
    while (y != 0) {
        const temp = y;
        y = x % y;
        x = temp;
    }
    return x;
}

pub fn lcm(a: u32, b: u32) u32 {
    return (a * b) / gcd(a, b);
}

test "factorial" {
    try std.testing.expectEqual(@as(u64, 1), factorial(0));
    try std.testing.expectEqual(@as(u64, 1), factorial(1));
    try std.testing.expectEqual(@as(u64, 120), factorial(5));
    try std.testing.expectEqual(@as(u64, 3628800), factorial(10));
}

test "isPrime" {
    try std.testing.expect(!isPrime(0));
    try std.testing.expect(!isPrime(1));
    try std.testing.expect(isPrime(2));
    try std.testing.expect(isPrime(3));
    try std.testing.expect(!isPrime(4));
    try std.testing.expect(isPrime(17));
    try std.testing.expect(!isPrime(100));
}

test "gcd and lcm" {
    try std.testing.expectEqual(@as(u32, 6), gcd(12, 18));
    try std.testing.expectEqual(@as(u32, 1), gcd(17, 19));
    try std.testing.expectEqual(@as(u32, 36), lcm(12, 18));
}