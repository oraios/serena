package main

import "fmt"

func main() {
	fmt.Println("Hello, World!")
	
	// Using undefined variable - should generate an error
	fmt.Println(undefinedVariable)
	
	// Calling undefined function - should generate an error  
	undefinedFunction()
	
	// Valid code
	validFunction()
}

func validFunction() {
	fmt.Println("This is a valid function")
}