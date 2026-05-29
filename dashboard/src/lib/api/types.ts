// Mirrors src/serena/dashboard.py response/request models. Field names must match JSON.

export interface ToolStatEntry {
  num_times_called: number;
  input_tokens: number;
  output_tokens: number;
  // Optional fields — backend Entry was extended in Phase 1. May be missing on
  // older backends, so all consumers must guard with `?? 0` / null checks.
  num_errors?: number;
  total_duration_ms?: number;
  min_duration_ms?: number | null;
  max_duration_ms?: number | null;
  last_called_at?: number | null;
}
export type ToolStats = Record<string, ToolStatEntry>;

// NOTE: /get_config_overview's tool_stats_summary is a DIFFERENT, reduced shape —
// the backend renames num_times_called -> num_calls and drops the token fields
// (dashboard.py:564). It is NOT a ToolStats.
export interface ToolSummaryEntry {
  num_calls: number;
}
export type ToolStatsSummary = Record<string, ToolSummaryEntry>;

export interface ResponseLog {
  messages: string[];
  max_idx: number;
  active_project: string | null;
}

export interface ResponseToolNames {
  tool_names: string[];
}
export interface ResponseToolStats {
  stats: ToolStats;
}

// Precise nested shapes verified against ResponseConfigOverview in dashboard.py.
export interface ActiveProject {
  name: string | null;
  language: string | null; // comma-separated, e.g. "Python, TypeScript"
  path: string | null;
}
export interface ContextInfo {
  name: string;
  description: string;
  path: string;
}
export interface ModeInfo {
  name: string;
  description?: string;
  path: string;
  is_active?: boolean;
}
export interface ProjectInfo {
  name: string;
  path: string;
  is_active: boolean;
}
export interface ToolInfo {
  name: string;
  is_active: boolean;
}
export interface ContextOption {
  name: string;
  is_active: boolean;
  path: string;
}

// Overview SummaryCards totals — backend-aggregated KPI strip for the Overview page.
export interface ToolStatsTotals {
  num_calls: number;
  num_errors: number;
  total_duration_ms: number;
  total_tokens: number;
}

export interface ResponseConfigOverview {
  active_project: ActiveProject | null;
  context: ContextInfo;
  modes: ModeInfo[];
  active_tools: string[];
  tool_stats_summary: ToolStatsSummary;
  tool_stats_totals?: ToolStatsTotals;
  registered_projects: ProjectInfo[];
  available_tools: ToolInfo[];
  available_modes: ModeInfo[];
  available_contexts: ContextOption[];
  available_memories: string[] | null;
  jetbrains_mode: boolean;
  languages: string[];
  encoding: string | null;
  current_client: string | null;
  serena_version: string;
}

export interface ResponseAvailableLanguages {
  languages: string[];
}
export interface ResponseGetMemory {
  content: string;
  memory_name: string;
  status?: string;
  message?: string;
}
export interface ResponseGetSerenaConfig {
  content: string;
  status?: string;
  message?: string;
}

export interface QueuedExecution {
  task_id: number;
  is_running: boolean;
  name: string;
  display_name: string;
  finished_successfully: boolean;
  logged: boolean;
  started_at: number | null;
  finished_at: number | null;
  duration_ms: number | null;
  error_message: string | null;
}
export interface ResponseQueuedExecutions {
  queued_executions: QueuedExecution[];
  status: string;
}
export interface ResponseLastExecution {
  last_execution: QueuedExecution | null;
  status: string;
}
export interface ResponseCancelExecution {
  status: string;
  was_cancelled: boolean;
  message?: string;
}

// News ids are YYYYMMDD strings; values are HTML snippets.
export interface ResponseNews {
  news: Record<string, string>;
  status: string;
}

// Generic mutation responses ({status, message}) for add/remove/save/delete/rename.
export interface StatusResponse {
  status: 'success' | 'error';
  message?: string;
}
export interface TokenEstimatorResponse {
  token_count_estimator_name: string;
}

// Tool Call Timeline — cursor-paginated ring buffer of per-call records.
export interface ToolCallRecord {
  seq: number;
  tool: string;
  started_at: number;
  duration_ms: number;
  success: boolean;
  error_message: string | null;
  input_preview: string;
  output_preview: string;
  input_truncated: boolean;
  output_truncated: boolean;
}
export interface ResponseToolCallTimeline {
  records: ToolCallRecord[];
  max_seq: number;
}

// Code-tab types (consumed in Phase 5/6; declared now so endpoints typecheck).
export interface DirEntry {
  name: string;
  kind: 'dir' | 'file';
  size?: number;
}
export interface ResponseListDir {
  entries: DirEntry[];
}

export interface FileSymbol {
  name: string;
  kind: string;
  range: { start: { line: number; character: number }; end: { line: number; character: number } };
  children?: FileSymbol[];
}
export interface ResponseFileSymbols {
  symbols: FileSymbol[];
}

export interface WorkspaceMatch {
  name: string;
  kind: string;
  path: string;
  range: { start: { line: number; character: number }; end: { line: number; character: number } };
}
export interface ResponseWorkspaceSymbolSearch {
  matches: WorkspaceMatch[];
}

export type DiagnosticSeverity = 'error' | 'warning' | 'info' | 'hint';
export interface Diagnostic {
  severity: DiagnosticSeverity;
  message: string;
  line: number;
  column: number;
  source?: string;
}
export interface FileDiagnostics {
  path: string;
  diagnostics: Diagnostic[];
}
export interface ResponseDiagnosticsSummary {
  files: FileDiagnostics[];
  truncated: boolean;
}
