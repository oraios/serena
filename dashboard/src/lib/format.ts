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

const numberFormatter = new Intl.NumberFormat('en-US');

// Thousands-separated integer formatter. Locale fixed to 'en-US' to keep
// rendering identical across browsers and CI; numbers are the user-facing
// stat totals (Tool Calls, tokens) where commas read naturally.
export function formatNumber(n: number): string {
  return numberFormatter.format(n);
}

// Human-readable duration. Crosses ms → s → m → h as the magnitude grows.
export function formatDurationMs(ms: number): string {
  if (ms < 1) return '<1 ms';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = s / 60;
  if (m < 60) return `${m.toFixed(1)} m`;
  const h = m / 60;
  return `${h.toFixed(1)} h`;
}

// Token totals: 5,678 → "5.7k", 1_234_000 → "1.23M".
export function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

// Inclusive-linear nearest-rank percentile (B24): floor((q/100) * (n-1)).
// `percentile([1..100], 95)` → sorted[94] = 95. Empty input → 0. q is clamped
// to [0, 100] so out-of-range quantiles don't blow up the index.
export function percentile(xs: number[], q: number): number {
  if (xs.length === 0) return 0;
  const sorted = [...xs].sort((a, b) => a - b);
  const clamped = Math.max(0, Math.min(100, q));
  const idx = Math.floor((clamped / 100) * (sorted.length - 1));
  return sorted[idx];
}
