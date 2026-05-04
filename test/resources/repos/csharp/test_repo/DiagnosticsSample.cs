using System;

namespace TestProject
{
    public static class DiagnosticsSample
    {
        public static string BrokenFactory()
        {
            return missingGreeting;
        }

        public static void BrokenConsumer()
        {
            string value = BrokenFactory();
            Console.WriteLine(value);
            Console.WriteLine(missingConsumerValue);
        }
    }
}
