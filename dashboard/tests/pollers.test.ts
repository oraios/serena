import { describe, it, expect } from 'vitest';
import { pollersForView } from '../src/lib/pollers';

describe('pollersForView', () => {
  it('overview polls config, queued, last, and timeline', () => {
    expect(pollersForView('overview')).toEqual(['config', 'queued', 'last', 'timeline']);
  });
  it('logs polls only logs', () => {
    expect(pollersForView('logs')).toEqual(['logs']);
  });
  it('stats polls config + timeline', () => {
    expect(pollersForView('stats')).toEqual(['config', 'timeline']);
  });
  it('code polls config only (Code-tab routes are on-demand)', () => {
    expect(pollersForView('code')).toEqual(['config']);
  });
  it('includes timeline for overview and stats', () => {
    expect(pollersForView('overview')).toContain('timeline');
    expect(pollersForView('stats')).toContain('timeline');
  });
  it('does not run timeline on logs/code', () => {
    expect(pollersForView('logs')).not.toContain('timeline');
    expect(pollersForView('code')).not.toContain('timeline');
  });
});
