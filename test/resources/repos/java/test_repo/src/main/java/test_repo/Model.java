package test_repo;

public class Model {
    private String name;

    public Model(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public String getName(int maxChars) {
        if (name.length() <= maxChars) {
            return name;
        } else {
            return name.substring(0, maxChars) + "...";
        }
    }
}
