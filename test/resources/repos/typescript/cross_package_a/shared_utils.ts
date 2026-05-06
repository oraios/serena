export function sharedUtilityFunction(input: string): string {
    return `processed: ${input}`;
}

export class SharedClass {
    name: string;
    constructor(name: string) {
        this.name = name;
    }

    greet(): string {
        return `Hello, ${this.name}`;
    }
}
