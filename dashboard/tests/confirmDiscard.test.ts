import { describe, it, expect, vi, afterEach } from 'vitest';
import { confirmDiscard } from '../src/lib/confirmDiscard';

afterEach(() => vi.restoreAllMocks());

describe('confirmDiscard', () => {
  it('returns true without prompting when not dirty', () => {
    const spy = vi.spyOn(window, 'confirm');
    expect(confirmDiscard(false)).toBe(true);
    expect(spy).not.toHaveBeenCalled();
  });

  it('defers to window.confirm when dirty', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    expect(confirmDiscard(true)).toBe(true);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    expect(confirmDiscard(true)).toBe(false);
  });
});
