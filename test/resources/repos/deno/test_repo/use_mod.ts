import { helperFunction } from "./mod.ts";
import { assertEquals } from "https://deno.land/std@0.224.0/assert/assert_equals.ts";

export function useHelper(): void {
    const cwd = helperFunction();
    assertEquals(typeof cwd, "string");
}

useHelper();
