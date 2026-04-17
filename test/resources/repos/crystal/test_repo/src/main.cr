require "./utils"

class Calculator
  def add(a : Int32, b : Int32) : Int32
    a + b
  end

  def multiply(a : Int32, b : Int32) : Int32
    a * b
  end
end

struct User
  getter name : String
  getter age : Int32

  def initialize(@name : String, @age : Int32)
  end

  def greet : String
    "Hello, my name is #{name} and I am #{age} years old."
  end

  def adult? : Bool
    age >= 18
  end
end

module Status
  Active   = 0
  Inactive = 1
  Pending  = 2
end

calculator = Calculator.new
result = calculator.add(5, 3)
puts "Result: #{result}"

user = User.new("Alice", 30)
puts user.greet

area = Utils.calculate_area(5.0)
puts "Circle area: #{area}"
