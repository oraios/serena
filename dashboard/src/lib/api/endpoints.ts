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
  ResponseLastExecution,
  ResponseCancelExecution,
  ResponseNews,
  StatusResponse,
  TokenEstimatorResponse,
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
export const fetchLastExecution = () => getJson<ResponseLastExecution>('/last_execution');
export const fetchUnreadNews = () => getJson<ResponseNews>('/fetch_unread_news');
export const markNewsRead = (news_snippet_id: string) =>
  postJson<StatusResponse>('/mark_news_snippet_as_read', { news_snippet_id });
