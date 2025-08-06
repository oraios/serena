pub fn multiply(a: i32, b: i32) -> i32 {
    a * b
}

pub struct Calculator {
    pub result: i32,
}

impl Calculator {
    pub fn new() -> Self {
        Calculator { result: 0 }
    }

    pub fn add(&mut self, value: i32) {
        self.result += value;
    }

    pub fn get_result(&self) -> i32 {
        self.result
    }
}