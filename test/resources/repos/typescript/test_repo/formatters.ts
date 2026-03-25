export interface Greeter {
    formatGreeting(name: string): string;
}

export class ConsoleGreeter implements Greeter {
    formatGreeting(name: string): string {
        return `Hello, ${name}!`;
    }
}
