import { sharedUtilityFunction, SharedClass } from "../cross_package_a/shared_utils";

export function consumeSharedUtil(): string {
    return sharedUtilityFunction("test data");
}

export function consumeSharedClass(): string {
    const instance = new SharedClass("World");
    return instance.greet();
}
