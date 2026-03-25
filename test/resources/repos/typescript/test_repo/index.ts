import { ConsoleGreeter, Greeter } from "./formatters";

export class DemoClass {
    value: number;
    constructor(value: number) {
        this.value = value;
    }
    printValue() {
        console.log(this.value);
    }
}

export function helperFunction() {
    const demo = new DemoClass(42);
    demo.printValue();

    const greeter: Greeter = new ConsoleGreeter();
    console.log(greeter.formatGreeting("World"));
}

helperFunction();
