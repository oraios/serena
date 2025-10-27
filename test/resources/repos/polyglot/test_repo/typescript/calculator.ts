// TypeScript Calculator implementation for polyglot testing

export class Calculator {
    value: number;

    constructor(initialValue: number = 0) {
        this.value = initialValue;
    }

    add(x: number): number {
        this.value += x;
        return this.value;
    }

    subtract(x: number): number {
        this.value -= x;
        return this.value;
    }

    multiply(x: number): number {
        this.value *= x;
        return this.value;
    }

    divide(x: number): number {
        if (x === 0) {
            throw new Error("Cannot divide by zero");
        }
        this.value /= x;
        return this.value;
    }

    reset(): number {
        this.value = 0;
        return this.value;
    }
}

export function helperDouble(x: number): number {
    return x * 2;
}

export function helperSquare(x: number): number {
    return x * x;
}
