package test_repo;

public class ConsoleGreeter implements Greeter {
    @Override
    public String formatGreeting(String name) {
        return "Hello, " + name + "!";
    }
}
