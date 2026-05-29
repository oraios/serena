declare module 'frappe-charts' {
  export class Chart {
    constructor(parent: HTMLElement | string, options: Record<string, unknown>);
    update(data: { labels: string[]; datasets: Array<{ name?: string; values: number[] }> }): void;
    destroy(): void;
  }
}
