pub fn broken_factory() -> String {
    missing_greeting
}

pub fn broken_consumer() {
    let value = broken_factory();
    println!("{value}");
    println!("{}", missing_consumer_value);
}
