//! # Test Repository Library
//! 
//! This library contains utility functions for testing various Rust language features
//! and documentation patterns.

use std::collections::HashMap;

/// Adds two numbers together and returns the result.
/// 
/// This function demonstrates basic arithmetic operations in Rust.
/// 
/// # Examples
/// 
/// ```
/// let result = test_repo::add();
/// assert_eq!(result, 4);
/// ```
pub fn add() -> i32 {
    let res = 2 + 2;
    res
}

/// Multiplies two predefined numbers and returns the result.
/// 
/// This function shows a simple multiplication operation.
/// 
/// # Returns
/// 
/// Returns the product of 2 and 3 as an i32.
/// 
/// # Examples
/// 
/// ```
/// let result = test_repo::multiply();
/// assert_eq!(result, 6);
/// ```
pub fn multiply() -> i32 {
    2 * 3
}

/// Calculates the factorial of a given number.
/// 
/// # Arguments
/// 
/// * `n` - A positive integer to calculate the factorial for
/// 
/// # Returns
/// 
/// Returns the factorial of `n` as a u64, or None if `n` is 0.
/// 
/// # Examples
/// 
/// ```
/// use test_repo::factorial;
/// 
/// assert_eq!(factorial(5), Some(120));
/// assert_eq!(factorial(0), None);
/// ```
pub fn factorial(n: u32) -> Option<u64> {
    if n == 0 {
        return None;
    }
    
    let mut result = 1u64;
    for i in 1..=n {
        result *= i as u64;
    }
    Some(result)
}

/// A simple structure representing a point in 2D space.
/// 
/// This struct demonstrates basic Rust struct syntax and documentation.
#[derive(Debug, Clone, PartialEq)]
pub struct Point {
    /// The x-coordinate of the point
    pub x: f64,
    /// The y-coordinate of the point  
    pub y: f64,
}

impl Point {
    /// Creates a new Point with the given coordinates.
    /// 
    /// # Arguments
    /// 
    /// * `x` - The x-coordinate
    /// * `y` - The y-coordinate
    /// 
    /// # Examples
    /// 
    /// ```
    /// use test_repo::Point;
    /// 
    /// let p = Point::new(1.0, 2.0);
    /// assert_eq!(p.x, 1.0);
    /// assert_eq!(p.y, 2.0);
    /// ```
    pub fn new(x: f64, y: f64) -> Self {
        Point { x, y }
    }
    
    /// Calculates the distance from this point to another point.
    /// 
    /// # Arguments
    /// 
    /// * `other` - The other point to calculate distance to
    /// 
    /// # Returns
    /// 
    /// Returns the Euclidean distance between the two points.
    /// 
    /// # Examples
    /// 
    /// ```
    /// use test_repo::Point;
    /// 
    /// let p1 = Point::new(0.0, 0.0);
    /// let p2 = Point::new(3.0, 4.0);
    /// assert_eq!(p1.distance_to(&p2), 5.0);
    /// ```
    pub fn distance_to(&self, other: &Point) -> f64 {
        let dx = self.x - other.x;
        let dy = self.y - other.y;
        (dx * dx + dy * dy).sqrt()
    }
}

/// Processes a vector of numbers using a given function.
/// 
/// # Arguments
/// 
/// * `numbers` - A vector of i32 numbers to process
/// * `processor` - A function that takes an i32 and returns an i32
/// 
/// # Returns
/// 
/// Returns a new vector with all numbers processed by the given function.
/// 
/// # Examples
/// 
/// ```
/// use test_repo::process_numbers;
/// 
/// let numbers = vec![1, 2, 3, 4];
/// let doubled = process_numbers(numbers, |x| x * 2);
/// assert_eq!(doubled, vec![2, 4, 6, 8]);
/// ```
pub fn process_numbers<F>(numbers: Vec<i32>, processor: F) -> Vec<i32>
where
    F: Fn(i32) -> i32,
{
    numbers.into_iter().map(processor).collect()
}

/// Creates a frequency map of characters in a string.
/// 
/// # Arguments
/// 
/// * `text` - The input string to analyze
/// 
/// # Returns
/// 
/// Returns a HashMap where keys are characters and values are their frequencies.
/// 
/// # Examples
/// 
/// ```
/// use test_repo::char_frequency;
/// 
/// let freq = char_frequency("hello");
/// assert_eq!(freq.get(&'l'), Some(&2));
/// assert_eq!(freq.get(&'h'), Some(&1));
/// ```
pub fn char_frequency(text: &str) -> HashMap<char, usize> {
    let mut freq = HashMap::new();
    for ch in text.chars() {
        *freq.entry(ch).or_insert(0) += 1;
    }
    freq
}