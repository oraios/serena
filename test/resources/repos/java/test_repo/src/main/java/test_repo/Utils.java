package test_repo;

import java.util.List;
import java.util.ArrayList;
import java.util.Collections;

/**
 * Utility class containing various helper methods for common operations.
 * This class demonstrates Java documentation standards using Javadoc comments.
 */
public class Utils {
    
    /**
     * Prints a hello message to the console.
     * This is a simple demonstration method with no parameters or return value.
     */
    public static void printHello() {
        System.out.println("Hello from Utils!");
    }
    
    /**
     * Calculates the factorial of a given number.
     * @param n the number to calculate factorial for (must be non-negative)
     * @return the factorial of n
     * @throws IllegalArgumentException if n is negative
     */
    public static long factorial(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("Factorial is not defined for negative numbers");
        }
        if (n == 0 || n == 1) {
            return 1;
        }
        long result = 1;
        for (int i = 2; i <= n; i++) {
            result *= i;
        }
        return result;
    }
    
    /**
     * Sorts a list of integers in ascending order and returns a new list.
     * The original list is not modified.
     * @param numbers the list of integers to sort
     * @return a new sorted list containing the same elements
     */
    public static List<Integer> sortNumbers(List<Integer> numbers) {
        List<Integer> sorted = new ArrayList<>(numbers);
        Collections.sort(sorted);
        return sorted;
    }
    
    /**
     * Checks if a string is null or empty.
     * @param str the string to check
     * @return true if the string is null or empty, false otherwise
     */
    public static boolean isNullOrEmpty(String str) {
        return str == null || str.trim().isEmpty();
    }
    
    /**
     * Finds the maximum value in an array of integers.
     * @param values the array of integers to search
     * @return the maximum value in the array
     * @throws IllegalArgumentException if the array is null or empty
     */
    public static int findMax(int[] values) {
        if (values == null || values.length == 0) {
            throw new IllegalArgumentException("Array cannot be null or empty");
        }
        int max = values[0];
        for (int i = 1; i < values.length; i++) {
            if (values[i] > max) {
                max = values[i];
            }
        }
        return max;
    }
}
