import { describe, it, expect } from 'vitest';
import { pageTitle } from '../src/lib/title';

describe('pageTitle', () => {
  it('includes the active project when present', () => {
    expect(pageTitle('serena')).toBe('serena – Serena Dashboard');
  });
  it('falls back to the bare title when there is no project', () => {
    expect(pageTitle(null)).toBe('Serena Dashboard');
    expect(pageTitle(undefined)).toBe('Serena Dashboard');
  });
});
