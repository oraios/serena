import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import LogViewer from '../src/components/logs/LogViewer.svelte';

describe('LogViewer', () => {
  it('renders a line per message with a level class', () => {
    const { container } = render(LogViewer, {
      props: { lines: ['INFO hello', 'ERROR boom'], toolNames: [] },
    });
    const rows = container.querySelectorAll('.log-line');
    expect(rows.length).toBe(2);
    expect(rows[1].classList.contains('error')).toBe(true);
  });

  it('scrolls to the bottom on the first non-empty render', async () => {
    const { container } = render(LogViewer, {
      props: { lines: ['INFO a', 'INFO b'], toolNames: [] },
    });
    const el = container.querySelector('.log-container') as HTMLElement;
    let scrollTopValue = 0;
    Object.defineProperty(el, 'scrollHeight', { configurable: true, value: 500 });
    Object.defineProperty(el, 'clientHeight', { configurable: true, value: 100 });
    Object.defineProperty(el, 'scrollTop', {
      configurable: true,
      get: () => scrollTopValue,
      set: (v) => {
        scrollTopValue = v;
      },
    });
    // Flush the effect's queueMicrotask: setTimeout(0) is a macrotask, and the
    // microtask queue always drains before the next macrotask fires, so awaiting
    // a setTimeout reliably yields control until our scroll-write has happened.
    await new Promise((r) => setTimeout(r, 0));
    expect(scrollTopValue).toBe(500);
  });

  it('does not force-scroll when the user has scrolled up', async () => {
    const { container, rerender } = render(LogViewer, {
      props: { lines: ['INFO a'], toolNames: [] },
    });
    const el = container.querySelector('.log-container') as HTMLElement;
    let scrollTopValue = 0;
    Object.defineProperty(el, 'scrollHeight', { configurable: true, value: 500 });
    Object.defineProperty(el, 'clientHeight', { configurable: true, value: 100 });
    Object.defineProperty(el, 'scrollTop', {
      configurable: true,
      get: () => scrollTopValue,
      set: (v) => {
        scrollTopValue = v;
      },
    });
    await new Promise((r) => setTimeout(r, 0)); // initial scroll fires once
    scrollTopValue = 0; // simulate the user scrolling back to the top
    await rerender({ lines: ['INFO a', 'INFO b', 'INFO c'], toolNames: [] });
    await new Promise((r) => setTimeout(r, 0));
    expect(scrollTopValue).toBe(0); // sticky logic must NOT yank to the bottom
  });
});
