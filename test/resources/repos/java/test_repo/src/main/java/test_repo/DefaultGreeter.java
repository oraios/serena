package test_repo;

class DefaultGreeter implements LombokModel.Greeter {
    @Override
    public String greet() {
        return "hi";
    }

    @Override
    public String farewell() {
        return "bye";
    }
}
