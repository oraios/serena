package test_repo;

public class Main {
    public static void main(String[] args) {
        Utils.printHello();
        Model model = new Model("Cascade");
        System.out.println(model.getName());
        acceptModel(model);
    }
    public static void acceptModel(Model m) {
        // Do nothing, just for LSP reference
    }
}
