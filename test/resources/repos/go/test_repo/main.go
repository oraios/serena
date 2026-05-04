package main

import "fmt"

func main() {
    fmt.Println("Hello, Go!")
    Helper()
    var greeter Greeter = ConsoleGreeter{}
    fmt.Println(greeter.FormatGreeting("Go"))
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

type Greeter interface {
    FormatGreeting(name string) string
}

type ConsoleGreeter struct{}

func (ConsoleGreeter) FormatGreeting(name string) string {
    return "Hello, " + name + "!"
}
