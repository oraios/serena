package test_repo;

public class Main {
    public static void main(String[] args) {
        Utils.printHello();
        Model model = new Model("Cascade");
        System.out.println(model.getName());
        acceptModel(model);
        Greeter greeter = new ConsoleGreeter();
        System.out.println(greeter.formatGreeting("Cascade"));
    }
    public static void acceptModel(Model m) {
        // Do nothing, just for LSP reference
    }
}
