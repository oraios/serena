class OuterClass
  def initialize
    @value = "outer"
  end

  def outer_method
    inner_function = lambda do |x|
      x * 2
    end
    
    result = inner_function.call(5)
    puts "Result: #{result}"
  end

  class NestedClass
    def initialize(name)
      @name = name
    end

    def find_me
      "Found in NestedClass: #{@name}"
    end

    def nested_method
      puts "Nested method called"
    end

    class DeeplyNested
      def deep_method
        "Deep inside"
      end
    end
  end

  module NestedModule
    def module_method
      "Module method"
    end

    class ModuleClass
      def module_class_method
        "Module class method"
      end
    end
  end
end

# Test usage of nested classes
outer = OuterClass.new
nested = OuterClass::NestedClass.new("test")
result = nested.find_me