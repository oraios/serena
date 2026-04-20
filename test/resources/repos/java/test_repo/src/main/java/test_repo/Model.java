package test_repo;

/**
 * A simple model class that holds a name and provides methods to retrieve it.
 */
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
