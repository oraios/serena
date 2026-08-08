import { add } from "./util.ts";

export class Calculator {
  sum(a: number, b: number): number {
    return add(a, b);
  }
}

// Uses the Deno global namespace, which the plain TypeScript language server does not know about.
export function describeCwd(): string {
  return `cwd: ${Deno.cwd()}`;
}

const calc = new Calculator();
console.log(calc.sum(2, 3));
