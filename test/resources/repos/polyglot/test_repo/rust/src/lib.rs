/// Rust Calculator implementation for polyglot testing

pub struct Calculator {
    pub value: f64,
}

impl Calculator {
    /// Create new calculator with optional initial value
    pub fn new(initial_value: f64) -> Self {
        Calculator { value: initial_value }
    }

    /// Add x to current value
    pub fn add(&mut self, x: f64) -> f64 {
        self.value += x;
        self.value
    }

    /// Subtract x from current value
    pub fn subtract(&mut self, x: f64) -> f64 {
        self.value -= x;
        self.value
    }

    /// Multiply current value by x
    pub fn multiply(&mut self, x: f64) -> f64 {
        self.value *= x;
        self.value
    }

    /// Divide current value by x
    pub fn divide(&mut self, x: f64) -> Result<f64, String> {
        if x == 0.0 {
            return Err("Cannot divide by zero".to_string());
        }
        self.value /= x;
        Ok(self.value)
    }

    /// Reset value to zero
    pub fn reset(&mut self) -> f64 {
        self.value = 0.0;
        self.value
    }
}

/// Helper function that doubles a number
pub fn helper_double(x: f64) -> f64 {
    x * 2.0
}

/// Helper function that squares a number
pub fn helper_square(x: f64) -> f64 {
    x * x
}
