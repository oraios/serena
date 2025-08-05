fn main() {
    println!("Hello, Rust 2024 edition!");
    let result = add(2, 3);
    println!("2 + 3 = {}", result);
}

pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add() {
        assert_eq!(add(2, 3), 5);
    }
}