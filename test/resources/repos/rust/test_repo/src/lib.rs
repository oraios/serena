pub mod diagnostics_sample;

// This function returns the sum of 2 + 2
pub fn add() -> i32 {
    let res = 2 + 2;
    res
}
pub fn multiply() -> i32 {
    2 * 3
}

pub trait Greeter {
    fn format_greeting(&self, name: &str) -> String;
}

pub struct ConsoleGreeter;

impl Greeter for ConsoleGreeter {
    fn format_greeting(&self, name: &str) -> String {
        format!("Hello, {name}!")
    }
}

