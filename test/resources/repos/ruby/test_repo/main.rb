require './lib.rb'

class DemoClass
  attr_accessor :value

  def initialize(value)
    @value = value
  end

  def print_value
    puts @value
  end
end

def helper_function(number = 42)
  demo = DemoClass.new(number)
  Calculator.new.add(demo.value, 10)
  demo.print_value
end

helper_function
