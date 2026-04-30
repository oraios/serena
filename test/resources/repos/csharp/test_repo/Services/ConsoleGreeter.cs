namespace TestProject.Services
{
    public class ConsoleGreeter : IGreeter
    {
        public string FormatGreeting(string name)
        {
            return $"Hello, {name}!";
        }
    }
}
