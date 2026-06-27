import { describe, it, expect } from 'vitest';
import { KIND_META } from '../src/lib/symbolTree';
import { countByKind, pluralizeKind } from '../src/lib/symbolTree';
import type { FileSymbol } from '../src/lib/api/types';

function sym(name: string, kind: string, children: FileSymbol[] = []): FileSymbol {
  return {
    name,
    kind,
    range: { start: { line: 0, character: 0 }, end: { line: 0, character: 0 } },
    children,
  };
}

describe('KIND_META', () => {
  it('maps known kinds to {icon, colorVar, label} with no duplicates', () => {
    const known = [
      'Class',
      'Method',
      'Function',
      'Variable',
      'Field',
      'Property',
      'Interface',
      'Enum',
      'Constant',
      'Module',
    ];
    for (const k of known) {
      const meta = KIND_META[k];
      expect(meta).toBeDefined();
      expect(meta.colorVar.startsWith('--')).toBe(true);
      expect(typeof meta.label).toBe('string');
      expect(meta.icon).toBeDefined();
    }
  });

  it('returns a fallback for unknown kinds via getKindMeta', async () => {
    const { getKindMeta } = await import('../src/lib/symbolTree');
    const meta = getKindMeta('totally-unknown-kind');
    expect(meta).toBeDefined();
    expect(meta.label).toBe('totally-unknown-kind');
  });
});

describe('countByKind', () => {
  it('returns empty for no symbols', () => {
    expect(countByKind([])).toEqual({});
  });

  it('counts kinds recursively including children', () => {
    const tree = [
      sym('A', 'Class', [sym('m1', 'Method'), sym('m2', 'Method'), sym('v1', 'Variable')]),
      sym('B', 'Class', [sym('m3', 'Method')]),
      sym('fn1', 'Function'),
    ];
    expect(countByKind(tree)).toEqual({ Class: 2, Method: 3, Variable: 1, Function: 1 });
  });
});

describe('pluralizeKind', () => {
  it('returns the singular for count 1', () => {
    expect(pluralizeKind('Class', 1)).toBe('1 class');
    expect(pluralizeKind('Method', 1)).toBe('1 method');
  });

  it('returns the plural for count !== 1', () => {
    expect(pluralizeKind('Class', 2)).toBe('2 classes');
    expect(pluralizeKind('Property', 3)).toBe('3 properties');
    expect(pluralizeKind('Method', 0)).toBe('0 methods');
  });

  it('falls back to "<count> <kind>" for unknown kinds', () => {
    expect(pluralizeKind('Weird', 2)).toBe('2 weird');
  });
});

import { filterTree } from '../src/lib/symbolTree';

describe('filterTree', () => {
  const tree = [
    sym('Alpha', 'Class', [sym('foo', 'Method'), sym('bar', 'Method')]),
    sym('Beta', 'Class', [sym('baz', 'Method'), sym('qux', 'Method')]),
  ];

  it('returns the tree unchanged for empty query', () => {
    expect(filterTree(tree, '')).toEqual(tree);
    expect(filterTree(tree, '   ')).toEqual(tree);
  });

  it('case-insensitively matches names; keeps parents of matches', () => {
    const result = filterTree(tree, 'foo');
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('Alpha');
    expect(result[0].children).toHaveLength(1);
    expect(result[0].children?.[0].name).toBe('foo');
  });

  it('keeps a parent if the parent itself matches (all children retained)', () => {
    const result = filterTree(tree, 'alpha');
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('Alpha');
    expect(result[0].children).toHaveLength(2);
  });

  it('prunes branches with no matches', () => {
    const result = filterTree(tree, 'baz');
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('Beta');
    expect(result[0].children).toHaveLength(1);
    expect(result[0].children?.[0].name).toBe('baz');
  });

  it('returns empty array when nothing matches', () => {
    expect(filterTree(tree, 'zzz')).toEqual([]);
  });
});

import { flattenForDisplay, symbolKey } from '../src/lib/symbolTree';

describe('symbolKey', () => {
  it('uses name + start.line as a stable key', () => {
    const s = sym('foo', 'Method');
    s.range.start.line = 42;
    expect(symbolKey(s)).toBe('foo:42');
  });
});

describe('flattenForDisplay', () => {
  const tree = [
    sym('Alpha', 'Class', [sym('foo', 'Method'), sym('bar', 'Method')]),
    sym('Beta', 'Class', [sym('baz', 'Method')]),
  ];

  it('includes all rows with correct depths when all expanded', () => {
    const expanded = new Set(['Alpha:0', 'Beta:0']);
    const rows = flattenForDisplay(tree, expanded, '');
    expect(rows.map((r) => [r.symbol.name, r.depth])).toEqual([
      ['Alpha', 0],
      ['foo', 1],
      ['bar', 1],
      ['Beta', 0],
      ['baz', 1],
    ]);
  });

  it('hides children of collapsed parents', () => {
    const expanded = new Set(['Beta:0']);
    const rows = flattenForDisplay(tree, expanded, '');
    expect(rows.map((r) => r.symbol.name)).toEqual(['Alpha', 'Beta', 'baz']);
  });

  it('marks hasChildren and isExpanded correctly', () => {
    const expanded = new Set(['Alpha:0']);
    const rows = flattenForDisplay(tree, expanded, '');
    const alpha = rows.find((r) => r.symbol.name === 'Alpha')!;
    expect(alpha.hasChildren).toBe(true);
    expect(alpha.isExpanded).toBe(true);
    const foo = rows.find((r) => r.symbol.name === 'foo')!;
    expect(foo.hasChildren).toBe(false);
    expect(foo.isExpanded).toBe(false);
  });

  it('forces all matching branches expanded when filtering', () => {
    const expanded = new Set<string>(); // nothing expanded
    const rows = flattenForDisplay(tree, expanded, 'foo');
    expect(rows.map((r) => r.symbol.name)).toEqual(['Alpha', 'foo']);
  });
});
