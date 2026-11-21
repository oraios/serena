import type { Greeter } from "./types";

export class Polite implements Greeter {
  greet(name: string): string {
    return `hello ${name}`;
  }
}
