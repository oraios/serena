import { getJson, postJson, putJson } from './client';
import type {
  ResponseLog,
  ResponseToolNames,
  ResponseToolStats,
  ResponseConfigOverview,
  ResponseAvailableLanguages,
  ResponseGetMemory,
  ResponseGetSerenaConfig,
  ResponseQueuedExecutions,
  ResponseCancelExecution,
  ResponseNews,
  StatusResponse,
  TokenEstimatorResponse,
  ResponseToolCallTimeline,
  ResponseListDir,
  ResponseFileSymbols,
  ResponseWorkspaceSymbolSearch,
  ResponseDiagnosticsSummary,
} from './types';

export const fetchConfigOverview = () => getJson<ResponseConfigOverview>('/get_config_overview');
export const fetchLogMessages = (startIdx: number) =>
  postJson<ResponseLog>('/get_log_messages', { start_idx: startIdx });
export const clearLogs = () => postJson<StatusResponse>('/clear_logs');
export const fetchToolNames = () => getJson<ResponseToolNames>('/get_tool_names');
export const fetchToolStats = () => getJson<ResponseToolStats>('/get_tool_stats');
export const clearToolStats = () => postJson<StatusResponse>('/clear_tool_stats');
export const fetchEstimatorName = () =>
  getJson<TokenEstimatorResponse>('/get_token_count_estimator_name');
export const shutdown = () => putJson<StatusResponse>('/shutdown');
export const fetchAvailableLanguages = () =>
  getJson<ResponseAvailableLanguages>('/get_available_languages');
export const addLanguage = (language: string) =>
  postJson<StatusResponse>('/add_language', { language });
export const removeLanguage = (language: string) =>
  postJson<StatusResponse>('/remove_language', { language });
export const getMemory = (memory_name: string) =>
  postJson<ResponseGetMemory>('/get_memory', { memory_name });
export const saveMemory = (memory_name: string, content: string) =>
  postJson<StatusResponse>('/save_memory', { memory_name, content });
export const deleteMemory = (memory_name: string) =>
  postJson<StatusResponse>('/delete_memory', { memory_name });
export const renameMemory = (old_name: string, new_name: string) =>
  postJson<StatusResponse>('/rename_memory', { old_name, new_name });
export const getSerenaConfig = () => getJson<ResponseGetSerenaConfig>('/get_serena_config');
export const saveSerenaConfig = (content: string) =>
  postJson<StatusResponse>('/save_serena_config', { content });
export const fetchQueuedExecutions = () =>
  getJson<ResponseQueuedExecutions>('/queued_task_executions');
export const cancelExecution = (task_id: number) =>
  postJson<ResponseCancelExecution>('/cancel_task_execution', { task_id });
export const fetchUnreadNews = () => getJson<ResponseNews>('/fetch_unread_news');
export const markNewsRead = (news_snippet_id: string) =>
  postJson<StatusResponse>('/mark_news_snippet_as_read', { news_snippet_id });

export const fetchToolCallTimeline = (params: {
  since_seq?: number;
  tool?: string;
  limit?: number;
}) => {
  const qs = new URLSearchParams();
  if (params.since_seq !== undefined) qs.set('since_seq', String(params.since_seq));
  if (params.tool) qs.set('tool', params.tool);
  if (params.limit !== undefined) qs.set('limit', String(params.limit));
  const query = qs.toString();
  const url = query ? `/get_tool_call_timeline?${query}` : '/get_tool_call_timeline';
  return getJson<ResponseToolCallTimeline>(url);
};

export const fetchCodeListDir = (path: string) =>
  getJson<ResponseListDir>(`/code/list_dir?path=${encodeURIComponent(path)}`);

export const fetchCodeFileSymbols = (path: string) =>
  getJson<ResponseFileSymbols>(`/code/file_symbols?path=${encodeURIComponent(path)}`);

export const fetchCodeWorkspaceSymbolSearch = (q: string, limit = 50) =>
  getJson<ResponseWorkspaceSymbolSearch>(
    `/code/workspace_symbol_search?q=${encodeURIComponent(q)}&limit=${limit}`,
  );

export const fetchCodeDiagnosticsSummary = (
  file_limit = 1000,
  path?: string,
  min_severity?: number,
) => {
  const qs = new URLSearchParams({ file_limit: String(file_limit) });
  if (path) qs.set('path', path);
  if (min_severity !== undefined) qs.set('min_severity', String(min_severity));
  return getJson<ResponseDiagnosticsSummary>(`/code/diagnostics_summary?${qs}`);
};
