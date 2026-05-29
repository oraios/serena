import { describe, it, expect } from 'vitest';
import { isValidMemoryName } from '../src/lib/validation';

describe('memory name validation', () => {
  it('accepts names with letters, digits, underscores, and slashes', () => {
    expect(isValidMemoryName('architecture/api_design')).toBe(true);
    expect(isValidMemoryName('global/java/style_guide')).toBe(true);
  });
  it('rejects spaces and other punctuation', () => {
    expect(isValidMemoryName('bad name')).toBe(false);
    expect(isValidMemoryName('weird!')).toBe(false);
    expect(isValidMemoryName('')).toBe(false);
  });
});
