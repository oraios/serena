// Modern Svelte 5 reactive state using runes instead of svelte/store
export let count = $state(0);

export function resetCount() {
    count = 0;
}

export function incrementCount() {
    count++;
}