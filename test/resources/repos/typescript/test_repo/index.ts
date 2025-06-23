/**
 * A demonstration class that holds a numeric value and provides operations on it.
 * This class showcases basic TypeScript class features including constructors,
 * properties, and methods.
 */
export class DemoClass {
    /** The numeric value stored in this instance */
    value: number;
    
    /**
     * Creates a new DemoClass instance with the specified value.
     * @param value - The initial numeric value to store
     */
    constructor(value: number) {
        this.value = value;
    }
    
    /**
     * Prints the current value to the console.
     * This method demonstrates a simple void method with no parameters.
     */
    printValue(): void {
        console.log(this.value);
    }
    
    /**
     * Multiplies the current value by the given factor.
     * @param factor - The number to multiply the current value by
     * @returns The new value after multiplication
     */
    multiply(factor: number): number {
        this.value *= factor;
        return this.value;
    }
}

/**
 * A helper function that demonstrates the usage of DemoClass.
 * Creates an instance, prints its value, and performs operations.
 * @returns The DemoClass instance for further use
 */
export function helperFunction(): DemoClass {
    const demo = new DemoClass(42);
    demo.printValue();
    demo.multiply(2);
    return demo;
}

/**
 * Utility function that processes an array of numbers.
 * @param numbers - Array of numbers to process
 * @param operation - Function to apply to each number
 * @returns Array of processed numbers
 */
export function processNumbers(
    numbers: number[], 
    operation: (n: number) => number
): number[] {
    return numbers.map(operation);
}

/**
 * Interface defining a user object structure.
 */
export interface User {
    /** Unique identifier for the user */
    id: number;
    /** User's display name */
    name: string;
    /** User's email address */
    email: string;
    /** Whether the user account is active */
    isActive?: boolean;
}

/**
 * Creates a new user with the provided information.
 * @param name - The user's name
 * @param email - The user's email address
 * @param id - Optional user ID, auto-generated if not provided
 * @returns A new User object
 */
export function createUser(name: string, email: string, id?: number): User {
    return {
        id: id ?? Math.floor(Math.random() * 10000),
        name,
        email,
        isActive: true
    };
}

// Execute the helper function
helperFunction();
