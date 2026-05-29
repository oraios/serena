import { describe, it, expect } from 'vitest';
import { detectLevel, escapeHtml, highlightTools } from '../src/lib/format';

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
