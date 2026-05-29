/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { svelteTesting } from '@testing-library/svelte/vite';
import { fileURLToPath } from 'node:url';

const BACKEND = 'http://localhost:24282';
// All non-static backend routes that the app calls (frozen contract).
const API_ROUTES = [
  '/get_log_messages',
  '/clear_logs',
  '/get_tool_names',
  '/get_tool_stats',
  '/clear_tool_stats',
  '/get_token_count_estimator_name',
  '/get_config_overview',
  '/shutdown',
  '/get_available_languages',
  '/add_language',
  '/remove_language',
  '/get_memory',
  '/save_memory',
  '/delete_memory',
  '/rename_memory',
  '/get_serena_config',
  '/save_serena_config',
  '/queued_task_executions',
  '/cancel_task_execution',
  '/fetch_unread_news',
  '/mark_news_snippet_as_read',
  '/heartbeat',
  '/get_tool_call_timeline',
  '/code/list_dir',
  '/code/file_symbols',
  '/code/workspace_symbol_search',
  '/code/diagnostics_summary',
];

export default defineConfig({
  plugins: [svelte(), svelteTesting()],
  base: './',
  resolve: { alias: { $lib: fileURLToPath(new URL('./src/lib', import.meta.url)) } },
  build: {
    outDir: fileURLToPath(new URL('../src/serena/resources/dashboard', import.meta.url)),
    emptyOutDir: false, // keep icons/logos/*.png that live in the same dir
    assetsDir: 'assets',
  },
  server: {
    port: 5273,
    proxy: Object.fromEntries(API_ROUTES.map((r) => [r, { target: BACKEND, changeOrigin: true }])),
  },
  test: {
    environment: 'jsdom',
    environmentOptions: {
      jsdom: {
        url: 'http://localhost/',
      },
    },
    setupFiles: ['./tests/setup.ts'],
    globals: true,
  },
});
