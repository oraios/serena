import Foundation

// Main entry point
func main() {
    let calculator = Calculator()
    let result = calculator.add(5, 3)
    print("Result: \(result)")
    
    let user = User(name: "Alice", age: 30)
    user.greet()
    
    let area = Utils.calculateArea(radius: 5.0)
    print("Circle area: \(area)")
}

class Calculator {
    func add(_ a: Int, _ b: Int) -> Int {
        return a + b
    }
    
    func multiply(_ a: Int, _ b: Int) -> Int {
        return a * b
    }
}

struct User {
    let name: String
    let age: Int
    
    func greet() {
        print("Hello, my name is \(name) and I am \(age) years old.")
    }
    
    func isAdult() -> Bool {
        return age >= 18
    }
}

enum Status {
    case active
    case inactive
    case pending
}

protocol Drawable {
    func draw()
}

class Circle: Drawable {
    let radius: Double
    
    init(radius: Double) {
        self.radius = radius
    }
    
    func draw() {
        print("Drawing a circle with radius \(radius)")
    }
}

// Call main
main()