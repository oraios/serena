export interface CounterStore {
  count: number;
  increment: () => void;
  decrement: () => void;
}

export function createCounter(): CounterStore {
  let count = 0;

  return {
    get count() {
      return count;
    },
    increment() {
      count++;
    },
    decrement() {
      count--;
    },
  };
}
