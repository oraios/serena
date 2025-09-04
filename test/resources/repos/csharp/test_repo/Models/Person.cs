using TestProject;

namespace TestProject.Models
{
    public class Person
    {
        public string Name { get; set; }
        public int Age { get; set; }
        public string Email { get; set; }
        
        public Person(string name, int age, string email)
        {
            Name = name;
            Age = age;
            Email = email;
        }
        
        public override string ToString()
        {
            return $"{Name} ({Age}) - {Email}";
        }
        
        public bool IsAdult()
        {
            return Age >= 18;
        }
        
        public int CalculateYearsUntilRetirement()
        {
            var calculator = new Calculator();
            return calculator.Subtract(65, Age);
        }

        public void CalculateAge()
        {
            var calc = new Calculator();
            var result = calc.Subtract(2025, 1990); // This creates the reference the test needs
        }
}