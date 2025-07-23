import { writable } from 'svelte/store';

export const count = writable(0);

export function resetCount() {
    count.set(0);
}

export function getCountValue() {
    let value;
    count.subscribe(n => value = n)();
    return value;
}