# Code Tab Visual Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the dashboard Code tab — tree-grouped Symbols outline with lucide kind-icons, move Diagnostics into a third middle-pane tab with a persistent slow-warning + severity chips, and sweep ad-hoc Unicode/emoji affordances across the dashboard to lucide icons.

**Architecture:** Pure helpers (`symbolTree.ts`) handle tree filtering/flattening/counting outside Svelte so they're trivially unit-testable. `code` store gains expand-state + symbol-filter + diagnostics-severity-filter slots. Components stay thin: header + flat-row render driven by `flattenForDisplay`. Backend `/code/*` HTTP API is unchanged.

**Tech Stack:** Svelte 5 (runes), TypeScript, Vite, Vitest + @testing-library/svelte, `@lucide/svelte` ^1.17.0 (official Svelte 5 lucide package).

**Source spec:** `docs/superpowers/specs/2026-05-29-code-tab-visual-redesign-design.md`

**Working directory for all `npm` commands:** `dashboard/` (run from there).

---

## File map

**Create:**

- `dashboard/src/components/common/Icon.svelte` — thin wrapper that defaults size/stroke-width and a11y attrs.
- `dashboard/src/lib/symbolTree.ts` — pure helpers (`countByKind`, `pluralizeKind`, `filterTree`, `flattenForDisplay`, `KIND_META`).
- `dashboard/tests/symbol-tree.test.ts` — unit tests for the pure helpers.
- `dashboard/tests/file-symbols.test.ts` — render + interaction tests.
- `dashboard/tests/diagnostics-panel.test.ts` — render + interaction tests.
- `dashboard/tests/code-page.test.ts` — 3-tab switch test.

**Modify:**

- `dashboard/package.json` — add `@lucide/svelte` dep.
- `dashboard/src/lib/stores/code.svelte.ts` — widen `middle_pane`, add symbol expand-state + filter, add diag severity filter + counts, add expand/collapse-all actions.
- `dashboard/src/components/code/CodePage.svelte` — 2-col grid, 3-tab nav, drop right column.
- `dashboard/src/components/code/FileTree.svelte` — lucide chevron + warning icons.
- `dashboard/src/components/code/FileSymbols.svelte` — full rebuild: header bar, breadcrumb, counts, filter, expand-all/collapse-all, icon rows, sticky parents, copy-to-clipboard.
- `dashboard/src/components/code/WorkspaceSearch.svelte` — lucide `Search` prefix.
- `dashboard/src/components/code/DiagnosticsPanel.svelte` — persistent slow-warning, severity chips, icon refresh, count-driven layout.
- `dashboard/src/components/shell/ThemeToggle.svelte` — `Sun` / `Moon` icons.
- `dashboard/src/components/shell/Header.svelte` — `Server` icon.
- `dashboard/src/components/overview/Timeline.svelte` — `Play` / `Pause` / `RotateCw` / `CheckCircle` / `XCircle` / `X`.
- `dashboard/src/components/overview/TimelineRow.svelte` — `ChevronDown` / `ChevronRight` / `X`.
- `dashboard/src/components/common/Combobox.svelte` — `ChevronDown`.
- `dashboard/src/components/common/FilterDropdown.svelte` — `ChevronDown` / `X` / `Check`.
- `dashboard/src/components/common/Collapsible.svelte` — `ChevronDown`.
- `dashboard/src/components/logs/LogToolbar.svelte` — `Copy` / `Check`.
- `dashboard/src/components/modals/EditMemoryModal.svelte` — `Pencil` / `Check`.
- `dashboard/src/components/overview/ConfigCard.svelte` — `X`.
- `dashboard/src/components/stats/DrillDownPanel.svelte` — `X` / `ArrowRight`.
- `dashboard/src/resources/dashboard/` — regenerated bundle via `npm run build`.

---

## Task 1: Install `@lucide/svelte` and add the `Icon` wrapper

**Files:**

- Modify: `dashboard/package.json`
- Create: `dashboard/src/components/common/Icon.svelte`
- Create: `dashboard/tests/icon.test.ts`

- [ ] **Step 1: Install lucide**

From `dashboard/`:

```bash
npm install @lucide/svelte@^1.17.0
```

Verify `package.json` `dependencies` now contains `"@lucide/svelte": "^1.17.0"` (or the resolved patch).

- [ ] **Step 2: Write the failing Icon test**

Create `dashboard/tests/icon.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import Icon from '../src/components/common/Icon.svelte';
import { Search } from '@lucide/svelte';

describe('Icon', () => {
  it('renders the given lucide component', () => {
    const { container } = render(Icon, { props: { icon: Search, label: 'Search' } });
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('aria-label')).toBe('Search');
    expect(svg?.getAttribute('role')).toBe('img');
  });

  it('defaults to aria-hidden when no label is given', () => {
    const { container } = render(Icon, { props: { icon: Search } });
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('aria-hidden')).toBe('true');
    expect(svg?.getAttribute('aria-label')).toBeNull();
  });

  it('passes size and strokeWidth to the lucide component', () => {
    const { container } = render(Icon, {
      props: { icon: Search, size: 24, strokeWidth: 2.25 },
    });
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('width')).toBe('24');
    expect(svg?.getAttribute('stroke-width')).toBe('2.25');
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

From `dashboard/`:

```bash
npm test -- icon.test.ts
```

Expected: FAIL — `Cannot find module '../src/components/common/Icon.svelte'`.

- [ ] **Step 4: Implement Icon.svelte**

Create `dashboard/src/components/common/Icon.svelte`:

```svelte
<script lang="ts">
  import type { Component } from 'svelte';

  interface Props {
    icon: Component<{ size?: number | string; strokeWidth?: number | string; class?: string }>;
    size?: number;
    strokeWidth?: number;
    label?: string;
    class?: string;
  }

  let {
    icon: IconCmp,
    size = 16,
    strokeWidth = 1.75,
    label,
    class: cls = '',
  }: Props = $props();
</script>

{#if label}
  <IconCmp {size} {strokeWidth} class={cls} role="img" aria-label={label} />
{:else}
  <IconCmp {size} {strokeWidth} class={cls} aria-hidden="true" />
{/if}
```

Note: lucide components forward unknown SVG attributes. `role`, `aria-label`, `aria-hidden` will land on the rendered `<svg>`.

- [ ] **Step 5: Run test to verify it passes**

```bash
npm test -- icon.test.ts
```

Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add dashboard/package.json dashboard/package-lock.json dashboard/src/components/common/Icon.svelte dashboard/tests/icon.test.ts
git commit -m "feat(dashboard): add @lucide/svelte + Icon wrapper

Foundation for the Code tab redesign + dashboard-wide icon sweep.
Icon.svelte standardizes size (16), stroke-width (1.75), and
aria attributes so icons inherit currentColor and a11y defaults."
```

---

## Task 2: Migrate `FileTree` to lucide icons (smoke-test the pipeline)

**Files:**

- Modify: `dashboard/src/components/code/FileTree.svelte`

- [ ] **Step 1: Replace chevron + warning icons**

Edit `dashboard/src/components/code/FileTree.svelte`. In the `<script>` block at the top, add:

```svelte
<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import Icon from '$lib/../components/common/Icon.svelte';
  import { ChevronRight, ChevronDown, TriangleAlert } from '@lucide/svelte';
  // ... existing code
</script>
```

(If `$lib/../components` aliases are awkward, use the relative path `../common/Icon.svelte` — match whatever the existing FileTree imports do for sibling components.)

Replace the chevron span on line ~41:

```svelte
<!-- before -->
<span class="chev">{code.expanded.has(fullPath) ? '▾' : '▸'}</span>

<!-- after -->
<span class="chev">
  <Icon icon={code.expanded.has(fullPath) ? ChevronDown : ChevronRight} size={14} />
</span>
```

Replace the warning span (two occurrences on lines ~25 and ~44):

```svelte
<!-- before -->
<span class="warn" title={error}>⚠</span>

<!-- after -->
<span class="warn" title={error}>
  <Icon icon={TriangleAlert} size={14} label="Error" />
</span>
```

Replace the empty chev span for file rows on line ~57:

```svelte
<!-- before -->
<span class="chev"></span>

<!-- after (keep alignment but no icon) -->
<span class="chev" aria-hidden="true"></span>
```

- [ ] **Step 2: Run check + tests**

```bash
npm run check
npm test
```

Expected: PASS — no FileTree tests exist; just verify no other tests regress and svelte-check is clean.

- [ ] **Step 3: Run dev server, eyeball-check the tree**

```bash
npm run dev
```

Open http://localhost:5273 (Serena MCP server with dashboard must be running on :24282 first; see `dashboard/README.md`). Navigate to the Code tab. Chevrons + warning icons should render as lucide SVGs that inherit text color.

If running headless, skip this step but note "visual not verified" in the commit body.

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/components/code/FileTree.svelte
git commit -m "feat(dashboard): FileTree uses lucide chevron + warning icons"
```

---

## Task 3a: `symbolTree.ts` — `KIND_META` table

**Files:**

- Create: `dashboard/src/lib/symbolTree.ts`
- Create: `dashboard/tests/symbol-tree.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/symbol-tree.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { KIND_META } from '../src/lib/symbolTree';

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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npm test -- symbol-tree.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `KIND_META` + `getKindMeta`**

Create `dashboard/src/lib/symbolTree.ts`:

```ts
import {
  Box,
  Diamond,
  Sigma,
  Variable,
  Hash,
  Tag,
  Braces,
  List,
  Lock,
  Package,
  Code2,
} from '@lucide/svelte';
import type { Component } from 'svelte';
import type { FileSymbol } from './api/types';

export interface KindMeta {
  icon: Component;
  colorVar: string; // CSS var name, e.g. '--chart-6'
  label: string;
}

// Order also defines the display order in the counts row.
export const KIND_ORDER = [
  'Class',
  'Interface',
  'Enum',
  'Function',
  'Method',
  'Property',
  'Field',
  'Variable',
  'Constant',
  'Module',
] as const;

export const KIND_META: Record<string, KindMeta> = {
  Class: { icon: Box, colorVar: '--chart-6', label: 'Class' },
  Interface: { icon: Braces, colorVar: '--chart-2', label: 'Interface' },
  Enum: { icon: List, colorVar: '--chart-3', label: 'Enum' },
  Function: { icon: Sigma, colorVar: '--chart-2', label: 'Function' },
  Method: { icon: Diamond, colorVar: '--chart-5', label: 'Method' },
  Property: { icon: Tag, colorVar: '--accent', label: 'Property' },
  Field: { icon: Hash, colorVar: '--chart-4', label: 'Field' },
  Variable: { icon: Variable, colorVar: '--chart-3', label: 'Variable' },
  Constant: { icon: Lock, colorVar: '--accent', label: 'Constant' },
  Module: { icon: Package, colorVar: '--text-muted', label: 'Module' },
};

export function getKindMeta(kind: string): KindMeta {
  return KIND_META[kind] ?? { icon: Code2, colorVar: '--text-muted', label: kind };
}

// Placeholder exports — implemented in later tasks.
export function countByKind(_symbols: FileSymbol[]): Record<string, number> {
  return {};
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npm test -- symbol-tree.test.ts
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/symbolTree.ts dashboard/tests/symbol-tree.test.ts
git commit -m "feat(dashboard): symbolTree KIND_META + getKindMeta"
```

---

## Task 3b: `symbolTree.ts` — `countByKind` + `pluralizeKind`

**Files:**

- Modify: `dashboard/src/lib/symbolTree.ts`
- Modify: `dashboard/tests/symbol-tree.test.ts`

- [ ] **Step 1: Append failing tests**

Append to `dashboard/tests/symbol-tree.test.ts`:

```ts
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- symbol-tree.test.ts
```

Expected: FAIL — `pluralizeKind` not exported; `countByKind` returns `{}`.

- [ ] **Step 3: Implement**

Replace the placeholder `countByKind` in `dashboard/src/lib/symbolTree.ts` and add `pluralizeKind`:

```ts
export function countByKind(symbols: FileSymbol[]): Record<string, number> {
  const out: Record<string, number> = {};
  const walk = (list: FileSymbol[]) => {
    for (const s of list) {
      out[s.kind] = (out[s.kind] ?? 0) + 1;
      if (s.children && s.children.length > 0) walk(s.children);
    }
  };
  walk(symbols);
  return out;
}

const PLURAL_OVERRIDES: Record<string, string> = {
  Class: 'classes',
  Property: 'properties',
};

export function pluralizeKind(kind: string, count: number): string {
  const lower = kind.toLowerCase();
  if (count === 1) return `1 ${lower}`;
  const plural = PLURAL_OVERRIDES[kind] ?? `${lower}s`;
  return `${count} ${plural}`;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- symbol-tree.test.ts
```

Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/symbolTree.ts dashboard/tests/symbol-tree.test.ts
git commit -m "feat(dashboard): symbolTree countByKind + pluralizeKind"
```

---

## Task 3c: `symbolTree.ts` — `filterTree`

**Files:**

- Modify: `dashboard/src/lib/symbolTree.ts`
- Modify: `dashboard/tests/symbol-tree.test.ts`

- [ ] **Step 1: Append failing tests**

Append to `dashboard/tests/symbol-tree.test.ts`:

```ts
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- symbol-tree.test.ts
```

Expected: FAIL — `filterTree` not exported.

- [ ] **Step 3: Implement `filterTree`**

Append to `dashboard/src/lib/symbolTree.ts`:

```ts
export function filterTree(symbols: FileSymbol[], query: string): FileSymbol[] {
  const q = query.trim().toLowerCase();
  if (q === '') return symbols;

  const matches = (name: string) => name.toLowerCase().includes(q);

  const walk = (list: FileSymbol[]): FileSymbol[] => {
    const out: FileSymbol[] = [];
    for (const s of list) {
      if (matches(s.name)) {
        // Parent matched — keep all descendants.
        out.push(s);
        continue;
      }
      const kids = s.children ? walk(s.children) : [];
      if (kids.length > 0) {
        out.push({ ...s, children: kids });
      }
    }
    return out;
  };
  return walk(symbols);
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- symbol-tree.test.ts
```

Expected: PASS (10 tests total).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/symbolTree.ts dashboard/tests/symbol-tree.test.ts
git commit -m "feat(dashboard): symbolTree filterTree"
```

---

## Task 3d: `symbolTree.ts` — `flattenForDisplay` + `symbolKey`

**Files:**

- Modify: `dashboard/src/lib/symbolTree.ts`
- Modify: `dashboard/tests/symbol-tree.test.ts`

- [ ] **Step 1: Append failing tests**

Append to `dashboard/tests/symbol-tree.test.ts`:

```ts
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- symbol-tree.test.ts
```

Expected: FAIL — `flattenForDisplay`, `symbolKey` not exported.

- [ ] **Step 3: Implement**

Append to `dashboard/src/lib/symbolTree.ts`:

```ts
export interface DisplayRow {
  symbol: FileSymbol;
  depth: number;
  hasChildren: boolean;
  isExpanded: boolean;
  key: string;
}

export function symbolKey(s: FileSymbol): string {
  return `${s.name}:${s.range.start.line}`;
}

export function flattenForDisplay(
  symbols: FileSymbol[],
  expanded: ReadonlySet<string>,
  filter: string,
): DisplayRow[] {
  const filtered = filterTree(symbols, filter);
  const isFiltering = filter.trim() !== '';
  const out: DisplayRow[] = [];
  const walk = (list: FileSymbol[], depth: number) => {
    for (const s of list) {
      const key = symbolKey(s);
      const hasChildren = !!s.children && s.children.length > 0;
      // While filtering, force open so matches are visible.
      const isExpanded = hasChildren && (isFiltering || expanded.has(key));
      out.push({ symbol: s, depth, hasChildren, isExpanded, key });
      if (isExpanded && s.children) walk(s.children, depth + 1);
    }
  };
  walk(filtered, 0);
  return out;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- symbol-tree.test.ts
```

Expected: PASS (15 tests total).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/symbolTree.ts dashboard/tests/symbol-tree.test.ts
git commit -m "feat(dashboard): symbolTree flattenForDisplay + symbolKey"
```

---

## Task 4: Extend `code` store — symbol expand state + filter

**Files:**

- Modify: `dashboard/src/lib/stores/code.svelte.ts`
- Modify: `dashboard/tests/code-store.test.ts`

- [ ] **Step 1: Append failing tests**

Append to `dashboard/tests/code-store.test.ts`:

```ts
describe('code store — symbol view state', () => {
  it('exposes per-path expand state via getExpandedSymbols', () => {
    const store = createCodeStore();
    const set = store.getExpandedSymbols('a.py');
    expect(set instanceof Set).toBe(true);
    expect(set.size).toBe(0);
  });

  it('toggleSymbolExpand flips a key on a given path', () => {
    const store = createCodeStore();
    store.toggleSymbolExpand('a.py', 'foo:1');
    expect(store.getExpandedSymbols('a.py').has('foo:1')).toBe(true);
    store.toggleSymbolExpand('a.py', 'foo:1');
    expect(store.getExpandedSymbols('a.py').has('foo:1')).toBe(false);
  });

  it('expandAllSymbols adds keys for every parent (with children) and collapseAllSymbols clears them', () => {
    const store = createCodeStore();
    const symbols = [
      {
        name: 'Alpha',
        kind: 'Class',
        range: { start: { line: 0, character: 0 }, end: { line: 0, character: 0 } },
        children: [
          {
            name: 'foo',
            kind: 'Method',
            range: { start: { line: 1, character: 0 }, end: { line: 1, character: 0 } },
          },
        ],
      },
      {
        name: 'leaf',
        kind: 'Function',
        range: { start: { line: 2, character: 0 }, end: { line: 2, character: 0 } },
      },
    ];
    // seed cache directly via the public loader API
    store.file_symbols['a.py'] = symbols as never;
    store.expandAllSymbols('a.py');
    expect(store.getExpandedSymbols('a.py').has('Alpha:0')).toBe(true);
    expect(store.getExpandedSymbols('a.py').has('leaf:2')).toBe(false);
    store.collapseAllSymbols('a.py');
    expect(store.getExpandedSymbols('a.py').size).toBe(0);
  });

  it('symbol filter is per-path and defaults to ""', () => {
    const store = createCodeStore();
    expect(store.getSymbolFilter('a.py')).toBe('');
    store.setSymbolFilter('a.py', 'foo');
    expect(store.getSymbolFilter('a.py')).toBe('foo');
    expect(store.getSymbolFilter('b.py')).toBe('');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- code-store.test.ts
```

Expected: FAIL — `getExpandedSymbols`, `toggleSymbolExpand`, `expandAllSymbols`, `collapseAllSymbols`, `getSymbolFilter`, `setSymbolFilter` not on the store.

- [ ] **Step 3: Implement**

Edit `dashboard/src/lib/stores/code.svelte.ts`. Inside `createCodeStore()`, after the existing `$state` declarations and before the `return {` block, add:

```ts
const symbolExpanded = $state<Record<string, SvelteSet<string>>>({});
const symbolFilters = $state<Record<string, string>>({});

function getOrCreateExpanded(path: string): SvelteSet<string> {
  let set = symbolExpanded[path];
  if (!set) {
    set = new SvelteSet<string>();
    symbolExpanded[path] = set;
  }
  return set;
}
```

Add these methods inside the returned object (after `loadFileSymbols`):

```ts
getExpandedSymbols(path: string): SvelteSet<string> {
  return getOrCreateExpanded(path);
},
toggleSymbolExpand(path: string, key: string) {
  const set = getOrCreateExpanded(path);
  if (set.has(key)) set.delete(key);
  else set.add(key);
},
expandAllSymbols(path: string) {
  const set = getOrCreateExpanded(path);
  const symbols = fileSymbols[path] ?? [];
  const walk = (list: typeof symbols) => {
    for (const s of list) {
      if (s.children && s.children.length > 0) {
        set.add(`${s.name}:${s.range.start.line}`);
        walk(s.children);
      }
    }
  };
  walk(symbols);
},
collapseAllSymbols(path: string) {
  symbolExpanded[path] = new SvelteSet<string>();
},
getSymbolFilter(path: string): string {
  return symbolFilters[path] ?? '';
},
setSymbolFilter(path: string, q: string) {
  symbolFilters[path] = q;
},
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- code-store.test.ts
```

Expected: PASS (8 tests total in this file).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/stores/code.svelte.ts dashboard/tests/code-store.test.ts
git commit -m "feat(dashboard): code store — symbol expand state + filter"
```

---

## Task 5: Rebuild `FileSymbols.svelte`

**Files:**

- Modify: `dashboard/src/components/code/FileSymbols.svelte`
- Create: `dashboard/tests/file-symbols.test.ts`

- [ ] **Step 1: Write failing component tests**

Create `dashboard/tests/file-symbols.test.ts`:

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/svelte';
import FileSymbols from '../src/components/code/FileSymbols.svelte';
import { code } from '../src/lib/stores/code.svelte';
import type { FileSymbol } from '../src/lib/api/types';

function sym(name: string, kind: string, line: number, children: FileSymbol[] = []): FileSymbol {
  return {
    name,
    kind,
    range: {
      start: { line, character: 0 },
      end: { line, character: 0 },
    },
    children,
  };
}

beforeEach(() => {
  // Reset the singleton store between tests.
  code.selectPath(null);
  // Wipe any stale per-path state.
  for (const k of Object.keys(code.file_symbols)) delete code.file_symbols[k];
});

describe('FileSymbols', () => {
  it('shows the empty hint when no file is selected', () => {
    const { getByText } = render(FileSymbols);
    expect(getByText(/Select a file/i)).toBeDefined();
  });

  it('renders breadcrumb, counts, and rows with kind icons', () => {
    code.file_symbols['src/foo/bar.py'] = [
      sym('Alpha', 'Class', 5, [sym('foo', 'Method', 10)]),
      sym('fn', 'Function', 20),
    ];
    code.selectPath('src/foo/bar.py');
    code.expandAllSymbols('src/foo/bar.py');
    const { container, getByText } = render(FileSymbols);
    // Breadcrumb shows path parts
    expect(getByText('src')).toBeDefined();
    expect(getByText('foo')).toBeDefined();
    expect(getByText('bar.py')).toBeDefined();
    // Counts row mentions kinds in KIND_ORDER
    expect(container.textContent).toMatch(/1 class/);
    expect(container.textContent).toMatch(/1 method/);
    expect(container.textContent).toMatch(/1 function/);
    // Rows include each name
    expect(getByText('Alpha')).toBeDefined();
    expect(getByText('foo')).toBeDefined();
    expect(getByText('fn')).toBeDefined();
  });

  it('filter input prunes non-matching rows', async () => {
    code.file_symbols['a.py'] = [
      sym('Alpha', 'Class', 0, [sym('foo', 'Method', 1), sym('bar', 'Method', 2)]),
    ];
    code.selectPath('a.py');
    const { getByPlaceholderText, queryByText } = render(FileSymbols);
    const input = getByPlaceholderText(/Filter symbols/i);
    await fireEvent.input(input, { target: { value: 'foo' } });
    await waitFor(() => expect(queryByText('bar')).toBeNull());
    expect(queryByText('foo')).not.toBeNull();
    expect(queryByText('Alpha')).not.toBeNull();
  });

  it('click on line:col copies path:line to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    code.file_symbols['x.py'] = [sym('foo', 'Function', 27)];
    code.selectPath('x.py');
    const { getByText } = render(FileSymbols);
    const loc = getByText('28:1'); // backend lines are 0-based, UI shows +1
    await fireEvent.click(loc);
    expect(writeText).toHaveBeenCalledWith('x.py:28');
  });

  it('expand-all and collapse-all buttons toggle the parent state', async () => {
    code.file_symbols['x.py'] = [sym('Alpha', 'Class', 0, [sym('foo', 'Method', 1)])];
    code.selectPath('x.py');
    const { getByLabelText, queryByText } = render(FileSymbols);
    // Initially collapsed (expand state empty)
    expect(queryByText('foo')).toBeNull();
    await fireEvent.click(getByLabelText(/Expand all/i));
    await waitFor(() => expect(queryByText('foo')).not.toBeNull());
    await fireEvent.click(getByLabelText(/Collapse all/i));
    await waitFor(() => expect(queryByText('foo')).toBeNull());
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- file-symbols.test.ts
```

Expected: FAIL — component does not yet render breadcrumb, counts, filter input, or expand-all controls.

- [ ] **Step 3: Replace `FileSymbols.svelte`**

Overwrite `dashboard/src/components/code/FileSymbols.svelte`:

```svelte
<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import {
    countByKind,
    pluralizeKind,
    flattenForDisplay,
    getKindMeta,
    symbolKey,
    KIND_ORDER,
    type DisplayRow,
  } from '$lib/symbolTree';
  import Icon from '../common/Icon.svelte';
  import {
    ChevronRight,
    ChevronDown,
    ChevronsDown,
    ChevronsUp,
    Search,
    Copy,
    Check,
  } from '@lucide/svelte';

  const path = $derived(code.selected_path);
  const symbols = $derived(path ? code.file_symbols[path] : undefined);
  const error = $derived(path ? code.file_symbol_errors[path] : undefined);
  const filter = $derived(path ? code.getSymbolFilter(path) : '');
  const expanded = $derived(path ? code.getExpandedSymbols(path) : new Set<string>());

  const rows = $derived<DisplayRow[]>(
    symbols ? flattenForDisplay(symbols, expanded, filter) : [],
  );
  const counts = $derived(symbols ? countByKind(symbols) : {});
  const pathParts = $derived(path ? path.split('/') : []);

  let copiedKey = $state<string | null>(null);
  let filterTimer: ReturnType<typeof setTimeout> | null = null;

  function retry() {
    if (path) void code.loadFileSymbols(path, true);
  }

  function onFilterInput(e: Event) {
    const value = (e.target as HTMLInputElement).value;
    if (!path) return;
    if (filterTimer) clearTimeout(filterTimer);
    filterTimer = setTimeout(() => {
      code.setSymbolFilter(path, value);
    }, 100);
  }

  function clickBreadcrumb(idx: number) {
    if (!path) return;
    const target = pathParts.slice(0, idx + 1).join('/');
    if (idx < pathParts.length - 1) {
      code.toggleExpand(target);
    }
  }

  async function copyLoc(row: DisplayRow) {
    if (!path) return;
    const ref = `${path}:${row.symbol.range.start.line + 1}`;
    try {
      await navigator.clipboard.writeText(ref);
      copiedKey = row.key;
      setTimeout(() => {
        if (copiedKey === row.key) copiedKey = null;
      }, 1000);
    } catch {
      /* clipboard unavailable — silently ignore */
    }
  }

  function onRowChevron(row: DisplayRow) {
    if (!path || !row.hasChildren) return;
    code.toggleSymbolExpand(path, row.key);
  }
</script>

<div class="root">
  {#if !path}
    <p class="empty">Select a file from the tree.</p>
  {:else if error !== undefined}
    <div class="error-card">
      <strong>Failed to load symbols.</strong>
      <div class="msg">{error}</div>
      <button type="button" class="retry" onclick={retry}>Retry</button>
    </div>
  {:else if symbols === undefined}
    <p class="empty">Loading…</p>
  {:else}
    <header class="bar">
      <nav class="breadcrumb" aria-label="File path">
        {#each pathParts as part, i (i)}
          {#if i < pathParts.length - 1}
            <button type="button" class="crumb" onclick={() => clickBreadcrumb(i)}>{part}</button>
            <span class="sep" aria-hidden="true">›</span>
          {:else}
            <span class="crumb leaf">{part}</span>
          {/if}
        {/each}
      </nav>
      <div class="counts">
        {#each KIND_ORDER.filter((k) => counts[k]) as k, i (k)}
          {#if i > 0}<span class="dot">·</span>{/if}
          <span>{pluralizeKind(k, counts[k])}</span>
        {/each}
        {#if Object.keys(counts).length === 0}
          <span class="muted">No symbols.</span>
        {/if}
      </div>
      <div class="controls">
        <label class="filter">
          <Icon icon={Search} size={14} />
          <input
            type="search"
            placeholder="Filter symbols…"
            value={filter}
            oninput={onFilterInput}
          />
        </label>
        <button
          type="button"
          class="icon-btn"
          aria-label="Expand all"
          title="Expand all"
          onclick={() => path && code.expandAllSymbols(path)}
        >
          <Icon icon={ChevronsDown} size={14} />
        </button>
        <button
          type="button"
          class="icon-btn"
          aria-label="Collapse all"
          title="Collapse all"
          onclick={() => path && code.collapseAllSymbols(path)}
        >
          <Icon icon={ChevronsUp} size={14} />
        </button>
      </div>
    </header>

    {#if rows.length === 0 && symbols.length > 0}
      <p class="empty">No matches.</p>
    {:else if symbols.length === 0}
      <p class="empty">No symbols.</p>
    {:else}
      <ul class="list">
        {#each rows as row (row.key)}
          {@const meta = getKindMeta(row.symbol.kind)}
          <li
            class="row"
            class:has-children={row.hasChildren}
            style:--depth={row.depth}
            style:--kind-color="var({meta.colorVar})"
          >
            {#if row.hasChildren}
              <button
                type="button"
                class="chev"
                aria-label={row.isExpanded ? 'Collapse' : 'Expand'}
                onclick={() => onRowChevron(row)}
              >
                <Icon icon={row.isExpanded ? ChevronDown : ChevronRight} size={12} />
              </button>
            {:else}
              <span class="chev" aria-hidden="true"></span>
            {/if}
            <span class="badge" title={meta.label}>
              <Icon icon={meta.icon} size={12} />
            </span>
            <span class="name">{row.symbol.name}</span>
            <button
              type="button"
              class="loc"
              title="Copy path:line"
              onclick={() => copyLoc(row)}
            >
              {#if copiedKey === row.key}
                <Icon icon={Check} size={12} />
                <span>copied</span>
              {:else}
                <span>{row.symbol.range.start.line + 1}:{row.symbol.range.start.character + 1}</span>
                <Icon icon={Copy} size={12} class="copy-icon" />
              {/if}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</div>

<style>
  .root {
    height: 100%;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .empty {
    color: var(--text-secondary);
    padding: var(--space-3);
  }
  .bar {
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--bg-elevated);
    border-bottom: 1px solid var(--border);
    padding: var(--space-2);
    display: grid;
    grid-template-columns: 1fr auto;
    grid-template-areas:
      'crumb controls'
      'counts counts';
    gap: var(--space-1) var(--space-2);
  }
  .breadcrumb {
    grid-area: crumb;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1);
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .crumb {
    background: transparent;
    border: 0;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0;
  }
  .crumb:hover {
    color: var(--text-primary);
    text-decoration: underline;
  }
  .crumb.leaf {
    color: var(--text-primary);
    font-weight: 600;
    cursor: default;
  }
  .sep {
    color: var(--text-muted);
  }
  .counts {
    grid-area: counts;
    color: var(--text-secondary);
    font-size: 0.8em;
    display: flex;
    align-items: center;
    gap: var(--space-1);
  }
  .dot {
    color: var(--text-muted);
  }
  .muted {
    color: var(--text-muted);
  }
  .controls {
    grid-area: controls;
    display: flex;
    align-items: center;
    gap: var(--space-1);
  }
  .filter {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: 0 var(--space-2);
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text-secondary);
  }
  .filter input {
    background: transparent;
    border: 0;
    padding: var(--space-1);
    color: var(--text-primary);
    font-family: inherit;
    font-size: 0.85em;
    outline: none;
    width: 140px;
  }
  .icon-btn {
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    padding: var(--space-1);
    color: var(--text-secondary);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .icon-btn:hover {
    color: var(--text-primary);
    background: var(--bg);
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .row {
    display: grid;
    grid-template-columns: 18px 22px 1fr auto;
    align-items: center;
    gap: var(--space-2);
    padding: 2px var(--space-2);
    padding-left: calc(var(--space-2) + var(--depth, 0) * var(--space-3));
    color: var(--text-primary);
    position: relative;
  }
  .row:hover {
    background: var(--bg);
  }
  /* Subtle indent guide: a 1px column drawn at each depth using a box-shadow. */
  .row::before {
    content: '';
    position: absolute;
    left: calc(var(--space-2) + var(--depth, 0) * var(--space-3) - var(--space-1));
    top: 0;
    bottom: 0;
    width: 1px;
    background: var(--border);
    opacity: 0.6;
    display: var(--depth, 0) > 0 ? block : none;
  }
  .chev {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    background: transparent;
    border: 0;
    color: var(--text-secondary);
    cursor: pointer;
  }
  span.chev {
    cursor: default;
  }
  .badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 6px;
    background: color-mix(in srgb, var(--kind-color) 18%, transparent);
    color: var(--kind-color);
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .loc {
    background: transparent;
    border: 0;
    color: var(--text-muted);
    font-family: inherit;
    font-size: 0.95em;
    cursor: pointer;
    font-variant-numeric: tabular-nums;
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }
  .loc:hover {
    color: var(--text-primary);
  }
  .row:hover .loc :global(.copy-icon) {
    opacity: 1;
  }
  .loc :global(.copy-icon) {
    opacity: 0;
    transition: opacity 0.12s;
  }
  /* Sticky parent name when scrolling past it.
     We rely on the parent row's natural position; making the row sticky keeps
     it visible while its children scroll under it. */
  .row.has-children {
    position: sticky;
    top: 0;
    background: var(--bg-elevated);
    z-index: 1;
  }
  .error-card {
    background: var(--bg);
    border: 1px solid var(--log-error);
    border-radius: var(--radius);
    padding: var(--space-2);
    color: var(--log-error);
    margin: var(--space-2);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .error-card .msg {
    font-family: var(--font-mono);
    font-size: 0.85em;
    color: var(--text-primary);
  }
  .retry {
    align-self: flex-start;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-1) var(--space-2);
    color: var(--text-primary);
    cursor: pointer;
  }
</style>
```

> **Note on `.row::before` indent guide:** CSS doesn't support `display: ...?...:...` inline ternaries. Replace the `display:` line with a no-op rule and add a `.row[style*='--depth:0']::before { display: none; }` selector, or — simpler — gate visibility with `opacity`:
>
> ```css
> .row[style*='--depth:0']::before {
>   opacity: 0;
> }
> ```
>
> Remove the offending `display:` line from the snippet above before saving.

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- file-symbols.test.ts
```

Expected: PASS (5 tests).

If any test fails because the filter is debounced 100ms, wrap the assertion in `await waitFor(...)` (already done above) and verify `vi.useFakeTimers()` is NOT needed because `waitFor` covers it.

- [ ] **Step 5: Run svelte-check**

```bash
npm run check
```

Expected: no new errors.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/code/FileSymbols.svelte dashboard/tests/file-symbols.test.ts
git commit -m "feat(dashboard): rebuild FileSymbols — breadcrumb, icons, filter, copy"
```

---

## Task 6: `WorkspaceSearch` — add `Search` prefix icon

**Files:**

- Modify: `dashboard/src/components/code/WorkspaceSearch.svelte`

- [ ] **Step 1: Add the icon**

Add to the `<script>` block:

```svelte
import Icon from '../common/Icon.svelte';
import { Search } from '@lucide/svelte';
```

Replace the bare `<input>` block with a labelled wrapper. Before:

```svelte
<input
  type="search"
  placeholder="Search workspace symbols…"
  {value}
  oninput={onInput}
  class="input"
/>
```

After:

```svelte
<label class="input-wrap">
  <Icon icon={Search} size={14} />
  <input
    type="search"
    placeholder="Search workspace symbols…"
    {value}
    oninput={onInput}
  />
</label>
```

In the `<style>` block, replace `.input { ... }` with:

```css
.input-wrap {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-secondary);
}
.input-wrap:focus-within {
  border-color: var(--accent);
  color: var(--text-primary);
}
.input-wrap input {
  flex: 1;
  background: transparent;
  border: 0;
  outline: none;
  color: var(--text-primary);
  font-family: inherit;
}
```

- [ ] **Step 2: Run check + tests**

```bash
npm run check && npm test
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/code/WorkspaceSearch.svelte
git commit -m "feat(dashboard): WorkspaceSearch — Search prefix icon"
```

---

## Task 7: Extend `code` store — diagnostics severity filter + counts + 3-pane type

**Files:**

- Modify: `dashboard/src/lib/stores/code.svelte.ts`
- Modify: `dashboard/tests/code-store.test.ts`

- [ ] **Step 1: Append failing tests**

Append to `dashboard/tests/code-store.test.ts`:

```ts
import type { DiagnosticSeverity, FileDiagnostics } from '../src/lib/api/types';

describe('code store — diagnostics filter + counts', () => {
  it('middle_pane widens to support "diagnostics"', () => {
    const store = createCodeStore();
    store.setMiddlePane('diagnostics');
    expect(store.middle_pane).toBe('diagnostics');
  });

  it('diag_counts aggregates by severity across files', () => {
    const store = createCodeStore();
    const files: FileDiagnostics[] = [
      {
        path: 'a.py',
        diagnostics: [
          { severity: 'error', message: 'x', line: 0, column: 0 },
          { severity: 'warning', message: 'y', line: 0, column: 0 },
        ],
      },
      {
        path: 'b.py',
        diagnostics: [
          { severity: 'error', message: 'z', line: 0, column: 0 },
          { severity: 'info', message: 'i', line: 0, column: 0 },
        ],
      },
    ];
    // Seed by stubbing fetch via refreshDiagnostics is overkill; just write the slot.
    (store as unknown as { __seedDiag(f: FileDiagnostics[]): void }).__seedDiag?.(files);
    // Fallback: write through the public mutator (refreshDiagnostics) is not viable here;
    // instead use the test-only helper exposed on the store:
    store._setDiagFilesForTest(files);
    expect(store.diag_counts).toEqual({ error: 2, warning: 1, info: 1, hint: 0 });
  });

  it('toggleDiagSeverity flips a severity in the filter set', () => {
    const store = createCodeStore();
    expect(store.diag_severity_filter.has('error')).toBe(false);
    store.toggleDiagSeverity('error');
    expect(store.diag_severity_filter.has('error')).toBe(true);
    store.toggleDiagSeverity('error');
    expect(store.diag_severity_filter.has('error')).toBe(false);
  });

  it('isDiagSeverityShown returns true when filter set is empty (show-all default)', () => {
    const store = createCodeStore();
    const all: DiagnosticSeverity[] = ['error', 'warning', 'info', 'hint'];
    for (const sev of all) {
      expect(store.isDiagSeverityShown(sev)).toBe(true);
    }
    store.toggleDiagSeverity('error');
    expect(store.isDiagSeverityShown('error')).toBe(true);
    expect(store.isDiagSeverityShown('warning')).toBe(false);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- code-store.test.ts
```

Expected: FAIL — APIs don't exist.

- [ ] **Step 3: Implement**

Edit `dashboard/src/lib/stores/code.svelte.ts`:

a) Change the `middlePane` declaration:

```ts
// before:
let middlePane = $state<'symbols' | 'search'>('symbols');
// after:
let middlePane = $state<'symbols' | 'search' | 'diagnostics'>('symbols');
```

b) Update the `setMiddlePane` signature:

```ts
setMiddlePane(pane: 'symbols' | 'search' | 'diagnostics') {
  middlePane = pane;
},
```

c) Add new state alongside the other diag fields:

```ts
const diagSeverityFilter = new SvelteSet<import('$lib/api/types').DiagnosticSeverity>();
```

d) Add getters and actions to the returned object (before the closing `};`):

```ts
get diag_severity_filter() {
  return diagSeverityFilter;
},
get diag_counts() {
  const counts = { error: 0, warning: 0, info: 0, hint: 0 } as Record<string, number>;
  for (const f of diagFiles) {
    for (const d of f.diagnostics) counts[d.severity]++;
  }
  return counts;
},
toggleDiagSeverity(sev: import('$lib/api/types').DiagnosticSeverity) {
  if (diagSeverityFilter.has(sev)) diagSeverityFilter.delete(sev);
  else diagSeverityFilter.add(sev);
},
isDiagSeverityShown(sev: import('$lib/api/types').DiagnosticSeverity): boolean {
  return diagSeverityFilter.size === 0 || diagSeverityFilter.has(sev);
},
_setDiagFilesForTest(files: import('$lib/api/types').FileDiagnostics[]) {
  diagFiles = files;
},
```

Also update `selectPath`'s `opts` type so callers can switch to diagnostics if needed (not required today, but keep coherent):

```ts
selectPath(path: string | null, opts: { switchMiddleTo?: 'symbols' | 'search' | 'diagnostics' } = {}) {
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- code-store.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/stores/code.svelte.ts dashboard/tests/code-store.test.ts
git commit -m "feat(dashboard): code store — 3rd pane + diag severity filter + counts"
```

---

## Task 8: Rebuild `DiagnosticsPanel.svelte`

**Files:**

- Modify: `dashboard/src/components/code/DiagnosticsPanel.svelte`
- Create: `dashboard/tests/diagnostics-panel.test.ts`

- [ ] **Step 1: Write failing tests**

Create `dashboard/tests/diagnostics-panel.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import DiagnosticsPanel from '../src/components/code/DiagnosticsPanel.svelte';
import { code } from '../src/lib/stores/code.svelte';

beforeEach(() => {
  code._setDiagFilesForTest([]);
  // Reset severity filter
  for (const s of ['error', 'warning', 'info', 'hint'] as const) {
    if (code.diag_severity_filter.has(s)) code.toggleDiagSeverity(s);
  }
});

describe('DiagnosticsPanel', () => {
  it('shows persistent slow-warning even when not loading and no data', () => {
    const { getByText } = render(DiagnosticsPanel);
    expect(getByText(/Computing diagnostics is slow/i)).toBeDefined();
  });

  it('renders severity chips with counts and lets the user filter', async () => {
    code._setDiagFilesForTest([
      {
        path: 'a.py',
        diagnostics: [
          { severity: 'error', message: 'boom', line: 0, column: 0 },
          { severity: 'warning', message: 'meh', line: 1, column: 0 },
        ],
      },
    ]);
    const { getByText, queryByText } = render(DiagnosticsPanel);
    // Counts visible
    expect(getByText(/Errors\s*\(1\)/)).toBeDefined();
    expect(getByText(/Warnings\s*\(1\)/)).toBeDefined();
    // Both messages visible initially (filter empty = show all)
    expect(queryByText('boom')).not.toBeNull();
    expect(queryByText('meh')).not.toBeNull();
    // Toggle to only-errors
    await fireEvent.click(getByText(/Errors\s*\(1\)/));
    expect(queryByText('boom')).not.toBeNull();
    expect(queryByText('meh')).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- diagnostics-panel.test.ts
```

Expected: FAIL — slow-warning is gated on `diag_loading`; no chips exist.

- [ ] **Step 3: Replace `DiagnosticsPanel.svelte`**

Overwrite `dashboard/src/components/code/DiagnosticsPanel.svelte`:

```svelte
<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import Icon from '../common/Icon.svelte';
  import {
    RotateCw,
    TriangleAlert,
    CircleAlert,
    Info,
    Lightbulb,
  } from '@lucide/svelte';
  import type { DiagnosticSeverity, FileDiagnostics } from '$lib/api/types';

  const counts = $derived(code.diag_counts);
  const visibleFiles = $derived<FileDiagnostics[]>(
    code.diag_files
      .map((f) => ({
        ...f,
        diagnostics: f.diagnostics.filter((d) => code.isDiagSeverityShown(d.severity)),
      }))
      .filter((f) => f.diagnostics.length > 0),
  );

  function refresh() {
    if (code.diag_loading) return;
    void code.refreshDiagnostics(1000);
  }

  const SEVERITIES: { sev: DiagnosticSeverity; label: string; icon: typeof CircleAlert; color: string }[] = [
    { sev: 'error', label: 'Errors', icon: CircleAlert, color: 'var(--log-error)' },
    { sev: 'warning', label: 'Warnings', icon: TriangleAlert, color: 'var(--log-warning)' },
    { sev: 'info', label: 'Info', icon: Info, color: 'var(--text-secondary)' },
    { sev: 'hint', label: 'Hints', icon: Lightbulb, color: 'var(--text-muted)' },
  ];
</script>

<section class="root">
  <header>
    <h3>Diagnostics</h3>
    <button type="button" class="refresh" onclick={refresh} disabled={code.diag_loading}>
      <span class="spin" class:on={code.diag_loading}>
        <Icon icon={RotateCw} size={14} />
      </span>
      <span>{code.diag_loading ? 'Computing…' : 'Refresh'}</span>
    </button>
  </header>

  <aside class="slow-warning" role="note">
    <Icon icon={TriangleAlert} size={14} label="Slow" />
    <span>
      Computing diagnostics is slow and temporarily delays other LSP tools. Use only when needed.
    </span>
  </aside>

  <nav class="chips" aria-label="Severity filter">
    {#each SEVERITIES as s (s.sev)}
      <button
        type="button"
        class="chip"
        class:active={code.diag_severity_filter.has(s.sev)}
        style:--chip-color={s.color}
        onclick={() => code.toggleDiagSeverity(s.sev)}
      >
        <Icon icon={s.icon} size={12} />
        <span>{s.label} ({counts[s.sev] ?? 0})</span>
      </button>
    {/each}
  </nav>

  {#if code.diag_error}
    <div class="error-card">
      <strong>Diagnostics failed.</strong>
      <div class="msg">{code.diag_error}</div>
    </div>
  {/if}

  {#if code.diag_truncated && !code.diag_loading}
    <div class="warn">
      Showing first {code.diag_files.length} files; project has more.
    </div>
  {/if}

  {#if code.diag_files.length === 0 && !code.diag_loading && !code.diag_error}
    <p class="empty">
      Click Refresh to compute diagnostics.
    </p>
  {/if}

  {#each visibleFiles as f (f.path)}
    <details class="file" open>
      <summary>
        <span class="path">{f.path}</span>
        <span class="count">{f.diagnostics.length}</span>
      </summary>
      <ul class="diags">
        {#each f.diagnostics as d, i (i)}
          <li class={`sev-${d.severity}`}>
            <span class="loc">{d.line + 1}:{d.column + 1}</span>
            <span class="sev">{d.severity}</span>
            <span class="msg">{d.message}</span>
            {#if d.source}<span class="source">[{d.source}]</span>{/if}
          </li>
        {/each}
      </ul>
    </details>
  {/each}
</section>

<style>
  .root {
    height: 100%;
    overflow-y: auto;
    padding: var(--space-2);
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: var(--space-2);
  }
  header h3 {
    margin: 0;
    font-size: 1em;
  }
  .refresh {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-1) var(--space-2);
    cursor: pointer;
    color: var(--text-primary);
  }
  .refresh:disabled {
    opacity: 0.6;
    cursor: progress;
  }
  .spin.on {
    animation: spin 1.2s linear infinite;
    display: inline-flex;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .slow-warning {
    display: flex;
    align-items: flex-start;
    gap: var(--space-2);
    background: var(--bg);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius);
    padding: var(--space-2);
    color: var(--text-secondary);
    margin-bottom: var(--space-2);
    font-size: 0.85em;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    margin-bottom: var(--space-2);
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 2px var(--space-2);
    color: var(--chip-color, var(--text-secondary));
    font-size: 0.8em;
    cursor: pointer;
  }
  .chip.active {
    background: color-mix(in srgb, var(--chip-color) 12%, transparent);
    border-color: var(--chip-color, var(--border));
  }
  .warn,
  .error-card {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-2);
    margin-bottom: var(--space-2);
  }
  .error-card {
    border-color: var(--log-error);
    color: var(--log-error);
  }
  .error-card .msg {
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .empty {
    color: var(--text-secondary);
    padding: var(--space-2);
  }
  .file {
    border-bottom: 1px solid var(--border);
    padding: var(--space-1) 0;
  }
  .file summary {
    display: flex;
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 0.9em;
  }
  .file summary .count {
    margin-left: auto;
    color: var(--text-secondary);
  }
  .diags {
    list-style: none;
    margin: var(--space-1) 0 0;
    padding: 0;
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .diags li {
    display: grid;
    grid-template-columns: 70px 60px 1fr auto;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-2);
  }
  .sev-error {
    color: var(--log-error);
  }
  .sev-warning {
    color: var(--log-warning);
  }
  .sev-info,
  .sev-hint {
    color: var(--text-secondary);
  }
  .source {
    color: var(--text-secondary);
  }
</style>
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- diagnostics-panel.test.ts
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/code/DiagnosticsPanel.svelte dashboard/tests/diagnostics-panel.test.ts
git commit -m "feat(dashboard): DiagnosticsPanel — slow-warning, severity chips, icon refresh"
```

---

## Task 9: Rebuild `CodePage.svelte` — 2-col grid + 3 tabs

**Files:**

- Modify: `dashboard/src/components/code/CodePage.svelte`
- Create: `dashboard/tests/code-page.test.ts`

- [ ] **Step 1: Write failing test**

Create `dashboard/tests/code-page.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import CodePage from '../src/components/code/CodePage.svelte';
import { code } from '../src/lib/stores/code.svelte';
import { stubFetchRoutes } from './helpers';

beforeEach(() => {
  stubFetchRoutes({
    '/code/list_dir': { entries: [] },
  });
  code.setMiddlePane('symbols');
  code._setDiagFilesForTest([]);
});

describe('CodePage', () => {
  it('renders three tabs and switches the middle pane on click', async () => {
    const { getByRole, container } = render(CodePage);
    const tabSymbols = getByRole('button', { name: /Symbols/i });
    const tabSearch = getByRole('button', { name: /Search/i });
    const tabDiag = getByRole('button', { name: /Diagnostics/i });
    expect(tabSymbols).toBeDefined();
    expect(tabSearch).toBeDefined();
    expect(tabDiag).toBeDefined();

    await fireEvent.click(tabDiag);
    expect(code.middle_pane).toBe('diagnostics');
    expect(container.textContent).toMatch(/Computing diagnostics is slow/i);
  });

  it('does not render a right-edge diagnostics column', () => {
    const { container } = render(CodePage);
    expect(container.querySelector('.diagnostics')).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- code-page.test.ts
```

Expected: FAIL — `Diagnostics` tab does not exist; `.diagnostics` aside still rendered.

- [ ] **Step 3: Replace `CodePage.svelte`**

Overwrite `dashboard/src/components/code/CodePage.svelte`:

```svelte
<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import FileTree from './FileTree.svelte';
  import FileSymbols from './FileSymbols.svelte';
  import WorkspaceSearch from './WorkspaceSearch.svelte';
  import DiagnosticsPanel from './DiagnosticsPanel.svelte';

  const diagTotal = $derived(
    code.diag_counts.error + code.diag_counts.warning + code.diag_counts.info + code.diag_counts.hint,
  );
</script>

<div class="layout">
  <aside class="tree">
    <FileTree />
  </aside>
  <section class="middle">
    <nav class="middle-tabs" aria-label="Code views">
      <button
        type="button"
        class:active={code.middle_pane === 'symbols'}
        onclick={() => code.setMiddlePane('symbols')}
      >
        Symbols (file)
      </button>
      <button
        type="button"
        class:active={code.middle_pane === 'search'}
        onclick={() => code.setMiddlePane('search')}
      >
        Search (workspace)
      </button>
      <button
        type="button"
        class:active={code.middle_pane === 'diagnostics'}
        onclick={() => code.setMiddlePane('diagnostics')}
      >
        Diagnostics (project)
        {#if diagTotal > 0}<span class="badge">· {diagTotal}</span>{/if}
      </button>
    </nav>
    {#if code.middle_pane === 'symbols'}
      <FileSymbols />
    {:else if code.middle_pane === 'search'}
      <WorkspaceSearch />
    {:else}
      <DiagnosticsPanel />
    {/if}
  </section>
</div>

<style>
  .layout {
    display: grid;
    grid-template-columns: 260px 1fr;
    gap: var(--space-2);
    height: calc(100vh - 140px);
  }
  .tree,
  .middle {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .middle-tabs {
    display: flex;
    border-bottom: 1px solid var(--border);
  }
  .middle-tabs button {
    background: transparent;
    border: 0;
    padding: var(--space-2);
    color: var(--text-secondary);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }
  .middle-tabs button.active {
    color: var(--accent);
    border-bottom: 2px solid var(--accent);
  }
  .badge {
    color: var(--text-muted);
    font-size: 0.85em;
  }
  .tree {
    overflow-y: auto;
  }
  @media (max-width: 1000px) {
    .layout {
      grid-template-columns: 1fr;
      grid-template-rows: auto auto;
      height: auto;
    }
  }
</style>
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- code-page.test.ts
```

Expected: PASS (2 tests).

- [ ] **Step 5: Run the full test suite**

```bash
npm test
```

Expected: all pre-existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/code/CodePage.svelte dashboard/tests/code-page.test.ts
git commit -m "feat(dashboard): CodePage — 2-col grid + Diagnostics as 3rd middle tab"
```

---

## Task 10: Drive-by sweep — shell (`ThemeToggle`, `Header`)

**Files:**

- Modify: `dashboard/src/components/shell/ThemeToggle.svelte`
- Modify: `dashboard/src/components/shell/Header.svelte`

- [ ] **Step 1: ThemeToggle**

Edit `dashboard/src/components/shell/ThemeToggle.svelte`. Replace the script + icon span:

```svelte
<script lang="ts">
  import { theme } from '$lib/stores/theme.svelte';
  import Icon from '../common/Icon.svelte';
  import { Sun, Moon } from '@lucide/svelte';
  const tooltip = $derived(
    theme.current === 'dark' ? 'Switch to light theme' : 'Switch to dark theme',
  );
</script>

<button
  class="theme-toggle"
  type="button"
  aria-label={tooltip}
  title={tooltip}
  onclick={() => theme.toggle()}
>
  <Icon icon={theme.current === 'dark' ? Sun : Moon} size={18} />
</button>
```

Leave the `<style>` block as-is.

- [ ] **Step 2: Header — find the `⏻` line**

Open `dashboard/src/components/shell/Header.svelte`. Find line 31 (`<span class="icon" aria-hidden="true">⏻</span>`).

Add to the `<script>` (preserving existing imports):

```svelte
import Icon from '../common/Icon.svelte';
import { Server } from '@lucide/svelte';
```

Replace the line:

```svelte
<!-- before -->
<span class="icon" aria-hidden="true">⏻</span>

<!-- after -->
<span class="icon" aria-hidden="true"><Icon icon={Server} size={14} /></span>
```

- [ ] **Step 3: Run check + existing tests**

```bash
npm run check && npm test
```

Expected: PASS. `header.test.ts` may assert on labels — if it asserted on the `⏻` glyph, update the assertion to check `[role="img"]` or simply omit. (Inspect the test first; the existing one likely tests a different aspect.)

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/components/shell/ThemeToggle.svelte dashboard/src/components/shell/Header.svelte
git commit -m "feat(dashboard): shell — lucide Sun/Moon + Server icons"
```

---

## Task 11: Drive-by sweep — overview (`Timeline`, `TimelineRow`)

**Files:**

- Modify: `dashboard/src/components/overview/Timeline.svelte`
- Modify: `dashboard/src/components/overview/TimelineRow.svelte`

- [ ] **Step 1: Inventory the icon characters in each file**

```bash
grep -nE '[▾▸×↻▶⏸✓✗→]' dashboard/src/components/overview/Timeline.svelte dashboard/src/components/overview/TimelineRow.svelte
```

Expected lines (per spec File Map):

- `Timeline.svelte:26` `'✓ Success'`
- `Timeline.svelte:27` `'✗ Failed'`
- `Timeline.svelte:68` `'▶ Resume'` / `'⏸ Pause'`
- `Timeline.svelte:71` `'↻ Clear'`
- `Timeline.svelte:95` `>×</button`
- `TimelineRow.svelte:46` `'▾' : '▸'`
- `TimelineRow.svelte:58` `>×</button`

- [ ] **Step 2: Migrate `Timeline.svelte`**

Add to imports:

```svelte
import Icon from '../common/Icon.svelte';
import { Play, Pause, RotateCw, X, CheckCircle, XCircle } from '@lucide/svelte';
```

The `success` / `fail` labels on lines 26–27 are used as plain text inside a small status badge. The simplest swap is to keep the text labels and prefix with an Icon component in the template, not in the constant. So change the constant to:

```ts
success: 'Success',
fail: 'Failed',
```

…then in the template where these are rendered, add the icon next to the label:

```svelte
{#if status === 'success'}<Icon icon={CheckCircle} size={12} />{:else if status === 'fail'}<Icon icon={XCircle} size={12} />{/if}
{label}
```

(Use the surrounding context to place these icons appropriately — the existing template will tell you where the label is rendered.)

For the Pause/Resume button (line 68):

```svelte
<!-- before -->
{store.paused ? '▶ Resume' : '⏸ Pause'}

<!-- after -->
<Icon icon={store.paused ? Play : Pause} size={12} />
{store.paused ? 'Resume' : 'Pause'}
```

For Clear (line 71):

```svelte
<!-- before -->
↻ Clear

<!-- after -->
<Icon icon={RotateCw} size={12} /> Clear
```

For the close `×` (line 95):

```svelte
<!-- before -->
aria-label="Dismiss">×</button

<!-- after -->
aria-label="Dismiss"><Icon icon={X} size={14} /></button
```

- [ ] **Step 3: Migrate `TimelineRow.svelte`**

Add to imports:

```svelte
import Icon from '../common/Icon.svelte';
import { ChevronRight, ChevronDown, X } from '@lucide/svelte';
```

Replace line 46:

```svelte
<!-- before -->
<span class="chev">{expanded ? '▾' : '▸'}</span>

<!-- after -->
<span class="chev"><Icon icon={expanded ? ChevronDown : ChevronRight} size={12} /></span>
```

Replace line 58 (cancel button):

```svelte
<!-- before -->
onclick={() => oncancel?.(row)}>×</button

<!-- after -->
onclick={() => oncancel?.(row)} aria-label="Cancel"><Icon icon={X} size={12} /></button
```

- [ ] **Step 4: Run tests + check**

```bash
npm run check && npm test
```

If `timeline.test.ts` or `timeline-rows.test.ts` asserts on the exact glyph text (`'▾'`, `'×'`, `'↻ Clear'`), update those assertions to query by `aria-label` or by the surrounding text label (e.g., `getByLabelText('Cancel')`, `getByText('Clear')`). Do not weaken assertions — just shift them to stable selectors.

Expected: PASS after assertion updates.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/overview/Timeline.svelte dashboard/src/components/overview/TimelineRow.svelte dashboard/tests/timeline.test.ts dashboard/tests/timeline-rows.test.ts
git commit -m "feat(dashboard): Timeline + TimelineRow — lucide icons"
```

---

## Task 12: Drive-by sweep — common primitives (`Combobox`, `FilterDropdown`, `Collapsible`)

**Files:**

- Modify: `dashboard/src/components/common/Combobox.svelte`
- Modify: `dashboard/src/components/common/FilterDropdown.svelte`
- Modify: `dashboard/src/components/common/Collapsible.svelte`

- [ ] **Step 1: Combobox**

Add to imports:

```svelte
import Icon from './Icon.svelte';
import { ChevronDown } from '@lucide/svelte';
```

Replace `<span class="combobox-caret" aria-hidden="true">▾</span>` (line ~55):

```svelte
<span class="combobox-caret" aria-hidden="true"><Icon icon={ChevronDown} size={12} /></span>
```

- [ ] **Step 2: FilterDropdown**

Add to imports:

```svelte
import Icon from './Icon.svelte';
import { ChevronDown, X, Check } from '@lucide/svelte';
```

Replace lines 98, 101, 123:

```svelte
<!-- 98: clear × → -->
onkeydown={(e) => e.key === 'Enter' && clear(e)}><Icon icon={X} size={12} /></span

<!-- 101: chevron ▾ → -->
<span class="chev" aria-hidden="true"><Icon icon={ChevronDown} size={12} /></span>

<!-- 123: check ✓ → -->
<span class="check">{#if o.value === value}<Icon icon={Check} size={12} />{/if}</span>
```

- [ ] **Step 3: Collapsible**

Add to imports:

```svelte
import Icon from './Icon.svelte';
import { ChevronDown } from '@lucide/svelte';
```

Replace `<span class="toggle-icon" class:open={expanded}>▼</span>` (line 20):

```svelte
<span class="toggle-icon" class:open={expanded}><Icon icon={ChevronDown} size={12} /></span>
```

- [ ] **Step 4: Tests + check**

```bash
npm run check && npm test
```

Update `combobox.test.ts` / `filter-dropdown.test.ts` if they query the glyph text.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/common/Combobox.svelte dashboard/src/components/common/FilterDropdown.svelte dashboard/src/components/common/Collapsible.svelte dashboard/tests/combobox.test.ts dashboard/tests/filter-dropdown.test.ts
git commit -m "feat(dashboard): common primitives — lucide chevrons + X + Check"
```

---

## Task 13: Drive-by sweep — logs + modals + drilldown

**Files:**

- Modify: `dashboard/src/components/logs/LogToolbar.svelte`
- Modify: `dashboard/src/components/modals/EditMemoryModal.svelte`
- Modify: `dashboard/src/components/overview/ConfigCard.svelte`
- Modify: `dashboard/src/components/stats/DrillDownPanel.svelte`

For each file, follow the same pattern: import `Icon` (with the correct relative path) + the lucide components, then replace the specific Unicode glyph at the line numbers listed below.

- [ ] **Step 1: LogToolbar** — `dashboard/src/components/logs/LogToolbar.svelte:29`

```svelte
<!-- imports -->
import Icon from '../common/Icon.svelte';
import { Copy, Check } from '@lucide/svelte';

<!-- replace -->
>{copied ? '✓ copied' : 'copy logs'}</button>

<!-- with -->
><Icon icon={copied ? Check : Copy} size={12} /> {copied ? 'copied' : 'copy logs'}</button>
```

- [ ] **Step 2: EditMemoryModal** — `dashboard/src/components/modals/EditMemoryModal.svelte:76,88`

```svelte
<!-- imports -->
import Icon from '../common/Icon.svelte';
import { Check, Pencil } from '@lucide/svelte';

<!-- replace line 76 -->
onclick={applyRename}><Icon icon={Check} size={14} label="Confirm rename" /></button>

<!-- replace line 88 -->
}}><Icon icon={Pencil} size={14} label="Rename" /></button>
```

- [ ] **Step 3: ConfigCard** — `dashboard/src/components/overview/ConfigCard.svelte:53,99`

```svelte
<!-- imports -->
import Icon from '../common/Icon.svelte';
import { X } from '@lucide/svelte';

<!-- replace both -->
><Icon icon={X} size={12} /></button>
```

(keep the surrounding `onclick` and any aria-labels in place; add `aria-label="Remove"` if missing).

- [ ] **Step 4: DrillDownPanel** — `dashboard/src/components/stats/DrillDownPanel.svelte:40,86`

```svelte
<!-- imports -->
import Icon from '../common/Icon.svelte';
import { X, ArrowRight } from '@lucide/svelte';

<!-- replace line 40 (close button) -->
onclick={() => stats.setDrillTool(null)} aria-label="Close"><Icon icon={X} size={14} /></button>

<!-- replace line 86 -->
>Open in Timeline <Icon icon={ArrowRight} size={12} /></button>
```

- [ ] **Step 5: Tests + check**

```bash
npm run check && npm test
```

Update assertions in `log-viewer.test.ts`, `edit-memory-modal.test.ts`, `config-card.test.ts`, `drilldown.test.ts` if they query glyph text (search them for the specific characters first):

```bash
grep -nE "[×✓✎→]" dashboard/tests/*.test.ts
```

Expected: PASS after assertion updates.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/logs/LogToolbar.svelte dashboard/src/components/modals/EditMemoryModal.svelte dashboard/src/components/overview/ConfigCard.svelte dashboard/src/components/stats/DrillDownPanel.svelte dashboard/tests/log-viewer.test.ts dashboard/tests/edit-memory-modal.test.ts dashboard/tests/config-card.test.ts dashboard/tests/drilldown.test.ts
git commit -m "feat(dashboard): logs + modals + drilldown — lucide icons"
```

---

## Task 14: Format, lint, full test, build, commit bundle

**Files:**

- Modify: `dashboard/src/serena/resources/dashboard/` (regenerated by `npm run build`)

- [ ] **Step 1: Format**

```bash
cd dashboard && npm run format
```

- [ ] **Step 2: Lint**

```bash
npm run lint
```

Expected: clean. Fix any new lint errors before proceeding.

- [ ] **Step 3: Full test run**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 4: svelte-check**

```bash
npm run check
```

Expected: clean.

- [ ] **Step 5: Build the bundle**

```bash
npm run build
```

This regenerates `../src/serena/resources/dashboard/{index.html,assets/}`. CI fails the PR if this is stale.

- [ ] **Step 6: Stage *every* changed file (formatted source + bundle)**

The dashboard CLAUDE.md note: "stage all changes — a partial stage can leave other files prettier-dirty and fail CI's `prettier --check`."

```bash
cd /Users/Pavlo_Basanets/PycharmProjects/serena_fork
git status
git add -A dashboard/ src/serena/resources/dashboard/
git status
```

Review the diff; ensure no `.env`, no credential files. The bundle changes will include hashed `assets/index-XXXX.{js,css}` plus an updated `index.html`.

- [ ] **Step 7: Commit the regenerated bundle**

```bash
git commit -m "build(dashboard): regenerate bundle for Code tab redesign

- Tree-grouped Symbols outline with lucide kind-icons
- Diagnostics moved to 3rd middle-pane tab
- Dashboard-wide lucide icon sweep"
```

- [ ] **Step 8: Smoke-run the dev server (optional but recommended)**

```bash
cd dashboard && npm run dev
```

Hand-verify in the browser:

- Code tab: breadcrumb + counts row + filter + expand/collapse-all all work.
- Symbol rows show colored kind badges; line:col copies to clipboard with a brief Check flash.
- Sticky parent: scroll inside a long class; the class name pins to the top of the list.
- Diagnostics tab: slow-warning is always visible. Refresh button spins while loading. Severity chips toggle correctly.
- ThemeToggle, Timeline play/pause, Combobox/FilterDropdown chevrons all render lucide icons in both light + dark themes.

Document anything visual that needs follow-up.

---

## Self-review notes (for the implementer)

- **Backend frozen:** No edits to `src/serena/dashboard.py`. All `/code/*` calls go through existing `endpoints.ts` functions.
- **Tests can rely on `code` singleton:** the existing pattern in `code-store.test.ts` uses `createCodeStore()` factory; component tests use the `code` singleton — beware test order coupling. The `beforeEach` blocks above explicitly reset state.
- **Clipboard in jsdom:** `navigator.clipboard.writeText` is stubbed inline in the test. If `setup.ts` already provides one, reconcile — never overwrite a global stub that other tests depend on.
- **Sticky parent rows:** confirmed to work because each parent `<li>` sits in the same scroll container (`.root`). If a future refactor wraps rows in additional scroll/overflow contexts, stickiness will silently break. The test in `file-symbols.test.ts` does not assert on CSS, so add a manual visual check during Task 14 Step 8.
- **Filter behavior:** when filtering, `flattenForDisplay` ignores the per-path `expanded` set and force-shows the path to every match. This is intentional and is asserted by the last test in Task 3d.
- **Indent guide CSS quirk:** the `display: var(...) > 0 ? block : none` line in the `Step 3` snippet of Task 5 is NOT valid CSS and is called out in the embedded note — replace with the `[style*='--depth:0']` opacity rule before saving the file.
