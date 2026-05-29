import { describe, it, expect } from 'vitest';
import { pollersForView } from '../src/lib/pollers';

describe('pollersForView', () => {
  it('overview polls config, queued, and last', () => {
    expect(pollersForView('overview')).toEqual(['config', 'queued', 'last']);
  });
  it('logs polls only logs', () => {
    expect(pollersForView('logs')).toEqual(['logs']);
  });
  it('stats polls nothing', () => {
    expect(pollersForView('stats')).toEqual([]);
  });
});
