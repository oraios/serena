package test_repo;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.With;
import lombok.experimental.Delegate;

@Data
@Builder(toBuilder = true)
@With
@AllArgsConstructor
@NoArgsConstructor
public class LombokModel {
    private String name;
    private int age;

    /** Lombok @Delegate forwards every method of Greeter to delegate.* (covers @Delegate generation). */
    public interface Greeter {
        String greet();
        String farewell();
    }

    @Delegate
    private final Greeter delegate = new DefaultGreeter();
}
