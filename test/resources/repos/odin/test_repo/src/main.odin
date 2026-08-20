package main

import "core:fmt"

Calculator :: struct {}

User :: struct {
	name: string,
	age:  int,
}

add :: proc(self: Calculator, a, b: int) -> int {
	return a + b
}

multiply :: proc(self: Calculator, a, b: int) -> int {
	return a * b
}

greet :: proc(self: User) -> string {
	return format_greeting(self.name, self.age)
}

is_adult :: proc(self: User) -> bool {
	return self.age >= 18
}

main :: proc() {
	calc := Calculator{}
	fmt.println("Result:", add(calc, 5, 3))

	user := User{name = "Alice", age = 30}
	fmt.println(greet(user))

	fmt.println("Circle area:", calculate_area(5.0))
}
