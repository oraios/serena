package main

import "core:fmt"
import "core:math"

calculate_area :: proc(radius: f64) -> f64 {
	return math.PI * radius * radius
}

format_greeting :: proc(name: string, age: int) -> string {
	return fmt.aprintf("Hello, my name is %s and I am %d years old.", name, age)
}
