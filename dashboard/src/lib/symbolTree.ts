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
  if (PLURAL_OVERRIDES[kind]) return `${count} ${PLURAL_OVERRIDES[kind]}`;
  if (KIND_META[kind]) return `${count} ${lower}s`;
  return `${count} ${lower}`;
}

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
