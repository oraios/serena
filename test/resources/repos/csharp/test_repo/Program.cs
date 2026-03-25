using System;
using TestProject.Services;

namespace TestProject
{
    class Program
    {
        static void Main(string[] args)
        {
            Console.WriteLine("Hello, World!");
             
            var calculator = new Calculator();
            int result = calculator.Add(5, 3);
            Console.WriteLine($"5 + 3 = {result}");

            IGreeter greeter = new ConsoleGreeter();
            Console.WriteLine(greeter.FormatGreeting("World"));
        }
    }
    
    public class Calculator
    {
        public int Add(int a, int b)
        {
            return a + b;
        }
        
        public int Subtract(int a, int b)
        {
            return a - b;
        }
        
        public int Multiply(int a, int b)
        {
            return a * b;
        }
        
        public double Divide(int a, int b)
        {
            if (b == 0)
            {
                throw new DivideByZeroException("Cannot divide by zero");
            }
            return (double)a / b;
        }
    }
}
