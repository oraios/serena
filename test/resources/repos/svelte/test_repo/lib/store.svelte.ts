// Modern Svelte 5 reactive state with TypeScript
import type { User } from './store';

// Reactive state using Svelte 5 runes
export let count = $state(0);
export let currentUser = $state<User | null>(null);

export function incrementCount(): void {
    count++;
}

export function resetCount(): void {
    count = 0;
}

export function setCurrentUser(user: User | null): void {
    currentUser = user;
}