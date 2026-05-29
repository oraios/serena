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
  if (!Number.isFinite(n)) return '—';
  return numberFormatter.format(n);
}

// Human-readable duration. Crosses ms → s → m → h as the magnitude grows.
export function formatDurationMs(ms: number): string {
  if (!Number.isFinite(ms)) return '—';
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
  if (!Number.isFinite(n)) return '—';
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

// Compact, live-refreshable relative timestamp: "just now", "12s ago", "5m ago",
// "3h ago", "2d ago". `thenEpochSec` is epoch *seconds* (matching the backend's
// started_at); `nowEpochMs` is epoch *milliseconds* (Date.now()). Non-finite or
// future timestamps degrade to '' / "just now" rather than throwing.
export function formatRelativeTime(thenEpochSec: number, nowEpochMs: number): string {
  if (!Number.isFinite(thenEpochSec)) return '';
  const diffSec = Math.round(nowEpochMs / 1000 - thenEpochSec);
  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const m = Math.floor(diffSec / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

// Best-effort: turn a Python literal (what `str(kwargs)` produces — single-quoted
// strings, None/True/False, escaped apostrophes) into a JSON string. Returns null
// when the source contains anything we can't faithfully represent (bare names like
// a `<Foo object>` repr, tuples, sets), so the caller can fall back to the raw text.
// A character scanner — not a regex swap — so apostrophes inside string values
// (`{'msg': "it's"}`) survive.
function pythonLiteralToJson(src: string): string | null {
  let out = '';
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === "'" || c === '"') {
      const quote = c;
      i++;
      let content = '';
      while (i < src.length && src[i] !== quote) {
        if (src[i] === '\\') {
          const next = src[i + 1];
          if (next === quote) content += quote;
          else if (next === '\\') content += '\\';
          else if (next === 'n') content += '\n';
          else if (next === 't') content += '\t';
          else if (next === 'r') content += '\r';
          else content += next ?? '';
          i += 2;
        } else {
          content += src[i];
          i++;
        }
      }
      i++; // skip closing quote
      out += JSON.stringify(content); // re-emit as a valid JSON double-quoted string
    } else if (/[A-Za-z_]/.test(c)) {
      let word = '';
      while (i < src.length && /[A-Za-z0-9_]/.test(src[i])) {
        word += src[i];
        i++;
      }
      if (word === 'None') out += 'null';
      else if (word === 'True') out += 'true';
      else if (word === 'False') out += 'false';
      else return null; // unknown bare identifier — can't represent as JSON
    } else {
      out += c;
      i++;
    }
  }
  return out;
}

function tryStructured(s: string): unknown | undefined {
  try {
    const v = JSON.parse(s);
    // Only treat objects/arrays as "structured" — leave plain text/numbers/bools as-is
    // so a tool's textual output isn't reinterpreted (e.g. "42" → 42).
    return v && typeof v === 'object' ? v : undefined;
  } catch {
    return undefined;
  }
}

// Pretty-print a tool-call input/output preview when it is structured (JSON, or a
// Python dict/list repr); otherwise return it unchanged. Pure and never throws —
// safe to call in a `$derived`.
export function prettyArgs(raw: string): string {
  const trimmed = raw.trim();
  const direct = tryStructured(trimmed);
  if (direct !== undefined) return JSON.stringify(direct, null, 2);
  const coerced = pythonLiteralToJson(trimmed);
  if (coerced != null) {
    const parsed = tryStructured(coerced);
    if (parsed !== undefined) return JSON.stringify(parsed, null, 2);
  }
  return raw;
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
