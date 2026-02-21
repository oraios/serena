import { join } from "jsr:@std/path@1";

export class DemoClass {
    value: number;
    constructor(value: number) {
        this.value = value;
    }
    printValue(): void {
        console.log(join("value", String(this.value)));
    }
}

export function helperFunction(): string {
    const demo = new DemoClass(42);
    demo.printValue();
    return Deno.cwd();
}
