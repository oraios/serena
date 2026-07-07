import { describe, it, expect } from 'vitest';
import { sortNewsEntries } from '../src/lib/news';

describe('sortNewsEntries', () => {
  it('orders YYYYMMDD ids newest-first', () => {
    const out = sortNewsEntries({ '20260101': 'a', '20260527': 'b', '20260315': 'c' });
    expect(out.map(([id]) => id)).toEqual(['20260527', '20260315', '20260101']);
  });
});
