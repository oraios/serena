import { describe, it, expect } from 'vitest';
import {
  detectLevel,
  escapeHtml,
  highlightTools,
  formatRelativeTime,
  formatNumber,
  formatTokens,
  formatDurationMs,
  prettyArgs,
} from '../src/lib/format';

describe('numeric formatters', () => {
  it('formats finite values', () => {
    expect(formatNumber(1234567)).toBe('1,234,567');
    expect(formatTokens(5678)).toBe('5.7k');
    expect(formatTokens(1_234_000)).toBe('1.23M');
    expect(formatDurationMs(0.5)).toBe('<1 ms');
    expect(formatDurationMs(1500)).toBe('1.5 s');
  });

  it('degrades non-finite input to an em dash instead of "NaN"/"NaNM"/"NaN h"', () => {
    for (const bad of [NaN, Infinity, -Infinity]) {
      expect(formatNumber(bad)).toBe('—');
      expect(formatTokens(bad)).toBe('—');
      expect(formatDurationMs(bad)).toBe('—');
    }
  });
});

describe('format', () => {
  it('detects log level from the line prefix', () => {
    expect(detectLevel('INFO  2026-01-01 something')).toBe('info');
    expect(detectLevel('WARNING 2026-01-01 watch out')).toBe('warning');
    expect(detectLevel('ERROR 2026-01-01 boom')).toBe('error');
    expect(detectLevel('DEBUG 2026-01-01 noise')).toBe('debug');
    expect(detectLevel('no level here')).toBe('info');
  });
  it('does not recolor a line just because a level word appears mid-message', () => {
    expect(detectLevel('INFO  handled an ERROR gracefully')).toBe('info');
  });
  it('highlights tool names case-insensitively', () => {
    const html = highlightTools('called Find_Symbol now', ['find_symbol']);
    expect(html).toContain('<span class="tool-name">find_symbol</span>');
  });
  it('escapes html including single quotes', () => {
    expect(escapeHtml(`<b>&"'`)).toBe('&lt;b&gt;&amp;&quot;&#39;');
  });
  it('escapes HTML in the log text before highlighting', () => {
    const html = highlightTools('<script>alert(1)</script> find_symbol', ['find_symbol']);
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<script>');
    expect(html).toContain('<span class="tool-name">find_symbol</span>');
  });
  it('does not re-match injected markup when a tool is named like a wrapper token', () => {
    const html = highlightTools('use find_symbol and name', ['find_symbol', 'name']);
    expect(html.match(/<span class="tool-name">/g)?.length).toBe(2);
    expect(html).not.toContain('class="tool-<span');
    expect(html).toContain('<span class="tool-name">find_symbol</span>');
    expect(html).toContain('<span class="tool-name">name</span>');
  });
  it('highlights each occurrence of overlapping names in one pass', () => {
    const html = highlightTools('find_symbol find_symbol', ['find_symbol']);
    expect(html.match(/<span class="tool-name">find_symbol<\/span>/g)?.length).toBe(2);
  });
});

describe('formatRelativeTime', () => {
  const NOW = 1_000_000 * 1000; // epoch ms at 1,000,000 s
  it('returns "just now" within 5s and empty for non-finite', () => {
    expect(formatRelativeTime(1_000_000, NOW)).toBe('just now');
    expect(formatRelativeTime(999_998, NOW)).toBe('just now');
    expect(formatRelativeTime(Number.POSITIVE_INFINITY, NOW)).toBe('');
    expect(formatRelativeTime(NaN, NOW)).toBe('');
  });
  it('crosses s → m → h → d boundaries', () => {
    expect(formatRelativeTime(1_000_000 - 30, NOW)).toBe('30s ago');
    expect(formatRelativeTime(1_000_000 - 120, NOW)).toBe('2m ago');
    expect(formatRelativeTime(1_000_000 - 2 * 3600, NOW)).toBe('2h ago');
    expect(formatRelativeTime(1_000_000 - 3 * 86400, NOW)).toBe('3d ago');
  });
  it('clamps a future timestamp to "just now"', () => {
    expect(formatRelativeTime(1_000_100, NOW)).toBe('just now');
  });
});

describe('prettyArgs', () => {
  it('pretty-prints a Python dict repr (single quotes, None/True/False)', () => {
    const out = prettyArgs("{'relative_path': 'src/foo.py', 'flag': True, 'x': None}");
    expect(out).toBe('{\n  "relative_path": "src/foo.py",\n  "flag": true,\n  "x": null\n}');
  });
  it('preserves apostrophes inside double-quoted values', () => {
    const out = prettyArgs(`{'msg': "it's fine"}`);
    expect(JSON.parse(out)).toEqual({ msg: "it's fine" });
  });
  it('pretty-prints already-valid JSON objects and arrays', () => {
    expect(prettyArgs('{"a":1}')).toBe('{\n  "a": 1\n}');
    expect(prettyArgs('[1,2]')).toBe('[\n  1,\n  2\n]');
  });
  it('leaves plain text untouched (not reinterpreted)', () => {
    expect(prettyArgs('Symbol read successfully')).toBe('Symbol read successfully');
    expect(prettyArgs('42')).toBe('42');
  });
  it('falls back to raw on unrepresentable reprs (objects, tuples)', () => {
    const repr = '<Foo object at 0x1>';
    expect(prettyArgs(repr)).toBe(repr);
    expect(prettyArgs("(1, 2, 'a')")).toBe("(1, 2, 'a')");
  });
});
