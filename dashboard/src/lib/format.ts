export type LogLevel = 'debug' | 'info' | 'warning' | 'error';

// Serena log lines start with the level name (SERENA_LOG_FORMAT = "%(levelname)-5s ...").
// Match on the prefix only — the legacy dashboard used `startsWith` — so that the word
// "ERROR" appearing inside an INFO message does not recolor the whole line.
export function detectLevel(line: string): LogLevel {
  if (line.startsWith('DEBUG')) return 'debug';
  if (line.startsWith('INFO')) return 'info';
  if (line.startsWith('WARNING')) return 'warning';
  if (line.startsWith('ERROR')) return 'error';
  return 'info'; // legacy `log-default` resolved to the same color as `log-info`
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Highlight tool names in ONE pass over the escaped text. Building a single combined
// alternation and replacing once means injected <span> markup is never re-scanned, so a
// tool literally named "name"/"span"/"class" can't nest a span into a previous wrapper.
export function highlightTools(text: string, toolNames: string[]): string {
  const escaped = escapeHtml(text);
  if (toolNames.length === 0) return escaped;
  // Longest-first so a longer name wins over a shorter name that is its prefix.
  const sorted = [...toolNames].sort((a, b) => b.length - a.length);
  // Build a map from lower-cased tool name to its canonical form for normalised output.
  const canonical = new Map(sorted.map((n) => [n.toLowerCase(), n]));
  const re = new RegExp(`\\b(?:${sorted.map(escapeRegExp).join('|')})\\b`, 'gi');
  return escaped.replace(re, (match) => {
    const name = canonical.get(match.toLowerCase()) ?? match;
    return `<span class="tool-name">${escapeHtml(name)}</span>`;
  });
}
