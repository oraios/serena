package main

import "fmt"

func main() {
    fmt.Println("Hello, Go!")
    Helper()
}

func Helper() {
    fmt.Println("Helper function called")
}

type DemoStruct struct {
    Field int
}

func (d *DemoStruct) Value() int {
    return d.Field
}

func UsingHelper() {
    Helper()
}
