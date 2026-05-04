package test_repo;

public class DiagnosticsSample {
    public static String brokenFactory() {
        return missingGreeting;
    }

    public static void brokenConsumer() {
        String value = brokenFactory();
        System.out.println(value);
        System.out.println(missingConsumerValue);
    }
}
