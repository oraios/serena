use rsandbox::{add, ConsoleGreeter, Greeter};

fn main() {
    println!("Hello, World!");
    println!("Good morning!");
    println!("add result: {}", add());
    let greeter = ConsoleGreeter;
    println!("{}", greeter.format_greeting("Rust"));
    println!("inserted line");
}
