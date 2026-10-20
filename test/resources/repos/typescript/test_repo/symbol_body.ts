// Fixture for verifying that replace_symbol_body includes the leading `export`/`const`/`let`/`var`
// keyword(s) in the symbol body and replacement range, just like `function`/`class` declarations do.

export const twice = (n: number): number => n * 2;

const localCounter: number = 0;

export let mutableFlag: boolean = false;

var legacyVar: string = "legacy";

export function helperFunction(): void {}

export class HelperClass {}
