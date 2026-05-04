class Calculator
  def add(a, b)
    a + b
  end

  def subtract(a, b)
    a - b
  end
end

class Greeter
  def format_greeting(name)
    name
  end
end

class ConsoleGreeter < Greeter
  def format_greeting(name)
    "Hello, #{name}!"
  end
end
